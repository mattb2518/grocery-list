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

Recipe import: if the emailed body is a single URL, the backend treats it as a recipe. It fetches the page, extracts the ingredient list (schema.org JSON-LD first, Claude fallback), and adds each ingredient as an item. Separately, the URL itself is logged to a recipes reference list shown below the items. Ingredients matching the staples list are routed to the Pantry Check zone instead of the main list.

## Categories
Items are sorted into exactly six buckets:
- **Pantry** — shelf-stable goods, canned goods, oils, condiments, snacks, beverages, paper goods
- **Produce** — fresh fruits and vegetables
- **Meat** — meat, poultry, seafood
- **Dairy** — milk, cheese, eggs, yogurt, butter
- **Frozen** — anything frozen
- **Deli** — deli meats, prepared foods, cheeses from the deli counter

Item names are stored exactly as written in the original message — quantities, notes, and qualifiers (whether they appear before or after the item name) are preserved verbatim.

These six are store-section categories (where an item lives in the store). 'Probably have already' is deliberately NOT a seventh category — it is a status (probably_have) orthogonal to the six. It controls display, not store section, so a staple like salt can be both a Pantry item and a probably-have item without a misclassification conflict.

## Recipe Import
- Trigger: an email whose body is a single URL.
- Extraction: schema.org JSON-LD recipeIngredient first; if absent, Claude reads the page text and extracts ingredients.
- Each ingredient is stored verbatim and categorized into the six buckets.
- Ingredients matching the static staples list get probably_have = true and render in the Pantry Check zone, not the main list.
- Failure (paywall, block, no ingredients found): the app adds one visible notice item ('Couldn't read recipe: <url>') rather than failing silently.
- Dedupe against the active list is best-effort in v0 (verbatim storage means 'kosher salt, to taste' and 'salt' may not match).

## This Week's Recipes
- A reference list below the items shows every recipe URL emailed into the active list — logged whether or not the parse succeeded. It is a simple log: it does NOT link to the parsed ingredients.
- Each entry: the URL as a clickable link (opens in a new tab), an 'x' to remove it outright, and an archive control that archives it with the list using the same mechanism items use.
- Removing (x) deletes only the logged link. Archiving carries it into the archived list like any item.

## Key Features
- Email-based input (freeform natural language)
- Submitter attribution on each item
- Inline item editing and re-categorization
- Archive active list → creates new empty active list
- Selective re-adding of items from archived lists
- "Check mail now" button for on-demand pull
- Mobile-first responsive UI using `shared.css` + `grocery.css`
- Recipe import via emailed URL
- Pantry Check zone — collapsed, default off; tap an item to move it to the main list
- This Week's Recipes — reference log of emailed recipe URLs (clickable, removable, archives with the list)

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
- New recipes table (reference log, not linked to items): id, list_id, url, submitter, archived (default 0), created_at
- Items table: gains probably_have (bool, default false)

## Live Email Path
Gmail inbox → make.com scenario (polls ~15 min) → POST `/inbound-email`
The Cloudflare Worker exists as a fallback but is NOT the live path.

## Out of Scope (v1)
- iOS app
- Instacart / FreshDirect export
- Per-item checkoff during shopping
- Push notifications
- Sender allowlist enforcement
