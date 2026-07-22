"""Tests for the one-shot scheduled-task runner."""
from __future__ import annotations

import io

import pytest

from paper_trade import run_once


def test_tee_writes_to_both_sinks():
    log, console = io.StringIO(), io.StringIO()
    tee = run_once._Tee(console, log)
    tee.write("hello")
    assert log.getvalue() == "hello"
    assert console.getvalue() == "hello"


def test_tee_survives_missing_console():
    # pythonw.exe gives sys.stdout is None; the log must still capture output.
    log = io.StringIO()
    tee = run_once._Tee(None, log)
    tee.write("still logged")
    tee.flush()
    assert log.getvalue() == "still logged"


def test_tee_survives_unencodable_console():
    class Hostile(io.StringIO):
        def write(self, text):
            raise UnicodeEncodeError("cp1252", text, 0, 1, "nope")

    log = io.StringIO()
    run_once._Tee(Hostile(), log).write("box-drawing chars")
    assert log.getvalue() == "box-drawing chars"


def test_tee_reports_not_a_tty():
    # Progress bars call isatty(); it must not raise when console is absent.
    assert run_once._Tee(None, io.StringIO()).isatty() is False


def test_failed_scan_returns_nonzero_exit_code(tmp_path, monkeypatch):
    # Task Scheduler surfaces the exit code as "Last Run Result" -- a crashed
    # scan must not look like success.
    monkeypatch.setattr(run_once, "PAPER_DIR", str(tmp_path))
    monkeypatch.setattr(run_once, "LOG_FILE", str(tmp_path / "engine_log.txt"))
    monkeypatch.setattr(run_once, "run_daily_job",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run_once.main() == 1
    assert "boom" in (tmp_path / "engine_log.txt").read_text(encoding="utf-8")


def test_successful_scan_returns_zero_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "PAPER_DIR", str(tmp_path))
    monkeypatch.setattr(run_once, "LOG_FILE", str(tmp_path / "engine_log.txt"))
    monkeypatch.setattr(run_once, "run_daily_job", lambda: print("scanned"))
    assert run_once.main() == 0
    text = (tmp_path / "engine_log.txt").read_text(encoding="utf-8")
    assert "scanned" in text and "status=0" in text


def test_log_rotates_when_oversized(tmp_path):
    path = tmp_path / "engine_log.txt"
    path.write_text("x" * 100, encoding="utf-8")
    run_once._rotate(str(path), max_bytes=50)
    assert not path.exists()
    assert (tmp_path / "engine_log.txt.1").read_text(encoding="utf-8") == "x" * 100


def test_log_does_not_rotate_when_small(tmp_path):
    path = tmp_path / "engine_log.txt"
    path.write_text("small", encoding="utf-8")
    run_once._rotate(str(path), max_bytes=1000)
    assert path.exists()
    assert not (tmp_path / "engine_log.txt.1").exists()
