from __future__ import annotations

import pytest

from mlox.project.entries import (
    BoardColumn,
    Entry,
    add_item,
    default_template,
    extract_links,
    find_template_body,
    is_valid_kind,
    move_item,
    parse_board,
    remove_item,
    rewrite_links,
    toggle_item,
)

BOARD_BODY = (
    "## Open\n"
    "\n"
    "- [ ] [[Renew TLS]]\n"
    "- [ ] write runbook\n"
    "\n"
    "## Doing\n"
    "\n"
    "- [ ] investigate mlflow\n"
    "\n"
    "## Done\n"
    "\n"
    "- [x] setup servers\n"
)


def test_is_valid_kind():
    assert is_valid_kind("note")
    assert is_valid_kind("board")
    assert not is_valid_kind("Note")
    assert not is_valid_kind("diary")


def test_parse_board_columns_items_and_links():
    columns = parse_board(BOARD_BODY)
    assert [c.name for c in columns] == ["Open", "Doing", "Done"]
    assert [i.text for i in columns[0].items] == ["[[Renew TLS]]", "write runbook"]
    assert columns[0].items[0].links == ["Renew TLS"]
    assert columns[0].items[1].links == []
    assert columns[2].items[0].checked is True


def test_parse_board_ignores_preamble_and_non_item_lines():
    body = "Some intro paragraph\n\n## Open\n\nplain text line\n- [ ] a card\n"
    columns = parse_board(body)
    assert len(columns) == 1
    assert [i.text for i in columns[0].items] == ["a card"]


def test_parse_board_without_headers_is_empty():
    assert parse_board("- [ ] not on a board\n") == []


def test_toggle_item_flips_and_forces_state():
    toggled = toggle_item(BOARD_BODY, 2)
    assert toggled.splitlines()[2] == "- [x] [[Renew TLS]]"
    forced = toggle_item(BOARD_BODY, 2, checked=False)
    assert forced.splitlines()[2] == "- [ ] [[Renew TLS]]"


def test_toggle_item_is_noop_for_non_item_lines():
    assert toggle_item(BOARD_BODY, 0) == BOARD_BODY
    assert toggle_item(BOARD_BODY, 999) == BOARD_BODY


def test_add_item_appends_to_column():
    body = add_item(BOARD_BODY, 1, "new card")
    columns = parse_board(body)
    assert [i.text for i in columns[1].items] == ["investigate mlflow", "new card"]


def test_add_item_to_empty_column_and_invalid_column():
    body = remove_item(BOARD_BODY, 1, 0)
    body = add_item(body, 1, "alone")
    columns = parse_board(body)
    assert [i.text for i in columns[1].items] == ["alone"]
    assert add_item(body, 9, "ghost") == body


def test_remove_item():
    body = remove_item(BOARD_BODY, 0, 0)
    assert "[[Renew TLS]]" not in body
    assert "write runbook" in body


def test_move_item_to_next_column():
    moved = move_item(BOARD_BODY, 0, 0, 1)
    columns = parse_board(moved)
    assert [i.text for i in columns[0].items] == ["write runbook"]
    assert [i.text for i in columns[1].items] == ["investigate mlflow", "[[Renew TLS]]"]


def test_move_item_to_previous_column():
    moved = move_item(BOARD_BODY, 2, 0, -1)
    columns = parse_board(moved)
    assert [i.text for i in columns[1].items] == ["investigate mlflow", "setup servers"]
    assert columns[2].items == []


def test_move_item_preserves_checked_state_and_trailing_newline():
    body = move_item(BOARD_BODY, 2, 0, -1)
    assert body.endswith("\n")
    assert parse_board(body)[1].items[-1].checked is True


def test_move_item_at_board_edges_is_noop():
    assert move_item(BOARD_BODY, 0, 0, -1) == BOARD_BODY
    assert move_item(BOARD_BODY, 2, 0, 1) == BOARD_BODY
    assert move_item(BOARD_BODY, 0, 0, 0) == BOARD_BODY
    assert move_item(BOARD_BODY, 9, 0, 1) == BOARD_BODY


def test_extract_links_dedupes_and_strips_display_syntax():
    assert extract_links("see [[B]] and [[B]] plus [[A|display]]") == ["B", "A"]
    assert extract_links("[[ B ]]") == ["B"]
    assert extract_links("no links here") == []


def test_rewrite_links_is_case_insensitive_and_keeps_display():
    body = "see [[Renew TLS]] and [[Renew TLS|the cert]] but not [[Other]]"
    rewritten = rewrite_links(body, "renew tls", "TLS renewal")
    assert rewritten == "see [[TLS renewal]] and [[TLS renewal|the cert]] but not [[Other]]"


def test_default_templates_per_kind():
    assert default_template("board", "Board").startswith("## Open")
    assert "- [ ]" in default_template("todo", "t")
    assert default_template("note", "n").startswith("## Notes")
    assert default_template("wiki", "w").startswith("## Overview")
    assert default_template("faq", "f").startswith("## Question")


def test_find_template_body_prefers_template_entries():
    entries = [
        Entry(kind="note", title="scratch"),
        Entry(kind="template", title="Board", body_md="## Backlog\n"),
        Entry(kind="template", title="note", body_md="custom"),
    ]
    assert find_template_body(entries, "board") == "## Backlog\n"
    assert find_template_body(entries, "NOTE") == "custom"
    assert find_template_body(entries, "todo") is None
