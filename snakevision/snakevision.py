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

    def __init__(self, input, dag=nx.DiGraph(), skip=[], verbose=False):
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
        return textwrap.dedent(
            """
            Class usage example:
            dag = SnakeVision('snakemake_rulegraph.txt')
            dag.write('/path/to/output/pipeline_dag.svg')
            """
        )

    def __str__(self):
        return self.verbose_dag

    def debug_dag(self):
        """Displays verbose information of the parsed rule graph."""
        _c = Colors
        self.verbose_dag = textwrap.dedent(
            """
            {3}{4}Node-to-label mappings:{5}
            • {0}

            {3}{4}Node to node relationship:{5}
            • {1}

            {3}{4}Order of encountered labels:{5}
            • {2}
            """.format(
                self.node2label, self.n2n, self.labels, _c.bold, _c.url, _c.end
            )
        )

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

    def write(self, output="snakevision_dag.svg", style={}):
        """Write DAG to output image."""
        # Create output directory as needed
        outdir = os.path.dirname(os.path.abspath(output))
        if not os.path.exists(outdir):
            # Pipeline output directory
            # does not exist on filesystem
            os.makedirs(outdir)
        # Apply a custom style if available
        custom_style = svg_renderer(StyleConfig(**style))
        # Write snakevision dag to SVG
        o = dagviz.render_svg(self.dag, style=custom_style)
        ## Write SVG to disk
        if os.path.exists(output): os.remove(output)
        with open(output, "wt") as fs:
            fs.write(o)
