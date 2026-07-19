# Decisions Log

Append-only. New entries go at the top. Format: `## YYYY-MM-DD — Title`

---

## Recipe import + Pantry Check zone + This Week's Recipes

Decision: Added recipe import via emailed URL, a 'Pantry Check — probably have' zone, and a 'This Week's Recipes' reference log.
- 'Probably have already' is a status (probably_have), not a seventh category. The six categories answer 'where in the store'; probably-have answers 'do I need to buy it.' Salt is both, so a peer category would force a misclassification. Keeping it orthogonal removes that conflict.
- Recipe import reuses the email pipeline: email a URL, backend detects a single-URL body and branches. No new input surface.
- This Week's Recipes is a deliberately simple log of URLs, NOT linked to the parsed items. It exists purely for reference/planning. Decoupling it from ingredients was an explicit scope choice to keep the feature small.
- Recipe URLs are logged regardless of parse success, so a paywalled recipe you still want to open manually isn't lost.
- Link text is the raw URL, not a parsed title, so success and failure render consistently.
- Per-recipe controls: 'x' hard-removes the logged link; archive control archives it with the list using the same mechanism items use.
- Staple detection is a static keyword list in the backend, not a Claude judgment. Predictable and editable; the human confirms in the Pantry Check zone, so a wrong flag costs one tap.
- Human-in-the-loop resolves have-vs-need. Email items = explicit buy -> main list. Recipe staples -> Pantry Check zone, default off; user taps what they're out of. The app never guesses pantry state.
- Extraction: JSON-LD recipeIngredient first, Claude-reads-page-text fallback. Paywalled/blocked sites fail with a visible notice item.
- Dedupe is best-effort (v0 limitation) because items are stored verbatim.

## 2026-07-03 — Preserve full item text on categorization
The original categorizer prompt told Claude to return a cleaned, normalized name, which stripped quantities, notes, and qualifiers (e.g. "Lemons (4)" became "Lemons", "Corn – 15-ish ears" became "Corn"). Changed the prompt to explicitly instruct Claude to preserve the complete original line exactly as written, regardless of whether extra text appears before or after the item name. This is more useful for shoppers and avoids lossy parsing.
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
