"""DG-FE-21 every list request of the frontend is one its route admits (04 API-C-09; dev-guide
§6.3 DG-LST-04; supervisor ruling R-67).

``api/lists.py::paginate`` answers 422 ``validation-failed`` (rule ``API-C-09``) for a ``sort`` key
the route's ``ListSpec`` does not list, for a ``-`` prefix on a key with a fixed direction, for a
query parameter that is not a filter of the resource, for a filter value outside its choices, for
``q`` on a list without search and for ``limit`` above 500. None of this is in the OpenAPI
document, so a page can pass every vitest and still fail to load (browser-QA finding Q-30,
``/settings/access-reviews``).

This test reads both sides:

- the API: every GET route and the ``ListSpec`` it paginates (``erev_api.api.v1``);
- the frontend: every ``fetchListPage(path, query, cursor, options)`` call under
  ``frontend/src`` and every call of a function that hands its own parameters on to one, the
  constants and path functions that build its path, the names and literal values of its query,
  its ``limit``, and every ``sortKey: "<key>"`` of a grid column.

A call or a sort key the test cannot tie to a route fails with the line to add. The annotations
are line comments in the TypeScript source (DG-FE-21):

- ``// API-C-09 list: GET /api/v1/<route>`` on a line above a call whose path is not a constant,
  a template or a path function (several routes: ``GET <a> | GET <b>``);
- ``// API-C-09 query: <key>, <key>=<value>|<value>`` on a line above a call whose query is built
  where this test cannot read it: the names it can send and the literal values it fixes;
- ``// API-C-09 sort keys: GET /api/v1/<route>`` above the columns of a grid, in a file that reads
  more than one sortable list: every ``sortKey`` below it, up to the next such line, is sent to
  that route.
"""

from __future__ import annotations

import re
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from erev_api.api import lists
from erev_api.config import Settings
from erev_api.controls.registry import REPOSITORY_ROOT
from erev_api.main import create_app
from fastapi.routing import iter_route_contexts

FRONTEND_SRC: Final = REPOSITORY_ROOT / "frontend" / "src"
RESERVED: Final = lists.RESERVED_PARAMETERS
LIST_NOTE: Final = "// API-C-09 list:"
QUERY_NOTE: Final = "// API-C-09 query:"
SORT_NOTE: Final = "// API-C-09 sort keys:"
HOLE: Final = "{}"
OPENERS: Final = {"(": ")", "[": "]", "{": "}"}
MAX_DEPTH: Final = 8


# ---- the API side --------------------------------------------------------------------------------


def _specs_reached(function: types.FunctionType, seen: set[types.FunctionType]) -> set[str]:
    """Names of the ``ListSpec`` globals a route function reaches through its module's functions."""
    if function in seen or len(seen) > 64:
        return set()
    seen.add(function)
    module = function.__globals__
    found: set[str] = set()
    codes = [function.__code__]
    while codes:
        code = codes.pop()
        codes.extend(const for const in code.co_consts if isinstance(const, types.CodeType))
        for name in code.co_names:
            value = module.get(name)
            if isinstance(value, lists.ListSpec):
                found.add(name)
            elif isinstance(value, types.FunctionType) and value.__module__ == function.__module__:
                found |= _specs_reached(value, seen)
    return found


def get_routes(settings: Settings) -> dict[str, lists.ListSpec | None]:
    """``{route path with {} holes: its ListSpec, or None}`` of every GET route of the API. A route
    that paginates exactly one ``ListSpec`` is a list route; any other answers without ``paginate``
    and ignores the list parameters ``fetchListPage`` adds."""
    found: dict[str, lists.ListSpec | None] = {}
    for route in iter_route_contexts(create_app(settings).routes):
        endpoint = getattr(route, "endpoint", None)
        if "GET" not in (route.methods or ()) or not isinstance(endpoint, types.FunctionType):
            continue
        names = _specs_reached(endpoint, set())
        spec = endpoint.__globals__[next(iter(names))] if len(names) == 1 else None
        found[re.sub(r"\{[^/]+\}", HOLE, route.path or "")] = spec
    return found


# ---- reading TypeScript --------------------------------------------------------------------------


def _skip_string(text: str, start: int) -> int:
    """The index after the string or template literal that opens at ``start``."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
        elif char == quote:
            return index + 1
        elif quote == "`" and text.startswith("${", index):
            index = _close(text, index + 1)
        else:
            index += 1
    return index


def _skip_comment(text: str, index: int) -> int | None:
    """The index after the comment that opens at ``index``, if one opens there."""
    if text.startswith("//", index):
        end = text.find("\n", index)
        return len(text) if end < 0 else end
    if text.startswith("/*", index):
        end = text.find("*/", index)
        return len(text) if end < 0 else end + 2
    return None


def _close(text: str, start: int) -> int:
    """The index after the bracket that closes the opener at ``start``."""
    closer = OPENERS[text[start]]
    index = start + 1
    while index < len(text):
        char = text[index]
        after = _skip_comment(text, index)
        if after is not None:
            index = after
        elif char in "\"'`":
            index = _skip_string(text, index)
        elif char in OPENERS:
            index = _close(text, index)
        elif char == closer:
            return index + 1
        else:
            index += 1
    return index


def _split(text: str, separator: str = ",") -> list[str]:
    """``text`` split at top-level separators, outside brackets and strings."""
    parts: list[str] = []
    start = index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            index = _skip_string(text, index)
        elif char in OPENERS:
            index = _close(text, index)
        elif char == separator:
            parts.append(text[start:index])
            start = index = index + 1
        else:
            index += 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _statement_end(code: str, start: int) -> int:
    index = start
    while index < len(code):
        char = code[index]
        if char in "\"'`":
            index = _skip_string(code, index)
        elif char in OPENERS:
            index = _close(code, index)
        elif char == ";":
            return index
        else:
            index += 1
    return index


def _uncommented(text: str) -> str:
    """``text`` with comments blanked, offsets and line numbers kept."""
    out = list(text)
    index = 0
    while index < len(text):
        after = _skip_comment(text, index)
        if after is not None:
            out[index:after] = [" " if char != "\n" else "\n" for char in text[index:after]]
            index = after
        elif text[index] in "\"'`":
            index = _skip_string(text, index)
        else:
            index += 1
    return "".join(out)


@dataclass(frozen=True, slots=True)
class Source:
    path: Path
    text: str
    code: str  # the text with comments blanked

    @classmethod
    def of(cls, path: Path, text: str) -> Source:
        return cls(path, text, _uncommented(text))

    @property
    def name(self) -> str:
        root = REPOSITORY_ROOT
        return str(self.path.relative_to(root) if self.path.is_relative_to(root) else self.path)

    def line(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1

    def notes_above(self, offset: int, prefix: str) -> list[str]:
        """The ``prefix`` comments on the lines above the statement that holds ``offset``."""
        found: list[str] = []
        code_lines = 0
        for line in reversed(self.text[:offset].split("\n")[:-1]):
            stripped = line.strip()
            if stripped.startswith(prefix):
                found.append(stripped[len(prefix) :].strip())
            elif not stripped.startswith("//"):
                # The statement that holds the call may open a few lines above it.
                code_lines += 1
                if code_lines > 6 or stripped == "" or stripped.endswith(("}", ";")):
                    break
        return found


def sources() -> list[Source]:
    found: list[Source] = []
    for path in sorted(FRONTEND_SRC.rglob("*.ts*")):
        skipped = (
            path.suffix not in {".ts", ".tsx"}
            or ".test." in path.name
            or path.name.endswith(".d.ts")
            or path.is_relative_to(FRONTEND_SRC / "test")
        )
        if not skipped:
            found.append(Source.of(path, path.read_text(encoding="utf-8")))
    return found


CONSTANT: Final = re.compile(r"^(?:export )?const (\w+)(?::[^=\n]+)? =\s*", re.MULTILINE)
FUNCTION: Final = re.compile(
    r"^(?:export )?(?:async )?function (\w+)\s*(?:<[^>(]*>)?\(", re.MULTILINE
)
IMPORT: Final = re.compile(
    r"^import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+\"(\.[^\"]*)\";", re.MULTILINE
)
STRING: Final = re.compile(r"^\"((?:[^\"\\]|\\.)*)\"$")
LITERALS: Final = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")
IDENTIFIER: Final = re.compile(r"[A-Za-z_$][\w$]*")
WORDS: Final = frozenset({"null", "undefined", "true", "false", "String", "length"})


@dataclass(slots=True)
class Module:
    """One source file: its module-level constants and functions and the names it imports."""

    source: Source
    constants: dict[str, str] = field(default_factory=dict)  # name → initializer text
    functions: dict[str, tuple[int, int]] = field(default_factory=dict)  # name → body span
    parameters: dict[str, tuple[str, ...]] = field(default_factory=dict)  # name → parameter names
    imports: dict[str, tuple[Path, str]] = field(default_factory=dict)  # local name → (file, name)

    @property
    def path(self) -> Path:
        return self.source.path.resolve()

    def enclosing(self, offset: int) -> tuple[str | None, int, int]:
        for name, (start, end) in self.functions.items():
            if start <= offset < end:
                return name, start, end
        return None, 0, len(self.source.code)


@dataclass(slots=True)
class Program:
    """The modules of the frontend, and what a name means where it is used."""

    modules: dict[Path, Module] = field(default_factory=dict)

    @classmethod
    def read(cls, files: Sequence[Source]) -> Program:
        program = cls()
        for source in files:
            module = Module(source)
            code = source.code
            for match in CONSTANT.finditer(code):
                end = _statement_end(code, match.end())
                module.constants[match.group(1)] = code[match.end() : end].strip()
            for match in FUNCTION.finditer(code):
                signature_end = _close(code, match.end() - 1)
                body_start = code.find("{", signature_end)
                if body_start < 0:
                    continue
                module.functions[match.group(1)] = (body_start, _close(code, body_start))
                names = [
                    IDENTIFIER.match(item.lstrip("."))
                    for item in _split(code[match.end() : signature_end - 1])
                ]
                module.parameters[match.group(1)] = tuple(
                    name.group(0) if name else "" for name in names
                )
            for match in IMPORT.finditer(code):
                target = (source.path.parent / match.group(2)).resolve()
                for item in match.group(1).split(","):
                    names_of = item.replace("type ", "").split(" as ")
                    if names_of[0].strip():
                        module.imports[names_of[-1].strip()] = (target, names_of[0].strip())
            program.modules[module.path] = module
        return program

    def resolve(self, module: Module, name: str, depth: int = 0) -> tuple[Module, str] | None:
        """The module that declares ``name`` as a constant or a function, through imports."""
        if name in module.constants or name in module.functions:
            return module, name
        imported = module.imports.get(name)
        if imported is None or depth > MAX_DEPTH:
            return None
        base, exported = imported
        for candidate in (
            Path(f"{base}.ts"),
            Path(f"{base}.tsx"),
            base / "index.ts",
            base / "index.tsx",
        ):
            target = self.modules.get(candidate)
            if target is not None:
                return self.resolve(target, exported, depth + 1)
        return None

    def constant(self, module: Module, name: str) -> tuple[Module, str] | None:
        found = self.resolve(module, name)
        if found is None or found[1] not in found[0].constants:
            return None
        return found[0], found[0].constants[found[1]]

    def function(self, module: Module, name: str) -> tuple[Module, int, int] | None:
        found = self.resolve(module, name)
        if found is None or found[1] not in found[0].functions:
            return None
        return (found[0], *found[0].functions[found[1]])

    def local_name(self, module: Module, owner: Path, name: str) -> str | None:
        """The name ``module`` uses for the function ``name`` declared in ``owner``."""
        for local in sorted({*module.imports, *module.functions}):
            target = self.resolve(module, local)
            if target is not None and target[0].path == owner and target[1] == name:
                return local
        return None

    def strings_of(self, module: Module, name: str, depth: int = 0) -> tuple[str, ...] | None:
        """The string, or the strings of the array, a constant holds."""
        found = self.constant(module, name)
        if found is None or depth > MAX_DEPTH:
            return None
        owner, value = found
        value = value.removesuffix("as const").strip()
        text = self.text_of(owner, value, depth + 1)
        if text is not None and HOLE not in text:
            return (text,)
        if _is_object(value):
            # A lookup table of literals, as in ``SORT_KEYS[query.sort]``: every value it holds.
            entries, spreads = _object_entries(value)
            literals = [STRING.match(item or "") for _, item in entries]
            if spreads or not all(literals):
                return None
            return tuple(literal.group(1) for literal in literals if literal)
        if not (value.startswith("[") and _close(value, 0) == len(value)):
            return None
        items: list[str] = []
        for item in _split(value[1:-1]):
            literal = STRING.match(item)
            more = (literal.group(1),) if literal else self.strings_of(owner, item, depth + 1)
            if more is None:
                return None
            items.extend(more)
        return tuple(items)

    def text_of(self, module: Module, expression: str, depth: int = 0) -> str | None:
        """The string an expression builds, with ``{}`` for what only the caller knows."""
        expression = expression.strip()
        if depth > MAX_DEPTH:
            return None
        string = STRING.match(expression)
        if string:
            return string.group(1)
        if IDENTIFIER.fullmatch(expression):
            found = self.constant(module, expression)
            return None if found is None else self.text_of(found[0], found[1], depth + 1)
        if expression.startswith("`") and _skip_string(expression, 0) == len(expression):
            return self._template(module, expression, depth)
        call = re.match(r"^(\w+)\(", expression)
        if call and _close(expression, call.end() - 1) == len(expression):
            target = self.function(module, call.group(1))
            if target is not None:
                owner, start, end = target
                returns = re.findall(r"\breturn\s+([^;]+);", owner.source.code[start:end])
                if len(returns) == 1:
                    return self.text_of(owner, returns[0], depth + 1)
        return None

    def _template(self, module: Module, expression: str, depth: int) -> str:
        out: list[str] = []
        index = 1
        while index < len(expression) - 1:
            if expression.startswith("${", index):
                end = _close(expression, index + 1)
                inner = self.text_of(module, expression[index + 2 : end - 1], depth + 1)
                out.append(HOLE if inner is None else inner)
                index = end
            else:
                out.append(expression[index])
                index += 1
        return "".join(out)


# ---- the frontend side ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    values: tuple[str, ...]  # the literal values the code fixes
    dynamic: bool  # part of the value is only known at run time


@dataclass(frozen=True, slots=True)
class ListCall:
    source: Source
    offset: int
    routes: tuple[str, ...]  # route paths with {} holes; empty when the path could not be tied
    path_text: str
    parameters: tuple[Parameter, ...]
    open_query: str | None  # the part of the query the test could not read
    limit: int | None
    function: str | None  # the module-level function that holds the call

    @property
    def where(self) -> str:
        return f"{self.source.name}:{self.source.line(self.offset)}"


@dataclass(frozen=True, slots=True)
class Fetcher:
    """A function that sends one list request: ``fetchListPage`` itself, or a function that hands
    its own parameters on to one (``fetchAll(path, query)``, ``fetchAccountsPage(query, …)``)."""

    owner: Path | None  # the module that declares it; None for fetchListPage
    name: str
    path: int | str  # the position of the path argument, or the path expression it fixes
    query: tuple[int | str, ...]  # positions of query arguments and query expressions it fixes
    limit: int | None
    module: Module | None  # where its fixed expressions are read


def _routes_of_note(note: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\{[^/]+\}", HOLE, part.strip().removeprefix("GET").strip())
        for part in note.split("|")
        if part.strip()
    )


def _object_entries(text: str) -> tuple[list[tuple[str, str | None]], list[str]]:
    """``(name, value or None for shorthand)`` of an object literal and its spread expressions."""
    entries: list[tuple[str, str | None]] = []
    spreads: list[str] = []
    for part in _split(text.strip()[1:-1]):
        if part.startswith("..."):
            spreads.append(part[3:].strip())
            continue
        pieces = _split(part, ":")
        name = pieces[0].strip().strip("\"'")
        entries.append((name, part[part.index(":") + 1 :].strip() if len(pieces) > 1 else None))
    return entries, spreads


def _is_object(expression: str) -> bool:
    return expression.startswith("{") and _close(expression, 0) == len(expression)


def _parameter(program: Program, module: Module, name: str, value: str | None) -> Parameter:
    if value is None:
        return Parameter(name, (), dynamic=True)
    literals = list(LITERALS.findall(value))
    dynamic = False
    for word in IDENTIFIER.findall(LITERALS.sub(" ", value)):
        fixed = program.strings_of(module, word)
        if fixed is not None:
            literals.extend(fixed)
        elif word not in WORDS:
            dynamic = True
    literals.extend(word for word in ("true", "false") if re.search(rf"\b{word}\b", value))
    return Parameter(name, tuple(dict.fromkeys(literals)), dynamic)


def _query(
    program: Program, module: Module, expression: str, scope: tuple[int, int], depth: int = 0
) -> tuple[list[Parameter], str | None]:
    """The parameters of a query expression; the second member names what could not be read."""
    expression = expression.strip()
    found: list[Parameter] = []
    unread: str | None = None
    if _is_object(expression):
        entries, spreads = _object_entries(expression)
        found = [_parameter(program, module, name, value) for name, value in entries]
        branches = [(module, spread, scope) for spread in spreads]
    else:
        stands_for = None if depth > MAX_DEPTH else _stands_for(program, module, expression, scope)
        if stands_for is None:
            return [], expression
        branches = stands_for
    for owner, text, inner in branches:
        more, missing = _query(program, owner, text, inner, depth + 1)
        found.extend(more)
        unread = unread or missing
    return found, unread


def _stands_for(
    program: Program, module: Module, expression: str, scope: tuple[int, int]
) -> list[tuple[Module, str, tuple[int, int]]] | None:
    """The expressions a query expression stands for: the arms of a conditional, the returns of
    a called function, or the initializer of a variable."""
    conditional = _split(expression, "?")
    if len(conditional) == 2 and len(_split(conditional[1], ":")) == 2:
        return [(module, arm, scope) for arm in _split(conditional[1], ":")]
    call = re.match(r"^(\w+)\(", expression)
    if call and _close(expression, call.end() - 1) == len(expression):
        target = program.function(module, call.group(1))
        if target is None:
            return None
        owner, start, end = target
        body = owner.source.code[start:end]
        returns = [
            body[item.end() : _statement_end(body, item.end())]
            for item in re.finditer(r"\breturn\s+", body)
        ]
        return [(owner, value, (start, end)) for value in returns] or None
    if IDENTIFIER.fullmatch(expression):
        body = module.source.code[scope[0] : scope[1]]
        declared = re.search(rf"\b(?:const|let) {re.escape(expression)}(?::[^=]+)? =\s*", body)
        if declared:
            value = body[declared.end() : _statement_end(body, declared.end())]
            return [(module, value, scope)]
        constant = program.constant(module, expression)
        if constant is not None:
            return [(constant[0], constant[1], (0, 0))]
    return None


def _noted_query(note: str) -> list[Parameter]:
    found: list[Parameter] = []
    for part in note.split(","):
        name, _, values = part.strip().partition("=")
        if name:
            fixed = tuple(item.strip() for item in values.split("|") if item.strip())
            found.append(Parameter(name.strip(), fixed, dynamic=not fixed))
    return found


def _limit(program: Program, module: Module, options: str | None) -> int | None:
    sized = re.search(r"\blimit:\s*(\w+)", options or "")
    if sized is None:
        return None
    constant = program.constant(module, sized.group(1))
    raw = (constant[1] if constant else sized.group(1)).replace("_", "")
    return int(raw) if raw.isdigit() else None


def _handed_on(expression: str, names: Sequence[str]) -> list[int]:
    """The parameter positions a query expression hands on: ``query`` or ``{ ...query, sort }``."""
    expression = expression.strip()
    if expression in names:
        return [names.index(expression)]
    if _is_object(expression):
        _, spreads = _object_entries(expression)
        return [names.index(item) for item in spreads if item in names]
    return []


def _beside_spread(expression: str, names: Sequence[str]) -> str:
    """An object literal without the spreads of the holding function's own parameters."""
    entries, spreads = _object_entries(expression)
    kept = [f"...{item}" for item in spreads if item not in names]
    kept += [name if value is None else f"{name}: {value}" for name, value in entries]
    return "{ " + ", ".join(kept) + " }"


def _call_site(
    program: Program,
    routes: Mapping[str, object],
    fetcher: Fetcher,
    module: Module,
    offset: int,
    arguments: Sequence[str],
) -> Fetcher | ListCall | None:
    """One call of a fetcher: a list request, or, when the holding function hands its own
    parameters on as the path or the query, a fetcher of its own."""
    source = module.source
    function, start, stop = module.enclosing(offset)
    names = module.parameters.get(function, ()) if function is not None else ()
    if isinstance(fetcher.path, int):
        if fetcher.path >= len(arguments):
            return None
        path_module, path_expression = module, arguments[fetcher.path].strip()
    elif fetcher.module is not None:
        path_module, path_expression = fetcher.module, fetcher.path
    else:
        return None
    queries: list[tuple[Module, str]] = []
    for item in fetcher.query:
        if isinstance(item, int):
            if item < len(arguments):
                queries.append((module, arguments[item]))
        elif fetcher.module is not None:
            queries.append((fetcher.module, item))
    limit = fetcher.limit
    if fetcher.owner is None:
        limit = _limit(program, module, arguments[3] if len(arguments) > 3 else None)

    path_handed = path_module is module and path_expression in names
    query_handed = any(where is module and _handed_on(text, names) for where, text in queries)
    if function is not None and (path_handed or query_handed):
        parts: list[int | str] = []
        for where, text in queries:
            positions = _handed_on(text, names) if where is module else []
            parts.extend(positions)
            if not positions:
                parts.append(text)
            elif text.strip() not in names:
                parts.append(_beside_spread(text, names))
        return Fetcher(
            owner=module.path,
            name=function,
            path=names.index(path_expression) if path_handed else path_expression,
            query=tuple(parts),
            limit=limit,
            module=module,
        )

    path_text = program.text_of(path_module, path_expression)
    tied = tuple(
        route for note in source.notes_above(offset, LIST_NOTE) for route in _routes_of_note(note)
    )
    if not tied and path_text is not None and path_text in routes:
        tied = (path_text,)
    parameters: list[Parameter] = []
    unread: str | None = None
    notes = source.notes_above(offset, QUERY_NOTE)
    if notes:
        parameters = [item for note in notes for item in _noted_query(note)]
    else:
        for where, text in queries:
            scope = (start, stop) if where is module else (0, 0)
            more, missing = _query(program, where, text, scope)
            parameters.extend(more)
            unread = unread or missing
    return ListCall(
        source=source,
        offset=offset,
        routes=tied,
        path_text=path_text if path_text is not None else path_expression,
        parameters=tuple(parameters),
        open_query=unread,
        limit=limit,
        function=function,
    )


def list_calls(
    program: Program, files: Sequence[Source], routes: Mapping[str, object]
) -> list[ListCall]:
    """Every list request: a call of ``fetchListPage``, or of a function that wraps it, whose path
    and query do not come from the parameters of the function that holds the call."""
    found: list[ListCall] = []
    pending = [Fetcher(None, "fetchListPage", 0, (1,), None, None)]
    seen: set[tuple[Path | None, str]] = set()
    while pending:
        fetcher = pending.pop()
        if (fetcher.owner, fetcher.name) in seen:
            continue
        seen.add((fetcher.owner, fetcher.name))
        for source in files:
            module = program.modules[source.path.resolve()]
            called = (
                fetcher.name
                if fetcher.owner is None
                else program.local_name(module, fetcher.owner, fetcher.name)
            )
            if called is None:
                continue
            pattern = rf"(?<!function )\b{re.escape(called)}\s*(?:<[^>(]*>)?\("
            for match in re.finditer(pattern, source.code):
                end = _close(source.code, match.end() - 1)
                arguments = _split(source.code[match.end() : end - 1])
                site = _call_site(program, routes, fetcher, module, match.start(), arguments)
                if isinstance(site, Fetcher):
                    pending.append(site)
                elif site is not None:
                    found.append(site)
    return sorted(found, key=lambda call: (call.source.name, call.offset))


@dataclass(frozen=True, slots=True)
class SortKey:
    source: Source
    offset: int
    key: str
    routes: tuple[str, ...]
    candidates: tuple[str, ...]

    @property
    def where(self) -> str:
        return f"{self.source.name}:{self.source.line(self.offset)}"


def sort_keys(
    program: Program, files: Sequence[Source], calls: Sequence[ListCall]
) -> list[SortKey]:
    """Every ``sortKey: "<key>"`` with the route its grid reads: the noted one, else the one
    sortable list whose fetch function the file imports or declares."""
    fetchers: dict[tuple[Path, str], set[str]] = {}
    for call in calls:
        sortable = any(item.name == "sort" and item.dynamic for item in call.parameters)
        if call.function is not None and sortable:
            fetchers.setdefault((call.source.path.resolve(), call.function), set()).update(
                call.routes
            )
    found: list[SortKey] = []
    for source in files:
        keys = list(re.finditer(r"\bsortKey:\s*\"([^\"]+)\"", source.code))
        if not keys:
            continue
        module = program.modules[source.path.resolve()]
        named: set[str] = set()
        for name in {*module.imports, *module.functions}:
            resolved = program.resolve(module, name)
            if resolved is not None:
                named |= fetchers.get((resolved[0].path, resolved[1]), set())
        candidates = tuple(sorted(named))
        notes = [
            (match.start(), _routes_of_note(match.group(1)))
            for match in re.finditer(
                rf"^[ \t]*{re.escape(SORT_NOTE)}(.*)$", source.text, re.MULTILINE
            )
        ]
        for key in keys:
            above = [tied for offset, tied in notes if offset < key.start()]
            tied = above[-1] if above else (candidates if len(candidates) == 1 else ())
            found.append(SortKey(source, key.start(), key.group(1), tied, candidates))
    return found


# ---- the comparison ------------------------------------------------------------------------------


def _sort_problem(spec: lists.ListSpec, value: str) -> str | None:
    key = value.removeprefix("-")
    if key not in spec.sort_keys:
        admitted = ", ".join(sorted(spec.sort_keys))
        return (
            f"sort {value!r} is not a sort key of {spec.resource} "
            f"(admits {admitted}; default {spec.default_sort})"
        )
    if key in spec.directions and value != key:
        return f"sort {value!r}: {key} has a fixed direction and takes no leading -"
    return None


def _parameter_problems(spec: lists.ListSpec, parameter: Parameter) -> list[str]:
    name = parameter.name
    if name == "sort":
        found = [_sort_problem(spec, value) for value in parameter.values]
        return [problem for problem in found if problem is not None]
    if name == "q":
        return [] if spec.search_columns else [f"q is sent and {spec.resource} has no search"]
    if name in RESERVED or name in spec.custom_filters:
        return []
    if name not in spec.filters:
        admitted = ", ".join(sorted({*spec.filters, *spec.custom_filters})) or "none"
        return [f"{name} is not a filter of {spec.resource} (filters: {admitted})"]
    choices = spec.filters[name].choices
    if choices is None:
        return []
    admitted = ", ".join(sorted(choices))
    return [
        f"{name}={value} is not one of {admitted}"
        for value in parameter.values
        if value not in choices
    ]


def call_problems(call: ListCall, routes: Mapping[str, lists.ListSpec | None]) -> list[str]:
    problems: list[str] = []
    for route in call.routes:
        if route not in routes:
            problems.append(f"{call.where} GET {route} is not a route of the API")
            continue
        spec = routes[route]
        if spec is None:
            # Not a paginated list: the route reads its own parameters and ignores the list ones.
            continue
        for parameter in call.parameters:
            problems.extend(
                f"{call.where} GET {route}: {problem}"
                for problem in _parameter_problems(spec, parameter)
            )
        if call.limit is not None and not 1 <= call.limit <= lists.MAX_LIMIT:
            problems.append(
                f"{call.where} GET {route}: limit {call.limit} is outside 1 to {lists.MAX_LIMIT}"
            )
    return problems


def untied(calls: Sequence[ListCall], keys: Sequence[SortKey]) -> list[str]:
    """What the test cannot tie to a route, each with the line to add."""
    found: list[str] = []
    for call in calls:
        if not call.routes:
            found.append(
                f"{call.where} fetchListPage({call.path_text}, …): the path is not a constant, a "
                f"template or a path function of an API route; add above the call: "
                f"{LIST_NOTE} GET /api/v1/<route>"
            )
        if call.open_query is not None:
            found.append(
                f"{call.where} fetchListPage(…, {call.open_query}, …): the query is built where "
                f"this test cannot read it; add above the call: "
                f"{QUERY_NOTE} <key>, <key>=<value>|<value>"
            )
    for key in keys:
        if not key.routes:
            candidates = " | ".join(f"GET {route}" for route in key.candidates)
            found.append(
                f'{key.where} sortKey "{key.key}": the file reads {len(key.candidates)} sortable '
                f"lists; add above the columns of this grid: "
                f"{SORT_NOTE} {candidates or 'GET /api/v1/<route>'}"
            )
    return found


@dataclass(frozen=True, slots=True)
class Reading:
    routes: Mapping[str, lists.ListSpec | None]
    calls: Sequence[ListCall]
    keys: Sequence[SortKey]


def read(routes: Mapping[str, lists.ListSpec | None], files: Sequence[Source]) -> Reading:
    program = Program.read(files)
    calls = list_calls(program, files, routes)
    return Reading(routes, calls, sort_keys(program, files, calls))


def problems(reading: Reading) -> list[str]:
    found: list[str] = []
    for call in reading.calls:
        found.extend(call_problems(call, reading.routes))
    for key in reading.keys:
        for route in key.routes:
            spec = reading.routes.get(route)
            if spec is None:
                found.append(f"{key.where} GET {route} is not a list route of the API")
                continue
            # A grid header cycles ascending, descending, unsorted: both values reach the route.
            for value in (key.key, f"-{key.key}"):
                problem = _sort_problem(spec, value)
                if problem:
                    found.append(f"{key.where} GET {route}: sortKey {problem}")
                    break
    return sorted(set(found))


def test_dg_fe_21_every_list_request_is_admitted_by_its_route(app_settings: Settings) -> None:
    assert problems(read(get_routes(app_settings), sources())) == []


def test_dg_fe_21_every_list_request_is_tied_to_a_route(app_settings: Settings) -> None:
    reading = read(get_routes(app_settings), sources())
    assert untied(reading.calls, reading.keys) == []


def test_dg_fe_21_the_reader_sees_both_sides(app_settings: Settings) -> None:
    """A rename of ``fetchListPage``, of ``sortKey`` or of ``ListSpec`` must not empty the check."""
    reading = read(get_routes(app_settings), sources())
    assert len(reading.calls) > 100
    assert len(reading.keys) > 40
    assert sum(spec is not None for spec in reading.routes.values()) > 80
    reviews = [call for call in reading.calls if call.routes == ("/api/v1/access-reviews",)]
    assert [sorted(item.name for item in call.parameters) for call in reviews] == [
        ["sort", "status"]
    ]


# ---- the reader against sources that exist only in this test ------------------------------------

QUERIES: Final = """
import { fetchListPage } from "../lists";
export const WIDGETS_PATH = "/api/v1/access-reviews";
export const DEFAULT_SORT = "-created_at";
export function itemsPath(id: string): string {
  return `${WIDGETS_PATH}/${id}/items`;
}
export function fetchWidgetsPage(query: Query, cursor: string | null, sort: string | null) {
  const found = { status: query.status, owner: "me", sort: sort ?? DEFAULT_SORT };
  return fetchListPage(WIDGETS_PATH, found, cursor);
}
async function fetchAll(path: string, query: Record<string, string>) {
  return fetchListPage(path, query, null, { limit: 900, count: false });
}
export function fetchItems(id: string) {
  return fetchAll(itemsPath(id), { q: "x" });
}
export function fetchOpaque(holder: Holder) {
  return fetchAll(holder.path, build());
}
export function fetchNoted(holder: Holder) {
  // API-C-09 list: GET /api/v1/access-reviews
  // API-C-09 query: status=DRAFT|BOGUS, sort
  return fetchAll(holder.path, build());
}
export const FINDINGS_PATH = "/api/v1/exceptions";
export function fetchFindingsPage(cursor: string | null, sort: string | null) {
  return fetchListPage(FINDINGS_PATH, { sort: sort ?? "severity" }, cursor);
}
"""
COLUMNS: Final = """
import { fetchWidgetsPage } from "./queries";
export const columns = [{ id: "name", sortKey: "name" }, { id: "made", sortKey: "created_at" }];
export const source = { fetchPage: (cursor, sort) => fetchWidgetsPage({}, cursor, sort) };
"""
FINDINGS: Final = """
import { fetchFindingsPage } from "./queries";
export const columns = [{ id: "rank", sortKey: "severity" }, { id: "at", sortKey: "created_at" }];
export const source = { fetchPage: (cursor, sort) => fetchFindingsPage(cursor, sort) };
"""


def test_dg_fe_21_the_reader_reports_each_kind_of_mismatch(
    app_settings: Settings, tmp_path: Path
) -> None:
    """A default sort, a filter, ``q``, a limit, a filter value and a ``sortKey`` the route does
    not admit, and a ``sortKey`` whose direction the route fixes (a header sends both), read
    through a constant, a variable, a path function, a wrapper, an import and the two call
    annotations; and the two forms the reader cannot tie."""
    files = []
    sources_here = (("queries.ts", QUERIES), ("columns.tsx", COLUMNS), ("findings.tsx", FINDINGS))
    for name, text in sources_here:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        files.append(Source.of(path, text))
    reading = read(get_routes(app_settings), files)

    def short(lines: Sequence[str]) -> list[str]:
        return [re.sub(r"^\S*/", "", line) for line in lines]

    reviews = "GET /api/v1/access-reviews"
    keys = "(admits as_of, id, name; default -id)"
    assert short(problems(reading)) == [
        f"columns.tsx:3 {reviews}: sortKey sort 'created_at' is not a sort key of access-reviews "
        f"{keys}",
        "findings.tsx:3 GET /api/v1/exceptions: sortKey sort '-severity': severity has a fixed "
        "direction and takes no leading -",
        f"queries.ts:10 {reviews}: owner is not a filter of access-reviews (filters: status)",
        f"queries.ts:10 {reviews}: sort '-created_at' is not a sort key of access-reviews {keys}",
        f"queries.ts:16 {reviews}/{{}}/items: limit 900 is outside 1 to 500",
        f"queries.ts:16 {reviews}/{{}}/items: q is sent and access-review-items has no search",
        f"queries.ts:24 {reviews}: limit 900 is outside 1 to 500",
        f"queries.ts:24 {reviews}: status=BOGUS is not one of CANCELLED, COMPLETED, DRAFT, "
        "IN_REVIEW",
    ]
    assert short(untied(reading.calls, reading.keys)) == [
        "queries.ts:19 fetchListPage(holder.path, …): the path is not a constant, a template or a "
        "path function of an API route; add above the call: "
        "// API-C-09 list: GET /api/v1/<route>",
        "queries.ts:19 fetchListPage(…, build(), …): the query is built where this test cannot "
        "read it; add above the call: // API-C-09 query: <key>, <key>=<value>|<value>",
    ]
