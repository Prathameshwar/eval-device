"""Publish the committed local root into GitHub main:device-poc."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "git@github-hcl:O230008-CTO-10006ZE690/Pratham-POCs.git"
FOLDER = b"device-poc"


def git(*args, data=None):
    result = subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def tree_entries(tree):
    entries = {}
    for record in git("ls-tree", "-z", tree).split(b"\0"):
        if record:
            metadata, name = record.split(b"\t", 1)
            entries[name] = metadata
    return entries


def publish(*, dry_run=False):
    for args in (
        ("remote", "get-url", "--all", "origin"),
        ("remote", "get-url", "--push", "--all", "origin"),
    ):
        if git(*args).decode().strip() != REMOTE:
            raise RuntimeError("origin must use the documented GitHub destination.")
    git_dir = Path(git("rev-parse", "--absolute-git-dir").decode().strip())
    state_path = git_dir / "device-publish-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    local_head = git("rev-parse", "HEAD").decode().strip()
    source_tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    if FOLDER in tree_entries(source_tree):
        raise RuntimeError("Keep the local project at its original root, without device-poc nesting.")

    git("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")
    remote_head = git("rev-parse", "refs/remotes/origin/main").decode().strip()
    remote_tree = git("rev-parse", remote_head + "^{tree}").decode().strip()
    remote_entries = tree_entries(remote_tree)
    expected = state["remote_project_entry"].encode() if state else None
    if remote_entries.get(FOLDER) != expected:
        raise RuntimeError(
            "GitHub device-poc differs from the saved publishing state. "
            "Reconcile it before publishing; do not delete or overwrite the state."
        )
    updated = dict(remote_entries)
    updated[FOLDER] = b"040000 tree " + source_tree.encode()
    records = b"".join(metadata + b"\t" + name + b"\0" for name, metadata in sorted(updated.items()))
    publication_tree = git("mktree", "-z", data=records).decode().strip()
    actual = tree_entries(publication_tree)
    if actual.pop(FOLDER) != updated[FOLDER] or actual != {
        name: value for name, value in remote_entries.items() if name != FOLDER
    }:
        raise RuntimeError("Publication must preserve all unrelated GitHub entries.")
    count = len([p for p in git("ls-tree", "-r", "--name-only", "-z", source_tree).split(b"\0") if p])
    if dry_run:
        print(f"Verified {count} committed files mapped into device-poc; other GitHub entries preserved.")
        return

    commit = remote_head
    if publication_tree != remote_tree:
        message = "Update device proof of concept\n\nLocal source commit: " + local_head
        commit = git("commit-tree", publication_tree, "-p", remote_head, "-m", message).decode().strip()
        # Fast-forward only: concurrent remote changes reject this push.
        # Stop on a push error for inspection instead of retrying automatically.
        git("push", "origin", commit + ":refs/heads/main")
        git("update-ref", "refs/remotes/origin/main", commit)
    state = {
        "local_commit": local_head,
        "remote_commit": commit,
        "remote_project_entry": updated[FOLDER].decode(),
    }
    pending = state_path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    pending.replace(state_path)
    print(f"Published {local_head[:7]} to origin/main:device-poc ({commit[:7]}).")
    print("https://github.com/O230008-CTO-10006ZE690/Pratham-POCs/tree/main/device-poc")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    publish(dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
