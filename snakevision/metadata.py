"""Package metadata and shared configuration constants for snakevision.

This module defines version information, author metadata, package identity,
runtime requirements, and other constants shared across the snakevision
package. Please do not forget to update the version number and other
relevant metadata when making changes to the package.
"""
# Python standard library
import os


# Important metadata and other constants
__authors__ = "Skyler Kuhn"
__home__ = os.path.dirname(os.path.abspath(__file__))
pkg_name = "snakevision"
pkg_description = "create an awesome snakemake dag!"
pkg_min_python = (3, 7)
