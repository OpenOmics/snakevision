"""Utility classes and helper functions for the snakevision package.

This module provides reusable support code shared across snakevision,
including ANSI terminal color definitions, standard error reporting helpers,
process-terminating error handling, and list-flattening utilities used for
normalizing parsed command-line arguments.
"""
# Python standard library
from datetime import datetime
import sys


# Helper classes and functions for snakevision.
class Colors:
    """Class encoding for ANSI escape sequeces for styling terminal text.
    Any string that is formatting with these styles must be terminated with
    the escape sequence, i.e. `Colors.end`.
    """

    # Escape sequence
    end = "\33[0m"
    # Formatting options
    bold = "\33[1m"
    italic = "\33[3m"
    url = "\33[4m"
    blink = "\33[5m"
    higlighted = "\33[7m"
    # Text Colors
    black = "\33[30m"
    red = "\33[31m"
    green = "\33[32m"
    yellow = "\33[33m"
    blue = "\33[34m"
    pink = "\33[35m"
    cyan = "\33[96m"
    white = "\33[37m"
    # Background fill colors
    bg_black = "\33[40m"
    bg_red = "\33[41m"
    bg_green = "\33[42m"
    bg_yellow = "\33[43m"
    bg_blue = "\33[44m"
    bg_pink = "\33[45m"
    bg_cyan = "\33[46m"
    bg_white = "\33[47m"


def err(*message, **kwargs):
    """Prints any provided args to standard error.
    kwargs can be provided to modify print functions
    behavior.
    @param message <any>:
        Values printed to standard error
    @params kwargs <print()>
        Key words to modify print function behavior
    """
    print(*message, file=sys.stderr, **kwargs)


def fatal(*message, **kwargs):
    """Prints any provided args to standard error
    and exits with an exit code of 1.
    @param message <any>:
        Values printed to standard error
    @params kwargs <print()>
        Key words to modify print function behavior
    """
    err(*message, **kwargs)
    sys.exit(1)


def timestamp(format="%Y-%m-%d %H:%M:%S"):
    """Returns a formatted timestamp string
    for the current time.
    @param format <str>:
        Format string for the timestamp, default:
        "%Y-%m-%d %H:%M:%S" which is equivalent to
        "2023-10-01 12:00:00" for example.
    @return <str>:
        Formatted timestamp string, i.e. "2023-10-01 12:00:00"
    """
    return datetime.now().strftime(format)


def log(*message):
    """Logs a message to standard output with a timestamp.
    @param message <any>:
        Values printed to log
    """
    print("[{0}] {1}".format(
        timestamp(),
        " ".join([str(m) for m in message]))
    )

def flatten(nested_list):
    """Flattens a nested list. This is used to flatten a nested list
    of parsed argparse arguments where there can be a 1:M relationship
    between a parameter and its provided values. This allows argparse
    options with 1:M relationships to be specified as via: `-x A -x B`
    or `-x A B` when the append action is used with nargs=+.
    @param nested_list <list[Any]>:
        Nested list to flatten, any encountered list elements will be
        flattened.
    @returns flattened_list <list[Any]>:
        Flattened list
    """
    flattened_list = []
    for v in nested_list:
        if isinstance(v, list):
            # Recursively flatten nested lists
            flattened_list.extend(flatten(v))
        else:
            flattened_list.append(v)
    return flattened_list
