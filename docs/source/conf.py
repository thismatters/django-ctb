# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys
from importlib.metadata import PackageNotFoundError, version as _version

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Django Clear To Build"
copyright = "2026, Paul Stiverson"
author = "Paul Stiverson"
try:
    release = _version("django_ctb")
except PackageNotFoundError:  # pragma: no cover
    release = "0.0.0"
version = release


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

# Make tests discoverable
sys.path.insert(0, os.path.abspath("./_ext"))
sys.path.insert(0, os.path.abspath("../.."))

extensions = [
    "sphinx.ext.autodoc",  # allows reading docstrings from codebase
    "sphinxcontrib_django",  # integrates django better
    "sphinxcontrib.images",
    "sphinxcontrib.plantuml",
    "bdd",  # custom documenters and directives for BDD features and scenarios
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]

# -- Options for sphinxcontrib-django ----------------------------------------

django_settings = "test_project.test_project.settings.base"

# -- Options for sphinxcontrib-plantuml ----------------------------------------

plantuml = os.environ.get("PLANTUML_COMMAND", "plantuml")
plantuml_output_format = "svg"
