# GitHub release handoff — V16 comparative-evidence candidate

**Status:** local candidate snapshot, not yet a Git commit, tag, or public release.

## Known release facts

- The source archive intentionally has no Git history; the preflight reports `git_commit: null`.
- Core and optional LLM requirements are pinned in `requirements.txt` and `requirements-llm.txt`.
- The latest local preflight in `research_artifacts/release_preflight_v16.json` reports required paths present, no active `.env`, no cache/OS metadata in the release tree, pinned requirement syntax, consistent archived-run counts, and 115 passing tests.
- This preflight does not demonstrate a clean network-enabled installation from an independently generated lockfile.
- The historical 2026-10-24 experiment lacks a source Git SHA and complete per-trial prompts/completions. A new tag cannot retroactively establish its source provenance.
- The V16 recovery extension compares deterministic gated repair to no-healing/retry on project-authored synthetic variants. No new live LLM calls were made in that extension.
- External RCA source review, independent annotation, and adjudication remain pending.

## Safe publication steps

Run these commands from an existing trusted clone of `https://github.com/adityaraj-12/self-healing-ml-pipeline`, not from the ZIP as if it contained history.

1. Back up or stash local work; inspect `git status --short` before syncing anything.
2. Copy only the reviewed V16 source files into the clone. Do not overwrite `.git` or local `.env`; do not copy secrets.
3. Generate a lockfile with the chosen package manager (for example, `uv lock`), inspect its diff, run `uv lock --check` and `uv sync --locked` in a network-enabled clean environment, then run `python -m pytest -q` and `python tools/release_preflight.py --output research_artifacts/release_preflight_v16.json`.
4. Manually inspect public files for credentials/private information and review the staged diff.
5. Commit the exact source snapshot; only then tag that commit. Push the branch and tag and verify the remote commit/tag.
6. Record the committed SHA in a new manifest for any future experiment. Do not attribute the historical 2026-10-24 run to that new SHA.

Example only, after the above checks and review:

```bash
git status --short
git diff --check
git add README.md RELEASE_TO_GITHUB_V16.md benchmarks configs docs failures healing pipeline research_artifacts tests tools requirements.txt requirements-llm.txt
# Review the staged diff before committing
git diff --cached --stat
git diff --cached
# Commit and tag only after author approval and all preflight checks
git commit -m "Prepare V16 comparative-evidence release"
git tag -a v16.0.0 -m "V16 comparative-evidence candidate"
git push origin HEAD
git push origin v16.0.0
```

Do not run the example blindly: review paths and differences, and include any new required files appropriate to the clone. The release remains a research prototype, not production certification.
