# Grocery List

Blumberg family grocery list app. Email `grocery@myblumberg.com` in plain English; Claude parses and categorizes items into Produce, Meat, Dairy, Frozen, Deli, and Pantry.

Lives at **tools.myblumberg.com/grocery/**

## Architecture

```
[Email] → [Cloudflare Worker] → [FastAPI :8001] → [SQLite]
                                        ↕
                             [Static frontend at /grocery/]
```

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
```

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
