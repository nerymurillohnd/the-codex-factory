"""Bootstrap failures must never masquerade as completed findings (exit 1)."""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path


def bootstrap():
    path = Path(__file__).resolve().parents[1] / "plugins/agent-context-audit/scripts/audit.py"
    spec = importlib.util.spec_from_file_location("audit_bootstrap_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_backend_without_report_is_not_exit_one(tmp_path):
    module = bootstrap()
    code = asyncio.run(
        module.run_child(
            [sys.executable, "-c", "raise SystemExit(1)"],
            dict(os.environ),
            cwd=str(tmp_path),
            audit_protocol=True,
        )
    )
    assert code == 3


def test_missing_runtime_is_explicit_failure(tmp_path, monkeypatch, capsys):
    import pytest

    module = bootstrap()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "fresh-data"))
    monkeypatch.setattr(sys, "argv", ["audit.py", "audit", "--root", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 3
    assert '"status": "failed"' in capsys.readouterr().err
