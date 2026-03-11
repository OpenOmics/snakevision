"""Command-line entry point for the snakevision package.

This module is executed when running `python -m snakevision`. The `main()`
function from `cli.py` validates the Python version, parses command-line
arguments, normalizes selected multi-value CLI options, constructs a
`SnakeVision` DAG object from the provided Snakemake rule graph input,
and writes the rendered DAG to an output file.

This module is intended as an execution wrapper around the package's reusable
library components and is not the primary location for core parsing or graph
construction logic. Please see `snakevision.py` for the main implementation
of the `SnakeVision` class. This contains the core logic for parsing Snakemake
rule graph, building a DAG, and writing the resulting DAG as a snakevision
image.

To run the command-line interface, execute the following command in your terminal:
    $ python -m snakevision [OPTIONS] snakemake_rulegraph

For more information about available options and usage, run:
    $ python -m snakevision --help
"""
# Local relative imports
from .cli import main


# Main entry-point to the command-line interface
main()
