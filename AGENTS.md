# Contributing to BitPolito Academy

This document defines how work is planned, branched, reviewed, and merged in this repository. It
applies to every contributor — human or automated. Read it before your first change.

New to the project? Start with [`docs/overview.md`](docs/overview.md) for the architecture and
[`docs/specifications.md`](docs/specifications.md) for what is and is not implemented.

---

## 1. Golden rules

1. **Never commit directly to `master`.** `master` is the default branch and is only ever updated
   through a merged pull request.
2. **One branch, one purpose.** A branch addresses a single issue or a single coherent change.
3. **Every change goes through a pull request.** No exceptions, including documentation.
4. **All CI checks must pass before merge.** Never merge red or pending.
5. **GitHub is the source of truth.** Issues, the project board, and milestones must reflect
   reality at all times — see section 7.
6. **Code, comments, commit messages, and documentation are written in English.**

---

## 2. Repository layout

```
apps/web              Next.js frontend
services/ai           FastAPI backend, ingestion pipeline, RAG orchestration
workers/qvac-service  Node service wrapping the local embedding and LLM models
docs/                 Project overview and functional specifications
scripts/, tests/      Evaluation tooling and cross-service test assets
```

---

## 3. Workflow

### 3.1 Pick up work

Work starts from a GitHub issue. Assign it to yourself and move it to **In Progress** on the
project board. If what you intend to do is not covered by an issue, open one first — untracked work
is the single biggest source of drift in this project.

### 3.2 Create a branch

Always branch from an up-to-date `master`:

```bash
git checkout master
git pull origin master
git checkout -b <type>/<short-description>
```

**Branch naming.** `<type>/<short-description>`, lowercase, hyphen-separated, descriptive of the
change rather than the ticket number.

| Type | Use for |
|---|---|
| `feat/` | New functionality |
| `fix/` | Bug fixes |
| `refactor/` | Restructuring without behaviour change |
| `docs/` | Documentation only |
| `test/` | Tests only |
| `chore/` | Tooling, CI, dependencies, configuration |
| `perf/` | Performance work |

Good: `feat/quiz-attempt-scoring`, `fix/bm25-index-rebuild`, `refactor/unify-retrieval-paths`
Avoid: `fix/bug`, `luca-branch`, `issue-70`, `new-stuff`

### 3.3 Commit

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <imperative summary under ~72 chars>

Optional body explaining what changed and, more importantly, why.
Wrap at 72 characters.

Refs #<issue>
```

Scopes in use: `api`, `web`, `rag`, `qvac`, `db`, `infra`, `ci`, `docs`, `auth`.

```
feat(rag): add MMR diversification to the study retrieval path

The study dispatcher reranked a pool too small for the reranker to make a
meaningful difference. Reuse the hybrid pool so retrieval quality matches
the conversational path.

Refs #72
```

Keep commits focused. Do not mix refactoring with behaviour changes — reviewers cannot tell them
apart in a diff.

### 3.4 Before you push

Run the checks locally. Pushing a branch that fails checks that would have taken thirty seconds to
run wastes everyone's time.

```bash
# Backend
cd services/ai && uv run pytest && mypy app

# Frontend
cd apps/web && npm run type-check && npm run lint && npm test

# QVAC service
cd workers/qvac-service && npm test
```

### 3.5 Open a pull request

```bash
git push -u origin <branch-name>
gh pr create --base master --title "<type>(<scope>): <summary>" --body "..."
```

A pull request must include:

- **What changed and why** — the reasoning, not a restatement of the diff.
- **Issue reference** — `Closes #<n>` when the PR fully resolves it, `Refs #<n>` otherwise.
  `Closes` matters: it is what keeps issues from lingering after the work has shipped.
- **How it was verified** — commands run, tests added, manual checks performed.
- **Anything reviewers should watch for** — risky areas, follow-up work, deliberate omissions.

Keep pull requests small enough to review properly. If a change exceeds roughly 400 lines of
meaningful diff, consider splitting it.

Open the PR as a **draft** if the work is not ready for review. Do not leave non-draft PRs open and
idle — either finish them or close them.

### 3.6 Wait for CI

CI runs on every push and pull request targeting `master` and covers three jobs: backend (mypy +
pytest), frontend (tsc + lint + Jest), and the QVAC service (tests).

**Do not merge until every check is green.** If CI fails, fix it on the same branch and push again;
never merge around a failure or disable a check to get past it. If a check is genuinely broken
rather than catching a real problem, fix the check in its own PR.

### 3.7 Review

At least one approving review is required. Reviewers should check correctness, test coverage,
adherence to the layered architecture, and whether the documentation and issues still tell the
truth after the change.

Address feedback with additional commits rather than force-pushing over the reviewed history, so
reviewers can see what changed.

### 3.8 Merge and clean up

Merge with a **merge commit** to preserve branch topology:

```bash
gh pr merge <n> --merge --delete-branch
```

Do not squash and do not rebase-merge. After merging, confirm the linked issue closed and move the
card to **Done** on the project board.

Never leave merged branches behind. Never leave an issue open once its PR has merged.

---

## 4. Architecture conventions

**Backend layering.** Controllers (`app/api`) handle HTTP and error mapping only. Business logic
lives in services (`app/services`). Data access goes through repositories (`app/repositories`)
under a unit of work. Pydantic schemas (`app/schemas`) are the contracts between layers. Do not
reach across layers — no database queries in controllers.

**RAG changes.** Retrieval, ranking, and evidence assembly must stay deterministic and inspectable.
Any change to retrieval quality should be measured against the RAG evaluation suite before and
after, and the numbers included in the PR description.

**The evidence pack is a contract.** Changes to its shape affect generation, citation rendering,
and the debug surface. Treat it as a public interface.

**Database changes require a migration.** Model edits without a matching Alembic revision will
break every other environment.

**Configuration.** New settings need a default that keeps the system working, an entry in
`.env.example`, and a row in the README's variable table. Defaults documented must match defaults
in code.

---

## 5. Testing expectations

| Change | Expected tests |
|---|---|
| New endpoint | Integration test covering success and failure paths |
| New service logic | Unit tests, including edge cases |
| Bug fix | A regression test that fails before the fix |
| RAG pipeline change | Evaluation suite run, with results in the PR |
| Frontend component | Unit test; integration test for full flows |

Do not weaken or delete a failing test to make CI pass. A failing test is either a real defect or a
test that no longer describes intended behaviour — say which, in the PR.

### The quality gate

Every pull request targeting `master` runs the full gate. The `Quality gate` job aggregates all
others and is the single required status check.

| Job | What it enforces |
|---|---|
| Backend | mypy, pytest, coverage above the ratchet |
| Frontend | tsc, lint (zero warnings), Jest, coverage above the ratchet |
| QVAC service | Node tests |
| Production build | All three Docker images build |

Run it locally before pushing:

```bash
cd services/ai && pytest --cov=app --cov-report=term-missing
cd apps/web && npm run type-check && npm run lint && npm test
cd workers/qvac-service && npm test
```

**Coverage is a ratchet.** Thresholds live in `services/ai/setup.cfg` (`[coverage:report] fail_under`)
and `apps/web/jest.config.js` (`coverageThreshold`). Raise them when coverage rises; never lower one
to make a build pass. A drop means new code arrived untested — add the tests instead.

Some behaviour is asserted structurally and will fail the moment new code forgets it:

- **Authorization** — `tests/integration/test_authorization_matrix.py` derives the endpoint list from
  the live OpenAPI schema. A new endpoint without authentication fails the build automatically. An
  endpoint that is deliberately public goes in `PUBLIC_ENDPOINTS`, which makes the decision visible
  in review.
- **Contracts** — the evidence pack shape, the study action registry and documented configuration
  defaults are pinned in `tests/unit/test_contracts.py`. A failure there is not necessarily a bug: it
  means a contract changed and the test must be updated in the same PR.

Flaky tests are quarantined and fixed, never retried until green. Re-running a red build until it
passes teaches everyone to ignore red.

---

## 6. Security

- Never commit secrets, `.env` files, credentials, or model artefacts.
- Authentication and authorization changes require explicit review attention; call them out in the
  PR description.
- The default development accounts are for local use only and must never be enabled in production.
- Report security-sensitive issues privately to the maintainers rather than in a public issue.

---

## 7. Keeping GitHub honest

This project treats GitHub as the authoritative record of its own state. Concretely:

- **Every piece of work has an issue.** Implemented-but-untracked work is invisible to everyone who
  was not in the room.
- **Issues describe enough to act on.** Someone assigned an issue should be able to start from the
  issue alone: context, acceptance criteria, and the files involved.
- **Issues close when the work ships**, via `Closes #<n>` in the PR.
- **Close issues honestly.** If something was implemented differently from what the issue asked —
  made configurable rather than replaced, for instance — say so in a closing comment. A `Done` that
  does not match the code is worse than an open issue.
- **The project board reflects reality.** Every open issue carries a status.
- **Milestones group work toward outcomes**, and are closed only when genuinely complete.
- **Documentation follows the code.** A PR that changes behaviour updates
  [`docs/specifications.md`](docs/specifications.md) in the same PR.

---

## 8. Getting help

Setup problems are usually covered by the README's troubleshooting table. For anything else, open a
question issue — if you were confused, the documentation was unclear, and the answer belongs
somewhere others will find it.
