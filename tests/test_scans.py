"""Tests for netaudit/scans/scans.py."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from netaudit.scans.scans import SCAN_TYPES, Scan


@dataclass
class FakeScan(Scan):
    """A minimal subclass, standing in for a real scan."""

    host_ip: str
    vlans: list[int]


def test_scan_types_match_their_class_names() -> None:
    """write saves the class name, so that must be the key to load it with."""
    for name, scan_class in SCAN_TYPES.items():
        assert name == scan_class.__name__
        assert issubclass(scan_class, Scan)


def test_base_scan_is_a_known_type() -> None:
    """A plain Scan can be loaded."""
    assert SCAN_TYPES["Scan"] is Scan


def test_scan_stores_when_it_was_performed() -> None:
    """The time is taken when the scan is created."""
    before = datetime.now()
    scan = Scan()
    assert before <= scan.performed_at <= datetime.now()


def test_write_includes_subclass_data(tmp_path: Path) -> None:
    """The base class writes fields that only the subclass declares."""
    when = datetime(2026, 1, 2, 3, 4, 5, 6)
    path = FakeScan("192.0.2.11", [10, 20], performed_at=when).write(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "type": "FakeScan",
        "performed_at": "2026-01-02T03:04:05.000006",
        "host_ip": "192.0.2.11",
        "vlans": [10, 20],
    }


def test_file_name_has_time_and_type(tmp_path: Path) -> None:
    """The name sorts by time and ends in what .gitignore matches."""
    when = datetime(2026, 1, 2, 3, 4, 5, 6)
    path = FakeScan("192.0.2.11", [], performed_at=when).write(tmp_path)
    assert path.name == "2026-01-02_03-04-05-000006_FakeScan.scan.json"


def test_write_creates_the_scans_folder(tmp_path: Path) -> None:
    """The first scan in a project creates its folder."""
    folder = tmp_path / "scans"
    path = Scan().write(folder)
    assert path.parent == folder
    assert path.is_file()


def test_write_never_overwrites_a_scan(tmp_path: Path) -> None:
    """A scan is a record, so a second write to the same file fails."""
    when = datetime(2026, 1, 2, 3, 4, 5)
    path = FakeScan("192.0.2.11", [10], performed_at=when).write(tmp_path)
    old_content = path.read_bytes()
    with pytest.raises(FileExistsError):
        FakeScan("192.0.2.99", [99], performed_at=when).write(tmp_path)
    assert path.read_bytes() == old_content


def test_write_to_missing_project_raises(tmp_path: Path) -> None:
    """Write creates the scans folder, but not a missing project above it."""
    with pytest.raises(FileNotFoundError):
        Scan().write(tmp_path / "missing" / "scans")


def test_new_scan_has_no_path() -> None:
    """A scan that hasn't been written isn't located anywhere."""
    assert Scan().path is None


def test_write_remembers_the_path(tmp_path: Path) -> None:
    """After writing, the scan knows where it is."""
    scan = Scan()
    path = scan.write(tmp_path)
    assert scan.path == path


def test_scan_with_a_path_can_be_written(tmp_path: Path) -> None:
    """A scan that knows its path can still be written."""
    scan = Scan(path=tmp_path / "earlier.scan.json")
    assert scan.write(tmp_path).is_file()
