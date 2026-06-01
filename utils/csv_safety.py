"""CSV formula-injection hardening for RABET exports.

Spreadsheet applications (Excel, LibreOffice Calc, Google Sheets) evaluate a
cell as a formula when its text begins with ``=``, ``+``, ``-``, ``@`` or a
leading TAB / CR. Because RABET writes user-controlled strings verbatim into
shared research CSVs — behaviour names (entered freely in the Action Map
dialog), ``animal_id`` (derived from a filename), and metric names — a value
such as ``=HYPERLINK(...)`` or ``=cmd|'/c ...'`` would execute on a
collaborator's machine the moment they open the file.

``sanitize_csv_cell`` neutralises that by prefixing a single quote, which the
spreadsheet treats as "force text". Crucially it leaves genuine numbers
untouched: a value that begins with ``-`` or ``+`` is only guarded when it does
*not* parse as a number, so formatted numeric cells like ``-0.5`` are preserved
byte-for-byte. This makes it safe to apply blanket-wise to every exported cell.
"""
from __future__ import annotations

from typing import Iterable

# Characters that trigger formula evaluation when they lead a cell.
_ALWAYS_DANGEROUS = ("=", "@", "\t", "\r")
# ``+`` / ``-`` are dangerous only when the cell is not a number.
_NUMERIC_SIGN_PREFIXES = ("+", "-")


def sanitize_csv_cell(value):
    """Return ``value`` made safe against CSV/formula injection.

    Non-string values (ints, floats, None) are returned unchanged. A string is
    prefixed with ``'`` only when it would otherwise be interpreted as a
    formula; numeric-looking strings beginning with a sign are preserved.
    """
    if not isinstance(value, str) or not value:
        return value

    first = value[0]
    if first in _ALWAYS_DANGEROUS:
        return "'" + value
    if first in _NUMERIC_SIGN_PREFIXES:
        try:
            float(value)
        except ValueError:
            return "'" + value
    return value


class SafeCsvWriter:
    """Thin wrapper over a ``csv.writer`` that sanitises every field.

    Exposes the subset of the writer API RABET uses (``writerow`` /
    ``writerows``) so existing export code can switch by wrapping the writer
    with no other changes.
    """

    def __init__(self, writer) -> None:
        self._writer = writer

    def writerow(self, row: Iterable) -> None:
        self._writer.writerow([sanitize_csv_cell(cell) for cell in row])

    def writerows(self, rows: Iterable[Iterable]) -> None:
        for row in rows:
            self.writerow(row)
