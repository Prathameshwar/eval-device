"""Human-test desktop client; model lifecycle belongs to Manage Local Models."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "human-test/scripts"))


def main():
    try:
        from demo import main as run

        sys.argv.insert(1, "--external-api")
        run()
    except KeyboardInterrupt:
        print("[STOP] Stopped by operator.", flush=True)
        return 130
    except ImportError:
        print(
            "[ERROR] Missing Python dependencies. Follow start/README.md setup.",
            flush=True,
        )
        return 1
    except Exception as error:  # noqa: BLE001 - redact provider details at the process boundary
        # Provider URLs, keys and database exception detail must stay private.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("[ERROR] " + detail, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
