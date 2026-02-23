"""
Welcome to the hackiest part of this whole project. In here I utterly abuse
the sphinx.ext.autodoc package to achieve the unholy ends of displaying BDD
Features from test docstrings alongside autodocumenting regular code. This
functionality does not seem possible in the new event hook based design for
autodoc; the legacy class based technique allows enough room to hack out
any weird thing you want to do.

This module utilizes the patterns (and literal code as of version 9.1.0) of
the sphinx class-based approach.
"""

from __future__ import annotations

import logging

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.parsers.rst import directives as rst_directives
from sphinx.domains import Domain

from .directives import BDDModuleDirective

logger = logging.getLogger(__name__)

# Documenters to specify how BDD docstrings should be composed in the
#  intermediate document


# Directives to render the final document


class BDDDirective(Directive):
    main_option: str = "placeholder"
    header_prefix: str = "Placeholder: "

    def run(self):
        try:
            title_text = self.options[self.main_option]
        except KeyError:
            return []

        feature_node = nodes.section(ids=[nodes.make_id(title_text)])
        # feature_node["classes"].append("bdd-feature")

        if not title_text.startswith(self.header_prefix):
            title_text = f"{self.header_prefix}{title_text}"
        feature_node += nodes.title(text=title_text)

        # process the scenarios
        content_node = nodes.container()
        self.state.nested_parse(self.content, self.content_offset, content_node)
        feature_node += content_node

        return [feature_node]


class BDDFeature(BDDDirective):
    required_arguments = 0
    has_content = True
    main_option = "feature"
    header_prefix = "Feature: "

    option_spec = {
        "feature": rst_directives.unchanged_required,
        "module": rst_directives.unchanged,
    }


class BDDScenario(BDDDirective):
    required_arguments = 0
    has_content = True
    main_option = "scenario"
    header_prefix = "Scenario: "

    option_spec = {
        "scenario": rst_directives.unchanged_required,
        "module": rst_directives.unchanged,
    }


class BDDDomain(Domain):
    name = "bdd"
    label = "Behavior Driven Development"

    directives = {
        "feature": BDDFeature,
        "scenario": BDDScenario,
    }

    initial_data = {
        "features": [],
    }

    def get_objects(self):
        for obj in self.data["features"]:
            yield obj


def setup(app):
    app.add_domain(BDDDomain)
    app.add_directive("bddmodule", BDDModuleDirective)

    return {
        "version": "0.0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
