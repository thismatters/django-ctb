from __future__ import annotations

import functools
import logging
import operator
import re
from typing import TYPE_CHECKING, Any

from docutils.statemachine import StringList
from sphinx.errors import PycodeError
from sphinx.ext.autodoc.importer import (
    import_object,
)
from sphinx.pycode import ModuleAnalyzer
from sphinx.util import inspect
from sphinx.util.docstrings import prepare_docstring
from sphinx.util.inspect import (
    getdoc,
    safe_getattr,
)

from .mock import ismock, mock, undecorate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from types import ModuleType

    from docutils.utils import Reporter
    from sphinx.config import Config
    from sphinx.environment import BuildEnvironment
    from sphinx.events import EventManager
    from sphinx.registry import SphinxComponentRegistry

logger = logging.getLogger(__name__)

INSTANCEATTR = object()

py_ext_sig_re = re.compile(
    r"""^ ([\w.]+::)?            # explicit module name
          ([\w.]+\.)?            # module and/or class name(s)
          (\w+)  \s*             # thing name
          (?: \[\s*(.*?)\s*])?   # optional: type parameters list
          (?: \((.*)\)           # optional: arguments
           (?:\s* -> \s* (.*))?  #           return annotation
          )? $                   # and nothing more
    """,
    re.VERBOSE,
)
special_member_re = re.compile(r"^__\S+__$")


def autodoc_attrgetter(
    obj: Any, name: str, *defargs: Any, registry: SphinxComponentRegistry
) -> Any:
    """Alternative getattr() for types"""
    for typ, func in registry.autodoc_attrgetters.items():
        if isinstance(obj, typ):
            return func(obj, name, *defargs)

    return safe_getattr(obj, name, *defargs)


class Options(dict[str, Any]):  # NoQA: FURB189
    """A dict/attribute hybrid that returns None on nonexisting keys."""

    def copy(self) -> Options:
        return Options(super().copy())

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name.replace("_", "-")]
        except KeyError:
            return None


class DocumenterBridge:
    """A parameters container for Documenters."""

    def __init__(
        self,
        env: BuildEnvironment,
        reporter: Reporter | None,
        options: Options,
        lineno: int | None,
        state: Any,
    ) -> None:
        self.env = env
        self._reporter = reporter
        self.genopt = options
        self.lineno = lineno
        self.record_dependencies: set[str] = set()
        self.result = StringList()
        self.state = state


class ObjectMember:
    """A member of object.

    This is used for the result of `Documenter.get_module_members()` to
    represent each member of the object.
    """

    __slots__ = "__name__", "object", "docstring", "class_", "skipped"

    __name__: str
    object: Any
    docstring: str | None
    class_: Any
    skipped: bool

    def __init__(
        self,
        name: str,
        obj: Any,
        *,
        docstring: str | None = None,
        class_: Any = None,
        skipped: bool = False,
    ) -> None:
        self.__name__ = name
        self.object = obj
        self.docstring = docstring
        self.class_ = class_
        self.skipped = skipped

    def __repr__(self) -> str:
        return (
            f"ObjectMember("
            f"name={self.__name__!r}, "
            f"obj={self.object!r}, "
            f"docstring={self.docstring!r}, "
            f"class_={self.class_!r}, "
            f"skipped={self.skipped!r}"
            f")"
        )


def unmangle(subject: Any, name: str) -> str | None:
    """Unmangle the given name."""
    try:
        if inspect.isclass(subject) and not name.endswith("__"):
            prefix = f"_{subject.__name__}__"
            if name.startswith(prefix):
                return name.replace(prefix, "__", 1)
            else:
                for cls in subject.__mro__:
                    prefix = f"_{cls.__name__}__"
                    if name.startswith(prefix):
                        # mangled attribute defined in parent class
                        return None
    except AttributeError:
        pass

    return name


def get_class_members(
    subject: Any,
    objpath: Any,
    attrgetter: Callable[..., Any],
    inherit_docstrings: bool = True,
) -> dict[str, ObjectMember]:
    """Get members and attributes of target class."""

    # the members directly defined in the class
    obj_dict = attrgetter(subject, "__dict__", {})

    members: dict[str, ObjectMember] = {}

    # other members
    for name in dir(subject):
        try:
            value = attrgetter(subject, name)
            if ismock(value):
                value = undecorate(value)

            unmangled = unmangle(subject, name)
            if unmangled and unmangled not in members:
                if name in obj_dict:
                    members[unmangled] = ObjectMember(unmangled, value, class_=subject)
                else:
                    members[unmangled] = ObjectMember(unmangled, value)
        except AttributeError:
            continue

    return members


class BDDDocumenter:
    bdddirectivetype = None
    has_content = True
    required_arguments = []
    optional_arguments = []
    priority = 10
    content_indent = "   "
    objtype = "object"

    def get_attr(self, obj: Any, name: str, *defargs: Any) -> Any:
        """getattr() override for types such as Zope interfaces."""
        return autodoc_attrgetter(obj, name, *defargs, registry=self.env._registry)

    def __init__(
        self, directive: DocumenterBridge, name: str, indent: str = ""
    ) -> None:
        self.directive = directive
        self.config: Config = directive.env.config
        self.env: BuildEnvironment = directive.env
        self._current_document = directive.env.current_document
        self._events: EventManager = directive.env.events
        self.options = directive.genopt
        self.name = name
        self.indent = indent
        # the module and object path within the module, and the fully
        # qualified name (all set after resolve_name succeeds)
        self.modname: str = ""
        self.module: ModuleType | None = None
        self.objpath: list[str] = []
        self.fullname = ""
        # extra signature items (arguments and return annotation,
        # also set after resolve_name succeeds)
        self.args: str | None = None
        self.retann: str = ""
        # the object to document (set after import_object succeeds)
        self.object: Any = None
        self.object_name = ""
        # the parent/owner of the object to document
        self.parent: Any = None
        # the module analyzer to get at attribute docs, or None
        self.analyzer: ModuleAnalyzer | None = None

    def parse_name(self) -> bool:
        """Determine what module to import and what attribute to document.

        Returns True and sets *self.modname*, *self.objpath*, *self.fullname*,
        *self.args* and *self.retann* if parsing and resolving was successful.
        """
        # first, parse the definition -- auto directives for classes and
        # functions can contain a signature which is then used instead of
        # an autogenerated one
        matched = py_ext_sig_re.match(self.name)
        if matched is None:
            logger.warning(
                "invalid signature for module (%r)",
                self.name,
            )
            return False
        explicit_modname, path, base, _tp_list, args, retann = matched.groups()

        # support explicit module and class name separation via ::
        if explicit_modname is not None:
            modname = explicit_modname[:-2]
            parents = path.rstrip(".").split(".") if path else []
        else:
            modname = None
            parents = []

        with mock(self.config.autodoc_mock_imports):
            modname, self.objpath = self.resolve_name(modname, parents, path, base)

        if not modname:
            return False

        self.modname = modname
        self.args = args
        self.retann = retann
        self.fullname = ".".join((self.modname or "", *self.objpath))
        return True

    def import_object(self, raiseerror: bool = False) -> bool:
        """Import the object given by *self.modname* and *self.objpath* and set
        it as *self.object*.

        Returns True if successful, False if an error occurred.
        """
        with mock(self.config.autodoc_mock_imports):
            try:
                ret = import_object(
                    self.modname, self.objpath, self.objtype, attrgetter=self.get_attr
                )
                self.module, self.parent, self.object_name, self.object = ret
                if ismock(self.object):
                    self.object = undecorate(self.object)
                return True
            except ImportError as exc:
                if raiseerror:
                    raise
                logger.warning(exc.args[0])
                self.env.note_reread()
                return False

    def get_real_modname(self) -> str:
        """Get the real module name of an object to document.

        It can differ from the name of the module through which the object was
        imported.
        """
        return self.get_attr(self.object, "__module__", None) or self.modname

    def generate(
        self,
        more_content: StringList | None = None,
        real_modname: str | None = None,
        check_module: bool = False,
    ) -> None:
        self.parse_name()
        # now, import the module and get object to document
        if not self.import_object():
            return
        self._generate()

    def check_module(self) -> bool:
        """Check if *self.object* is really defined in the module given by
        *self.modname*.
        """
        subject = inspect.unpartial(self.object)
        modname = self.get_attr(subject, "__module__", None)
        return not modname or modname == self.modname

    def _generate(
        self,
        more_content: StringList | None = None,
        real_modname: str | None = None,
        check_module: bool = False,
    ) -> None:
        # If there is no real module defined, figure out which to use.
        # The real module is used in the module analyzer to look up the module
        # where the attribute documentation would actually be found in.
        # This is used for situations where you have a module that collects the
        # functions and classes of internal submodules.
        guess_modname = self.get_real_modname()
        self.real_modname: str = real_modname or guess_modname

        # try to also get a source code analyzer for attribute docs
        try:
            self.analyzer = ModuleAnalyzer.for_module(self.real_modname)
            # parse right now, to get PycodeErrors on parsing (results will
            # be cached anyway)
            self.analyzer.find_attr_docs()
        except PycodeError as exc:
            logger.debug("[autodoc] module analyzer failed: %s", exc)
            # no source file -- e.g. for builtin and C modules
            self.analyzer = None
            # at least add the module.__file__ as a dependency
            if module___file__ := getattr(self.module, "__file__", ""):
                self.directive.record_dependencies.add(module___file__)
        else:
            self.directive.record_dependencies.add(self.analyzer.srcname)

        if self.real_modname != guess_modname:
            # Add module to dependency list if target object is defined in other module.
            try:
                analyzer = ModuleAnalyzer.for_module(guess_modname)
                self.directive.record_dependencies.add(analyzer.srcname)
            except PycodeError:
                pass

        docstrings: list[str] = functools.reduce(
            operator.iadd, self.get_doc() or [], []
        )
        if ismock(self.object) and not docstrings:
            logger.warning(
                "A mocked object is detected: %r",
                self.name,
            )

        # check __module__ of object (for members not given explicitly)
        if check_module:
            if not self.check_module():
                return

        sourcename = self.get_sourcename()

        # make sure that the result starts with an empty line.  This is
        # necessary for some situations where another directive preprocesses
        # reST and no starting newline is present
        self.add_line("", sourcename)

        if self.bdddirectivetype is not None:
            # generate the directive header
            self.add_line(f".. bdd:{self.bdddirectivetype}:: ", sourcename)
            # self.add_line("", sourcename)

            # e.g. the module directive doesn't have content
            self.indent += self.content_indent

        # add all content (from docstrings, attribute docs etc.)
        self.add_content()

        # document members, if possible
        self.document_members()

    def get_doc(self) -> list[list[str]] | None:
        """Decode and return lines of the docstring(s) for the object.

        When it returns None, autodoc-process-docstring will not be called for this
        object.
        """
        docstring = getdoc(
            self.object,
            self.get_attr,
            self.config.autodoc_inherit_docstrings,
            self.parent,
            self.object_name,
        )
        if docstring:
            tab_width = self.directive.state.document.settings.tab_width
            return [prepare_docstring(docstring, tab_width)]
        return []

    def process_doc(self, docstrings: list[list[str]]) -> Iterator[str]:
        """Let the user process the docstrings before adding them."""
        for docstringlines in docstrings:
            yield from docstringlines

    def get_sourcename(self) -> str:
        obj_module = inspect.safe_getattr(self.object, "__module__", None)
        obj_qualname = inspect.safe_getattr(self.object, "__qualname__", None)
        if obj_module and obj_qualname:
            # Get the correct location of docstring from self.object
            # to support inherited methods
            fullname = f"{self.object.__module__}.{self.object.__qualname__}"
        else:
            fullname = self.fullname

        if self.analyzer:
            return f"{self.analyzer.srcname}:docstring of {fullname}"
        else:
            return "docstring of %s" % fullname

    def add_content(self) -> None:
        """Add content from docstrings, attribute documentation and user."""
        docstring = True

        # set sourcename and add content from attribute documentation
        sourcename = self.get_sourcename()
        # add content from docstrings
        if docstring:
            docstrings = self.get_doc()
            if docstrings is None:
                # Do not call autodoc-process-docstring on get_doc() returns None.
                pass
            else:
                if not docstrings:
                    docstrings.append([])
                for i, line in enumerate(self.process_doc(docstrings)):
                    self.add_line(line, sourcename, i)

    def get_object_members(self) -> tuple[bool, list[ObjectMember]]:
        """Return `(members_check_module, members)` where `members` is a
        list of `(membername, member)` pairs of the members of *self.object*.

        If *want_all* is True, return all members.  Else, only return those
        members given by *self.options.members* (which may also be None).
        """
        msg = "must be implemented in subclasses"
        raise NotImplementedError(msg)

    def document_members(self) -> None:
        """Generate reST for member documentation.

        If *all_members* is True, document all members, else those given by
        *self.options.members*.
        """
        # set current namespace for finding members
        self._current_document.autodoc_module = self.modname
        if self.objpath:
            self._current_document.autodoc_class = self.objpath[0]

        # find out which members are documentable
        members_check_module, members = self.get_object_members()

        # document non-skipped members
        member_documenters: list[tuple[BDDDocumenter, bool]] = []
        for mname, member, isattr in self.filter_members(members):
            classes = [
                cls
                for cls in self.documenters.values()
                if cls.can_document_member(member, mname, isattr, self)
            ]
            if not classes:
                # don't know how to document this member
                continue
            # prefer the documenter with the highest priority
            classes.sort(key=lambda cls: cls.priority)
            # give explicitly separated module name, so that members
            # of inner classes can be documented
            full_mname = f"{self.modname}::" + ".".join((*self.objpath, mname))
            documenter = classes[-1](self.directive, full_mname, self.indent)
            member_documenters.append((documenter, isattr))

        # We now try to import all objects before ordering them. This is to
        # avoid possible circular imports if we were to import objects after
        # their associated documenters have been sorted.
        member_documenters = [
            (documenter, isattr)
            for documenter, isattr in member_documenters
            if documenter.parse_name() and documenter.import_object()
        ]

        for documenter, isattr in member_documenters:
            assert documenter.modname
            # We can directly call ._generate() since the documenters
            # already called parse_name() and import_object() before.
            #
            # Note that those two methods above do not emit events, so
            # whatever objects we deduced should not have changed.
            documenter._generate(
                real_modname=self.real_modname,
                check_module=members_check_module and not isattr,
            )

        # reset current objects
        self._current_document.autodoc_module = ""
        self._current_document.autodoc_class = ""

    def filter_members(
        self, members: list[ObjectMember]
    ) -> list[tuple[str, Any, bool]]:
        """Filter the given member list.

        Members are skipped if

        - they are private (except if given explicitly or the private-members
          option is set)
        - they are special methods (except if given explicitly or the
          special-members option is set)
        - they are undocumented (except if the undoc-members option is set)

        The user can override the skipping decision by connecting to the
        ``autodoc-skip-member`` event.
        """
        ret = []

        # search for members in source code too
        namespace = ".".join(self.objpath)  # will be empty for modules

        if self.analyzer:
            attr_docs = self.analyzer.find_attr_docs()
        else:
            attr_docs = {}

        # process members and determine which to skip
        for obj in members:
            membername = obj.__name__
            member = obj.object

            # if isattr is True, the member is documented as an attribute
            isattr = member is INSTANCEATTR or (namespace, membername) in attr_docs

            try:
                doc = getdoc(
                    member,
                    self.get_attr,
                    self.config.autodoc_inherit_docstrings,
                    self.object,
                    membername,
                )
                if not isinstance(doc, str):
                    # Ignore non-string __doc__
                    doc = None

                # if the member __doc__ is the same as self's __doc__, it's just
                # inherited and therefore not the member's doc
                cls = self.get_attr(member, "__class__", None)
                if cls:
                    cls_doc = self.get_attr(cls, "__doc__", None)
                    if cls_doc == doc:
                        doc = None

                if isinstance(obj, ObjectMember) and obj.docstring:
                    # hack for ClassDocumenter to inject docstring via ObjectMember
                    doc = obj.docstring

                has_doc = bool(doc)
                isprivate = membername.startswith("_")

                keep = False
                if ismock(member) and (namespace, membername) not in attr_docs:
                    # mocked module or object
                    pass
                elif special_member_re.match(membername):
                    # special __methods__
                    keep = False
                elif (namespace, membername) in attr_docs:
                    # PS: probably don't care about attr docs
                    keep = False
                elif isprivate:
                    keep = False
                else:
                    keep = has_doc

                if isinstance(obj, ObjectMember) and obj.skipped:
                    # forcedly skipped member (ex. a module attribute not defined in __all__)
                    keep = False
            except Exception as exc:
                logger.warning(
                    (
                        "autodoc: failed to determine %s.%s (%r) to be documented, "
                        "the following exception was raised:\n%s"
                    ),
                    self.name,
                    membername,
                    member,
                    exc,
                )
                keep = False

            if keep:
                ret.append((membername, member, isattr))

        return ret

    @property
    def documenters(self) -> dict[str, type[BDDDocumenter]]:
        """Returns registered BDDDocumenter classes"""
        return {}

    def add_line(self, line: str, source: str, *lineno: int) -> None:
        """Append one line of generated reST to the output."""
        if line.strip():  # not a blank line
            self.directive.result.append(self.indent + line, source, *lineno)
        else:
            self.directive.result.append("", source, *lineno)

    @classmethod
    def can_document_member(
        cls: type[BDDDocumenter],
        member: Any,
        membername: str,
        isattr: bool,
        parent: Any,
    ) -> bool:
        return False

    def resolve_name(
        self, modname: str | None, parents: Any, path: str, base: str
    ) -> tuple[str | None, list[str]]:
        """Resolve the module and name of the object to document given by the
        arguments and the current module/class.

        Must return a pair of the module name and a chain of attributes; for
        example, it would return ``('zipfile', ['ZipFile', 'open'])`` for the
        ``zipfile.ZipFile.open`` method.
        """
        msg = "must be implemented in subclasses"
        raise NotImplementedError(msg)


class ClassLevelDocumenter(BDDDocumenter):
    """Specialized Documenter subclass for objects on class level (methods,
    attributes).
    """

    def resolve_name(
        self, modname: str | None, parents: Any, path: str, base: str
    ) -> tuple[str | None, list[str]]:
        if modname is not None:
            return modname, [*parents, base]

        if path:
            mod_cls = path.rstrip(".")
        else:
            # if documenting a class-level object without path,
            # there must be a current class, either from a parent
            # auto directive ...
            mod_cls = self._current_document.autodoc_class
            # ... or from a class directive
            if not mod_cls:
                mod_cls = self.env.ref_context.get("bdd:class", "")
                # ... if still falsy, there's no way to know
                if not mod_cls:
                    return None, []
        modname, _sep, cls = mod_cls.rpartition(".")
        parents = [cls]
        # if the module name is still missing, get it like above
        if not modname:
            modname = self._current_document.autodoc_module
        if not modname:
            modname = self.env.ref_context.get("bdd:module")
        # ... else, it stays None, which means invalid
        return modname, [*parents, base]


class BDDMethodDocumenter(ClassLevelDocumenter):
    """Specialized Documenter subclass for methods (normal, static and class)."""

    objtype = "method"
    bdddirectivetype = "scenario"
    member_order = 50
    priority = 1  # must be more than FunctionDocumenter

    @classmethod
    def can_document_member(
        cls: type[BDDDocumenter],
        member: Any,
        membername: str,
        isattr: bool,
        parent: Any,
    ) -> bool:
        return inspect.isroutine(member) and not isinstance(parent, BDDModuleDocumenter)

    def import_object(self, raiseerror: bool = False) -> bool:
        ret = super().import_object(raiseerror)
        if not ret:
            return ret

        # to distinguish classmethod/staticmethod
        obj = self.parent.__dict__.get(self.object_name, self.object)
        if inspect.isstaticmethod(obj, cls=self.parent, name=self.object_name):
            # document static members before regular methods
            self.member_order -= 1  # type: ignore[misc]
        elif inspect.isclassmethod(obj):
            # document class methods before static methods as
            # they usually behave as alternative constructors
            self.member_order -= 2  # type: ignore[misc]
        return ret

    def document_members(self, all_members: bool = False) -> None:
        pass

    def get_doc(self) -> list[list[str]] | None:
        if self.objpath[-1] == "__init__":
            docstring = getdoc(
                self.object,
                self.get_attr,
                self.config.autodoc_inherit_docstrings,
                self.parent,
                self.object_name,
            )
            if docstring is not None and (
                docstring == object.__init__.__doc__  # for pypy
                or docstring.strip() == object.__init__.__doc__  # for !pypy
            ):
                docstring = None
            if docstring:
                tab_width = self.directive.state.document.settings.tab_width
                return [prepare_docstring(docstring, tabsize=tab_width)]
            else:
                return []
        elif self.objpath[-1] == "__new__":
            docstring = getdoc(
                self.object,
                self.get_attr,
                self.config.autodoc_inherit_docstrings,
                self.parent,
                self.object_name,
            )
            if docstring is not None and (
                docstring == object.__new__.__doc__  # for pypy
                or docstring.strip() == object.__new__.__doc__  # for !pypy
            ):
                docstring = None
            if docstring:
                tab_width = self.directive.state.document.settings.tab_width
                return [prepare_docstring(docstring, tabsize=tab_width)]
            else:
                return []
        else:
            return super().get_doc()


class ModuleLevelDocumenter(BDDDocumenter):
    """Specialized Documenter subclass for objects on module level (functions,
    classes, data/constants).
    """

    def resolve_name(
        self, modname: str | None, parents: Any, path: str, base: str
    ) -> tuple[str | None, list[str]]:
        if modname is not None:
            return modname, [*parents, base]
        if path:
            modname = path.rstrip(".")
            return modname, [*parents, base]

        # if documenting a toplevel object without explicit module,
        # it can be contained in another auto directive ...
        modname = self._current_document.autodoc_module
        # ... or in the scope of a module directive
        if not modname:
            modname = self.env.ref_context.get("bdd:module")
        # ... else, it stays None, which means invalid
        return modname, [*parents, base]


class BDDClassDocumenter(ModuleLevelDocumenter):
    """Specialized Documenter subclass for classes."""

    objtype = "class"
    bdddirectivetype = "feature"
    member_order = 20

    # Must be higher than FunctionDocumenter, ClassDocumenter, and
    # AttributeDocumenter as NewType can be an attribute and is a class
    # after Python 3.10.
    priority = 15

    _signature_class: Any = None
    _signature_method_name: str = ""

    @classmethod
    def can_document_member(
        cls: type[BDDDocumenter],
        member: Any,
        membername: str,
        isattr: bool,
        parent: Any,
    ) -> bool:
        return isinstance(member, type)

    def returns_false(self) -> tuple[bool, list[int]]:
        return False, []

    def get_object_members(self) -> tuple[bool, list[ObjectMember]]:
        members = get_class_members(
            self.object,
            self.objpath,
            self.get_attr,
            self.config.autodoc_inherit_docstrings,
        )
        return False, [m for m in members.values() if m.class_ == self.object]

    def get_doc(self) -> list[list[str]] | None:
        docstrings = []
        attrdocstring = getdoc(self.object, self.get_attr)
        if attrdocstring:
            docstrings.append(attrdocstring)

        tab_width = self.directive.state.document.settings.tab_width
        return [prepare_docstring(docstring, tab_width) for docstring in docstrings]

    def generate(
        self,
        more_content: StringList | None = None,
        real_modname: str | None = None,
        check_module: bool = False,
    ) -> None:
        # Do not pass real_modname and use the name from the __module__
        # attribute of the class.
        # If a class gets imported into the module real_modname
        # the analyzer won't find the source of the class, if
        # it looks in real_modname.
        return super().generate(
            more_content=more_content,
            check_module=check_module,
        )

    @property
    def documenters(self) -> dict[str, type[BDDDocumenter]]:
        """Returns registered BDDDocumenter classes"""
        return {"class": BDDMethodDocumenter}


class BDDModuleDocumenter(BDDDocumenter):
    objtype = "module"
    content_indent = ""
    bdddirectivetype = None
    _extra_indent = "   "

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.__all__: Sequence[str] | None = None

    def add_content(self) -> None:
        # module itself should not show docstring
        return
        # old_indent = self.indent
        # self.indent += self._extra_indent
        # super().add_content()
        # self.indent = old_indent

    def resolve_name(
        self, modname: str | None, parents: Any, path: str, base: str
    ) -> tuple[str | None, list[str]]:
        if modname is not None:
            logger.warning(
                ('"::" in automodule name doesn\'t make sense'),
            )
        return (path or "") + base, []

    def parse_name(self) -> bool:
        ret = super().parse_name()
        if self.args or self.retann:
            logger.warning(
                ("signature arguments or return annotation given for automodule %s"),
                self.fullname,
            )
        return ret

    def get_module_members(self) -> dict[str, ObjectMember]:
        """Get members of target module."""
        if self.analyzer:
            attr_docs = self.analyzer.attr_docs
        else:
            attr_docs = {}

        members: dict[str, ObjectMember] = {}
        for name in dir(self.object):
            try:
                value = safe_getattr(self.object, name, None)
                if ismock(value):
                    value = undecorate(value)
                docstring = attr_docs.get(("", name), [])
                members[name] = ObjectMember(
                    name, value, docstring="\n".join(docstring)
                )
            except AttributeError:
                continue

        # annotation only member (ex. attr: int)
        for name in inspect.getannotations(self.object):
            if name not in members:
                docstring = attr_docs.get(("", name), [])
                members[name] = ObjectMember(
                    name, INSTANCEATTR, docstring="\n".join(docstring)
                )

        return members

    def get_object_members(self) -> tuple[bool, list[ObjectMember]]:
        members = self.get_module_members()
        if self.__all__ is None:
            # for implicit module members, check __module__ to avoid
            # documenting imported objects
            return True, list(members.values())
        else:
            for member in members.values():
                if member.__name__ not in self.__all__:
                    member.skipped = True

            return False, list(members.values())

    def import_object(self, raiseerror: bool = False) -> bool:
        ret = super().import_object(raiseerror)

        try:
            self.__all__ = inspect.getall(self.object)
        except ValueError as exc:
            # invalid __all__ found.
            logger.warning(
                (
                    "__all__ should be a list of strings, not %r "
                    "(in module %s) -- ignoring __all__"
                ),
                exc.args[0],
                self.fullname,
            )

        return ret

    @property
    def documenters(self) -> dict[str, type[BDDDocumenter]]:
        """Returns registered BDDDocumenter classes"""
        return {"class": BDDClassDocumenter}
