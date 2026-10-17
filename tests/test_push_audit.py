"""Real local Git transport with synthetic keys; model transport is separately labelled."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from tools.push_audit import (
    audit_push,
    install_guard,
    parse_updates,
    review_evidence,
    run_command,
)

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str, input_data: bytes | None = None):
    return run_command(
        [shutil.which("git"), "-C", str(repo), *args],
        cwd=repo,
        env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1"),
        input_data=input_data,
    )


@pytest.fixture
def signed_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert git(repo, "init", "-b", "main").returncode == 0
    key = tmp_path / "fixture-key"
    result = run_command(
        [shutil.which("ssh-keygen"), "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    signers = tmp_path / "allowed-signers"
    signers.write_text("fixture@example.test " + key.with_suffix(".pub").read_text())
    for name, value in {
        "user.name": "Fixture",
        "user.email": "fixture@example.test",
        "gpg.format": "ssh",
        "user.signingkey": str(key),
        "gpg.ssh.allowedSignersFile": str(signers),
        "commit.gpgsign": "true",
    }.items():
        assert git(repo, "config", name, value).returncode == 0
    shutil.copytree(ROOT / "plugins/session-handoff", repo / "plugins/session-handoff")
    catalog = repo / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "the-codex-factory",
                "plugins": [
                    {
                        "name": "session-handoff",
                        "source": {"source": "local", "path": "./plugins/session-handoff"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Productivity",
                    }
                ],
            }
        )
    )
    (repo / "README.md").write_text(
        "| [Session Handoff](plugins/session-handoff/README.md) | 0.1.0 candidate | Handoff |\n"
    )
    assert git(repo, "add", ".").returncode == 0
    tree = git(repo, "write-tree").stdout.strip().decode()
    commit = git(repo, "commit-tree", "-S", tree, input_data=b"Synthetic signed fixture\n")
    assert commit.returncode == 0, commit.stderr
    oid = commit.stdout.strip().decode()
    assert git(repo, "update-ref", "refs/heads/main", oid).returncode == 0
    return repo, oid


@pytest.fixture
def reviewer(tmp_path: Path) -> Path:
    path = tmp_path / "codex-fixture"
    path.write_text(
        "#!" + sys.executable + "\n"
        "import json, pathlib, sys\n"
        "data=json.loads(sys.stdin.read())\n"
        "out={'status':'PASS','scope_digest':data['scope_digest'],"
        "'reviewed_files':data['required_files'],'findings':[]}\n"
        "p=pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])\n"
        "p.write_text(json.dumps(out))\n"
        "print(json.dumps({'type':'turn.completed'}))\n"
    )
    path.chmod(0o700)
    return path


def update(oid: str) -> str:
    return f"refs/heads/main {oid} refs/heads/main {'0' * 40}\n"


def test_signed_coherent_tip_passes(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS", report
    assert report["updates"][0]["local_oid"] == oid


def test_audit_uses_commit_not_dirty_working_copy(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    (repo / "plugins/session-handoff/LICENSE").write_text("Dirty invalid content")
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS", report


def test_unsigned_commit_is_blocked(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    tree = git(repo, "rev-parse", f"{oid}^{{tree}}").stdout.strip().decode()
    unsigned = git(repo, "commit-tree", tree, "-p", oid, input_data=b"Unsigned synthetic object\n")
    new_oid = unsigned.stdout.strip().decode()
    git(repo, "update-ref", "refs/heads/main", new_oid)
    report = audit_push(repo, parse_updates(update(new_oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "BLOCKED"
    assert any(f["code"] == "commit-signature" for f in report["findings"])


def test_malformed_reviewer_output_never_allows_push(signed_repo, tmp_path):
    repo, oid = signed_repo
    fake = tmp_path / "bad-codex"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o700)
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", fake)
    assert report["status"] == "ERROR"


@pytest.mark.parametrize("text", ["broken", f"refs/heads/main {'g' * 40} ref {'0' * 40}"])
def test_malformed_updates_fail_closed(text):
    with pytest.raises(ValueError):
        parse_updates(text)


def test_real_pre_push_blocks_inconsistent_committed_tree(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    remote = tmp_path / "remote.git"
    assert git(repo, "init", "--bare", str(remote)).returncode == 0
    assert git(repo, "remote", "add", "origin", str(remote)).returncode == 0
    install_guard(repo, ROOT, reviewer)
    passed = git(repo, "push", "origin", "main")
    assert passed.returncode == 0, passed.stderr.decode()
    (repo / "plugins/session-handoff/LICENSE").unlink()
    git(repo, "add", ".")
    tree = git(repo, "write-tree").stdout.strip().decode()
    bad = git(repo, "commit-tree", "-S", tree, "-p", oid, input_data=b"Broken fixture\n")
    bad_oid = bad.stdout.strip().decode()
    git(repo, "update-ref", "refs/heads/main", bad_oid)
    rejected = git(repo, "push", "origin", "main")
    assert rejected.returncode != 0
    assert git(repo, "--git-dir", str(remote), "rev-parse", "main").stdout.strip().decode() == oid


def test_existing_hook_is_chained_and_can_reject(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    captured = tmp_path / "captured-refs"
    hook = repo / ".git/hooks/pre-push"
    hook.write_text(f'#!/bin/sh\ncat > "{captured}"\nexit 9\n')
    hook.chmod(0o700)
    remote = tmp_path / "remote.git"
    git(repo, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    install_guard(repo, ROOT, reviewer)
    assert git(repo, "push", "origin", "main").returncode != 0
    assert captured.read_text() == update(oid)
    assert git(repo, "--git-dir", str(remote), "rev-parse", "--verify", "main").returncode != 0


def test_stale_local_reference_cannot_be_approved(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    tree = git(repo, "rev-parse", f"{oid}^{{tree}}").stdout.strip().decode()
    other = git(repo, "commit-tree", "-S", tree, "-p", oid, input_data=b"New signed tip\n")
    git(repo, "update-ref", "refs/heads/main", other.stdout.strip().decode())
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "ERROR"


@pytest.mark.parametrize(
    "change", ["wrong-digest", "incomplete", "duplicate-coverage", "contradictory", "exit-failure"]
)
def test_invalid_review_never_passes(signed_repo, reviewer, tmp_path, change):
    repo, oid = signed_repo
    content = reviewer.read_text()
    if change == "wrong-digest":
        content = content.replace(
            "p.write_text(json.dumps(out))",
            "out['scope_digest']='0'*64\np.write_text(json.dumps(out))",
        )
    elif change == "incomplete":
        content = content.replace(
            "p.write_text(json.dumps(out))",
            "out['reviewed_files']=[]\np.write_text(json.dumps(out))",
        )
    elif change == "duplicate-coverage":
        content = content.replace(
            "p.write_text(json.dumps(out))",
            "out['reviewed_files']=out['reviewed_files']*2\np.write_text(json.dumps(out))",
        )
    elif change == "contradictory":
        content = content.replace(
            "p.write_text(json.dumps(out))",
            "out['findings']=[{'code':'conflict','severity':'error','path':'README.md',"
            "'message':'Mismatch'}]\np.write_text(json.dumps(out))",
        )
    else:
        content = "#!" + sys.executable + "\nraise SystemExit(7)\n"
    reviewer.write_text(content)
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "ERROR"


def test_signed_release_tag_matches_plugin_version(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    name = "plugin/session-handoff/v0.1.0"
    assert git(repo, "tag", "-s", name, oid, "-m", "Synthetic release tag").returncode == 0
    tag = git(repo, "rev-parse", name).stdout.strip().decode()
    refs = f"refs/tags/{name} {tag} refs/tags/{name} {'0' * 40}\n"
    report = audit_push(repo, parse_updates(refs), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS", report


def test_deletion_still_requires_contextual_review(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    refs = f"(delete) {'0' * 40} refs/heads/obsolete {oid}\n"
    report = audit_push(repo, parse_updates(refs), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS"
    assert report["tips"][0]["operation"] == "delete"
    assert report["tips"][0]["review"]["status"] == "PASS"


def test_multiple_refs_are_all_audited(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    git(repo, "update-ref", "refs/heads/feature", oid)
    refs = update(oid) + f"refs/heads/feature {oid} refs/heads/feature {'0' * 40}\n"
    report = audit_push(repo, parse_updates(refs), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS"
    assert len(report["tips"]) == 2


def test_all_refs_are_rechecked_after_final_review(signed_repo, reviewer, tmp_path, monkeypatch):
    import tools.push_audit as controller

    repo, oid = signed_repo
    git(repo, "update-ref", "refs/heads/feature", oid)
    tree = git(repo, "rev-parse", f"{oid}^{{tree}}").stdout.strip().decode()
    moved = git(repo, "commit-tree", "-S", tree, "-p", oid, input_data=b"Concurrent tip\n")
    new_oid = moved.stdout.strip().decode()
    original = controller.native_review
    calls = []

    def review(*args):
        result = original(*args)
        calls.append(True)
        if len(calls) == 2:
            git(repo, "update-ref", "refs/heads/main", new_oid)
        return result

    monkeypatch.setattr(controller, "native_review", review)
    refs = update(oid) + f"refs/heads/feature {oid} refs/heads/feature {'0' * 40}\n"
    report = audit_push(repo, parse_updates(refs), tmp_path / "runs", reviewer)
    assert report["status"] == "ERROR"


def test_previous_changed_source_is_supplied_to_reviewer(signed_repo, reviewer, tmp_path):
    repo, oid = signed_repo
    path = repo / "README.md"
    path.write_text(path.read_text() + "\nA harmless fixture note.\n")
    git(repo, "add", ".")
    tree = git(repo, "write-tree").stdout.strip().decode()
    new = git(repo, "commit-tree", "-S", tree, "-p", oid, input_data=b"Document fixture\n")
    new_oid = new.stdout.strip().decode()
    git(repo, "update-ref", "refs/heads/main", new_oid)
    content = reviewer.read_text().replace(
        "out={'status'", "assert 'README.md' in data['previous_sources']\nout={'status'"
    )
    reviewer.write_text(content)
    refs = f"refs/heads/main {new_oid} refs/heads/main {oid}\n"
    report = audit_push(repo, parse_updates(refs), tmp_path / "runs", reviewer)
    assert report["status"] == "PASS", report


def test_installer_rejects_symlinked_hook_directory(signed_repo, reviewer, tmp_path):
    repo, _ = signed_repo
    hooks = repo / ".git/hooks"
    hooks.rename(tmp_path / "original-hooks")
    shared = tmp_path / "shared-hooks"
    shared.mkdir()
    hook = shared / "pre-push"
    hook.write_text("#!/bin/sh\n# shared outside this repository\nexit 0\n")
    original = hook.read_bytes()
    hooks.symlink_to(shared, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install_guard(repo, ROOT, reviewer)
    assert hook.read_bytes() == original


def test_documentation_only_review_includes_current_implementation(signed_repo):
    repo, _ = signed_repo
    files = {
        path.relative_to(repo).as_posix(): "fixture-hash"
        for path in (repo / "plugins").rglob("*")
        if path.is_file()
    }
    evidence = review_evidence(
        repo, files, ["plugins/session-handoff/README.md"], {"status": "PASS"}
    )
    assert "plugins/session-handoff/hooks/session-bootstrap.sh" in evidence["sources"]


@pytest.mark.parametrize("stream", ["NOT JSON", '{"type":"turn.started"}'])
def test_invalid_or_incomplete_native_stream_is_error(signed_repo, reviewer, tmp_path, stream):
    repo, oid = signed_repo
    text = reviewer.read_text().replace(
        "print(json.dumps({'type':'turn.completed'}))", f"print({stream!r})"
    )
    reviewer.write_text(text)
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "ERROR"


def test_reviewer_timeout_is_error(signed_repo, reviewer, tmp_path, monkeypatch):
    import tools.push_audit as controller

    repo, oid = signed_repo

    def timeout(*args):
        raise TimeoutError("Synthetic unavailable reviewer")

    monkeypatch.setattr(controller, "native_review", timeout)
    report = audit_push(repo, parse_updates(update(oid)), tmp_path / "runs", reviewer)
    assert report["status"] == "ERROR"


def test_command_timeout_terminates_owned_child(tmp_path):
    pid_file = tmp_path / "child.pid"
    program = (
        "import os,time;from pathlib import Path;"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()));time.sleep(20)"
    )
    with pytest.raises(TimeoutError):
        run_command([sys.executable, "-c", program], cwd=tmp_path, timeout=1)
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
