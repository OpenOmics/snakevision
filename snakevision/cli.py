"""Command-line argument parsing utilities for snakevision.

This module defines the command-line interface used by the snakevision
package, including argument parsing, validation of user-provided style
overrides, animation options, and generation of formatted help text
describing supported options and customizable rendering attributes.
"""
# Python standard library
from dataclasses import fields, MISSING
import argparse
import os
import sys
import textwrap

# 3rd party package from pypi,
# pip install if missing
from dagviz.style.metro import StyleConfig

# Local relative imports
from .animation import AnimationConfig
from .metadata import (
    pkg_name,
    pkg_description,
    pkg_min_python
)
from .snakevision import SnakeVision
from .utils import (
    Colors,
    fatal,
    flatten,
    log
)
from .version import __version__


# Helper functions for parsing command-line arguments and building
# custom help messages for the set of customizable style attributes.
def parse_style_attributes(styles: str):
    """Parses custom style attributes to override the default
    styling of dagviz. For more information, please reference:
    https://wimyedema.github.io/dagviz/dagviz/style/metro.html
    @param styles <str>:
        Custom style encoded as a key, value pair, i.e:
        'node_radius=0.6' or 'node_stroke=white'
    @returns parsed style info <tuple[str, str]>
    """
    # Get the set of allowed style attributes
    allowed_attributes = [f.name for f in fields(StyleConfig)]
    if "=" not in styles:
        raise argparse.ArgumentTypeError(f"Expected key=value, got: {styles!r}")
    k, v = styles.split("=", 1)
    for cast in (int, float):
        try:
            v = cast(v)
            break
        except ValueError:
            pass
    if k not in allowed_attributes:
        # Attribute is not valid
        raise argparse.ArgumentTypeError(
            "Invalid style attribute: '{0}'.\nPlease select one of the following attributes:\n{1}".format(
                k, "\n".join(["  • {0}".format(a) for a in allowed_attributes])
            )
        )
    if not k:
        raise argparse.ArgumentTypeError("Style key cannot be empty!")
    return (k, v)


def positive_float(option_name):
    """Create an argparse validator for positive floating-point options.
    @param option_name <str>:
        Name of the command-line option being validated. This is used only
        for generating a helpful error message.
    @returns validator <callable>:
        Function that converts an input string to a positive float.
    """
    def _validator(value):
        try:
            parsed = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "{0} must be a number, got: {1!r}".format(option_name, value)
            )
        if parsed <= 0:
            raise argparse.ArgumentTypeError(
                "{0} must be greater than 0, got: {1}".format(option_name, parsed)
            )
        return parsed

    return _validator


def positive_int(option_name):
    """Create an argparse validator for positive integer options.
    @param option_name <str>:
        Name of the command-line option being validated. This is used only
        for generating a helpful error message.
    @returns validator <callable>:
        Function that converts an input string to a positive integer.
    """
    def _validator(value):
        try:
            parsed = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "{0} must be an integer, got: {1!r}".format(option_name, value)
            )
        if parsed <= 0:
            raise argparse.ArgumentTypeError(
                "{0} must be greater than 0, got: {1}".format(option_name, parsed)
            )
        return parsed

    return _validator


def existing_path(option):
    """Normalize a user-provided path to an absolute path.
    @param option <str>:
        Path provided on the command line.
    @returns path <str>:
        Absolute, expanded path.
    """
    return os.path.abspath(os.path.expanduser(option))


def build_customizable_style_attributes_help_section(left_offset_amount=18):
    """Create the help section for the set of customizable style
    attributes along with their default values. This information
    is pulled from fields defined in the StyleConfig class.
    @param left_offset_amount <int>:
        Amount of white-space to left pad the help text
    @returns help style text <str>:
        Pre-formatted text containing style attributes and their defaults
    """
    stylized_attrs_defaults = []
    attr_idx = 0  # offset the first attribute less
    for f in fields(StyleConfig):
        offset = " " * left_offset_amount
        if attr_idx == 0:
            offset = " "
        default = None if f.default is MISSING else f.default
        stylized_attrs_defaults.append(f"{offset}• {f.name}: {default!r}")
        attr_idx += 1
    return "\n".join(stylized_attrs_defaults)


def parsed_arguments(name, description, version):
    """Parses user-provided command-line arguments. Requires argparse package.
    argparse was added to standard lib in python 3.5.
    @param name <str>:
        Name of the command-line tool
    @param description <str>:
        Short description of the command-line tool
    @returns parsed cli args <object argparse.ArgumentParser.parse_args()>
    """
    # Get the set customizable style attributes
    # along with their default values
    _style_attr_help = build_customizable_style_attributes_help_section()

    # Add styled name and description
    _c = Colors
    _n = "{0}{1}{2}{3}{4}".format(_c.bold, _c.bg_black, _c.cyan, name, _c.end)
    _d = "{0}{1}{2}".format(_c.bold, description, _c.end)

    # Creating a custom help and usage message,
    # the default styling of argparse is too basic.
    _styled_help = textwrap.dedent(
        """\
        {0}: {1}

        {3}{4}Synopsis:{5}
          $ {2} [--help] [--version] \\
                [--skip-rules RULE RULE ...] \\
                [--style KEY=VALUE [KEY=VALUE ...]] \\
                [--output OUTPUT] \\
                [--animate] \\
                [--interactive-js] \\
                [--packet-interval SECONDS] \\
                [--packet-speed SPEED] \\
                [--packet-radius RADIUS] \\
                [--rule-metadata-yaml RULE_METADATA_YAML] \\
                snakemake_rulegraph

        Optional arguments are shown in square brackets above.

        {3}{4}Description:{5}
          Create an awesome DAG from a snakemake rule graph. A rule graph
        can be generated by running a pipeline with the `--forceall` and
        `--rulegraph` options. The resulting rule graph can be saved to a
        file and provided as input, or the rule graph can be piped into
        this program via standard input.

        {3}{4}Positional arguments:{5}
          snakemake_rulegraph
                Input snakemake rule graph to visualize. The rule graph
                can be provided as an  input file or it can be provided
                via standard input (i.e. piped into the program).  If a
                file is not provided as input,  it is assummed the rule
                graph should be read from standard input.  A snakemake
                rule graph must be provided,  either as a file or via
                standard input.

        {3}{4}General Options:{5}
          -o, --output OUTPUT
                Name of the output SVG file. The resulting DAG generated
                by the provided input snakemake rule graph will be saved
                to this file.
                    • Default: "snakevision_dag.svg"
                    • Example: --output awesome_pipleine_dag.svg

          -s, --skip-rules RULE [RULE ...]
                Name of snakemake rule(s) to not include in the figure.
                One or more rule names can be provided.  Any rule names
                provided to  this option will not be included in the
                final snakevision figure. We recommend skipping rule
                all or any other rules that represent final targets
                in the pipeline as they tend to have many incoming
                edges which clutters the resulting image.
                    • Default: No rules are skipped
                    • Example: --skip-rules all multiqc

          -y, --style KEY=VALUE [KEY=VALUE ...]
                Apply custom style attributes as key=value pairs.
                Each key, value representing a style attribute and
                its value should be seperated by a "=" character.
                Here is a list of each available style attribute
                and their default values:
                 {7}
                    • Default: See key, value pairs listed above
                    • Example: --style "scale=11.0" "arc_radius=12.0"

          -d, --debug-dag
                Increases verbosity to help debug any DAG errors.
                    • Example: --debug-dag

          -h, --help
                Shows usage information, help message, and exits.
                    • Example: --help

          -v, --version
                Shows sematic version of tool and exits.
                    • Example: --version

        {3}{4}Animation Options:{5}
          --animate
                Add script-free SVG packet animation using declarative
                <animateMotion> elements. This mode is intended to be more
                suitable for embedding in a GitHub README because it does
                not require JavaScript.
                    • Default: No animation
                    • Example: --animate

          --interactive-js
                Add JavaScript-powered controls and interactions to the SVG.
                This enables play/pause, a reset button, hover dependency
                highlighting, and optional click-to-show rule metadata popups.
                Interactive SVG output starts paused by default.
                This option implies --animate.
                    • Default: No interactivity
                    • Example: --interactive-js

          --packet-interval SECONDS
                Seconds between repeated packet waves from each source node.
                This option only affects animated output.
                    • Default: 20.0
                    • Example: --packet-interval 10

          --packet-speed PX_PER_SECOND
                Packet speed in SVG pixels per second.
                This option only affects animated output.
                    • Default: 30.0
                    • Example: --packet-speed 20

          --packet-radius RADIUS
                Visual radius of each animated packet circle.
                This option only affects animated output.
                    • Default: 3.0
                    • Example: --packet-radius 4

          --rule-metadata-yaml RULE_METADATA_YAML
                Optional YAML file mapping DOT labels/rule names to text
                shown when clicking nodes in interactive SVG output. Values
                may be single-line strings or multiline YAML block strings.
                Requires --interactive-js and PyYAML.
                    • Example: --rule-metadata-yaml rule_metadata.yaml
        """.format(
            _n, _d, name, _c.bold, _c.url, _c.end, _c.italic, _style_attr_help
        )
    )

    # Supressing help messages, use style messages
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_styled_help,
        add_help=False,
    )

    # An optional positional argument that
    # takes a snakemake DAG as input:
    #     $ snakemake  --configfile=$outdir/config.json \
    #           -s $outdir/workflow/Snakefile \
    #           -d $outdir \
    #           --forceall \
    #           --rulegraph
    # If a file is not provided as input, then
    # the program will read from standard input.
    parser.add_argument(
        "input_file",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help=argparse.SUPPRESS,
    )

    # Optional output file name for DAG figure,
    # defaults: default: "snakevision_dag.svg"
    parser.add_argument(
        "-o",
        "--output",
        type=lambda option: os.path.abspath(os.path.expanduser(option)),
        required=False,
        default="snakevision_dag.svg",
        help=argparse.SUPPRESS,
    )

    # Define the name of rule all,
    # conventional name is 'all';
    # however a user can name it any-
    # thing. This rule in not included
    # in the final figure (recommended)
    # as it clutters image.
    parser.add_argument(
        "-s",
        "--skip-rules",
        type=str,
        action="append",
        required=False,
        nargs="+",
        default=[],
        help=argparse.SUPPRESS,
    )

    # Parse custom style attributes
    parser.add_argument(
        "-y",
        "--style",
        action="append",
        type=parse_style_attributes,
        nargs="+",
        default=[],
        required=False,
        help=argparse.SUPPRESS,
    )

    # Adds declarative packet animation to the SVG
    # This option should not change the core graph
    # layout. It only post-processes the rendered
    # SVG to add packet elements that follow the
    # existing edge geometry.
    parser.add_argument(
        "--animate",
        action="store_true",
        default=False,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Add optional javascript controls and node
    # interactions. This mode implies --animate
    # because the controls operate on the packet
    # animation layer. It starts paused by default
    # for accessibility and to avoid unexpected
    # motion in interactive contexts
    parser.add_argument(
        "--interactive-js",
        action="store_true",
        default=False,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Controls how often new packets are
    # emitted from the root nodes
    parser.add_argument(
        "--packet-interval",
        type=positive_float("--packet-interval"),
        default=20.0,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Controls how fast packets travel
    # along edges of the DAG
    parser.add_argument(
        "--packet-speed",
        type=positive_float("--packet-speed"),
        default=30.0,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Sets the size radius of the data packets
    parser.add_argument(
        "--packet-radius",
        type=positive_float("--packet-radius"),
        default=3.0,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Path to a YAML file containing rule
    # metadata, if the interactive-js option
    # is provided then this file can be provided
    # to add on click popups to annotate the
    # nodes, i.e show the rule or additional info
    parser.add_argument(
        "--rule-metadata-yaml",
        type=existing_path,
        default=None,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Debugs DAG, increases verbosity
    parser.add_argument(
        "-d",
        "--debug-dag",
        action="store_true",
        default=False,
        required=False,
        help=argparse.SUPPRESS,
    )

    # Add custom help message
    parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)

    # Adding sematic verison information
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="{0} {1}".format(name, version),
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    # Interactive SVGs imply animations, so
    # let's make --interactive-js imply
    # --animate. This gives users a simpler
    # command: `snakevision --interactive-js ...`
    # instead of requiring both flags be provided.
    if args.interactive_js:
        args.animate = True

    # Rule metadata is displayed by javascript
    # click popups. Without interactive javascript
    # there is no click handler or popup panel,
    # so fail early with a clear message rather
    # than silently ignoring the metadata file.
    if args.rule_metadata_yaml and not args.interactive_js:
        parser.error("--rule-metadata-yaml requires --interactive-js")

    return args


def main():
    """Entry-point to the snakevision command-line interface."""
    # Main function/entry point for snakevision,
    # called when executing `python -m snakevision`.
    # Check for minimum python verison,
    # enforces running with python>=3.7
    MINIMUM_PYTHON = pkg_min_python
    MAJOR_VERSION, MINOR_VERSION = MINIMUM_PYTHON
    if sys.version_info < MINIMUM_PYTHON:
        fatal(
            "Error: Python {0}.{1} or later is required!".format(
                MAJOR_VERSION, MINOR_VERSION
            )
        )

    # Parse command-line arguments
    args = parsed_arguments(
        name=pkg_name,
        description=pkg_description,
        version=__version__
    )

    # Flatten options witn a 1:M relationships.
    # This allows options to be specified as
    # mutiple times or a space seperated list,
    # i.e: `-x 1 -x 2 -x 3` or `-x 1 2 3`
    args.skip_rules = flatten(args.skip_rules)
    args.style = flatten(args.style)

    # Build animation configuration from CLI options.
    # This object is passed into SnakeVision.write(), where the static SVG can
    # be post-processed after dagviz renders the graph. Keeping this as a single
    # config object avoids adding many animation-specific parameters to
    # SnakeVision.write() and makes the feature easier to extend later.
    animation_config = AnimationConfig(
        enabled=args.animate,
        interactive_js=args.interactive_js,
        packet_interval=args.packet_interval,
        speed=args.packet_speed,
        packet_radius=args.packet_radius,
        rule_metadata_yaml=args.rule_metadata_yaml
    )

    log("Started parsing rulegraph: {0}".format(getattr(args.input_file, "name", "")))
    if args.skip_rules:
        log("Skipping over the following rules in DAG visualization: {0}".format(args.skip_rules))

    # Create a snakevision dag object
    dag = SnakeVision(
        input=args.input_file, skip=args.skip_rules, verbose=args.debug_dag
    )
    log("Finished parsing rulegraph: {0}".format(getattr(args.input_file, "name", "")))

    log("Started writing DAG to the following output file: {0}".format(args.output))
    if args.style:
        log("Applying additional styling options to DAG: {0}".format(args.style))
    if animation_config.enabled:
        if animation_config.interactive_js:
            log("Adding interactive SVG animation controls to DAG output")
        else:
            log("Adding script-free SVG packet animation to DAG output")
    if animation_config.rule_metadata_yaml:
        log("Adding rule metadata popups from: {0}".format(animation_config.rule_metadata_yaml))

    # Write the DAG to the specified output file
    dag.write(
        output=args.output,
        style=dict(args.style),
        animation_config=animation_config,
    )
    log("Finished writing DAG to the following output file: {0}".format(args.output))