#!/usr/bin/env python3
"""Watch the fixed Instinct import log and alert on stalls or exit.

This script polls:
- a log file size
- a PID file for the live importer process

It exits with a non-zero status and triggers `ponyalert RAINBOW_DASH` when:
- the PID is gone
- the log file has not grown for the configured stall window

Example:
  python3 scripts/watch_instinct_import_log.py \
    --log /tmp/evh_instinct_import_fixed.out \
    --pidfile /tmp/evh_instinct_import_fixed.pid
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _alert(message: str) -> None:
    print(message, flush=True)
    try:
        subprocess.run(
            ["/home/ggb66/dev/EVH/pony/bin/ponyalert", "RAINBOW_DASH"],
            check=False,
        )
    except Exception:
        pass


def _read_pid(pidfile: Path) -> int | None:
    try:
        raw = pidfile.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch the Instinct import log for stalls or exit.")
    parser.add_argument("--log", required=True, help="Path to the log file to watch.")
    parser.add_argument("--pidfile", required=True, help="Path to the PID file for the live importer.")
    parser.add_argument("--stall-seconds", type=int, default=60, help="Alert if log size does not change for this long.")
    parser.add_argument("--poll-seconds", type=int, default=5, help="How often to poll the log and PID.")
    args = parser.parse_args(argv)

    log_path = Path(args.log)
    pidfile = Path(args.pidfile)
    last_size: int | None = None
    last_change = time.monotonic()
    last_report_path = pidfile.with_suffix(pidfile.suffix + ".watch.json")

    print(
        f"watching log={log_path} pidfile={pidfile} stall_seconds={args.stall_seconds} poll_seconds={args.poll_seconds}",
        flush=True,
    )

    while True:
        pid = _read_pid(pidfile)
        if pid is None:
            _alert(f"ALERT: PID file {pidfile} is missing or invalid.")
            return 2
        if not Path(f"/proc/{pid}").exists():
            stale_note = ""
            try:
                if last_report_path.exists():
                    stale_note = f" last_report={last_report_path.read_text(encoding='utf-8').strip()}"
            except Exception:
                pass
            _alert(f"ALERT: importer PID {pid} is gone.{stale_note}")
            return 3

        try:
            size = log_path.stat().st_size
        except FileNotFoundError:
            _alert(f"ALERT: log file {log_path} is missing.")
            return 4
        except Exception as exc:
            _alert(f"ALERT: could not stat log file {log_path}: {exc}")
            return 5

        if last_size is None or size > last_size:
            last_size = size
            last_change = time.monotonic()
            try:
                last_report_path.write_text(f"pid={pid} size={size} last_change={last_change}\n", encoding="utf-8")
            except Exception:
                pass
        elif time.monotonic() - last_change >= args.stall_seconds:
            _alert(
                f"ALERT: log file {log_path} has not changed for {args.stall_seconds} seconds "
                f"(pid={pid}, size={size})."
            )
            return 6

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
