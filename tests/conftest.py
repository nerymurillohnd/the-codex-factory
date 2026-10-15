"""Synthetic homes and repositories; never the maintainer's real context."""

from pathlib import Path

import pytest
from agent_context_audit.models import SourceRoots, Target


@pytest.fixture
def context_tree(tmp_path: Path) -> tuple[Target, SourceRoots]:
    root = tmp_path / "project"
    home = tmp_path / "home"
    codex = home / ".codex"
    claude = home / ".claude"
    for directory in (root, codex, claude):
        directory.mkdir(parents=True)
    return Target(root, root), SourceRoots(codex, claude, home)


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def pytest_addoption(parser):
    parser.addoption(
        "--native-codex",
        default=None,
        help="Run native isolation/transport tests with this Codex binary",
    )


@pytest.fixture
def native_codex(request):
    path = request.config.getoption("--native-codex")
    if path is None:
        pytest.skip(
            "Native Codex checks require explicit --native-codex; semantic model tests are separate"
        )
    return Path(path).resolve()
