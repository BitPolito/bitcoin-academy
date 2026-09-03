# Dependency security triage

This document records the triage performed for issue #144 on 2 September 2026.
GitHub reported 75 open alerts by the time the work started (the original issue
count was 69). Alerts that differ only by package-name capitalisation are
combined below.

| Tree | Classification | Reachability | Resolution |
|---|---|---|---|
| `services/ai` | ChromaDB: 2 critical, 2 high | Runtime, direct, reachable from user-upload ingestion and chat fallback | Removed. QVAC is now the only dense index because no patched ChromaDB release exists. |
| `services/ai` | Pillow: 10 high, 3 medium | Runtime, transitive, reachable through document/image parsing | Pinned to `>=12.3.0`; lock resolved to 12.3.0. |
| `services/ai` | Starlette: 2 high, 2 medium, 1 low | Runtime, transitive through FastAPI, reachable by every HTTP request | Upgraded through FastAPI; lock resolved to Starlette 1.6.0. |
| `services/ai` | python-multipart: 1 high, 3 low | Runtime, direct, reachable by user uploads | Raised to `>=0.0.31`; lock resolved to 0.0.32. |
| `services/ai` | Transformers: 1 high | Runtime, transitive through sentence-transformers, reachable by reranking | Added security floor `>=5.10.0`; lock resolved to 5.16.1. |
| `services/ai` | PyJWT: 1 high, 3 medium, 1 low | Runtime, direct, reachable by authentication | Raised to `>=2.13.0`; lock resolved to 2.13.0. |
| `services/ai` | Bleach, pydantic-settings | Runtime, direct | Raised to Bleach 6.4.0 and pydantic-settings 2.14.2 or newer. |
| `services/ai` | setuptools, torch | Development/transitive or low severity | Updated by the lock refresh to setuptools 84.0.0 and torch 2.14.0. |
| `services/ai/requirements.txt` | python-jose, pytest, python-dotenv: 1 critical, 3 medium | Stale manifest deleted before this branch; none of these packages is installed from that path | No code change required; GitHub will close the stale alerts after scanning the updated default branch. Authentication uses PyJWT. |
| `apps/web` | NextAuth: 1 critical, 1 high, 1 medium | Runtime, direct, reachable by authentication | Upgraded to 4.24.15. |
| `apps/web` | Next.js: 3 high, 5 medium | Runtime, direct | Upgraded to the patched 15.5 line (15.5.25 in the lock). |
| `apps/web` | nanoid, PostCSS, sharp: 5 high, 2 medium | Runtime, transitive/direct; build and image paths | Updated to nanoid 3.3.18, PostCSS 8.5.26 and sharp 0.35.4. A global PostCSS override also replaces Next's vulnerable bundled version. |
| `apps/web` | browserslist, form-data, js-yaml, minimatch, ws, brace-expansion: 10 high, 2 medium | Development-only transitives; inert in the production image | Updated despite being dev-only. |
| `apps/web` | Babel, postcss-selector-parser, uuid: 2 low, 1 medium | Development-only except runtime UUID | Updated with the frontend lock refresh. |
| `workers/qvac-service` | No alerts | Runtime | `npm audit` reports zero vulnerabilities. |
| `workers/requirements.txt` | Docling: 5 high | Runtime in the legacy parser prototype; parser processes untrusted documents | Raised from 2.36.0 to `>=2.94.0`; ChromaDB was removed, and Pydantic, python-pptx and fastembed floors were raised to keep the tree resolvable. |

After the upgrades, `npm audit` reports zero vulnerabilities for both npm
trees. The Python lock contains none of the package versions identified by the
open alerts. There are therefore no accepted critical or high risks requiring
an issue comment.

Dependabot is configured to open grouped weekly updates every Monday against
`mvp-testing`, staggered by dependency tree to keep the resulting CI workload
predictable.
