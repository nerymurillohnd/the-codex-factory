"""Timeout and output limits must stop the actual child process."""

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest
from agent_context_audit.processes import run_process


def test_capture_reads_real_process_output(tmp_path: Path) -> None:
    result = asyncio.run(
        run_process(
            [sys.executable, "-c", "print('completed')"],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=5,
        )
    )
    assert result.stdout == b"completed\n"


def test_process_timeout_prevents_later_write(tmp_path: Path) -> None:
    output = tmp_path / "should-not-exist"
    script = (
        "import time; from pathlib import Path; time.sleep(2); "
        "Path('should-not-exist').write_text('bad')"
    )
    with pytest.raises(TimeoutError):
        asyncio.run(
            run_process(
                [sys.executable, "-c", script], cwd=tmp_path, env=dict(os.environ), timeout=0.1
            )
        )
    time.sleep(0.1)
    assert not output.exists()


def test_process_output_limit_is_not_silent_truncation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output limit"):
        asyncio.run(
            run_process(
                [sys.executable, "-c", "print('x'*100000)"],
                cwd=tmp_path,
                env=dict(os.environ),
                timeout=5,
                max_output=1024,
            )
        )


def test_timeout_stops_descendant_after_parent_exits(tmp_path: Path) -> None:
    child = (
        "import time; from pathlib import Path; time.sleep(.5); "
        "Path('late-write').write_text('bad')"
    )
    parent = f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
    with pytest.raises(TimeoutError):
        asyncio.run(
            run_process(
                [sys.executable, "-c", parent], cwd=tmp_path, env=dict(os.environ), timeout=0.1
            )
        )
    time.sleep(0.6)
    assert not (tmp_path / "late-write").exists()
