import csv
import io
import logging

import pandas as pd

# A leading UTF-8 BOM (e.g. when a CSV was saved by Excel as "CSV UTF-8")
# would otherwise glue itself onto the first header cell and defeat the
# section detection below. ``chr(0xFEFF)`` keeps the source ASCII-clean.
_BOM = chr(0xFEFF)


def _norm(cell):
    """Strip surrounding whitespace and a stray BOM from a header cell."""
    return str(cell).replace(_BOM, "").strip()


def _row_fields(line):
    """Parse one CSV line into fields, honouring quoting."""
    return next(iter(csv.reader([line])), [])


def _is_event_header(line):
    """True if ``line`` is the ``Event,Onset,Offset`` section header.

    Tolerant of BOM, surrounding whitespace, column-name case and extra
    trailing columns (e.g. a legacy ``...,Duration`` 5-column header), so
    annotation CSVs produced by slightly different tools still parse
    (BUG-016).
    """
    fields = [_norm(c).casefold() for c in _row_fields(line)]
    return fields[:3] == ["event", "onset", "offset"]


def _is_summary_header(line):
    """True if ``line`` starts the ``Behavior,Duration,Frequency`` summary."""
    fields = [_norm(c).casefold() for c in _row_fields(line)]
    return bool(fields) and fields[0] == "behavior"


def extract_event_dataframe(content, logger=None):
    """
    Extract the raw event table from an annotation CSV payload.

    RABET CSV files can include metadata and summary sections around the raw
    event table. This helper centralizes the extraction logic so analysis and
    visualization parse files consistently.
    """
    logger = logger or logging.getLogger(__name__)

    # Strip a leading UTF-8 BOM so the first header line is recognised.
    if content.startswith(_BOM):
        content = content[len(_BOM):]

    lines = content.splitlines()
    start_line = -1
    end_line = len(lines)

    for index, line in enumerate(lines):
        if _is_event_header(line):
            start_line = index
            break

    if start_line >= 0:
        for index in range(start_line + 1, len(lines)):
            if not lines[index].strip() or _is_summary_header(lines[index]):
                end_line = index
                logger.debug(f"Found end of event data at line {index}")
                break

        csv_content = '\n'.join(lines[start_line:end_line])
        df = pd.read_csv(io.StringIO(csv_content), dtype=str)
    else:
        df = pd.read_csv(io.StringIO(content), dtype=str)

    # Normalise column names (strip whitespace / stray BOM) so a header cell
    # with trailing spaces or a stray BOM still maps to the canonical name.
    df.columns = [_norm(c) for c in df.columns]
    return normalize_event_dataframe(df)


def load_event_dataframe(file_path, logger=None, encoding='utf-8'):
    """Load and parse an annotation CSV file into a normalized event DataFrame."""
    with open(file_path, 'r', encoding=encoding) as file_obj:
        return extract_event_dataframe(file_obj.read(), logger=logger)


def normalize_event_dataframe(df):
    """Normalize common event timestamp columns to numeric values."""
    if 'Onset' in df.columns:
        df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
    if 'Offset' in df.columns:
        df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')

    return df
