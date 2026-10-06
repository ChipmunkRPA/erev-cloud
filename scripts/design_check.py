#!/usr/bin/env python3
"""Design-check lint (docs/design/DESIGN_SYSTEM.md §12; docs/dev-guide.md DG-MK-design-check).

Steps, stopping at the first failing step:
  1. self-test (DS-LINT-21): every fixture listed in the configuration, scanned as its virtual
     repository path, yields exactly its expected rule ids; every implemented rule has a fixture;
  2. scan frontend/src/**/*.{ts,tsx,css,json} with every DS-LINT rule except DS-LINT-19 (make
     vocab-check) and DS-LINT-21 (step 1), excluding the token copy, the generated API types and
     the lint fixtures;
  3. DS-LINT-14 compares the token copy with docs/design/tokens.css by SHA-256; DS-LINT-15
     compares the two dark theme blocks of docs/design/tokens.css.

Findings print as `path:line:col DS-LINT-NN message`. Exit 1 on any error; warnings are printed
and counted. Scan paths resolve against --root; the fixtures resolve against the repository that
holds this script. A comment `design-check-ignore DS-LINT-NN: <reason>` on the same or preceding
line suppresses one rule on one line; a suppression without a reason is a DS-LINT-00 error.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "scripts" / "design_check.toml"
CLEAN_FIXTURE = "clean.tsx"

ERROR = "error"
WARNING = "warning"

IMPLEMENTED_RULES = tuple(f"DS-LINT-{number:02d}" for number in (*range(1, 19), 20, 22, 23))
UNSUPPRESSIBLE = frozenset(
    {f"DS-LINT-{number:02d}" for number in (1, 2, 3, 4, 5, 6)}
    | {"DS-LINT-14", "DS-LINT-15", "DS-LINT-23"}
)
SUPPRESSION_RULE = "DS-LINT-00"
MESSAGES = {
    "DS-LINT-00": "Suppression needs a reason: design-check-ignore DS-LINT-NN: <reason>.",
    "DS-LINT-01": "Use a colour token.",
    "DS-LINT-02": (
        "Default palette class; use a token utility (for example `bg-surface`, `text-fg-2`)."
    ),
    "DS-LINT-03": "Arbitrary colour value; use a token.",
    "DS-LINT-04": "Only `shadow-popover` and `shadow-overlay` exist; no blur.",
    "DS-LINT-05": "Gradients are not part of the design system.",
    "DS-LINT-06": "No emoji or pictographs in UI strings; use a Phosphor icon.",
    "DS-LINT-07": "Use the icon registry (DS-ICO-02).",
    "DS-LINT-08": "Charts go through the chart module; no pies, funnels or animation.",
    "DS-LINT-09": "Format through the format module (§6).",
    "DS-LINT-10": "Use logical properties (§9).",
    "DS-LINT-11": "Use z-index, radius and type tokens.",
    "DS-LINT-12": "Use the spacing scale or a layout token.",
    "DS-LINT-13": "Keep the focus ring (DS-A11Y-02).",
    "DS-LINT-14": "Token copy differs from docs/design/tokens.css. Run make tokens.",
    "DS-LINT-15": "Dark theme blocks are out of sync.",
    "DS-LINT-16": "Inline colour; use a token class or `var()`.",
    "DS-LINT-17": "Minimum text size is 12 px.",
    "DS-LINT-18": "No exclamation marks in UI copy.",
    "DS-LINT-20": "Avoid !important.",
    "DS-LINT-22": (
        "Themes switch through tokens; no `dark:` variants or opacity modifiers "
        "(DS-COL-25, DS-COL-26)."
    ),
    "DS-LINT-23": (
        "Business dates stay YYYY-MM-DD strings; construct dates only in the format module "
        "(05 TZ-10)."
    ),
}
SCANNED_SUFFIXES = frozenset({".ts", ".tsx", ".css", ".json"})
TEST_SUFFIXES = (".test.ts", ".test.tsx")
QUOTES = "'\"`"

# DESIGN_SYSTEM §12 patterns. `CLS` patterns run only inside class strings (className/class
# values, cn()/clsx() arguments, @apply lines).
VARIANTS = r"(?:[\w-]+:)*"
PALETTE = (
    r"(?:slate|gray|zinc|neutral|stone|taupe|mauve|mist|olive|red|orange|amber|yellow|lime|green"
    r"|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
)

HEX_COLOUR = re.compile(r"(?<![\w&/])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
COLOUR_FUNCTION = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(")
NAMED_COLOUR = re.compile(
    r"(?:fill|stroke|color|background(?:Color)?|borderColor|stopColor)\s*[=:]\s*[\"'{`]\s*"
    r"(?:white|black|red|green|blue|gr[ae]y|orange|yellow|purple|pink)\b"
)
PALETTE_UTILITY = re.compile(
    rf"\b{VARIANTS}!?-?(?:bg|text|border(?:-[xytrblse])?|ring(?:-offset)?|outline|fill|stroke"
    r"|from|via|to|divide|placeholder|caret|accent|decoration|shadow|inset-shadow|drop-shadow)"
    rf"-{PALETTE}-(?:50|[1-9]00|950)(?:/\d{{1,3}})?\b"
)
BLACK_WHITE_UTILITY = re.compile(
    rf"\b{VARIANTS}(?:bg|text|border|ring|fill|stroke|outline|divide|decoration)-(?:white|black)\b"
)
ARBITRARY_COLOUR = re.compile(
    r"\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|shadow|decoration|caret|accent"
    r"|placeholder|divide)-\[(?!var\(--)"
)
ARBITRARY_COLOUR_FUNCTION = re.compile(r"-(?:\[|\()(?:#|rgb|hsl|oklch)")
CLASS_SHADOW = re.compile(
    r"\b(?:shadow|inset-shadow|drop-shadow)-(?!popover\b|overlay\b|none\b)[\w\[\]\(\)/.-]+"
)
CLASS_DROP_SHADOW = re.compile(r"\bdrop-shadow\b")
CLASS_BACKDROP = re.compile(r"\bbackdrop-(?:blur|filter)")
CLASS_BLUR = re.compile(r"\bblur(?:-[\w\[\]]+)?\b")
STYLE_BOX_SHADOW = re.compile(r"\bboxShadow\s*:")
CSS_SHADOW_OR_BLUR = re.compile(
    r"box-shadow\s*:|backdrop-filter\s*:|(?<![\w-])filter\s*:\s*[^;]*blur"
)
CLASS_GRADIENT = re.compile(r"\bbg-(?:linear|radial|conic|gradient)-")
CLASS_GRADIENT_STOP = re.compile(r"\b(?:from|via|to)-(?:[\w\[]|\()")
GRADIENT_FUNCTION = re.compile(r"(?:linear|radial|conic)-gradient\(")
SVG_GRADIENT = re.compile(r"<(?:linearGradient|radialGradient)\b")
EMOJI = re.compile(
    r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u231A\u231B\u23E9-\u23F3"
    r"\u23F8-\u23FA\uFE0F\u200D]"
)
IMPORT_SPECIFIER = re.compile(r"\b(?:from|import|require)\s*\(?\s*([\"'])([^\"'\n]+)\1")
NAMED_IMPORT = re.compile(
    r"\bimport\s+(?:type\s+)?(?:[\w$]+\s*,\s*)?\{([^}]*)\}\s*from\s*([\"'])([^\"'\n]+)\2"
)
IMPORTED_NAME = re.compile(r"(?:^|,)\s*(?:type\s+)?([\w$]+)")
BLOCKED_ICON_PACKAGES = (
    "lucide-react",
    "react-icons",
    "@radix-ui/react-icons",
    "@tabler/icons-react",
    "@mui/icons-material",
)
BLOCKED_ICON_SCOPES = ("@heroicons/", "@fortawesome/")
PHOSPHOR_PACKAGE = "@phosphor-icons/react"
ICON_REGISTRY_SPECIFIER = re.compile(
    r"(?:^|/)icons/registry(?:\.tsx?)?$|(?:^|/)components/icons/?$"
)
INLINE_SVG = re.compile(r"<svg\b")
CHART_PACKAGE = "recharts"
FORBIDDEN_CHARTS = frozenset(
    {"PieChart", "Pie", "RadialBar", "RadialBarChart", "Funnel", "FunnelChart", "Treemap", "Sankey"}
)
CHART_ANIMATION = re.compile(r"isAnimationActive\s*=\s*\{?\s*true")
FORMAT_CALL = re.compile(
    r"\.toFixed\(|\.toLocaleString\(|\.toLocaleDateString\(|\.toLocaleTimeString\("
    r"|new\s+Intl\.(?:NumberFormat|DateTimeFormat|RelativeTimeFormat)\(|\bparseFloat\("
)
DATE_LITERAL = re.compile(r"new\s+Date\(\s*[\"'`]\d{4}-\d{2}-\d{2}[\"'`]\s*\)")
CLASS_PHYSICAL = re.compile(
    rf"\b{VARIANTS}-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-(?:l|r|tl|tr|bl|br)"
    r"|scroll-(?:ml|mr|pl|pr)|inset-(?:l|r))-[\w\[]"
    r"|\b(?:text-left|text-right|float-left|float-right)\b"
)
CSS_PHYSICAL = re.compile(
    r"\b(?:margin|padding|border)-(?:left|right)\s*:|(?<![\w-])(?:left|right)\s*:"
    r"|text-align\s*:\s*(?:left|right)"
)
ARBITRARY_TOKEN = re.compile(
    r"\bz-(?:\d+|\[(?!var\(--z-))|\brounded-\[|\bfont-\[|\btext-\[\d|\btracking-\[|\bleading-\["
)
SPACING_PREFIX = r"(?:p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy]"
ARBITRARY_SPACING = re.compile(
    rf"\b{VARIANTS}-?{SPACING_PREFIX}|w|h|min-w|min-h|max-w|max-h|size|inset(?:-[xy])?|top|bottom"
    r"|start|end|translate-[xy]|basis)-\[(?!var\(--)"
)
OFF_SCALE_SPACING = re.compile(
    rf"\b{VARIANTS}-?{SPACING_PREFIX})-(?:7|9|11|14|20|24|28|32|36|40|44|48|52|56|60|64|72|80|96)\b"
)
CLASS_FOCUS_REMOVAL = re.compile(r"\boutline-(?:none|hidden)\b|focus:outline-none")
FOCUS_VISIBLE_OUTLINE = "focus-visible:outline"
CSS_OUTLINE_REMOVAL = re.compile(r"outline\s*:\s*(?:none|0)\b")
INLINE_STYLE_COLOUR = re.compile(
    r"style=\{\{[^}]*\b(?:color|background(?:Color)?|border(?:Color)?|fill|stroke|outlineColor)"
    r"\s*:\s*+(?![\"'`]?var\(--)"
)
CLASS_SMALL_TEXT = re.compile(r"\btext-\[(?:[0-9]|1[01])(?:\.\d+)?px\]")
CSS_SMALL_TEXT = re.compile(
    r"font-size\s*:\s*(?:[0-9]|1[01])(?:\.\d+)?px|font-size\s*:\s*0?\.[0-6]\d*rem"
)
JSX_TEXT = re.compile(r"[>}]([^<>{}]*)(?=[<{])")
IMPORTANT = re.compile(r"!\s*important\b")
DARK_VARIANT = re.compile(rf"\b{VARIANTS}dark:")
OPACITY_MODIFIER = re.compile(
    r"\b(?:bg|text|border|ring|fill|stroke|outline|divide|decoration)-[\w-]+/\d{1,3}\b"
)
DATE_CONSTRUCTION = re.compile(r"\bnew\s+Date\s*\(|\bDate\.parse\s*\(")
CLASS_ATTRIBUTE = re.compile(r"\b(?:class|\w*[cC]lassName)\s*[=:]\s*")
CLASS_CALL = re.compile(r"\b(?:cn|clsx)\s*\(")
APPLY_LINE = re.compile(r"@apply\b([^;}\n]*)")
CSS_VALUE = re.compile(r":([^;{}]*)(?=[;}])")
SUPPRESSION = re.compile(r"design-check-ignore\s+(DS-LINT-\d{2})\b([^\n]*)")
SUPPRESSION_REASON = re.compile(r"\s*:(.*)")
COMMENT_CLOSE = re.compile(r"\s*(?:\*/)?\s*\}?\s*$")
MEDIA_DARK = re.compile(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{")
MEDIA_DARK_ROOT = re.compile(r":root:not\(\[data-theme=\"light\"\]\)\s*\{")
ATTRIBUTE_DARK_ROOT = re.compile(r":root\[data-theme=\"dark\"\]\s*\{")
RULE_ID = re.compile(r"^DS-LINT-\d{2}$")


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int
    col: int
    rule: str
    severity: str = ERROR

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.col} {self.rule} {MESSAGES[self.rule]}"


@dataclass(frozen=True, slots=True)
class Paths:
    """The DESIGN_SYSTEM §12 path table, repository-relative; directories end with "/"."""

    scan_root: str
    token_copy: str
    token_source: str
    icon_registry: str
    icon_directory: str
    chart_directory: str
    ai_directory: str
    format_module: str
    api_types: str
    fixtures: str
    theme_bootstrap: str


@dataclass(frozen=True, slots=True)
class Fixture:
    file: str
    path: str
    expect: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Config:
    paths: Paths
    fixtures: tuple[Fixture, ...]


class ConfigError(ValueError):
    """The configuration file is missing, unparsable or invalid."""


@dataclass(frozen=True, slots=True)
class Source:
    """A file with comments blanked (``code``) and, in addition, string contents blanked
    (``skeleton``); offsets are identical in all three texts."""

    text: str
    code: str
    skeleton: str
    strings: tuple[tuple[int, int], ...]  # content spans, quotes excluded
    line_starts: tuple[int, ...]

    def position(self, offset: int) -> tuple[int, int]:
        index = bisect.bisect_right(self.line_starts, offset) - 1
        return index + 1, offset - self.line_starts[index] + 1

    def string_at(self, start: int) -> tuple[int, int] | None:
        index = bisect.bisect_left(self.strings, (start, -1))
        if index < len(self.strings) and self.strings[index][0] == start:
            return self.strings[index]
        return None

    def strings_within(self, start: int, end: int) -> list[tuple[int, int]]:
        index = bisect.bisect_left(self.strings, (start, -1))
        spans: list[tuple[int, int]] = []
        while index < len(self.strings) and self.strings[index][1] <= end:
            spans.append(self.strings[index])
            index += 1
        return spans


def _blank(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = " "


def _string_end(text: str, start: int) -> int | None:
    """Offset of the closing quote; ' and " strings end at a newline (unterminated: None)."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index
        if char == "\n" and quote != "`":
            return None
        index += 1
    return None


def lex(text: str, *, line_comments: bool, block_comments: bool) -> Source:
    code = list(text)
    skeleton = list(text)
    strings: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if line_comments and text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end < 0 else end
        elif block_comments and text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
        elif char in QUOTES:
            close = _string_end(text, index)
            if close is None:
                index += 1
                continue
            strings.append((index + 1, close))
            _blank(skeleton, index + 1, close)
            index = close + 1
            continue
        else:
            index += 1
            continue
        _blank(code, index, end)
        _blank(skeleton, index, end)
        index = end
    line_starts = (0, *(match.end() for match in re.finditer("\n", text)))
    return Source(text, "".join(code), "".join(skeleton), tuple(strings), line_starts)


def _matching(skeleton: str, open_index: int) -> int:
    """Offset of the bracket closing the one at ``open_index`` (end of text when unbalanced)."""
    opening = skeleton[open_index]
    closing = {"{": "}", "(": ")"}[opening]
    depth = 0
    for index in range(open_index, len(skeleton)):
        char = skeleton[index]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return len(skeleton)


def class_regions(source: Source, *, css: bool) -> list[tuple[int, int]]:
    """Spans of class strings: @apply lines in CSS; className/class values and cn()/clsx()
    string arguments in scripts."""
    if css:
        return [match.span(1) for match in APPLY_LINE.finditer(source.code)]
    regions: set[tuple[int, int]] = set()
    skeleton = source.skeleton
    for match in CLASS_ATTRIBUTE.finditer(skeleton):
        start = match.end()
        if start >= len(skeleton):
            continue
        if skeleton[start] in QUOTES:
            span = source.string_at(start + 1)
            if span is not None:
                regions.add(span)
        elif skeleton[start] == "{":
            regions.update(source.strings_within(start, _matching(skeleton, start)))
    for match in CLASS_CALL.finditer(skeleton):
        open_index = match.end() - 1
        regions.update(source.strings_within(open_index, _matching(skeleton, open_index)))
    return sorted(regions)


class FileLint:
    """Collects the findings of one file."""

    def __init__(self, path: str, source: Source) -> None:
        self.path = path
        self.source = source
        self.findings: list[Finding] = []

    def emit(self, rule: str, offset: int, severity: str = ERROR) -> None:
        line, col = self.source.position(offset)
        self.findings.append(Finding(self.path, line, col, rule, severity))

    def search(
        self,
        rule: str,
        pattern: re.Pattern[str],
        span: tuple[int, int] | None = None,
        severity: str = ERROR,
        text: str | None = None,
    ) -> None:
        haystack = self.source.code if text is None else text
        start, end = span if span is not None else (0, len(haystack))
        for match in pattern.finditer(haystack, start, end):
            self.emit(rule, match.start(), severity)


def _under(path: str, directory: str) -> bool:
    return path.startswith(directory.rstrip("/") + "/")


def _lint_classes(lint: FileLint, span: tuple[int, int], *, css: bool, chart: bool) -> None:
    lint.search("DS-LINT-02", PALETTE_UTILITY, span)
    lint.search("DS-LINT-02", BLACK_WHITE_UTILITY, span)
    lint.search("DS-LINT-03", ARBITRARY_COLOUR, span)
    lint.search("DS-LINT-03", ARBITRARY_COLOUR_FUNCTION, span)
    for pattern in (CLASS_SHADOW, CLASS_DROP_SHADOW, CLASS_BACKDROP, CLASS_BLUR):
        lint.search("DS-LINT-04", pattern, span)
    lint.search("DS-LINT-05", CLASS_GRADIENT, span)
    lint.search("DS-LINT-05", CLASS_GRADIENT_STOP, span)
    if not chart:
        lint.search("DS-LINT-10", CLASS_PHYSICAL, span)
    region = lint.source.code[span[0] : span[1]]
    removal = CLASS_FOCUS_REMOVAL.search(region)
    if removal is not None and FOCUS_VISIBLE_OUTLINE not in region:
        lint.emit("DS-LINT-13", span[0] + removal.start())
    lint.search("DS-LINT-17", CLASS_SMALL_TEXT, span)
    if css:
        return
    lint.search("DS-LINT-11", ARBITRARY_TOKEN, span)
    lint.search("DS-LINT-12", ARBITRARY_SPACING, span)
    lint.search("DS-LINT-12", OFF_SCALE_SPACING, span, severity=WARNING)
    lint.search("DS-LINT-22", DARK_VARIANT, span)
    lint.search("DS-LINT-22", OPACITY_MODIFIER, span)


def _lint_imports(lint: FileLint, paths: Paths) -> None:
    path = lint.path
    code = lint.source.code
    in_icons = _under(path, paths.icon_directory)
    in_charts = _under(path, paths.chart_directory)
    for match in IMPORT_SPECIFIER.finditer(code):
        specifier = match.group(2)
        offset = match.start(2)
        blocked = any(
            specifier == package or specifier.startswith(f"{package}/")
            for package in BLOCKED_ICON_PACKAGES
        ) or specifier.startswith(BLOCKED_ICON_SCOPES)
        phosphor = specifier == PHOSPHOR_PACKAGE or specifier.startswith(f"{PHOSPHOR_PACKAGE}/")
        if blocked or (phosphor and path != paths.icon_registry):
            lint.emit("DS-LINT-07", offset)
        if (specifier == CHART_PACKAGE or specifier.startswith(f"{CHART_PACKAGE}/")) and not (
            in_charts
        ):
            lint.emit("DS-LINT-08", offset)
    for match in NAMED_IMPORT.finditer(code):
        names = set(IMPORTED_NAME.findall(match.group(1)))
        specifier = match.group(3)
        offset = match.start(3)
        if specifier == CHART_PACKAGE and names & FORBIDDEN_CHARTS:
            lint.emit("DS-LINT-08", offset)
        if (
            ICON_REGISTRY_SPECIFIER.search(specifier)
            and "Sparkle" in names
            and not _under(path, paths.ai_directory)
        ):
            lint.emit("DS-LINT-07", offset)
    if not in_icons and not in_charts:
        lint.search("DS-LINT-07", INLINE_SVG)


def _lint_script(lint: FileLint, paths: Paths, *, tsx: bool, is_test: bool) -> None:
    source = lint.source
    path = lint.path
    in_format = _under(path, paths.format_module)
    chart = _under(path, paths.chart_directory)
    if not is_test:
        for span in source.strings:
            lint.search("DS-LINT-01", HEX_COLOUR, span)
            lint.search("DS-LINT-01", COLOUR_FUNCTION, span)
        lint.search("DS-LINT-01", NAMED_COLOUR)
    for span in class_regions(source, css=False):
        _lint_classes(lint, span, css=False, chart=chart)
    lint.search("DS-LINT-04", STYLE_BOX_SHADOW)
    for span in source.strings:
        lint.search("DS-LINT-05", GRADIENT_FUNCTION, span)
    lint.search("DS-LINT-05", SVG_GRADIENT)
    lint.search("DS-LINT-06", EMOJI)
    _lint_imports(lint, paths)
    lint.search("DS-LINT-08", CHART_ANIMATION)
    if not is_test:
        if not in_format:
            lint.search("DS-LINT-09", FORMAT_CALL)
        lint.search("DS-LINT-09", DATE_LITERAL)
    if tsx:
        lint.search("DS-LINT-16", INLINE_STYLE_COLOUR)
        for match in JSX_TEXT.finditer(source.code):
            segment = match.group(1).rstrip()
            if segment.endswith("!") and any(char.isalpha() for char in segment):
                lint.emit("DS-LINT-18", match.start(1) + len(segment) - 1, WARNING)
    if not in_format:
        lint.search("DS-LINT-23", DATE_CONSTRUCTION)


def _lint_css(lint: FileLint, paths: Paths) -> None:
    source = lint.source
    chart = _under(lint.path, paths.chart_directory)
    for match in CSS_VALUE.finditer(source.code):
        lint.search("DS-LINT-01", HEX_COLOUR, match.span(1))
        lint.search("DS-LINT-01", COLOUR_FUNCTION, match.span(1))
    lint.search("DS-LINT-01", NAMED_COLOUR)
    for span in class_regions(source, css=True):
        _lint_classes(lint, span, css=True, chart=chart)
    lint.search("DS-LINT-04", CSS_SHADOW_OR_BLUR)
    lint.search("DS-LINT-05", GRADIENT_FUNCTION)
    if not chart:
        lint.search("DS-LINT-10", CSS_PHYSICAL)
    lint.search("DS-LINT-13", CSS_OUTLINE_REMOVAL)
    lint.search("DS-LINT-17", CSS_SMALL_TEXT)
    lint.search("DS-LINT-20", IMPORTANT, severity=WARNING)


def _lint_json(lint: FileLint) -> None:
    source = lint.source
    lint.search("DS-LINT-06", EMOJI)
    for start, end in source.strings:
        following = source.text[end + 1 :].lstrip()
        is_value = following[:1] in (",", "}", "]")
        if is_value and source.text[start:end].endswith("!"):
            lint.emit("DS-LINT-18", end - 1, WARNING)


def _apply_suppressions(lint: FileLint) -> list[Finding]:
    allowed: set[tuple[int, str]] = set()
    errors: list[Finding] = []
    for number, line in enumerate(lint.source.text.split("\n"), start=1):
        for match in SUPPRESSION.finditer(line):
            rule = match.group(1)
            reason_match = SUPPRESSION_REASON.match(match.group(2))
            reason = COMMENT_CLOSE.sub("", reason_match.group(1)) if reason_match else ""
            if reason.strip():
                allowed.update({(number, rule), (number + 1, rule)})
            else:
                errors.append(Finding(lint.path, number, match.start() + 1, SUPPRESSION_RULE))
    kept = [
        finding
        for finding in lint.findings
        if finding.rule in UNSUPPRESSIBLE or (finding.line, finding.rule) not in allowed
    ]
    return kept + errors


def lint_source(path: str, text: str, paths: Paths) -> list[Finding]:
    """Findings of one scanned file; ``path`` is the repository-relative POSIX path."""
    suffix = Path(path).suffix
    if suffix in (".ts", ".tsx"):
        lint = FileLint(path, lex(text, line_comments=True, block_comments=True))
        _lint_script(lint, paths, tsx=suffix == ".tsx", is_test=path.endswith(TEST_SUFFIXES))
    elif suffix == ".css":
        lint = FileLint(path, lex(text, line_comments=False, block_comments=True))
        _lint_css(lint, paths)
    elif suffix == ".json":
        lint = FileLint(path, lex(text, line_comments=False, block_comments=False))
        _lint_json(lint)
    else:
        return []
    return sorted(set(_apply_suppressions(lint)), key=_sort_key)


def check_token_copy(path: str, copy: bytes | None, source: bytes | None) -> list[Finding]:
    """DS-LINT-14: the token copy must be byte-identical to docs/design/tokens.css."""
    if copy is None or source is None:
        return [Finding(path, 1, 1, "DS-LINT-14")]
    if hashlib.sha256(copy).hexdigest() != hashlib.sha256(source).hexdigest():
        return [Finding(path, 1, 1, "DS-LINT-14")]
    return []


def _declarations(body: str) -> list[str]:
    return [re.sub(r"\s+", " ", part.strip()) for part in body.split(";") if part.strip()]


def dark_blocks(text: str) -> tuple[list[str] | None, list[str] | None]:
    """Declarations of the OS-preference dark block and of the attribute dark block, in order."""
    source = lex(text, line_comments=False, block_comments=True)
    code, skeleton = source.code, source.skeleton
    media_declarations: list[str] | None = None
    media_span = (-1, -1)
    media = MEDIA_DARK.search(code)
    if media is not None:
        media_close = _matching(skeleton, media.end() - 1)
        media_span = (media.start(), media_close)
        inner = MEDIA_DARK_ROOT.search(code, media.end(), media_close)
        if inner is not None:
            inner_close = _matching(skeleton, inner.end() - 1)
            media_declarations = _declarations(code[inner.end() : inner_close])
    attribute_declarations: list[str] | None = None
    for match in ATTRIBUTE_DARK_ROOT.finditer(code):
        if media_span[0] <= match.start() <= media_span[1]:
            continue
        close = _matching(skeleton, match.end() - 1)
        attribute_declarations = _declarations(code[match.end() : close])
        break
    return media_declarations, attribute_declarations


def check_dark_blocks(path: str, text: str) -> list[Finding]:
    """DS-LINT-15: both dark theme blocks hold the same ordered declarations."""
    media, attribute = dark_blocks(text)
    if media is not None and media == attribute:
        return []
    match = ATTRIBUTE_DARK_ROOT.search(text)
    line = text.count("\n", 0, match.start()) + 1 if match else 1
    return [Finding(path, line, 1, "DS-LINT-15")]


def _sort_key(finding: Finding) -> tuple[str, int, int, str]:
    return (finding.path, finding.line, finding.col, finding.rule)


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def load_config(path: Path) -> Config:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"{path.name}: file not found") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path.name}: {error}") from error
    unknown = set(document) - {"paths", "fixture"}
    if unknown:
        raise ConfigError(f"{path.name}: unknown top-level keys {sorted(unknown)}")
    raw_paths = document.get("paths")
    names = {field.name for field in fields(Paths)}
    if not isinstance(raw_paths, dict) or set(raw_paths) != names:
        raise ConfigError(f"{path.name}: [paths] must have exactly {sorted(names)}")
    if not all(isinstance(value, str) and value for value in raw_paths.values()):
        raise ConfigError(f"{path.name}: [paths] values must be non-empty strings")
    raw_fixtures = document.get("fixture", [])
    if not isinstance(raw_fixtures, list):
        raise ConfigError(f"{path.name}: 'fixture' must be an array of tables")
    fixtures: list[Fixture] = []
    for index, raw in enumerate(raw_fixtures, start=1):
        if not isinstance(raw, dict) or set(raw) != {"file", "path", "expect"}:
            raise ConfigError(f"{path.name}: fixture {index} must have exactly file, path, expect")
        file, virtual, expect = raw["file"], raw["path"], raw["expect"]
        if not (isinstance(file, str) and file and isinstance(virtual, str) and virtual):
            raise ConfigError(f"{path.name}: fixture {index} file and path must be strings")
        if not isinstance(expect, list) or not all(
            isinstance(rule, str) and RULE_ID.match(rule) for rule in expect
        ):
            raise ConfigError(f"{path.name}: fixture {index} expect must list DS-LINT ids")
        fixtures.append(Fixture(file, virtual, tuple(expect)))
    return Config(Paths(**raw_paths), tuple(fixtures))


def fixture_findings(
    fixture: Fixture, fixtures_dir: Path, paths: Paths, token_source: bytes | None
) -> list[Finding]:
    """Findings of one fixture scanned as its virtual repository path."""
    data = (fixtures_dir / fixture.file).read_bytes()
    if fixture.path == paths.token_copy:
        return check_token_copy(fixture.path, data, token_source)
    if fixture.path == paths.token_source:
        return check_dark_blocks(fixture.path, data.decode("utf-8"))
    return lint_source(fixture.path, data.decode("utf-8"), paths)


def self_test(config: Config, fixtures_dir: Path, token_source: bytes | None) -> list[str]:
    """Error messages; empty when every fixture yields exactly its expected rule ids."""
    if not fixtures_dir.is_dir():
        return [f"fixture directory {fixtures_dir.name} not found"]
    errors: list[str] = []
    listed = [fixture.file for fixture in config.fixtures]
    on_disk = {path.name for path in fixtures_dir.iterdir() if path.is_file()}
    errors.extend(f"fixture {name} is not listed" for name in sorted(on_disk - set(listed)))
    errors.extend(f"fixture {name} not found" for name in sorted(set(listed) - on_disk))
    covered: set[str] = set()
    for fixture in config.fixtures:
        stem = Path(fixture.file).stem
        if fixture.file == CLEAN_FIXTURE:
            if fixture.expect:
                errors.append(f"fixture {CLEAN_FIXTURE} must expect no rule id")
        elif stem in IMPLEMENTED_RULES and stem in fixture.expect:
            covered.add(stem)
        else:
            errors.append(f"fixture {fixture.file} must be named for a rule it expects")
        if fixture.file not in on_disk:
            continue
        findings = fixture_findings(fixture, fixtures_dir, config.paths, token_source)
        actual = {finding.rule for finding in findings}
        if actual != set(fixture.expect):
            errors.append(
                f"fixture {fixture.file} expected {sorted(fixture.expect)} but yielded "
                f"{sorted(actual)}"
            )
    if CLEAN_FIXTURE not in listed:
        errors.append(f"fixture {CLEAN_FIXTURE} not listed")
    missing = [rule for rule in IMPLEMENTED_RULES if rule not in covered]
    errors.extend(f"rule {rule} has no fixture" for rule in missing)
    return errors


def scan_repository(root: Path, paths: Paths) -> tuple[int, list[Finding]]:
    findings: list[Finding] = []
    scanned = 0
    base = root / paths.scan_root
    excluded = {paths.token_copy, paths.api_types}
    candidates = sorted(base.rglob("*")) if base.is_dir() else []
    for candidate in candidates:
        if candidate.suffix not in SCANNED_SUFFIXES or candidate.is_symlink():
            continue
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        if relative in excluded or _under(relative, paths.fixtures):
            continue
        scanned += 1
        findings.extend(lint_source(relative, candidate.read_text(encoding="utf-8"), paths))
    token_source = _read_bytes(root / paths.token_source)
    findings.extend(
        check_token_copy(paths.token_copy, _read_bytes(root / paths.token_copy), token_source)
    )
    if token_source is None:
        findings.append(Finding(paths.token_source, 1, 1, "DS-LINT-15"))
    else:
        findings.extend(check_dark_blocks(paths.token_source, token_source.decode("utf-8")))
    return scanned, sorted(findings, key=_sort_key)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to scan")
    parser.add_argument("--fixtures", type=Path, default=None, help="self-test fixture directory")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"design-check configuration: {error}")
        return 1

    fixtures_dir = args.fixtures if args.fixtures is not None else ROOT / config.paths.fixtures
    errors = self_test(config, fixtures_dir, _read_bytes(ROOT / config.paths.token_source))
    if errors:
        for message in errors:
            print(f"design-check self-test: {message}")
        return 1

    scanned, findings = scan_repository(args.root.resolve(), config.paths)
    for finding in findings:
        print(finding.render())
    error_count = sum(1 for finding in findings if finding.severity == ERROR)
    warning_count = len(findings) - error_count
    print(f"design-check: {scanned} files scanned, {error_count} errors, {warning_count} warnings")
    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
