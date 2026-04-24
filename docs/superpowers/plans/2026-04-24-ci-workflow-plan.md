# Plan — Issue #32: CI lint + test GitHub Actions workflow

**Branch:** `feature/ci` (worktree at `.worktrees/feature-ci`)
**Base:** `main` @ `afff549`
**Issue:** https://github.com/cbeaulieu-gt/claude-usage/issues/32
**PR target:** one PR, six commits, closes #32
**Version pinning:** compatible-release (`~=`) — picks up patch fixes, avoids surprise minor-release rule additions

---

## Task list

### Phase 1 — Dependency declaration
- [x] **1.1** Add `[project.optional-dependencies]` to `pyproject.toml` with `dev = ["ruff~=0.6.0", "pytest~=8.0"]` (match pytest's existing pin if one is present; otherwise introduce the compatible-release pin).
- [x] **1.2** Verify `uv pip install -e .[dev]` resolves cleanly in the worktree; capture the installed ruff + pytest versions in the commit message.

### Phase 2 — Lint cleanup (pre-existing errors)
- [x] **2.1** Run `ruff check .` to produce the baseline. Confirm 10 errors (F401 unused imports in tests + one E741 `l` in `test_e2e.py`).
- [x] **2.2** Fix each error with the minimum diff. Remove unused imports; rename `l` to something descriptive (`line` or `record` — pick based on usage).
- [x] **2.3** Re-run `ruff check .` — must exit 0.
- [x] **2.4** Full pytest suite — must pass (`151 passed`).

### Phase 3 — Format drift
- [x] **3.1** Run `ruff format .` — should touch exactly 16 files per pre-existing baseline. Commit as a single mechanical change so review diff is scannable.
- [x] **3.2** Re-run `ruff format --check .` — must exit 0.
- [x] **3.3** Full pytest suite — must pass.

### Phase 4 — CI workflow
- [ ] **4.1** Write `.github/workflows/ci.yml` with:
  - Triggers: `pull_request` and `push` on `main`.
  - `permissions: contents: read`.
  - `lint` job: `ubuntu-latest`, Python 3.10, `astral-sh/setup-uv@v5` with cache, `uv pip install -e .[dev]`, then `ruff check .` + `ruff format --check .`.
  - `test` job: matrix `os: [ubuntu-latest, windows-latest]`, Python 3.10, same uv setup, `pytest`.
- [ ] **4.2** Lint and test jobs are separate top-level jobs (not sequential steps in one job) — per `feedback_ci_split_lint_and_test.md`, distinct check entries make failure source obvious at a glance.
- [ ] **4.3** Validate YAML syntax locally with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`.

### Phase 5 — README
- [ ] **5.1** Add a "Development" section to `README.md` between "Subcommands" and wherever makes structural sense. Cover: `uv pip install -e .[dev]`, `pytest`, `ruff check`, `ruff format`.
- [ ] **5.2** No other README sections modified.

### Phase 6 — PR + verification
- [ ] **6.1** Push `feature/ci` and open PR with body containing plain-text `Closes #32` (no backticks).
- [ ] **6.2** Wait for first CI run. Both jobs green before requesting review.
- [ ] **6.3** After merge, user manually enables branch protection on `main`: required checks = `lint`, `test (ubuntu-latest)`, `test (windows-latest)`.

---

## Verification (applied after EVERY commit)

Full suite, mirroring CI — not just the file touched:

```bash
ruff check .
ruff format --check .
pytest
```

All three must exit 0 before moving to the next task.

---

## Out of scope (explicit)

- `mypy` / `pyright` typecheck — deferred (user decision).
- Coverage reporting (`pytest-cov` + codecov upload).
- Pre-commit hooks.
- Python 3.11 / 3.12 matrix expansion.
- `uv.lock` commit (not using a lockfile strategy for this dev-only dependency).

These may land as follow-up issues after #32 merges.
