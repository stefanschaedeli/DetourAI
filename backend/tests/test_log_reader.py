"""Tests for log file reading utilities."""
import asyncio
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# parse_log_line
# ---------------------------------------------------------------------------

def test_parse_full_line():
    from utils.log_reader import parse_log_line
    line = "[2026-05-18 10:00:00] [INFO] [job:abcd1234] [RouteArchitect] Processing route"
    result = parse_log_line(line)
    assert result["ts"] == "2026-05-18 10:00:00"
    assert result["level"] == "INFO"
    assert result["job"] == "abcd1234"
    assert result["agent"] == "RouteArchitect"
    assert result["message"] == "Processing route"
    assert result["raw"] == line


def test_parse_line_without_job():
    from utils.log_reader import parse_log_line
    line = "[2026-05-18 10:01:00] [WARNING] [Orchestrator] Starting pipeline"
    result = parse_log_line(line)
    assert result["level"] == "WARNING"
    assert result["job"] is None
    assert result["agent"] == "Orchestrator"
    assert result["message"] == "Starting pipeline"


def test_parse_line_without_agent():
    from utils.log_reader import parse_log_line
    line = "[2026-05-18 10:02:00] [ERROR] Something went wrong"
    result = parse_log_line(line)
    assert result["level"] == "ERROR"
    assert result["job"] is None
    assert result["agent"] is None
    assert result["message"] == "Something went wrong"


def test_parse_unparseable_line():
    from utils.log_reader import parse_log_line
    line = "this is not a structured log line"
    result = parse_log_line(line)
    assert result["level"] == "RAW"
    assert result["message"] == line
    assert result["ts"] is None


def test_parse_empty_line_returns_none():
    from utils.log_reader import parse_log_line
    assert parse_log_line("") is None
    assert parse_log_line("   ") is None


# ---------------------------------------------------------------------------
# read_last_n_lines
# ---------------------------------------------------------------------------

def test_read_last_n_lines(tmp_path):
    from utils.log_reader import read_last_n_lines
    f = tmp_path / "test.log"
    lines = [f"line {i}" for i in range(100)]
    f.write_text("\n".join(lines) + "\n")
    result = read_last_n_lines(f, 10)
    assert len(result) == 10
    assert result[-1] == "line 99"
    assert result[0] == "line 90"


def test_read_last_n_lines_fewer_than_n(tmp_path):
    from utils.log_reader import read_last_n_lines
    f = tmp_path / "short.log"
    f.write_text("a\nb\nc\n")
    result = read_last_n_lines(f, 20)
    assert result == ["a", "b", "c"]


def test_read_last_n_lines_missing_file(tmp_path):
    from utils.log_reader import read_last_n_lines
    result = read_last_n_lines(tmp_path / "nonexistent.log", 10)
    assert result == []


# ---------------------------------------------------------------------------
# matches_filters
# ---------------------------------------------------------------------------

def test_matches_filters_level():
    from utils.log_reader import matches_filters
    entry = {"level": "INFO", "job": None, "agent": "X", "message": "hello", "ts": "2026-05-18 10:00:00", "raw": ""}
    assert matches_filters(entry, levels={"INFO"}, job_id="", search="")
    assert not matches_filters(entry, levels={"ERROR"}, job_id="", search="")


def test_matches_filters_job_id():
    from utils.log_reader import matches_filters
    entry = {"level": "INFO", "job": "abcd1234", "agent": "X", "message": "hello", "ts": "2026-05-18 10:00:00", "raw": ""}
    assert matches_filters(entry, levels=set(), job_id="abcd", search="")
    assert not matches_filters(entry, levels=set(), job_id="zzzz", search="")


def test_matches_filters_search():
    from utils.log_reader import matches_filters
    entry = {"level": "INFO", "job": None, "agent": "X", "message": "Processing route stops", "ts": "2026-05-18 10:00:00", "raw": ""}
    assert matches_filters(entry, levels=set(), job_id="", search="route")
    assert not matches_filters(entry, levels=set(), job_id="", search="xyz")


def test_matches_filters_raw_only_when_no_level_filter():
    from utils.log_reader import matches_filters
    entry = {"level": "RAW", "job": None, "agent": None, "message": "startup noise", "ts": None, "raw": "startup noise"}
    assert matches_filters(entry, levels=set(), job_id="", search="")
    assert not matches_filters(entry, levels={"INFO"}, job_id="", search="")
