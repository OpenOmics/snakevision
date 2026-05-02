"""Core classes for parsing and rendering Snakemake workflow DAGs.

This module defines the abstract and concrete interfaces used to transform a
Snakemake rule graph into a directed acyclic graph (DAG) representation backed
by `networkx` and rendered as SVG output with `dagviz`. The primary public
class, `SnakeVision`, parses rule graph input, builds the internal DAG, and
writes the resulting workflow visualization to disk. An optional abstract base
class, `AbstractSnakeVision`, is also defined to provide a common interface for
potential future extensions or alternative implementations of snakevision.

The resulting DAG visualization can be customized with user-defined styles
and can optionally exclude specific rules (such as the conventional `all`
rule) to reduce clutter in the final image.

The module is intended to provide the reusable program logic for the
snakevision package independent of its command-line interface.
"""

# Python standard library
from abc import ABC, abstractmethod
import os
import textwrap

# 3rd party package from pypi,
# pip install if missing
import dagviz
from dagviz.style.metro import svg_renderer, StyleConfig
import networkx as nx

# Local relative imports
from .animation import AnimationConfig, enhance_svg
from .utils import Colors


class AbstractSnakeVision(ABC):
    """An abstract base class for defining an common interface for snakevision.
    A snakevision class contains methods for parsing rulegraphs, building a DAG,
    and writing the resulting dag as a snakevision image.

    Usage example:
        dag = SnakeVision('snakemake_rulegraph')
        dag.write('/path/to/output/pipeline_dag.svg')
    """

    @abstractmethod
    def parse(self): ...

    @abstractmethod
    def build(self): ...

    @abstractmethod
    def write(self): ...


class SnakeVision(AbstractSnakeVision):
    """SnakeVision class contains methods for parsing snakemake rule graphs,
    building a DAG, and writing the resulting dag as a snakevision image.

    Usage example:
        dag = SnakeVision('snakemake_rulegraph')
        dag.write('/path/to/output/pipeline_dag.svg')
    """

    def __init__(self, input, dag=None, skip=None, verbose=False):
        # Avoid mutable default arguments so each SnakeVision instance starts
        # with its own graph and skip list. This is especially important for
        # library usage and tests where multiple instances may be created in
        # the same Python process.
        if dag is None:
            dag = nx.DiGraph()
        if skip is None:
            skip = []

        self.input = input  # Input open file handle to a snakemake rule graph
        self.dag = dag  # networkx.DiGraph() object to model relationships
        self.skip = skip  # Do not add these rules in figure
        self.verbose = verbose  # Prints parsed nodes and relationships
        self.node2label = {}  # Maps node ids to rule names
        self.labels = []  # Keeps track of rule name order
        self.n2n = []  # Nested list keeps track of node-to-node relationships
        self.verbose_dag = ""  # Verbose dag debugging information

        # Parse input snakemake rule graph.
        self.parse()
        # Builds dag from the parsed rule graph
        self.build()
        # Collect and display dag debugging information
        self.debug_dag()
        if self.verbose:
            print(self.verbose_dag)

    def __repr__(self):
        return textwrap.dedent("""
            Class usage example:
            dag = SnakeVision('snakemake_rulegraph.txt')
            dag.write('/path/to/output/pipeline_dag.svg')
            """)

    def __str__(self):
        return self.verbose_dag

    def debug_dag(self):
        """Displays verbose information of the parsed rule graph."""
        _c = Colors
        self.verbose_dag = textwrap.dedent("""
            {3}{4}Node-to-label mappings:{5}
            • {0}

            {3}{4}Node to node relationship:{5}
            • {1}

            {3}{4}Order of encountered labels:{5}
            • {2}
            """.format(self.node2label, self.n2n, self.labels, _c.bold, _c.url, _c.end))

    def parse(self):
        """Parses a snakemake rule graph, saves parsed output in node2labels
        labels, and n2n instance variables.

        Example input rule graph:
           0[label = "all", color = "0.34 0.6 0.85", style="rounded"];
           1[label = "fc_lane", color = "0.35 0.6 0.85", style="rounded"];
           2[label = "fastqc_raw", color = "0.09 0.6 0.85", style="rounded"];
           1 -> 0
           2 -> 0
        """
        for line in self.input:
            line = line.strip()
            # Skip over empty and un-important
            # lines, rulegraph node ids start
            # with a number
            if not line:
                continue
            if not line[0].isdigit():
                continue
            # Parse nodes and edges in dag,
            # need to map a node id to a
            # snakemake rule name
            if "[" in line:
                # node definition line, i.e:
                # 0[label = "all", color = "0.34 0.6 0.85", style="rounded"];
                node = int(line.split("[")[0])
                label = (
                    line.split("=")[1]
                    .split(",")[0]
                    .strip()
                    .replace('"', "")
                    .replace("'", "")
                )
                if label == self.skip:
                    # Get node ID of skip node, i.e
                    # rule all or the final target
                    skipnode = node
                self.node2label[node] = label
                self.labels.append(label)
            elif "->" in line:
                # node relationships or edges, i.e:
                # 1 -> 0
                nodes = [int(n.strip()) for n in line.split("->")]
                lab1 = self.node2label[nodes[0]]
                lab2 = self.node2label[nodes[1]]
                self.n2n.append([lab1, lab2])

    def build(self):
        """Builds a DAG from a parsed snakemake rule graph."""
        # Add nodes to the dag
        for lab in self.labels:
            if lab in self.skip:
                # Do NOT include rule all
                # in the final figure
                continue
            self.dag.add_node(lab)

        # Add relationships or edges to dag
        for l1, l2 in self.n2n:
            if l1 in self.skip or l2 in self.skip:
                # Do NOT include rule all
                # in the final figure
                continue
            self.dag.add_edge(l1, l2)

    def write(
        self,
        output="snakevision_dag.svg",
        style=None,
        animation_config=None,
    ):
        """Write DAG to output image.

        @param output <str>:
            Path to the SVG output file.
        @param style <dict|None>:
            Optional dagviz StyleConfig overrides. When None, default dagviz
            styling is used.
        @param animation_config <AnimationConfig|None>:
            Optional animation configuration. When provided and enabled, the
            static dagviz SVG is post-processed to add declarative packet
            animation and, optionally, interactive JavaScript controls.
        """
        if style is None:
            style = {}

        # Create output directory as needed
        outdir = os.path.dirname(os.path.abspath(output))
        if not os.path.exists(outdir):
            # Pipeline output directory
            # does not exist on filesystem
            os.makedirs(outdir)

        # Apply a custom style if available
        custom_style = svg_renderer(StyleConfig(**style))

        # Render the static snakevision DAG first.
        # This preserves existing behavior and lets
        # the optional animation code operate as a
        # pure SVG post-processing step.
        svg_text = dagviz.render_svg(self.dag, style=custom_style)

        # Add optional packet animation and interactive
        # controls. We pass the final rendered graph
        # edges, not the raw parsed edges, so animation
        # respects any skipped rules and exactly matches
        # what the user should see.
        if animation_config is not None and (
            animation_config.enabled or animation_config.interactive_js
        ):
            # Add animation and interactivity
            svg_text = enhance_svg(
                svg_text=svg_text,
                edges=list(self.dag.edges()),
                config=animation_config,
                arc_radius=style.get("edge_arc_radius", 15.0),
            )

        # Write DAG SVG to disk
        if os.path.exists(output):
            os.remove(output)
        with open(output, "wt") as fs:
            fs.write(svg_text)
