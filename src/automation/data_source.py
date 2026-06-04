"""Unified input layer (issue #15) — the seam between *where* the data comes
from and the processors that consume it.

Today the only source is an Excel file on disk, but the processors no longer
read it directly: they ask a data source for already-normalized records. This
is the foundation the rest of epic #14 builds on — a future in-app manual-entry
grid (issue #16) or smart-paste (issue #17) plugs in here by implementing the
same interface, with no change to the processors.

Two record shapes, matching the two processor families:

  * **tabular** — TYPE 1 (LoginProcessor) / TYPE 2 (CandidateProcessor): an
    ordered list of row dicts, keyed by the Hebrew column names the processors
    read (``תעודות זהות`` / ``סוג`` / ``תאריך``). This mirrors what
    ``DataFrame.iterrows()`` used to yield, so equality checks like
    ``row['סוג'] == 1`` behave exactly as before.

  * **matrix** — TYPE 3 (AttendanceProcessor): the attendance-matrix dict
    produced by :func:`ExcelParser.parse_attendance_matrix`
    (``start_time`` / ``end_time`` / ``dates`` / ``participants``).
"""
from abc import ABC, abstractmethod

import pandas as pd

from src.automation.excel_parser import ExcelParser


class TabularSource(ABC):
    """A source of per-row records for the TYPE 1 / TYPE 2 processors."""

    @abstractmethod
    def rows(self):
        """Return an ordered list of Hebrew-keyed row dicts (possibly empty)."""


class MatrixSource(ABC):
    """A source of the TYPE 3 attendance matrix."""

    @abstractmethod
    def matrix(self):
        """Return the attendance-matrix dict."""


class ExcelTabularSource(TabularSource):
    """Reads tabular input (TYPE 1 / 2) from an Excel file."""

    def __init__(self, file_path):
        self.file_path = file_path

    def rows(self):
        # ``to_dict('records')`` preserves per-column dtypes and the Hebrew
        # keys, so downstream access (row['תעודות זהות'], row['סוג'] == 1) is
        # identical to the previous df.iterrows() path — just without handing a
        # pandas object to the processors.
        df = pd.read_excel(self.file_path)
        return df.to_dict("records")


class ExcelMatrixSource(MatrixSource):
    """Reads the TYPE 3 attendance matrix from an Excel file."""

    def __init__(self, file_path):
        self.file_path = file_path

    def matrix(self):
        return ExcelParser.parse_attendance_matrix(self.file_path)


class MemoryTabularSource(TabularSource):
    """Tabular input (TYPE 1 / 2) held in memory — the in-app manual-entry grid
    (issue #16). Built by the UI from the grid's rows; the processors can't tell
    it apart from :class:`ExcelTabularSource`."""

    def __init__(self, rows):
        self._rows = rows

    def rows(self):
        # Copy so the consumer can't mutate the grid's backing list.
        return list(self._rows)


class MemoryMatrixSource(MatrixSource):
    """Attendance matrix (TYPE 3) held in memory — the in-app manual-entry grid
    (issue #16). Must carry the exact same dict shape as
    :func:`ExcelParser.parse_attendance_matrix`."""

    def __init__(self, matrix):
        self._matrix = matrix

    def matrix(self):
        return self._matrix
