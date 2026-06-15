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
Email routing: Cloudflare Email Routing → Cloudflare Worker → this API
Design
Link to /var/www/tools/shared.css for all base styles — this file was extracted from the existing tools and is the single source of truth for colors, typography, nav, cards, and buttons
Use CSS variables defined in shared.css (--color-accent, --color-background, --color-text, etc.) — do not hardcode any color values
Add a grocery.css for any grocery-specific styles only
The nav bar at the top must use the shared nav pattern already established in tools-directory and the relationships app
Mobile-first, responsive
Architecture Overview
[Grocery Gmail inbox] → [make.com scenario] → [FastAPI on DO :8001] → [SQLite]
                                                      ↕
                                       [Static frontend at /grocery/]
LIVE PUSH PATH (in use): family emails land in a Gmail inbox; a make.com scenario polls Gmail (~15 min) and POSTs each message to POST /inbound-email. All intelligence (Claude categorization) happens in the backend.
The Cloudflare Worker in worker/index.js is an ALTERNATIVE receiver for the same /inbound-email endpoint and is NOT currently deployed/in use — the make.com path was chosen instead. Keep the Worker code as a fallback but do not assume it is the live path.
PULL PATH (backend/mail_poller.py): the backend can also pull the Gmail inbox directly over IMAP — on demand via POST /check-mail (the "Check mail now" button, the main reason this exists: pull now instead of waiting for make.com's cycle) and optionally on a schedule (every POLL_INTERVAL_MINUTES). Recommended to run with POLL_INTERVAL_MINUTES=0 so the backend does not duplicate make.com's scheduled polling. All paths share the same ingest code; the poller reads only unseen mail and marks it seen, and insert_items dedupes by name, so nothing is double-added.
Repository & File Structure
grocery-list/
├── CLAUDE.md
├── README.md
├── backend/
│   ├── main.py              ← FastAPI app
│   ├── categorizer.py       ← Claude API call for item categorization
│   ├── mail_poller.py       ← IMAP pull: scheduled + on-demand mailbox polling
│   ├── database.py          ← SQLite setup and queries
│   ├── models.py            ← Pydantic models
│   └── requirements.txt
├── frontend/
│   ├── index.html           ← single page app
│   ├── grocery.css          ← grocery-specific styles only
│   └── app.js
├── worker/
│   └── index.js             ← Cloudflare Worker (deployed separately)
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
    checked INTEGER DEFAULT 0
);
lists table
CREATE TABLE lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    archived_at DATETIME,
    label TEXT
);
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
Endpoints
POST /inbound-email — receives from Cloudflare Worker, requires X-Worker-Secret header
POST /check-mail — pulls unseen mail from the IMAP mailbox on demand, categorizes, and adds items (powers the "Check mail now" button)
GET /list — returns active list with all items
POST /archive — archives the active list; body {checked_only: false} archives the full list and creates a new empty active list, {checked_only: true} archives only checked items into a new past list and leaves unchecked items active
POST /item/{item_id}/check — sets the checked flag on an active-list item ({checked: bool})
POST /item/{item_id}/edit — renames an active-list item ({name: str}); powers the inline ✎ edit on each item
GET /archived — returns all archived lists (summary)
GET /archived/{list_id} — returns full items for archived list
POST /restore/{list_id} — copies archived list items into active list
POST /add-items — adds specific items (by id) from archived list to active list
DELETE /item/{item_id} — removes item from active list
Security
The /inbound-email endpoint requires X-Worker-Secret header matching .env value
All other endpoints unauthenticated in v1
Cloudflare Worker (worker/index.js)
Deployed separately via Wrangler CLI — cannot deploy until Cloudflare Email Routing configured manually.
Worker secrets set in Cloudflare dashboard, not in code.
Manual Setup Steps (Claude Code cannot do these)
1. Create grocery@myblumberg.com in Hosted Exchange as mailbox or forward alias
2. Configure Cloudflare Email Routing to route grocery@myblumberg.com to the Worker
3. Set up forwarding in Exchange to the Cloudflare inbound address
4. Set WORKER_SECRET in both .env on droplet AND in Cloudflare Worker env vars — must match exactly
5. Set ANTHROPIC_API_KEY in .env on droplet
Deployment
Backend runs as systemd service on DO droplet, port 8001
Caddy/Nginx proxies /grocery/ → localhost:8001
Frontend static files served by FastAPI from /frontend directory
Future Considerations (out of scope v1)
iOS app, Instacart/FreshDirect export, per-item checkoff, push notifications, sender allowlist
