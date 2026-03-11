"""Top-level package for snakevision.

This package provides tools for parsing Snakemake rule graphs, constructing
directed acyclic graph (DAG) representations, and rendering workflow
visualizations. The package exposes the `SnakeVision` class as its primary
public interface, along with other package metadata (such as the version).
"""
from .snakevision import SnakeVision
from .metadata import __version__


# Expose the SnakeVision class along
# with its version information
__all__ = ["SnakeVision", "__version__"]
