# DevLens , AWS private-alpha deployment

Single EC2 box (t3.medium), all services via `docker-compose.prod.yml`, fronted by
Caddy with free Let's Encrypt HTTPS. Visitors hit a branded login page and must enter a
shared access key (`DEVLENS_GATE_SECRET`) before reaching the app, so it stays invite-only.

## What you need
- AWS CLI configured (`aws sts get-caller-identity` works)
- An OpenRouter key (embeddings and LLM) and a GitHub OAuth app
- No domain needed: the hostname is derived from the instance IP via sslip.io

## 1. Provision the instance
```bash
AWS_REGION=us-east-1 INSTANCE_TYPE=t3.medium bash deploy/provision-aws.sh
```
Note the **Elastic IP** and the saved `devlens-key.pem`. (t3.medium is well inside the
$150 credit for year 1; set an AWS billing alarm so you are never surprised.)

## 2. Derive your hostname (sslip.io)
No DNS setup needed, the hostname is the Elastic IP via sslip.io. For IP `52.1.2.3`
it is `52-1-2-3.sslip.io` (dashes) or `52.1.2.3.sslip.io`. Confirm with
`nslookup 52-1-2-3.sslip.io`. Use this as `DEVLENS_DOMAIN` below. (If Let's Encrypt
ever rate-limits sslip.io, fall back to a free DuckDNS subdomain.)

## 3. GitHub OAuth app
Use your existing OAuth app (or create one). Set the **Authorization callback URL** to:
```
https://<your-sslip-host>/api/v1/auth/callback
```
and the Homepage URL to `https://<your-sslip-host>`.

## 4. Ship the repo + config to the box
```bash
ssh -i devlens-key.pem ubuntu@<ELASTIC_IP>
git clone https://github.com/atikulmunna/devlens-fullstack.git && cd devlens-fullstack
cp deploy/env.prod.example .env.prod
nano .env.prod   # fill DEVLENS_DOMAIN, TLS email, DEVLENS_GATE_SECRET, OpenRouter key, GitHub OAuth, JWT_SECRET, strong POSTGRES_PASSWORD
```
Keep `DATABASE_URL`'s password in sync with `POSTGRES_PASSWORD`.

## 5. Set the access key
`DEVLENS_GATE_SECRET` in `.env.prod` is the shared access key for the branded login page.
Hand it to people you invite; rotate it (and recreate Caddy) to revoke access for everyone.

## 6. Bring it up
```bash
bash deploy/bootstrap.sh
```
This installs Docker, adds swap, builds + starts the stack, and runs migrations.
First build is slow (a few minutes) because of the backend image.

## 7. Verify
- `https://<your-sslip-host>` shows the branded login page; the access key lets you in.
- After entering the key, the workspace loads; "Login with GitHub" enables chat.
- Analyze a small repo (e.g. `https://github.com/pallets/markupsafe`), then chat and
  open the commit-diff view.

## Operations
- **Update:** back up first (see Backups), then build, migrate, and only then start the new worker. The worker
  reads new columns as soon as it starts, so starting it before migrating makes it crash-loop until the
  schema catches up.
  ```bash
  git pull
  C="sudo docker compose -f docker-compose.prod.yml --env-file .env.prod"
  $C build
  $C up -d backend                                   # also starts postgres, redis, qdrant
  $C exec -T backend alembic -c alembic.ini upgrade head
  $C up -d                                           # worker, frontend, caddy
  $C restart caddy                                   # Caddyfile and gate.html are single-file mounts
  ```
- **Backups:** `sudo docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U postgres devlens > backup-$(date +%F).sql` (cron it).
- **Logs:** `sudo docker compose -f docker-compose.prod.yml logs -f backend worker`
- **Restart on reboot:** handled by `restart: unless-stopped` on every service.
- **Billing alarm:** create a CloudWatch billing alarm (e.g. at $20) so credit burn stays visible.

## Teardown
```bash
# On the box:
sudo docker compose -f docker-compose.prod.yml --env-file .env.prod down -v
# From your laptop (releases the Elastic IP and terminates the instance):
aws ec2 terminate-instances --instance-ids <INSTANCE_ID> --region us-east-1
aws ec2 release-address --allocation-id <ALLOC_ID> --region us-east-1
```

## Notes
- Auth model (two layers): Caddy gates all traffic behind a cookie set by the branded
  login page (the shared `DEVLENS_GATE_SECRET`). The cookie does not touch the
  Authorization header, so the app's own JWT bearer auth works unchanged, chat and
  commit-diff require signing in with GitHub inside the app. So a tester needs the access
  key (to pass the gate) plus a GitHub login for chat.
- Share links (`/share/...`) skip the gate, along with the share API and the app's static
  files, so anyone with a link can read that one overview. Everything else still needs the key.
- The reranker is forced off in prod (`RERANKER_ENABLED=false`) to keep the box light;
  dense + lexical retrieval still runs. Flip it on later if you size up.
- The backend is never exposed directly; Caddy serves the Next.js frontend, which
  proxies `/api/v1` to the backend inside the compose network.
