"""SVG animation and interactivity helpers for snakevision.

This module contains optional post-processing logic for snakevision to animate
an output SVG DAG. The core package renders static metro-style snakemake rule
graph using `dagviz`. This module can then optionally enhance that rendered SVG
with animated data packets to visualize data flowing through the DAG and,
when requested, it can add additional interactivity with javascript to add
pause/play/reset controls for direct-browser or github pages usage. It can
also add extra on-hoover effects to view parent nodes, and it can optionally
add on-click effects to view metadata for a given node (such as a description
of the rule or the actually rule itself).

The default animation mode is intentionally script-free. It uses SVG
`<animateMotion>` elements so the generated SVG that are friendly for
embedding within GitHub READMEs. It is worth noting that javascript will
not be executed within a github README. As so, the `interactive_js` option
should not be provided if a README is the target. As so, the interactive
mode is opt-in because it injects javascript. This mode adds play/pause/reset
controls, hover dependency highlighting, and additional options pertaining to
click-to-show rule metadata popups. It is intended for embedding the SVG on
Github pages or for opening the SVG directly in a browser.
"""
# Python standard library
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple
# 3rd party package from pypi,
# pip install if missing
import yaml
# Local relative imports
from .interactivity import javascript

# Constants
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def q(tag: str) -> str:
    """Return a namespaced SVG tag name for use with ElementTree.

    ElementTree stores XML namespaced tags in Clark notation, for example:
    `{http://www.w3.org/2000/svg}circle`. This helper keeps the rest of the
    module readable when querying or creating SVG elements.
    """
    return f"{{{SVG_NS}}}{tag}"


@dataclass
class AnimationConfig:
    """Configuration animating snakevision SVG DAG. The class is serializable-
    friendly so the CLI can construct it directly from parsed command-line options,
    and tests can create focused configurations without needing to exercise the
    full CLI.

    @param enabled <bool>:
        Whether to add declarative packet animation. If false, `enhance_svg`
        returns the input SVG unchanged.
    @param interactive_js <bool>:
        Whether to add JavaScript controls and hover/click interactions. This
        mode starts paused by default and is intended for direct browser or
        GitHub Pages usage.
    @param packet_interval <float>:
        Seconds between repeated packet waves from source nodes.
    @param speed <float>:
        Packet travel speed in SVG pixels per second.
    @param packet_radius <float>:
        Radius of the visible packet circles.
    @param sample_phase_resolution <float>:
        Resolution in seconds used when merging nearly identical packet phases.
    @param max_phases_per_edge <int>:
        Safety cap for unique propagated packet phases per edge.
    @param max_copies_per_phase <int>:
        Safety cap for overlapping packet copies when an edge traversal takes
        longer than one packet interval.
    @param rule_metadata_yaml <str|None>:
        Optional YAML file mapping DOT labels/rule names to text displayed when
        a node is clicked in interactive mode.
    @param reduced_motion_css <bool>:
        Whether to add CSS that hides packet animation when the user has enabled
        the OS/browser `prefers-reduced-motion` accessibility setting.
    """
    # Animation configuration options
    # and their defaults
    enabled: bool = False
    interactive_js: bool = False
    packet_interval: float = 15.0
    speed: float = 30.0
    packet_radius: float = 3.0
    sample_phase_resolution: float = 0.01
    max_phases_per_edge: int = 64
    max_copies_per_phase: int = 20
    rule_metadata_yaml: Optional[str] = None
    reduced_motion_css: bool = True


def validate_animation_config(config: AnimationConfig) -> None:
    """Validate animation configuration values before modifying the SVG.

    Validation is centralized here so both the CLI and programmatic callers get
    the same behavior. The CLI may still perform its own argparse-level checks,
    but this function protects the library API from invalid values as well.
    """
    # Sanity checks to catch common
    # configuration errors
    if config.packet_interval <= 0:
        raise ValueError("packet_interval must be > 0")
    if config.speed <= 0:
        raise ValueError("speed must be > 0")
    if config.packet_radius <= 0:
        raise ValueError("packet_radius must be > 0")
    if config.sample_phase_resolution <= 0:
        raise ValueError("sample_phase_resolution must be > 0")
    if config.max_phases_per_edge <= 0:
        raise ValueError("max_phases_per_edge must be > 0")
    if config.max_copies_per_phase <= 0:
        raise ValueError("max_copies_per_phase must be > 0")
    if config.rule_metadata_yaml and not config.interactive_js:
        raise ValueError("rule_metadata_yaml requires interactive_js=True")


def parse_svg_text(svg_text: str) -> ET.Element:
    """Parse SVG document text and return its root element.

    `dagviz.render_svg` returns SVG text rather than an ElementTree object. We
    parse it here so the animation layer can be inserted in the same SVG
    document instead of requiring a separate post-processing file.
    """
    return ET.fromstring(svg_text)


def load_rule_metadata_yaml(path: Optional[str]) -> Optional[Dict[str, str]]:
    """Load optional rule metadata from a simple YAML mapping.

    Expected YAML schema:

        rule_name: |
          arbitrary multiline text

        another_rule: "single line text"

    Values are intentionally restricted to scalar values. This keeps the
    interaction generic: snakevision does not need to understand Snakemake
    fields such as input/output/shell; it simply displays the user-provided text.

    @param path <str|None>:
        YAML file path, or None if rule metadata should not be loaded.
    @returns metadata <dict[str, str]|None>:
        None when no path is provided, otherwise a normalized string mapping.
    """
    if not path:
        return None # empty string

    with open(path, "r", encoding="utf-8") as fh:
        # Load the yaml file
        data = yaml.safe_load(fh)

    if data is None:
        return {} # empty file

    if not isinstance(data, dict):
        raise ValueError(
            f"{path} must contain a top-level YAML mapping from rule name "
            "or DOT label to text."
        )
    # Parse key, value pairs of information,
    # keys should represent node/rule names
    # and their values are used for annotation
    normalized = {}
    for key, value in data.items():
        normalized_key = str(key)

        if value is None:
            normalized[normalized_key] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[normalized_key] = str(value)
        else:
            raise ValueError(
                f"Metadata value for key {normalized_key!r} must be a "
                "single-line or multiline scalar string, not a list/object."
            )

    return normalized


def extract_svg_nodes(root: ET.Element) -> Dict[str, Dict[str, Any]]:
    """Extract rendered snakevision node positions from SVG circles.

    The packet animation must follow the already-rendered SVG geometry rather
    than recomputing layout from the graph. We therefore read each node's
    position, radius, and color from the SVG itself.

    snakevision/dagviz node circles are expected to have stable IDs derived from
    rule labels. Non-node circles are ignored if they lack an ID or numeric
    coordinates.
    """
    nodes: Dict[str, Dict[str, Any]] = {}

    for el in root.iter(q("circle")):
        node_id = el.get("id")
        if not node_id:
            continue

        try:
            cx = float(el.get("cx", "nan"))
            cy = float(el.get("cy", "nan"))
        except ValueError:
            continue

        if not (math.isfinite(cx) and math.isfinite(cy)):
            continue

        try:
            radius = float(el.get("r", "6"))
        except ValueError:
            radius = 6.0

        nodes[node_id] = {
            "x": cx,
            "y": cy,
            "color": el.get("fill", "#888888"),
            "r": radius,
        }

    return nodes


def detect_viewbox(root: ET.Element) -> Tuple[float, float, float, float]:
    """Return the SVG viewBox as `(x, y, width, height)`.

    The interactive controls are positioned in SVG coordinate space, not CSS
    pixel space. Using the viewBox keeps controls correctly placed regardless of
    how the SVG is scaled by a browser or documentation page.
    """
    raw_viewbox = root.get("viewBox")

    if raw_viewbox:
        parts = raw_viewbox.replace(",", " ").split()
        if len(parts) >= 4:
            try:
                return tuple(float(v) for v in parts[:4])  # type: ignore[return-value]
            except ValueError:
                pass

    width = parse_svg_length(root.get("width"), 500.0)
    height = parse_svg_length(root.get("height"), 400.0)

    return 0.0, 0.0, width, height


def parse_svg_length(value: Optional[str], default: float) -> float:
    """Parse a simple SVG length and ignore units.

    This is only a fallback for SVGs without a `viewBox`. For control placement
    we only need approximate document dimensions, so accepting the leading
    numeric portion of values like `500px` is sufficient.
    """
    if not value:
        return default

    match = re.match(r"^\s*([0-9.]+)", value)
    if not match:
        return default

    try:
        return float(match.group(1))
    except ValueError:
        return default


def svg_id(label: str) -> str:
    """Return the snakevision/dagviz SVG ID for a rule label.

    This mirrors the ID convention used by the existing standalone animation
    prototype. Matching labels to SVG IDs lets us connect graph edges from
    NetworkX to the already-rendered SVG node circles.
    """
    return "N" + re.sub(r"[^0-9a-zA-Z_-]+", "", label)


def edge_path_d(
    from_id: str,
    to_id: str,
    nodes: Dict[str, Dict[str, Any]],
    arc_radius: float,
) -> str:
    """Build an SVG path string for one metro-style edge.

    The packet path intentionally follows the rendered snakevision convention:

        vertical lane -> quarter-circle arc -> horizontal segment

    Using the same geometry is important because `<animateMotion>` moves along
    the path we provide here; if this path differs from the visible DAG edge, the
    packet appears to drift away from the graph.
    """
    source = nodes[from_id]
    target = nodes[to_id]

    ax = source["x"]
    ay = source["y"]
    bx = target["x"]
    by = target["y"]
    radius = arc_radius

    if abs(ax - bx) < 0.5:
        return f"M {ax},{ay} L {bx},{by}"

    arc_start_y = by - radius

    if bx > ax:
        return (
            f"M {ax},{ay} "
            f"L {ax},{arc_start_y} "
            f"A {radius},{radius} 0 0 0 {ax + radius},{by} "
            f"L {bx},{by}"
        )

    return (
        f"M {ax},{ay} "
        f"L {ax},{arc_start_y} "
        f"A {radius},{radius} 0 0 1 {ax - radius},{by} "
        f"L {bx},{by}"
    )


def edge_length_estimate(
    from_id: str,
    to_id: str,
    nodes: Dict[str, Dict[str, Any]],
    arc_radius: float,
) -> float:
    """Estimate length of a metro-style edge path.

    Browser APIs such as `getTotalLength()` are unavailable while generating the
    SVG in Python. We therefore estimate length analytically from the known
    vertical segment, quarter-circle arc, and horizontal segment. This controls
    packet duration and phase propagation.
    """
    source = nodes[from_id]
    target = nodes[to_id]

    ax = source["x"]
    ay = source["y"]
    bx = target["x"]
    by = target["y"]
    radius = arc_radius

    if abs(ax - bx) < 0.5:
        return math.hypot(bx - ax, by - ay)

    arc_start_y = by - radius
    vertical_len = abs(arc_start_y - ay)
    arc_len = 0.5 * math.pi * radius
    arc_end_x = ax + radius if bx > ax else ax - radius
    horizontal_len = abs(bx - arc_end_x)

    return vertical_len + arc_len + horizontal_len


def build_animation_graph(
    edges: Sequence[Tuple[str, str]],
    svg_nodes: Dict[str, Dict[str, Any]],
    arc_radius: float,
    speed: float,
    rule_metadata: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Build the compact graph representation used by animation code.

    The main `SnakeVision` class already owns the canonical graph. This function
    converts its label-level edges into a JSON-friendly structure with SVG node
    IDs, node coordinates, edge paths, edge lengths, and optional rule metadata.

    Edges whose endpoints cannot be found in the SVG are skipped. This prevents
    post-processing from failing if the renderer changes or if a rule was
    filtered out before rendering.
    """
    animation_edges: List[Dict[str, Any]] = []
    used: Set[str] = set()
    label_by_node_id: Dict[str, str] = {}

    for src_label, dst_label in edges:
        src_id = svg_id(src_label)
        dst_id = svg_id(dst_label)

        if src_id not in svg_nodes or dst_id not in svg_nodes:
            continue

        path = edge_path_d(src_id, dst_id, svg_nodes, arc_radius)
        length = edge_length_estimate(src_id, dst_id, svg_nodes, arc_radius)
        duration = max(length / speed, 0.001)

        animation_edges.append(
            {
                "from": src_id,
                "to": dst_id,
                "path": path,
                "length": length,
                "duration": duration,
            }
        )

        used.update([src_id, dst_id])
        label_by_node_id[src_id] = src_label
        label_by_node_id[dst_id] = dst_label

    incoming: Dict[str, int] = {node_id: 0 for node_id in used}
    outgoing: Dict[str, List[int]] = {node_id: [] for node_id in used}

    for idx, edge in enumerate(animation_edges):
        incoming[edge["to"]] += 1
        outgoing[edge["from"]].append(idx)

    nodes: Dict[str, Dict[str, Any]] = {}

    for node_id in used:
        node = dict(svg_nodes[node_id])
        label = label_by_node_id.get(node_id, node_id)
        node["label"] = label

        if rule_metadata is not None:
            # Primary lookup is the original rule label. The SVG ID fallback is
            # convenient when users inspect the SVG and key metadata by node ID.
            if label in rule_metadata:
                node["ruleText"] = rule_metadata[label]
            elif node_id in rule_metadata:
                node["ruleText"] = rule_metadata[node_id]

        nodes[node_id] = node

    sources = sorted(
        [node_id for node_id, deg in incoming.items() if deg == 0],
        key=lambda node_id: svg_nodes[node_id]["y"],
    )

    return {
        "nodes": nodes,
        "edges": animation_edges,
        "incoming": incoming,
        "outgoing": outgoing,
        "sources": sources,
    }


def topological_order(graph: Dict[str, Any]) -> List[str]:
    """Return a topological ordering of animation graph nodes.

    Snakemake rule graphs should be DAGs. If unexpected cyclic input appears, we
    fall back to y-position ordering so the SVG can still be generated and the
    user gets a warning instead of a hard failure.
    """
    nodes = graph["nodes"]
    edges = graph["edges"]

    indegree = {node_id: 0 for node_id in nodes}
    children: Dict[str, List[str]] = {node_id: [] for node_id in nodes}

    for edge in edges:
        indegree[edge["to"]] += 1
        children[edge["from"]].append(edge["to"])

    queue = deque(
        sorted(
            [node_id for node_id, deg in indegree.items() if deg == 0],
            key=lambda node_id: nodes[node_id]["y"],
        )
    )

    order: List[str] = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)

        for child_id in children[node_id]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                queue.append(child_id)

    if len(order) == len(nodes):
        return order

    print(
        "Warning: animation graph does not appear to be acyclic; "
        "falling back to y-order.",
        file=sys.stderr,
    )

    return sorted(nodes, key=lambda node_id: nodes[node_id]["y"])


def normalize_phase(value: float, interval: float, resolution: float) -> float:
    """Normalize and quantize an animation phase.

    Packet phases are propagated through the graph so downstream packets appear
    after upstream travel time. Quantizing phases prevents tiny floating-point
    differences from creating many visually-identical packet elements.
    """
    phase = value % interval
    rounded = round(phase / resolution) * resolution

    if rounded >= interval:
        rounded = 0.0

    return round(rounded, 6)


def compute_edge_start_phases(
    graph: Dict[str, Any],
    packet_interval: float,
    phase_resolution: float,
    max_phases_per_edge: int,
) -> Tuple[Dict[int, List[float]], List[str]]:
    """Compute repeated packet start phases for each edge.

    Source nodes emit packets at phase zero. Each edge propagates packet phases
    to its target by adding edge travel duration modulo the packet interval.
    This creates the visual effect of data packets flowing through downstream
    steps after upstream packets arrive.
    """
    edges = graph["edges"]
    outgoing = graph["outgoing"]
    sources = graph["sources"]

    node_phases: DefaultDict[str, Set[float]] = defaultdict(set)
    edge_start_phases: DefaultDict[int, Set[float]] = defaultdict(set)

    for source_id in sources:
        node_phases[source_id].add(0.0)

    warnings: List[str] = []

    for node_id in topological_order(graph):
        phases = sorted(node_phases[node_id])

        if not phases:
            continue

        for edge_idx in outgoing.get(node_id, []):
            edge = edges[edge_idx]

            for phase in phases:
                edge_start_phases[edge_idx].add(phase)

                arrival_phase = normalize_phase(
                    phase + edge["duration"],
                    packet_interval,
                    phase_resolution,
                )
                node_phases[edge["to"]].add(arrival_phase)

            if len(edge_start_phases[edge_idx]) > max_phases_per_edge:
                sorted_phases = sorted(edge_start_phases[edge_idx])
                edge_start_phases[edge_idx] = set(sorted_phases[:max_phases_per_edge])
                warnings.append(
                    f"edge {edge_idx} exceeded max_phases_per_edge="
                    f"{max_phases_per_edge}; truncating visual packet phases"
                )

    return {
        edge_idx: sorted(phases)
        for edge_idx, phases in edge_start_phases.items()
    }, warnings


def ensure_defs(root: ET.Element) -> ET.Element:
    """Return the SVG `<defs>` element, creating one if needed.

    Styles are inserted into `<defs>` so they remain part of the SVG document
    without interfering with the visible graph element order.
    """
    defs = root.find(q("defs"))

    if defs is None:
        defs = ET.SubElement(root, q("defs"))

    return defs


def add_style(
    root: ET.Element,
    add_reduced_motion_css: bool,
    interactive_js: bool,
    has_rule_metadata: bool,
) -> None:
    """Add CSS rules needed by packet animation and optional interactivity.

    The CSS is kept inside the SVG so the output is self-contained. Pointer
    events are disabled for packet/highlight layers to avoid those generated
    elements blocking interactions with the original DAG nodes.
    """
    defs = ensure_defs(root)
    style = ET.SubElement(defs, q("style"))

    css = [
        ".packet-layer, .pkt, .highlight-layer { pointer-events: none; }",
        ".pkt-core { fill: black; stroke: white; stroke-width: 0.8; }",
        ".pkt-glow { fill: black; opacity: 0.15; }",
    ]

    if interactive_js:
        css.extend(
            [
                "#play-pause-btn, #reset-packets-btn { cursor: pointer; }",
                "#play-pause-btn:hover #btn-bg, #reset-packets-btn:hover #reset-btn-bg { opacity: 0.88; }",
                "#play-pause-btn:focus, #reset-packets-btn:focus { outline: none; }",
                "#play-pause-btn:focus #btn-bg, #reset-packets-btn:focus #reset-btn-bg { stroke: white; stroke-width: 1.5; }",
                "#reset-packets-btn text { pointer-events: none; user-select: none; }",
                ".dag-node { cursor: pointer; }",
                ".hl-edge { transition: opacity 0.12s ease; }",
                ".hl-ring { transition: opacity 0.12s ease; }",
                ".dag-node-circle { transition: opacity 0.12s ease; }",
                ".dag-orig-edge { transition: opacity 0.12s ease; }",
            ]
        )

    if has_rule_metadata:
        css.extend(
            [
                "#rule-info-panel { pointer-events: auto; }",
                "#rule-info-panel-bg { fill: #111; opacity: 0.94; stroke: #666; stroke-width: 0.8; }",
                "#rule-info-panel-title { fill: white; font-family: sans-serif; font-weight: bold; }",
                "#rule-info-panel-body { fill: #eeeeee; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }",
                "#rule-info-panel-close { fill: white; font-family: sans-serif; cursor: pointer; }",
            ]
        )

    if add_reduced_motion_css and not interactive_js:
        # In script-free README-friendly mode, CSS is our only way to respect
        # reduced-motion preferences. In interactive mode JS pauses animations.
        css.extend(
            [
                "@media (prefers-reduced-motion: reduce) {",
                "  #packet-animation-layer { display: none; }",
                "}",
            ]
        )

    style.text = "\n" + "\n".join(css) + "\n"


def fmt_seconds(value: float) -> str:
    """Format a float seconds value for SVG animation attributes."""
    if abs(value) < 1e-9:
        return "0s"

    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{text}s"


def fmt_float(value: float) -> str:
    """Return compact string formatting for SVG numeric attributes."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def add_packet(
    layer: ET.Element,
    path_d: str,
    packet_radius: float,
    begin: float,
    travel_duration: float,
    cycle_duration: float,
) -> None:
    """Add one declarative animated packet to the packet layer.

    The packet is visible only while traversing the edge. If the cycle duration
    is longer than the travel duration, the packet is hidden while it waits for
    the next repeat. This creates repeated waves without needing JavaScript.
    """
    group = ET.SubElement(layer, q("g"))
    group.set("class", "pkt")
    group.set("opacity", "1")

    glow = ET.SubElement(group, q("circle"))
    glow.set("class", "pkt-glow")
    glow.set("r", fmt_float(packet_radius * 1.8))

    core = ET.SubElement(group, q("circle"))
    core.set("class", "pkt-core")
    core.set("r", fmt_float(packet_radius))

    active_fraction = travel_duration / cycle_duration
    active_fraction = max(0.000001, min(1.0, active_fraction))

    motion = ET.SubElement(group, q("animateMotion"))
    motion.set("path", path_d)
    motion.set("begin", fmt_seconds(begin))
    motion.set("dur", fmt_seconds(cycle_duration))
    motion.set("repeatCount", "indefinite")
    motion.set("calcMode", "linear")

    if active_fraction < 0.999999:
        motion.set("keyPoints", "0;1;1")
        motion.set("keyTimes", f"0;{fmt_float(active_fraction)};1")

        opacity = ET.SubElement(group, q("animate"))
        opacity.set("attributeName", "opacity")
        opacity.set("begin", fmt_seconds(begin))
        opacity.set("dur", fmt_seconds(cycle_duration))
        opacity.set("repeatCount", "indefinite")
        opacity.set("calcMode", "discrete")
        opacity.set("values", "1;0;0")
        opacity.set("keyTimes", f"0;{fmt_float(active_fraction)};1")
    else:
        motion.set("keyPoints", "0;1")
        motion.set("keyTimes", "0;1")


def add_declarative_packet_animation(
    root: ET.Element,
    graph: Dict[str, Any],
    packet_interval: float,
    packet_radius: float,
    edge_start_phases: Dict[int, List[float]],
    max_copies_per_phase: int,
) -> Tuple[int, List[str]]:
    """Add the script-free SVG `<animateMotion>` packet animation layer.

    This function is used for both README-friendly and interactive output. The
    interactive JS controls the SVG animation clock, but the packet movement
    itself remains declarative SVG animation in both modes.
    """
    layer = ET.SubElement(root, q("g"))
    layer.set("id", "packet-animation-layer")
    layer.set("class", "packet-layer")

    warnings: List[str] = []
    packet_count = 0

    for edge_idx, edge in enumerate(graph["edges"]):
        phases = edge_start_phases.get(edge_idx, [])

        if not phases:
            continue

        travel_duration = edge["duration"]
        copies_needed = max(1, math.ceil(travel_duration / packet_interval))

        if copies_needed > max_copies_per_phase:
            warnings.append(
                f"edge {edge_idx} needs {copies_needed} overlapping copies per "
                f"phase, but max_copies_per_phase={max_copies_per_phase}; "
                "truncating visual packet copies"
            )
            copies_needed = max_copies_per_phase

        cycle_duration = packet_interval * copies_needed

        for phase in phases:
            for copy_idx in range(copies_needed):
                begin = phase + copy_idx * packet_interval

                add_packet(
                    layer=layer,
                    path_d=edge["path"],
                    packet_radius=packet_radius,
                    begin=begin,
                    travel_duration=travel_duration,
                    cycle_duration=cycle_duration,
                )
                packet_count += 1

    return packet_count, warnings


def add_interactive_script(
    root: ET.Element,
    graph: Dict[str, Any],
    viewbox: Tuple[float, float, float, float],
    has_rule_metadata: bool,
) -> None:
    """Inject JavaScript for play/pause, reset, hover, and optional popups.

    JavaScript is intentionally added only in explicit interactive mode because
    many documentation renderers, including GitHub README rendering, will not
    execute SVG scripts. In direct-browser/GitHub Pages contexts, however, this
    provides a richer exploratory view of the workflow.
    """
    vx, vy, vw, vh = viewbox

    btn_cx = vx + vw - 13
    btn_cy = vy + 13
    btn_r = 10

    reset_btn_w = 24.0
    reset_btn_h = 18.0
    reset_btn_x = btn_cx - btn_r - 5.0 - reset_btn_w
    reset_btn_y = btn_cy - reset_btn_h / 2.0

    panel_w = min(320.0, max(180.0, vw - 28.0))
    panel_x = vx + vw - panel_w - 14.0
    panel_y = vy + 30.0

    if panel_x < vx + 8.0:
        panel_x = vx + 8.0
        panel_w = max(120.0, vw - 16.0)

    if panel_y + 80.0 > vy + vh:
        panel_y = vy + 14.0

    if reset_btn_x < vx + 4.0:
        reset_btn_x = vx + 4.0

    payload = json.dumps(
        {
            "graph": graph,
            "btnCx": btn_cx,
            "btnCy": btn_cy,
            "btnR": btn_r,
            "resetBtnX": reset_btn_x,
            "resetBtnY": reset_btn_y,
            "resetBtnW": reset_btn_w,
            "resetBtnH": reset_btn_h,
            "panelX": panel_x,
            "panelY": panel_y,
            "panelW": panel_w,
            "panelMaxH": max(80.0, vh - (panel_y - vy) - 14.0),
            "hasRuleMetadata": has_rule_metadata,
        }
    )

    script = ET.SubElement(root, q("script"))
    script.text = "\n" + javascript(payload) + "\n"


def add_animation_metadata(
    root: ET.Element,
    graph: Dict[str, Any],
    config: AnimationConfig,
    arc_radius: float,
    packet_count: int,
    has_rule_metadata: bool,
) -> None:
    """Add machine-readable metadata describing the animation enhancement.

    This is useful for debugging generated SVGs later. It also lets tests or
    downstream tools identify whether a given SVG was generated with animation
    and/or interactive features.
    """
    metadata = ET.SubElement(root, q("metadata"))
    metadata.text = json.dumps(
        {
            "generatedBy": "snakevision.animation",
            "animation": "declarative-svg-animateMotion",
            "interactiveJs": config.interactive_js,
            "interactiveModeStartsPaused": config.interactive_js,
            "hasRuleMetadata": has_rule_metadata,
            "hasResetPacketsButton": config.interactive_js,
            "edgeCount": len(graph["edges"]),
            "sourceCount": len(graph["sources"]),
            "packetElementCount": packet_count,
            "speed": config.speed,
            "packetInterval": config.packet_interval,
            "packetRadius": config.packet_radius,
            "arcRadius": arc_radius,
        },
        indent=2,
        sort_keys=True,
    )


def enhance_svg(
    svg_text: str,
    edges: Sequence[Tuple[str, str]],
    config: AnimationConfig,
    arc_radius: float
) -> str:
    """Enhance a rendered snakevision SVG with optional packet animation.

    This is the main public entry point for the module. The expected usage is:

        1. `SnakeVision` builds the NetworkX graph.
        2. `dagviz.render_svg(...)` renders the static SVG.
        3. `enhance_svg(...)` post-processes the SVG text.  <- HERE
        4. `SnakeVision.write(...)` writes the final SVG to disk.

    Keeping this as post-processing avoids changing the existing rendering
    pipeline and keeps the default static output behavior unchanged.

    @param svg_text <str>:
        SVG document text produced by `dagviz.render_svg`.
    @param edges <Sequence[tuple[str, str]]>:
        Label-level directed edges from the final rendered graph, typically
        `list(self.dag.edges())`.
    @param config <AnimationConfig>:
        Animation and interactivity options.
    @param arc_radius <float>:
        The radius of the arc used for edge animations.
    @returns enhanced_svg <str>:
        The original SVG if animation is disabled, otherwise an enhanced SVG.
    """
    if not config.enabled and not config.interactive_js:
        return svg_text

    validate_animation_config(config)

    rule_metadata = load_rule_metadata_yaml(config.rule_metadata_yaml)
    has_rule_metadata = rule_metadata is not None

    root = parse_svg_text(svg_text)
    svg_nodes = extract_svg_nodes(root)
    viewbox = detect_viewbox(root)

    graph = build_animation_graph(
        edges=edges,
        svg_nodes=svg_nodes,
        arc_radius=arc_radius,
        speed=config.speed,
        rule_metadata=rule_metadata,
    )

    add_style(
        root=root,
        add_reduced_motion_css=config.reduced_motion_css,
        interactive_js=config.interactive_js,
        has_rule_metadata=has_rule_metadata,
    )

    edge_start_phases, phase_warnings = compute_edge_start_phases(
        graph=graph,
        packet_interval=config.packet_interval,
        phase_resolution=config.sample_phase_resolution,
        max_phases_per_edge=config.max_phases_per_edge,
    )

    packet_count, packet_warnings = add_declarative_packet_animation(
        root=root,
        graph=graph,
        packet_interval=config.packet_interval,
        packet_radius=config.packet_radius,
        edge_start_phases=edge_start_phases,
        max_copies_per_phase=config.max_copies_per_phase,
    )

    if config.interactive_js:
        add_interactive_script(
            root=root,
            graph=graph,
            viewbox=viewbox,
            has_rule_metadata=has_rule_metadata,
        )

    add_animation_metadata(
        root=root,
        graph=graph,
        config=config,
        arc_radius=arc_radius,
        packet_count=packet_count,
        has_rule_metadata=has_rule_metadata,
    )

    for warning in phase_warnings + packet_warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    return ET.tostring(root, encoding="unicode")