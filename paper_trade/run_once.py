"""One-shot paper-trade scan for Windows Task Scheduler.

``paper_engine.py`` runs a scan and then blocks forever in its own scheduler
loop, which is the wrong shape for Task Scheduler: the OS owns the schedule, so
the process must do one scan and exit.  This runs exactly one scan, mirrors all
console output to a log file, and returns a non-zero exit code on failure so a
broken run shows up as "Last Run Result" in the Task Scheduler UI instead of
failing silently.

Usage::

    python -m paper_trade.run_once
"""
from __future__ import annotations

import sys
import os
import traceback
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from paper_trade.paper_engine import PAPER_DIR, run_daily_job

LOG_FILE = os.path.join(PAPER_DIR, "engine_log.txt")
MAX_LOG_BYTES = 2_000_000        # keep the log from growing without bound


class _Tee:
    """Write to the real stream and the log file at once.

    ``stream`` is None under ``pythonw.exe`` (no console), which is how the
    scheduled task runs — the log file is then the only sink.  Console writes
    are best-effort: a dead or non-encodable console must never abort a scan.
    """

    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, text: str) -> int:
        self._log.write(text)
        if self._stream is not None:
            try:
                self._stream.write(text)
            except (UnicodeEncodeError, ValueError, OSError):
                pass
        return len(text)

    def flush(self) -> None:
        self._log.flush()
        if self._stream is not None:
            try:
                self._stream.flush()
            except (ValueError, OSError):
                pass

    def isatty(self) -> bool:
        # Progress bars query this; without it they raise under pythonw.
        return False

    @property
    def encoding(self) -> str:
        return getattr(self._stream, "encoding", None) or "utf-8"


def _rotate(path: str, max_bytes: int = MAX_LOG_BYTES) -> None:
    """Keep one previous log once the current one gets large."""
    if os.path.exists(path) and os.path.getsize(path) > max_bytes:
        backup = path + ".1"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)


def main() -> int:
    os.makedirs(PAPER_DIR, exist_ok=True)
    _rotate(LOG_FILE)
    started = datetime.now()

    # errors="replace": the dashboard uses box-drawing characters that the
    # Windows console codepage cannot always encode.
    with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n{'=' * 62}\nRUN START {started:%Y-%m-%d %H:%M:%S}\n{'=' * 62}\n")
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = _Tee(real_out, log)
        sys.stderr = _Tee(real_err, log)
        try:
            run_daily_job()
            status = 0
        except Exception:                                  # noqa: BLE001
            log.write("RUN FAILED\n" + traceback.format_exc())
            traceback.print_exc(file=real_err)
            status = 1
        finally:
            sys.stdout, sys.stderr = real_out, real_err
            elapsed = (datetime.now() - started).total_seconds()
            log.write(f"RUN END status={status} elapsed={elapsed:.0f}s\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
