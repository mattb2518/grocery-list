# Grocery List — Product Spec

## What This Is
A mobile-first family web app for building, organizing, and archiving grocery lists.
Lives at `tools.myblumberg.com/grocery/`. Part of the `tools.myblumberg.com` suite.

## How It Works
Family members email `grocery@myblumberg.com` in freeform natural language.
A Cloudflare Worker receives the inbound email and forwards it to the backend.
The backend (Python/FastAPI) calls Claude to categorize each item and adds it to
the active list in SQLite. Items are attributed to the submitter.

There is also a "Check mail now" button that pulls unseen Gmail directly via IMAP
on demand, without waiting for the Cloudflare polling cycle.

The frontend is a single-page app served as static files. It displays items
organized by category, supports inline editing and re-categorization, and allows
archiving the active list after a shopping trip with selective item re-adding.

## Categories
Items are sorted into exactly six buckets:
- **Pantry** — shelf-stable goods, canned goods, oils, condiments, snacks, beverages, paper goods
- **Produce** — fresh fruits and vegetables
- **Meat** — meat, poultry, seafood
- **Dairy** — milk, cheese, eggs, yogurt, butter
- **Frozen** — anything frozen
- **Deli** — deli meats, prepared foods, cheeses from the deli counter

Item names are stored exactly as written in the original message — quantities, notes, and qualifiers (whether they appear before or after the item name) are preserved verbatim.
## Key Features
- Email-based input (freeform natural language)
- Submitter attribution on each item
- Inline item editing and re-categorization
- Archive active list → creates new empty active list
- Selective re-adding of items from archived lists
- "Check mail now" button for on-demand pull
- Mobile-first responsive UI using `shared.css` + `grocery.css`

## Architecture
- **Hosting:** Digital Ocean droplet (same as tools-directory and relationship intelligence app)
- **DNS/CDN:** Cloudflare
- **URL:** `tools.myblumberg.com/grocery/` (port 8001, proxied via Nginx)
- **Backend:** Python + FastAPI (`backend/main.py`)
- **Database:** SQLite (`data/grocery.db`)
- **Email routing:** Cloudflare Email Routing → Cloudflare Worker → `/inbound-email` endpoint
- **Worker:** `worker/index.js` (alternative receiver, not the live path — make.com is live)
- **Frontend:** Static HTML/JS (`frontend/index.html`, `frontend/app.js`)
- **Styles:** `shared.css` (from `/var/www/tools/shared.css`) + `frontend/grocery.css`
- **AI:** Anthropic Claude API (item categorization, called from backend)
- **Source control:** GitHub (`mattb2518/grocery-list`, private)

## Live Email Path
Gmail inbox → make.com scenario (polls ~15 min) → POST `/inbound-email`
The Cloudflare Worker exists as a fallback but is NOT the live path.

## Out of Scope (v1)
- iOS app
- Instacart / FreshDirect export
- Per-item checkoff during shopping
- Push notifications
- Sender allowlist enforcement
