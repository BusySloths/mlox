"""Knowledge-base entries for MLOX projects: data model and markdown helpers.

Entries are the storage unit of the project knowledge base: a titled markdown
body with a kind (note, faq, wiki, todo, board, template). Boards are a
convention over markdown — ``## Column`` subheaders name the lanes and
``- [ ]`` checkbox lines are the cards — so the raw text stays the single
source of truth for TUI rendering and future markdown export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

ENTRY_KINDS = ("note", "faq", "wiki", "todo", "board", "template")
TEMPLATE_ENTRY_KIND = "template"

BOARD_HEADER_RE = re.compile(r"^##\s+(?P<name>.+?)\s*$")
BOARD_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+\[(?P<check>[ xX])\]\s?(?P<text>.*)$")
WIKILINK_RE = re.compile(r"\[\[(?P<target>[^\[\]|]+?)(?:\|[^\[\]]*)?\]\]")


@dataclass
class Entry:
    """One knowledge-base entry stored inside the encrypted project file."""

    kind: str
    title: str
    body_md: str = ""
    id: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class BoardItem:
    """One ``- [ ]`` card inside a board column."""

    text: str
    checked: bool
    line_no: int
    links: list[str] = field(default_factory=list)


@dataclass
class BoardColumn:
    """One ``## <name>`` lane of a board entry."""

    name: str
    header_line: int
    end_line: int
    items: list[BoardItem] = field(default_factory=list)


def is_valid_kind(kind: str) -> bool:
    return kind in ENTRY_KINDS


def item_line_text(item: BoardItem, checked: bool | None = None) -> str:
    """Render the canonical markdown line for a board item."""
    mark = "x" if (item.checked if checked is None else checked) else " "
    return f"- [{mark}] {item.text}"


def parse_board(body: str) -> list[BoardColumn]:
    """Parse a board body into columns; non-board content is ignored."""
    lines = body.splitlines()
    columns: list[BoardColumn] = []
    current: Optional[BoardColumn] = None
    for line_no, line in enumerate(lines):
        header = BOARD_HEADER_RE.match(line)
        if header:
            if current is not None:
                current.end_line = line_no
            current = BoardColumn(
                name=header.group("name"), header_line=line_no, end_line=len(lines)
            )
            columns.append(current)
            continue
        item = BOARD_ITEM_RE.match(line)
        if item and current is not None:
            current.items.append(
                BoardItem(
                    text=item.group("text").rstrip(),
                    checked=item.group("check").lower() == "x",
                    line_no=line_no,
                    links=extract_links(item.group("text")),
                )
            )
    if current is not None:
        current.end_line = len(lines)
    return columns


def _split_body(body: str) -> tuple[list[str], bool]:
    return body.splitlines(), body.endswith("\n")


def _join_body(lines: list[str], had_newline: bool) -> str:
    text = "\n".join(lines)
    if had_newline and not text.endswith("\n"):
        text += "\n"
    return text


def toggle_item(body: str, line_no: int, checked: bool | None = None) -> str:
    """Flip (or force with ``checked``) the checkbox on the given body line."""
    lines, had_newline = _split_body(body)
    if not (0 <= line_no < len(lines)):
        return body
    match = BOARD_ITEM_RE.match(lines[line_no])
    if not match:
        return body
    if checked is None:
        checked = match.group("check").lower() != "x"
    mark = "x" if checked else " "
    lines[line_no] = f"{match.group('indent')}- [{mark}] {match.group('text')}"
    return _join_body(lines, had_newline)


def add_item(body: str, column_index: int, text: str, checked: bool = False) -> str:
    """Append a card to the given board column."""
    columns = parse_board(body)
    if not (0 <= column_index < len(columns)):
        return body
    column = columns[column_index]
    lines, had_newline = _split_body(body)
    mark = "x" if checked else " "
    item_line = f"- [{mark}] {text}"
    insert_at = column.items[-1].line_no + 1 if column.items else column.header_line + 1
    lines.insert(insert_at, item_line)
    return _join_body(lines, had_newline)


def remove_item(body: str, column_index: int, item_index: int) -> str:
    """Remove a card from the given board column."""
    columns = parse_board(body)
    if not (0 <= column_index < len(columns)):
        return body
    column = columns[column_index]
    if not (0 <= item_index < len(column.items)):
        return body
    lines, had_newline = _split_body(body)
    del lines[column.items[item_index].line_no]
    return _join_body(lines, had_newline)


def move_item(body: str, column_index: int, item_index: int, offset: int) -> str:
    """Move a card to the previous (``-1``) or next (``1``) board column."""
    columns = parse_board(body)
    if not (0 <= column_index < len(columns)):
        return body
    source = columns[column_index]
    if not (0 <= item_index < len(source.items)):
        return body
    target_index = column_index + offset
    if offset == 0 or not (0 <= target_index < len(columns)):
        return body
    target = columns[target_index]
    item = source.items[item_index]

    lines, had_newline = _split_body(body)
    del lines[item.line_no]

    # Insertion point in original line numbering; compensate for the removal.
    insert_at = target.items[-1].line_no + 1 if target.items else target.header_line + 1
    if item.line_no < insert_at:
        insert_at -= 1
    lines.insert(insert_at, item_line_text(item))
    return _join_body(lines, had_newline)


def linkify_item(body: str, line_no: int, title: str) -> str:
    """Rewrite one board card line to link an entry (keeps position/state)."""
    lines, had_newline = _split_body(body)
    if not (0 <= line_no < len(lines)):
        return body
    match = BOARD_ITEM_RE.match(lines[line_no])
    if not match:
        return body
    lines[line_no] = f"{match.group('indent')}- [{match.group('check')}] [[{title}]]"
    return _join_body(lines, had_newline)


def extract_links(body: str) -> list[str]:
    """Return deduplicated ``[[wikilink]]`` targets in document order."""
    links: list[str] = []
    for match in WIKILINK_RE.finditer(body):
        target = match.group("target").strip()
        if target and target not in links:
            links.append(target)
    return links


def rewrite_links(body: str, old: str, new: str) -> str:
    """Rewrite ``[[old]]`` (and ``[[old|display]]``) links to ``new``."""
    pattern = re.compile(
        r"\[\[\s*" + re.escape(old) + r"\s*(\|[^\[\]]*)?\]\]", re.IGNORECASE
    )
    return pattern.sub(lambda m: f"[[{new}{m.group(1) or ''}]]", body)


def default_template(kind: str, title: str) -> str:
    """Built-in markdown body for a new entry of the given kind."""
    if kind == "board":
        return "## Open\n\n## Doing\n\n## Done\n"
    if kind == "todo":
        return "## Details\n\n- [ ] \n"
    if kind == "faq":
        return "## Question\n\n\n## Answer\n\n\n"
    if kind == "wiki":
        return "## Overview\n\n\n"
    return "## Notes\n\n\n"


def find_template_body(entries: Iterable[Entry], kind: str) -> Optional[str]:
    """Return the overriding body from a ``template`` entry matching ``kind``."""
    wanted = kind.strip().casefold()
    for entry in entries:
        if entry.kind != TEMPLATE_ENTRY_KIND:
            continue
        if entry.title.strip().casefold() == wanted:
            return entry.body_md
    return None
