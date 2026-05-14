import logging
import pandas as pd


def extract_event_dataframe(content, logger=None):
    """
    Extract the raw event table from an annotation CSV payload.

    RABET CSV files can include metadata and summary sections around the raw
    event table. This helper centralizes the extraction logic so analysis and
    visualization parse files consistently.
    """
    logger = logger or logging.getLogger(__name__)
    lines = content.splitlines()
    start_line = -1
    end_line = len(lines)

    for index, line in enumerate(lines):
        if line.startswith('Event,Onset,Offset'):
            start_line = index
            break

    if start_line >= 0:
        for index in range(start_line + 1, len(lines)):
            if not lines[index].strip() or lines[index].startswith('Behavior,'):
                end_line = index
                logger.debug(f"Found end of event data at line {index}")
                break

        csv_content = '\n'.join(lines[start_line:end_line])
        df = pd.read_csv(pd.io.common.StringIO(csv_content), dtype=str)
    else:
        df = pd.read_csv(pd.io.common.StringIO(content), dtype=str)

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
