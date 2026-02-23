"""
A package for tracking inventory for small-scale electronics manufacturing.
It tracks parts, vendors, orders, inventories (the parts that you have
on-hand), projects across several versions (and their bills of materials,
including cost breakdowns), and finally provides clearance to build---indicating
that your inventory of parts is sufficient to complete the project build.
"""

from importlib.metadata import PackageNotFoundError, version

__title__ = "Django Clear To Build"
__author__ = "Paul Stiverson"
__license__ = "GNU Affero General Public License v3"
__copyright__ = "Copyright 2024 Paul Stiverson"

try:
    __version__ = version("django_ctb")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
