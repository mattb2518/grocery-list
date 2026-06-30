# Decisions Log

Append-only. New entries go at the top. Format: `## YYYY-MM-DD — Title`

---

## 2026-06-30 — Established GitHub as canonical source of truth
SPEC.md, DECISIONS.md, and docs/working-instructions.md added to repo.
Workflow: spec/design in Claude.ai chat → written to GitHub → Claude Code reads
from GitHub and builds. Spec-to-code is one-way; Claude Code never rewrites
the spec wholesale.

## 2026-06-14 — Live email path is make.com, not Cloudflare Worker
make.com scenario polls Gmail (~15 min) and POSTs to /inbound-email.
Cloudflare Worker (worker/index.js) exists as a fallback receiver for the same
endpoint but is NOT the live path. Decision: keep the Worker code but do not
assume it is active.

## 2026-06-14 — Added on-demand mail pull via IMAP
Backend can pull unseen Gmail directly via IMAP on demand (POST /check-mail).
Powers the "Check mail now" button. Exists so users don't have to wait for
make.com's ~15-min polling cycle. POLL_INTERVAL_MINUTES=0 recommended to avoid
duplicates with make.com.

## 2026-06-14 — Six fixed categories, no free-form tagging
Items sorted into exactly: pantry, produce, meat, dairy, frozen, deli.
Claude categorizes on ingest. Users can re-categorize inline via the frontend.
Categories are hardcoded; no user-defined categories in v1.

## 2026-06-14 — Archive creates new list, not a reset
Archiving the active list creates a new empty active list. The old list is
preserved and viewable. Items from archived lists can be selectively re-added
to the active list.

## 2026-06-14 — Shared CSS, grocery-specific overrides
All base styles come from /var/www/tools/shared.css (the tools suite shared
file). Grocery-specific styles go in frontend/grocery.css only. No color values
hardcoded; CSS variables used throughout.

## 2026-06-14 — SQLite as the database
Single SQLite file at data/grocery.db on the droplet. Two tables: items and
lists. There is always exactly one active list.
