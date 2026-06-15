# Grocery List

Blumberg family grocery list app. Email `grocery@myblumberg.com` in plain English; Claude parses and categorizes items into Produce, Meat, Dairy, Frozen, Deli, and Pantry.

Lives at **tools.myblumberg.com/grocery/**

## Architecture

```
[Grocery Gmail inbox] → [make.com scenario] → [FastAPI :8001] → [SQLite]
                                                     ↕
                                      [Static frontend at /grocery/]
```

Live ingestion is **push via make.com**: emails land in a Gmail inbox, a make.com
scenario polls Gmail (~15 min) and POSTs each message to `/inbound-email`. The
Cloudflare Worker in `worker/index.js` is an alternative receiver for the same
endpoint and is **not currently deployed** — kept as a fallback. The backend can
also **pull** Gmail directly over IMAP (see below), mainly for the on-demand
"Check mail now" button.

## Deployment (Droplet)

```bash
cd /opt/grocery-list
git pull
pip install -r backend/requirements.txt
systemctl restart grocery-list
```

Systemd service file at `/etc/systemd/system/grocery-list.service`:

```ini
[Unit]
Description=Grocery List API
After=network.target

[Service]
WorkingDirectory=/opt/grocery-list
EnvironmentFile=/opt/grocery-list/.env
ExecStart=/usr/local/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8001
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

Caddy config at `/etc/caddy/Caddyfile` (add under `tools.myblumberg.com`):

```
handle /grocery/* {
    reverse_proxy localhost:8001
}
```

FastAPI serves the frontend from the `frontend/` directory. The `/grocery/api/*` routes handle API calls; everything else serves `index.html`.

## Cloudflare Worker (Manual Setup Required)

The Worker in `worker/index.js` cannot be deployed until the following manual steps are complete:

1. **Create `grocery@myblumberg.com`** in Hosted Exchange as a mailbox or forward alias
2. **Configure Cloudflare Email Routing** to route `grocery@myblumberg.com` to the Worker
3. **Set up forwarding** in Exchange to the Cloudflare-provided inbound address
4. **Set `WORKER_SECRET`** in the Cloudflare Worker environment variables (dashboard → Worker → Settings → Variables → Secrets) — must match the value in `.env` on the droplet exactly
5. **Set `ANTHROPIC_API_KEY`** in `.env` on the droplet

Once steps 1–3 are done, deploy the Worker:

```bash
cd worker
npx wrangler deploy
```

Worker secrets are configured in the Cloudflare dashboard, **not** in `index.js` or any committed file.

## Environment Variables

Copy `.env.example` to `.env` and fill in values:

```
ANTHROPIC_API_KEY=    # from console.anthropic.com
WORKER_SECRET=        # generate a random string, e.g.: openssl rand -hex 32
DATABASE_PATH=./data/grocery.db

# Mailbox polling — powers the "Check mail now" button. Leave blank to disable.
IMAP_HOST=            # e.g. outlook.office365.com
IMAP_USER=            # grocery@myblumberg.com
IMAP_PASSWORD=        # mailbox / app password
IMAP_PORT=993
IMAP_FOLDER=INBOX
IMAP_SSL=true
POLL_INTERVAL_MINUTES=15   # auto-pull cadence; 0 disables the scheduled poll
```

### Mail ingestion: push + pull

The live path is **push via make.com** — Gmail inbox → make.com scenario →
`POST /inbound-email` (the Cloudflare Worker is an unused alternative receiver).
The backend can also **pull** the same Gmail inbox over IMAP:

- **Scheduled pull** — a background task started at app startup polls every
  `POLL_INTERVAL_MINUTES` (default 15). Set `POLL_INTERVAL_MINUTES=0` to disable it.
- **On-demand pull** — `POST /grocery/api/check-mail` (the "Check mail now" button)
  runs the same poll immediately.

Both read only **unseen** messages and mark them seen, so push and pull can't
double-add the same email.

## Local Development

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # then fill in values
uvicorn main:app --reload --port 8001
```

Open http://localhost:8001/

To test email ingestion without a real email:

```bash
curl -X POST http://localhost:8001/api/inbound-email \
  -H "Content-Type: application/json" \
  -H "X-Worker-Secret: your-secret" \
  -d '{"sender":"matt@myblumberg.com","subject":"groceries","body":"milk, eggs, chicken thighs, frozen pizza, sourdough bread"}'
```
