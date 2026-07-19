# DevLens , AWS private-alpha deployment

Single EC2 box (t3.medium), all services via `docker-compose.prod.yml`, gated by
Caddy Basic Auth with free Let's Encrypt HTTPS. Only people you issue credentials
to can reach the app.

## What you need
- AWS CLI configured (`aws sts get-caller-identity` works)
- A free DuckDNS subdomain (https://www.duckdns.org , sign in, create a subdomain)
- Your NVIDIA NIM + Groq keys, and a GitHub OAuth app

## 1. Provision the instance
```bash
AWS_REGION=us-east-1 INSTANCE_TYPE=t3.medium bash deploy/provision-aws.sh
```
Note the **Elastic IP** and the saved `devlens-key.pem`. (t3.medium is well inside the
$150 credit for year 1; set an AWS billing alarm so you are never surprised.)

## 2. Point DuckDNS at the box
On duckdns.org, set your subdomain's IP to the Elastic IP from step 1. Confirm:
`nslookup yourname.duckdns.org` returns that IP.

## 3. GitHub OAuth app
Use your existing OAuth app (or create one). Set the **Authorization callback URL** to:
```
https://yourname.duckdns.org/api/v1/auth/callback
```
and the Homepage URL to `https://yourname.duckdns.org`.

## 4. Ship the repo + config to the box
```bash
ssh -i devlens-key.pem ubuntu@<ELASTIC_IP>
git clone https://github.com/atikulmunna/devlens-fullstack.git && cd devlens-fullstack
cp deploy/env.prod.example .env.prod
nano .env.prod   # fill DEVLENS_DOMAIN, TLS email, NIM/Groq keys, GitHub OAuth, JWT_SECRET, strong POSTGRES_PASSWORD
```
Keep `DATABASE_URL`'s password in sync with `POSTGRES_PASSWORD`.

## 5. Create alpha credentials
```bash
bash deploy/adduser.sh alice          # prints a generated password
bash deploy/adduser.sh bob s3cret     # or set one
```
Each tester gets their own username/password. Revoke by deleting their line in
`deploy/alpha_users` and re-running any `adduser.sh` (it reloads Caddy).

## 6. Bring it up
```bash
bash deploy/bootstrap.sh
```
This installs Docker, adds swap, builds + starts the stack, and runs migrations.
First build is slow (a few minutes) because of the backend image.

## 7. Verify
- `https://yourname.duckdns.org` prompts for Basic Auth (401 without it).
- With a tester credential, the workspace loads; "Login with GitHub" enables chat.
- Analyze a small repo (e.g. `https://github.com/pallets/markupsafe`), then chat and
  open the commit-diff view.

## Operations
- **Update:** `git pull && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
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
- The reranker is forced off in prod (`RERANKER_ENABLED=false`) to keep the box light;
  dense + lexical retrieval still runs. Flip it on later if you size up.
- The backend is never exposed directly; Caddy serves the Next.js frontend, which
  proxies `/api/v1` to the backend inside the compose network.
