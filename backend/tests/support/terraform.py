"""Text-level reader for the Terraform artifacts under ``deploy/terraform/gcp`` (05 §8.3 DPL-30 to
DPL-42; BUILD_SPEC DEP-3, DEP-4).

The loop never runs Terraform (DG-FORBID-07, DG-FORBID-12) and the backend environment carries no
HCL parser (DG-FORBID-08 forbids adding one outside ``make setup LOCK=1``), so the static tests read
the ``.tf`` files as text: block headers are matched, bodies are found by brace matching after
string literals and comments are removed, and attributes are read with anchored patterns. This is
enough for the DEP-3/DEP-4 assertions and deliberately simple; ``make tf-validate`` (supervisor) is
the schema check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_DIR = ROOT / "deploy" / "terraform" / "gcp"

_HEADER = re.compile(
    r"^\s*(resource|data|variable|output|locals|module|terraform|provider|check|moved|import)"
    r'((?:\s+"[^"]*")*)\s*\{\s*$'
)
_LABEL = re.compile(r'"([^"]*)"')
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_COMMENT = re.compile(r"(#|//).*$")


@dataclass(frozen=True)
class Block:
    """One top-level or nested HCL block: ``kind "label" "label" { body }``."""

    kind: str
    labels: tuple[str, ...]
    body: str
    file: str
    line: int

    @property
    def type(self) -> str:
        return self.labels[0] if self.labels else ""

    @property
    def name(self) -> str:
        return self.labels[1] if len(self.labels) > 1 else (self.labels[0] if self.labels else "")

    @property
    def address(self) -> str:
        return ".".join((self.kind, *self.labels))

    def attribute(self, name: str) -> str | None:
        """The right-hand side of the first single-line ``name = value`` at the body's own depth."""
        return attribute(self.body, name)

    def attributes(self, name: str) -> list[str]:
        """Every single-line ``name = value`` at any depth inside the body."""
        pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", re.MULTILINE)
        return [strip_comment(m.group(1)) for m in pattern.finditer(self.body)]

    def children(self) -> list[Block]:
        """The blocks written directly inside this body. A ``dynamic "x"`` block counts as ``x``
        with its ``for_each`` line and the lines of its ``content`` block flattened into one body,
        so attributes and nested blocks read the same way as in a static block."""
        found: list[Block] = []
        for block in blocks_in(self.body, self.file, self.line):
            if block.kind == "dynamic" and block.labels:
                found.append(_flatten_dynamic(block))
            else:
                found.append(block)
        return found

    def nested(self, name: str) -> list[Block]:
        """Direct child blocks called ``name`` (including ``dynamic "name"``)."""
        return [block for block in self.children() if block.kind == name]

    def descendants(self, name: str) -> list[Block]:
        """Blocks called ``name`` at any depth inside this body."""
        found: list[Block] = []
        for block in self.children():
            if block.kind == name:
                found.append(block)
            found.extend(block.descendants(name))
        return found

    def has(self, text: str) -> bool:
        return text in self.body


def _flatten_dynamic(block: Block) -> Block:
    """``dynamic "x" { for_each = … content { … } }`` as ``x { for_each = … ; … }``."""
    depth = 0
    own: list[str] = []
    for raw in block.body.splitlines():
        bare = _bare(raw)
        opening, closing = bare.count("{"), bare.count("}")
        if depth == 0 and opening == 0 and closing == 0:
            own.append(raw)
        depth += opening - closing
    content = [child for child in blocks_in(block.body) if child.kind == "content"]
    inner = content[0].body if content else ""
    return Block(block.labels[0], block.labels, "\n".join([*own, inner]), block.file, block.line)


def _bare(line: str) -> str:
    """A line with string literals and trailing comments removed, for brace counting."""
    return _COMMENT.sub("", _STRING.sub('""', line))


def blocks_in(text: str, file: str = "<text>", line_offset: int = 0) -> list[Block]:
    """Every block whose header sits at depth 0 of ``text`` (nested blocks are in their bodies)."""
    lines = text.splitlines()
    found: list[Block] = []
    index = 0
    while index < len(lines):
        raw = lines[index]
        header = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_-]*)((?:\s+"[^"]*")*)\s*\{\s*$', raw)
        standard = _HEADER.match(raw)
        if header is None and standard is None:
            index += 1
            continue
        match = standard or header
        assert match is not None
        kind = match.group(1)
        labels = tuple(_LABEL.findall(match.group(2)))
        depth = 1
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines) and depth > 0:
            bare = _bare(lines[cursor])
            depth += bare.count("{") - bare.count("}")
            if depth > 0:
                body.append(lines[cursor])
            cursor += 1
        found.append(Block(kind, labels, "\n".join(body), file, line_offset + index + 1))
        index = cursor
    return found


def strip_comment(value: str) -> str:
    """``value`` without a trailing ``#`` or ``//`` comment that sits outside string literals."""
    in_string = False
    escaped = False
    for index, char in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "#" or value.startswith("//", index):
            return value[:index].rstrip()
    return value.rstrip()


def attribute(body: str, name: str) -> str | None:
    """The first ``name = value`` written at depth 0 of ``body`` (single-line values only)."""
    depth = 0
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*(.+?)\s*$")
    for raw in body.splitlines():
        if depth == 0:
            match = pattern.match(raw)
            if match:
                return strip_comment(match.group(1))
        bare = _bare(raw)
        depth += bare.count("{") - bare.count("}")
    return None


def unquote(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def tf_files(directory: Path = TERRAFORM_DIR) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*.tf")
        if ".terraform" not in path.parts and path.suffix == ".tf"
    )


def read_blocks(directory: Path = TERRAFORM_DIR) -> list[Block]:
    found: list[Block] = []
    for path in tf_files(directory):
        found.extend(blocks_in(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT))))
    return found


def resources(kind: str, directory: Path = TERRAFORM_DIR) -> list[Block]:
    return [
        block for block in read_blocks(directory) if block.kind == "resource" and block.type == kind
    ]


def resource(kind: str, name: str, directory: Path = TERRAFORM_DIR) -> Block:
    matches = [block for block in resources(kind, directory) if block.name == name]
    assert len(matches) == 1, f"expected one resource {kind}.{name}, found {len(matches)}"
    return matches[0]


def variables(directory: Path = TERRAFORM_DIR) -> dict[str, Block]:
    return {block.name: block for block in read_blocks(directory) if block.kind == "variable"}


def variable_default(name: str, directory: Path = TERRAFORM_DIR) -> str | None:
    block = variables(directory).get(name)
    assert block is not None, f"variable {name} is not declared"
    return block.attribute("default")


def outputs(directory: Path = TERRAFORM_DIR) -> dict[str, Block]:
    return {block.name: block for block in read_blocks(directory) if block.kind == "output"}


def locals_text(directory: Path = TERRAFORM_DIR) -> str:
    return "\n".join(block.body for block in read_blocks(directory) if block.kind == "locals")


def local_value(name: str, directory: Path = TERRAFORM_DIR) -> str | None:
    return attribute(locals_text(directory), name)


def all_text(directory: Path = TERRAFORM_DIR) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in tf_files(directory))
