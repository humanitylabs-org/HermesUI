import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "hermesui" / "check_boundary.py"
MANIFEST_UPDATER = ROOT / "hermesui" / "update_overlay_manifest.py"


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def test_live_checkout_preserves_the_upstream_backend():
    result = run("python3", str(CHECKER), cwd=ROOT)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "upstream backend" in result.stdout
    assert "is untouched" in result.stdout


def test_boundary_rejects_backend_drift_but_accepts_recorded_static_overlay(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "api").mkdir(parents=True)
    (repo / "static").mkdir()
    (repo / "hermesui").mkdir()
    (repo / "api" / "routes.py").write_text("UPSTREAM = True\n", encoding="utf-8")
    (repo / "static" / "index.html").write_text("upstream\n", encoding="utf-8")
    (repo / "hermesui" / "check_boundary.py").write_bytes(CHECKER.read_bytes())
    (repo / "hermesui" / "update_overlay_manifest.py").write_bytes(MANIFEST_UPDATER.read_bytes())
    assert run("git", "init", "-q", cwd=repo).returncode == 0
    run("git", "config", "user.name", "Boundary QA", cwd=repo)
    run("git", "config", "user.email", "boundary@example.invalid", cwd=repo)
    run("git", "add", ".", cwd=repo)
    assert run("git", "commit", "-q", "-m", "upstream", cwd=repo).returncode == 0
    commit = run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
    tree = run("git", "rev-parse", "HEAD^{tree}", cwd=repo).stdout.strip()
    (repo / "UPSTREAM.json").write_text(
        json.dumps(
            {
                "repository": "https://github.com/nesquena/hermes-webui",
                "commit": commit,
                "tree": tree,
                "tag": "fixture",
            }
        ),
        encoding="utf-8",
    )
    (repo / "static" / "index.html").write_text("hermes ui\n", encoding="utf-8")
    assert run("python3", "hermesui/update_overlay_manifest.py", cwd=repo).returncode == 0
    accepted = run("python3", "hermesui/check_boundary.py", cwd=repo)
    assert accepted.returncode == 0, accepted.stderr or accepted.stdout

    (repo / "api" / "routes.py").write_text("DOWNSTREAM_BACKEND = True\n", encoding="utf-8")
    rejected = run("python3", "hermesui/check_boundary.py", cwd=repo)
    assert rejected.returncode == 1
    assert "api/routes.py" in rejected.stdout
    assert "backend/runtime" in rejected.stdout


def test_overlay_manifest_hashes_every_custom_frontend_file():
    payload = json.loads((ROOT / "hermesui" / "frontend-overlay.json").read_text(encoding="utf-8"))
    paths = [entry["path"] for entry in payload["files"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    for entry in payload["files"]:
        assert entry["path"].startswith("static/")
        digest = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        assert entry["hermesui_sha256"] == digest
