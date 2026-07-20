CLAUDE.md — Grocery List App
Project Overview
A mobile-friendly, single-page grocery list app for the Blumberg family. Lives at tools.myblumberg.com/grocery/. Family members email grocery@myblumberg.com in freeform natural language; the app parses, categorizes, and displays items organized by store section. Built to eventually support iOS and shopping service integrations (Instacart, FreshDirect).
Infrastructure Context
Droplet: Same DO droplet as tools-directory and relationship intelligence app
DNS/CDN: Cloudflare
URL: tools.myblumberg.com/grocery/
Port: 8001 (already registered in tools-directory Nginx config as a placeholder)
Backend language: Python (FastAPI)
Database: SQLite on the droplet
Email routing: grocery@myblumberg.com → forwards to blumberg.grocery Gmail → backend IMAP poll
Design
Link to /var/www/tools/shared.css for all base styles — this file was extracted from the existing tools and is the single source of truth for colors, typography, nav, cards, and buttons
Use CSS variables defined in shared.css (--color-accent, --color-background, --color-text, etc.) — do not hardcode any color values
Add a grocery.css for any grocery-specific styles only
The nav bar at the top must use the shared nav pattern already established in tools-directory and the relationships app
Mobile-first, responsive
Architecture Overview
[grocery@myblumberg.com] → [forwards to blumberg.grocery Gmail] → [backend IMAP poll every 15 min] → [SQLite]
                                                                              ↕
                                                               [Static frontend at /grocery/]
LIVE INGEST PATH: family emails land in blumberg.grocery Gmail; the backend polls Gmail over IMAP every 15 minutes (POLL_INTERVAL_MINUTES=15 in .env) and ingests unseen messages. All intelligence (Claude categorization) happens in the backend. make.com was previously used for push delivery but was retired in June 2026 — the backend now self-sufficiently pulls mail. make.com is left dormant as a fallback; dedup-by-name means no double-adds if it ever revives.
IMAP PULL (backend/mail_poller.py): polls Gmail (imap.gmail.com, App Password) for unseen mail. On demand via POST /api/check-mail (the "Check mail now" button). Scheduled via the POLL_INTERVAL_MINUTES env var (set to 15 on the droplet). Messages are marked seen only after successful ingest, so transient failures leave them unread for retry. insert_items dedupes by name within the active list.
RECIPE PATH: if an ingested email's body contains a bare https:// URL on any line, the backend routes to recipe_parser.py instead of the freeform categorizer. URL detection scans all lines (not just the first) to handle Outlook forwarded-message headers (From/Sent/To/Subject) that precede the URL. URL is logged to the recipes table first. Ingredients extracted via schema.org JSON-LD (recipeIngredient) first, Claude page-text fallback second. Each ingredient is categorized through the existing categorizer unchanged; staples (matched against staples.py keyword list) get probably_have=1 and render in the Pantry Check zone. Parse failures produce one visible notice item. Both paths share the same dedup-by-name logic. recipe_parser.py uses a realistic Chrome browser User-Agent with Accept headers — many recipe sites (Cloudflare-protected) block bot UA strings with 403.
The Cloudflare Worker in worker/index.js is an ALTERNATIVE push receiver for /api/inbound-email and is NOT currently deployed/in use. Keep the Worker code as a fallback but do not assume it is the live path.
Repository & File Structure
grocery-list/
├── CLAUDE.md
├── README.md
├── backend/
│   ├── main.py              ← FastAPI app
│   ├── categorizer.py       ← Claude API call for item categorization
│   ├── recipe_parser.py     ← fetch URL, JSON-LD extraction, Claude fallback
│   ├── staples.py           ← static staple keyword list + is_staple()
│   ├── mail_poller.py       ← IMAP pull: scheduled + on-demand mailbox polling
│   ├── database.py          ← SQLite setup and queries
│   ├── models.py            ← Pydantic models
│   └── requirements.txt
├── frontend/
│   ├── index.html           ← single page app
│   ├── grocery.css          ← grocery-specific styles only
│   └── app.js
├── worker/
│   └── index.js             ← Cloudflare Worker (deployed separately, not active)
├── data/
│   └── grocery.db           ← SQLite, gitignored
└── .env.example             ← documents required env vars, never commit .env
Data Model
items table
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    submitted_at DATETIME NOT NULL,
    list_id INTEGER NOT NULL,
    checked INTEGER DEFAULT 0,
    probably_have INTEGER DEFAULT 0
);
probably_have=1 means the item is a detected pantry staple from a recipe. It renders in the Pantry Check zone instead of the main list. Tapping "Need it" sets probably_have=0 and moves it to the main list.
lists table
CREATE TABLE lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    archived_at DATETIME,
    label TEXT
);
category_overrides table
CREATE TABLE category_overrides (
    name_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    updated_at DATETIME NOT NULL
);
Stores learned re-categorizations: when a user re-files an item via the category chips, the correction is recorded here and re-applied on future ingests of the same item name. The 40 most recent overrides are also sent to Claude as few-shot examples to improve future categorizations.
recipes table (reference log — NOT linked to items)
CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    submitter TEXT NOT NULL,
    archived INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL
);
Logged whenever a recipe URL is emailed — before parsing, so success and failure both get a record. archived=0 = on the active trip's This Week's Recipes; archived=1 = in the Recipe Library (permanent, cross-list). archive_active_list() sweeps the trip's archived=0 recipes to archived=1 automatically. archive_checked_items() does NOT sweep recipes — the active trip continues.
There is always exactly one active list. Archiving creates a new active list.
Categories
Items must be sorted into exactly one of these six buckets:
pantry — shelf-stable goods, canned goods, oils, condiments, snacks, beverages, paper goods
produce — fresh fruits and vegetables
meat — meat, poultry, seafood
dairy — milk, cheese, eggs, yogurt, butter
frozen — anything frozen
deli — deli meats, prepared foods, cheeses from the deli counter
Backend — FastAPI (main.py)
All API endpoints are prefixed with /api/.
Endpoints
POST /api/inbound-email — receives push delivery (Cloudflare Worker or make.com), requires X-Worker-Secret header
POST /api/check-mail — pulls unseen mail from the IMAP mailbox on demand, categorizes, and adds items (powers the "Check mail now" button)
GET /api/list — returns active list with all items
POST /api/archive — archives the active list; body {checked_only: false, label?: str} archives the full list and creates a new empty active list, {checked_only: true} archives only checked items into a new past list and leaves unchecked items active; optional label is stored with the archived list
POST /api/item/{item_id}/check — sets the checked flag on an active-list item ({checked: bool})
POST /api/item/{item_id}/edit — renames an active-list item ({name: str}); powers the inline ✎ edit on each item
POST /api/item/{item_id}/category — moves an active-list item to a different section ({category: str}, must be one of the six categories); also records a category_override so future ingests of the same name land in the right bucket
GET /api/archived — returns all archived lists (summary)
GET /api/archived/{list_id} — returns full items for archived list
POST /api/restore/{list_id} — copies all items from an archived list into the active list
POST /api/add-items — adds specific items (by id) from an archived list to the active list ({item_ids: [int]})
POST /api/add-item — adds a single item directly from the web UI ({name: str, submitted_by: str}); runs through the categorizer (with override lookup) and dedupes
DELETE /api/item/{item_id} — removes item from active list
POST /api/item/{item_id}/probably-have — sets probably_have on an active-list item ({probably_have: bool}); setting false moves it from Pantry Check zone to the main list
DELETE /api/recipe/{recipe_id} — permanently deletes a recipe (works for both active and Library entries)
POST /api/recipe/{recipe_id}/archive — sets archived=1; sends the recipe from This Week's Recipes into the Recipe Library
GET /api/recipes/library — returns all recipes with archived=1 across all list_ids, newest first (powers the Library view)
Security
The /api/inbound-email endpoint requires X-Worker-Secret header matching .env value
All other endpoints unauthenticated in v1
Cloudflare Worker (worker/index.js)
Deployed separately via Wrangler CLI — not currently active. Would receive push email from Cloudflare Email Routing and forward to /api/inbound-email.
Worker secrets set in Cloudflare dashboard, not in code.
Manual Setup Steps (Claude Code cannot do these)
1. Gmail account blumberg.grocery@gmail.com with App Password for IMAP access
2. grocery@myblumberg.com forwards to blumberg.grocery Gmail
3. Set IMAP_HOST, IMAP_USER, IMAP_PASS, POLL_INTERVAL_MINUTES in .env on droplet
4. Set WORKER_SECRET in .env on droplet (and in Cloudflare Worker env vars if Worker is ever activated — must match)
5. Set ANTHROPIC_API_KEY in .env on droplet
Deployment
Backend runs as systemd service on DO droplet, port 8001
Caddy/Nginx proxies /grocery/ → localhost:8001
Frontend static files served by FastAPI's StaticFiles mount at "/" (from /frontend directory)
POLL_INTERVAL_MINUTES=15 is the live setting on the droplet; the backend polls Gmail every 15 min
Future Considerations (out of scope v1)
iOS app, Instacart/FreshDirect export, push notifications, sender allowlist
Spec Maintenance Rule
Before the final commit of any session, update this file (CLAUDE.md) to reflect any new decisions, patterns, features completed, or status changes made during the session. The spec update must be included in the same commit as the code — not as a follow-up. Things worth capturing: new endpoints, changed data model, revised architecture, env vars added, deployment changes, decisions about what was tried and rejected, and anything that would surprise a future contributor reading the spec cold.
