# GitHub publishing

This workspace stays at `C:\Pratham\poc-device`. Its committed root is published
to [`O230008-CTO-10006ZE690/Pratham-POCs`, `main`, `device-poc/`](https://github.com/O230008-CTO-10006ZE690/Pratham-POCs/tree/main/device-poc).
The existing `bill-poc/` and all other repository contents are preserved.

The SSH remote is `git@github-hcl:O230008-CTO-10006ZE690/Pratham-POCs.git`, using
the same existing SSH host alias and Git identity as the billing workspace.
No SSH keys or credentials belong in this project.

## Included files

The root `.gitignore` keeps source code, JSON defaults/examples and fixtures,
dependency manifests and lock files, migrations, SQL, scripts, tests,
documentation, and its illustrative images eligible for version control.
It excludes private `.env` files and keys, `start/cloud-models.json`, local
configuration overrides, virtual environments, caches, build output, models,
recordings, local databases, logs, and `.test_artifacts/`.
Use `start/cloud-models.example.json` when configuring a new machine.
Review staged files before every commit; ignore rules do not detect embedded secrets.

## Publish a change

Run from the local project root, staging only files for the current task:

```powershell
git add -- path/to/changed-file
git diff --cached --stat
git commit -m "Describe the completed change"
git publish --dry-run
git publish
```

The local `publish` alias runs `python start/publish.py`. The helper publishes
only committed files, maps the local root into `device-poc/`, preserves every
other remote root entry, and uses a normal fast-forward push. It refuses a
changed destination or unexpected modifications to the remote project folder.
After a push error, inspect GitHub and local state before taking any recovery
action. Do not blindly retry an uncertain push or discard publishing state.

`push.default=nothing` and the absence of a branch upstream are intentional.
Never use direct `git push`, force push, or pull/merge/rebase `origin/main`
into this local branch: its directory layout is different. Fetching is safe.
Do not move files into a new local `device-poc/` folder.

The state is stored in `.git/device-publish-state.json`. The alias and state
are local Git metadata, so cloning does not install them. In a normal clone
of `Pratham-POCs`, edit its existing `device-poc/` subtree using that checkout's
instructions; do not initialize this standalone mapping over an existing remote
folder or fabricate its saved state.

The existing workflow is included at `device-poc/.github/workflows/pms-api.yml`.
GitHub Actions only discovers workflows at the repository root, so importing
this folder does not activate that workflow. CI wiring is a separate change.
