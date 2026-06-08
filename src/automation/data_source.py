"""Unified input layer (issue #15) — the seam between *where* the data comes
from and the processors that consume it.

The processors never read an input medium directly: they ask a data source for
already-normalized records. Input now always originates in the in-app entry grid
(epic #14 — issue #16 typed it, #17 added smart-paste, #18 made Excel an *import
path into the grid*), so the only live implementations are the in-memory ones
below. The Excel-file-as-direct-source classes were removed once Excel became an
import path: a chosen file is read into the editable grid (see
``src/automation/excel_import.py``) and the grid then yields one of these
in-memory sources — the processors still can't tell where the data came from.

Two record shapes, matching the two processor families:

  * **tabular** — TYPE 1 (LoginProcessor) / TYPE 2 (CandidateProcessor): an
    ordered list of row dicts, keyed by the Hebrew column names the processors
    read (``תעודות זהות`` / ``סוג`` / ``תאריך``). This mirrors what
    ``DataFrame.iterrows()`` used to yield, so equality checks like
    ``row['סוג'] == 1`` behave exactly as before.

  * **matrix** — TYPE 3 (AttendanceProcessor): the attendance-matrix dict
    (``start_time`` / ``end_time`` / ``dates`` / ``participants``), the same
    shape :func:`ExcelParser.parse_attendance_matrix` produces.
"""
from abc import ABC, abstractmethod


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


class MemoryTabularSource(TabularSource):
    """Tabular input (TYPE 1 / 2) held in memory — the in-app manual-entry grid
    (issue #16). Built by the UI from the grid's rows."""

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
