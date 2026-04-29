from __future__ import annotations

import shutil
import textwrap
from typing import Any, List, Optional, Sequence

import typer


def _stringify_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value if item is not None and item != ""]
        return ", ".join(parts) if parts else "-"
    if isinstance(value, dict):
        if not value:
            return "-"
        return ", ".join(f"{key}={val}" for key, val in value.items())
    text = str(value)
    return text if text.strip() else "-"


def _wrap_cell(text: str, width: int) -> List[str]:
    width = max(width, 8)
    lines: List[str] = []
    for raw_line in text.splitlines() or [""]:
        wrapped = textwrap.wrap(
            raw_line,
            width=width,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        if not wrapped:
            lines.append("")
        else:
            lines.extend(wrapped)
    return lines or [""]


def _format_table_lines(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> List[str]:
    if not headers:
        return []

    term_width = shutil.get_terminal_size((100, 20)).columns
    per_column_cap = max(16, min(48, max((term_width - 6) // len(headers), 16)))
    string_rows = [[_stringify_value(cell) for cell in row] for row in rows]

    col_widths = [len(header) for header in headers]
    prepared_cells: List[List[List[str]]] = []

    for row in string_rows:
        row_cells: List[List[str]] = []
        for index, header in enumerate(headers):
            cell_value = row[index] if index < len(row) else "-"
            cell_lines = _wrap_cell(cell_value, per_column_cap)
            row_cells.append(cell_lines)
            longest_line = max(len(line) for line in cell_lines) if cell_lines else 0
            col_widths[index] = min(
                per_column_cap,
                max(col_widths[index], longest_line),
            )
        prepared_cells.append(row_cells)

    for index, header in enumerate(headers):
        wrapped_header = _wrap_cell(header, per_column_cap)
        header_width = max(len(line) for line in wrapped_header)
        col_widths[index] = min(per_column_cap, max(col_widths[index], header_width))

    def make_border(char: str = "-") -> str:
        parts = ["+"]
        for width in col_widths:
            parts.append(char * (width + 2))
            parts.append("+")
        return "".join(parts)

    def make_row(line_parts: Sequence[str]) -> str:
        padded = [part.ljust(width) for part, width in zip(line_parts, col_widths)]
        return "| " + " | ".join(padded) + " |"

    top_border = make_border("-")
    separator_border = make_border("=")
    rows_border = make_border("-")

    table_lines: List[str] = [top_border]
    header_cell_lines = [
        _wrap_cell(header, col_widths[index]) for index, header in enumerate(headers)
    ]
    header_height = max(len(cell) for cell in header_cell_lines)
    for line_index in range(header_height):
        parts = [
            header_cell_lines[index][line_index]
            if line_index < len(header_cell_lines[index])
            else ""
            for index in range(len(headers))
        ]
        table_lines.append(make_row(parts))
    table_lines.append(separator_border)

    if not prepared_cells:
        table_lines.append(make_row(["-"] * len(headers)))
        table_lines.append(rows_border)
        return table_lines

    for row_cells in prepared_cells:
        row_height = max(len(cell) for cell in row_cells)
        for line_index in range(row_height):
            parts = [
                row_cells[index][line_index]
                if line_index < len(row_cells[index])
                else ""
                for index in range(len(headers))
            ]
            table_lines.append(make_row(parts))
        table_lines.append(rows_border)
    return table_lines


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    title: Optional[str] = None,
) -> None:
    lines = _format_table_lines(headers, rows)
    if not lines:
        return

    if title:
        typer.echo(typer.style(title, fg=typer.colors.BRIGHT_BLUE, bold=True))

    header_end = 0
    for index, line in enumerate(lines):
        if "=" in line and set(line.strip()) <= {"+", "="}:
            header_end = index
            break

    for index, line in enumerate(lines):
        if 0 < index < header_end:
            typer.echo(typer.style(line, bold=True))
        else:
            typer.echo(line)
