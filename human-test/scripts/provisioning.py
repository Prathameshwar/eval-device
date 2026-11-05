"""Explicit local reset, serialized with the managed launcher."""

from pathlib import Path

from human_test.connection import save_connection


def reset_connection(root: Path):
    from ownership import FileLock
    from training_contracts.privacy import no_link

    def checked_path(base, relative):
        path = base / relative
        if ".." in path.parts or not path.absolute().is_relative_to(base.absolute()):
            raise ValueError("Invalid connection path")
        for part in (*reversed(path.parents), path):
            if part.exists() or part.is_symlink():
                no_link(part)
        return path

    state = checked_path(root, "human-test/.local/platform-client")
    state.mkdir(parents=True, exist_ok=True)
    with FileLock(state / "owner.lock", "Close the running Human-test window before clearing provisioning"):
        # A tombstone suppresses legacy .env credentials on subsequent starts too.
        path = checked_path(root, "human-test/.local/platform-connection/connection.json")
        names = ("human.env", "audio.env", "video.env", "config.json", "launcher.json")
        targets = [checked_path(root, "human-test/.local/platform-client/" + name) for name in names]
        save_connection({"version": 1, "unpaired": True}, path)
        for target in targets:
            target.unlink(missing_ok=True)
