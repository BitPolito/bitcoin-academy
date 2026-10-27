# Python security dependency candidate

Refs #282. This draft targets the current master independently of the document
authorization PR #273. Follow-up #281 has already been merged into #273's branch,
not master. The certifi correction remains in the existing Dependabot PR #275;
do not count this draft as fixing certifi.

The candidate updates Pillow 12.3.0 → 13.0.0, filelock 3.32.5 → 4.2.4,
setuptools 84.0.0 → 84.2.1 and the resolver-required fastembed 0.9.0 → 0.9.1.
The manifest records corrected floors, including the build backend. Python
remains 3.11+. This includes a filelock major migration.

The complete uv lock resolves with Python 3.12. A local comparison of its 131
registry packages against the downloaded public OSV database leaves only the
certifi version already addressed by #275. Nine previous Torch matches were
scanner false positives: legacy OSV build labels were not parsed correctly.
Those records do not justify a Torch upgrade.

This is not an ingestion/model compatibility certification. Complete backend
pytest/coverage and mypy, model/cache/file-lock paths, every supported Python
version, frontend/QVAC quality gates and Docker builds before merge. No model
weights or real document corpus were downloaded or processed during lock
resolution. No secret, environment, provider or production setting was changed.

The current CI workflow still lacks an explicit read-only token permission;
the separately prepared permissions patch requires an identity with workflow
write scope. This draft uses skip-ci until that prerequisite is applied. It must
not be merged around a skipped/red/pending gate. See the local audit for the
administrator patch and full unresolved verification list.
