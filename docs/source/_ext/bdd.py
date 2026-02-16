"""
Welcome to the hackiest part of this whole project. In here I utterly abuse
the sphinx.ext.autodoc package to achieve the unholy ends of displaying BDD
Features from test docstrings alongside autodocumenting regular code. This
functionality does not seem possible in the new event hook based design for
autodoc; the legacy class based technique allows enough room to hack out
any weird thing you want to do.
"""

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from sphinx.domains import Domain, Index
from docutils.statemachine import StringList
from sphinx.ext import autodoc


# Documenters to specify how BDD docstrings should be composed in the
#  intermediate document


class BDDDocumenterMixin:
    priority = 20
    bdddirectivetype = ""

    def add_directive_header(self, sig: str) -> None:
        if self.objpath[0].startswith("Test"):
            # override header to the bdd directives defined below
            self.add_line(f".. bdd:{self.bdddirectivetype}:: ", self.get_sourcename())
        else:
            super().add_directive_header(sig)

    def format_name(self) -> str:
        if self.objpath[0].startswith("Test"):
            # do not show the test name at all!
            return ""
        return super().format_name()

    def add_content(self, more_content: StringList | None) -> None:
        if self.objpath[0].startswith("Test"):
            # _generate adds a blank line to separate the header from the
            #   rest... we have to add stuff to the header so we must first
            #   remove the blank line.
            self.directive.result.pop()
        super().add_content(more_content)


class FeatureClassDocumenter(BDDDocumenterMixin, autodoc.ClassDocumenter):
    objtype = "class"
    bdddirectivetype = "feature"  # directive used in intermediate document


class ScenarioMethodDocumenter(BDDDocumenterMixin, autodoc.MethodDocumenter):
    objtype = "method"
    bdddirectivetype = "scenario"


# Directives to render the final document


class BDDElementMixin:
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


class BDDFeature(BDDElementMixin, Directive):
    required_arguments = 0
    has_content = True
    main_option = "feature"
    header_prefix = "Feature: "

    option_spec = {
        "feature": directives.unchanged_required,
        "module": directives.unchanged,
    }


class BDDScenario(BDDElementMixin, Directive):
    required_arguments = 0
    has_content = True
    main_option = "scenario"
    header_prefix = "Scenario: "

    option_spec = {
        "scenario": directives.unchanged_required,
        "module": directives.unchanged,
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
    app.add_autodocumenter(FeatureClassDocumenter)
    app.add_autodocumenter(ScenarioMethodDocumenter)

    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
