# Testing DevLens

Two parts: what a tester does, and how the owner opens the demo for a test session and closes it
again afterwards. The demo runs on one AWS instance that is stopped between sessions, so it only
costs money while someone is actually trying it.

## For testers

### Getting in

You need two things from the owner, sent privately: the site's address and an access key.

1. Open the address. You see the DevLens access page.
2. Enter the access key. Your browser stays signed in to the site for 30 days.
3. To ask questions or look at commit changes, click **Sign in with GitHub** in the header. Any
   GitHub account works. DevLens reads your GitHub profile and email address, nothing else: it
   gets no access to your repositories.

If the page does not load at all, the demo is probably switched off. Ask the owner to start it.

### What to try

1. **Analyze a repository.** Paste a public GitHub URL on the home page, for example
   `https://github.com/pallets/itsdangerous`. A small repository takes a minute or two, and the
   steps show their progress as they run. Repositories over 8,000 source files are turned away.
2. **Overview.** The architecture summary, language mix, contributors, code health (long
   functions linked to their lines on GitHub), hotspots, the import explorer, and the file tree.
3. **Chat.** Ask how something works, for example "How are tokens signed?". Answers cite the
   files and lines they come from; the small numbers open those lines on GitHub. Earlier chats are
   listed on the left. You can stop an answer or copy it.
4. **Changes.** Pick an analyzed commit to see each changed file's diff, the security-sensitive
   lines with how serious they are, and the files that import the change, drawn as rings. You can
   ask questions about the commit too.
5. **Share.** On a repository page, **Share** makes a read-only link to its Overview that works
   for 7 days without a key or a sign-in. **Stop sharing** turns it off.
6. **Dark mode.** The moon button in the header. Your browser remembers the choice.

### Good to know

- You can make 50 requests an hour while signed in (analyses, questions), and 10 without signing
  in. At the limit, an analysis says "Rate limit exceeded" and the chat says how long to wait;
  either way, try again later in the hour.
- Answers describe the commit that was analyzed. If the repository changed since, analyze it
  again to pick up the new code.
- Hotspots need an analysis made after 2026-11-01. On an older one, the card says to analyze the
  repository again.
- To get comments on your own pull requests, add the Action described in the
  [README](README.md#what-it-does) to your repository. It runs in your CI and does not need this
  demo.

### Reporting a problem

Note the address of the page, what you did, and what you expected. A screenshot helps. Send it to
the owner or open an issue on the repository.

## For the owner: running a test session

Everything below runs from a clone of this repository on your computer, with the AWS CLI signed
in to the account that hosts the demo. Set these two once per terminal:

```bash
ID=<INSTANCE_ID>                  # the instance from provisioning (deploy/aws.md)
SITE=https://<your-sslip-host>    # the address testers open
```

### 1. Start the demo

```bash
aws ec2 start-instances --region us-east-1 --instance-ids $ID
aws ec2 wait instance-status-ok --region us-east-1 --instance-ids $ID
curl -s -o /dev/null -w "%{http_code}\n" $SITE/     # 200 means the access page is up
```

The address does not change between sessions (the instance keeps its Elastic IP), and the
services start by themselves when the instance boots. To see them:

```bash
bash deploy/remote.sh $ID 'cd ~/devlens-fullstack && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod ps'
```

All seven (backend, worker, frontend, caddy, postgres, redis, qdrant) should be up, and postgres,
redis, and the backend should say healthy.

### 2. Give testers access

Read the current access key on the server:

```bash
bash deploy/remote.sh $ID 'grep ^DEVLENS_GATE_SECRET ~/devlens-fullstack/.env.prod'
```

Send the address and the key to each tester privately, by direct message or email, never in an
issue or a public channel.

To lock everyone out and start fresh (for example after a session with testers you will not
invite again), rotate the key. Everyone, you included, needs the new key afterwards:

```bash
bash deploy/remote.sh $ID 'cd ~/devlens-fullstack && sed -i "s/^DEVLENS_GATE_SECRET=.*/DEVLENS_GATE_SECRET=$(openssl rand -hex 24)/" .env.prod && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod up -d caddy frontend'
```

For someone who only needs to read one repository's Overview, a share link is enough: sign in,
open the repository, click **Share**, and send the link. It needs no key.

### 3. During the session

- Logs: `bash deploy/remote.sh $ID 'cd ~/devlens-fullstack && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod logs --since 30m backend worker'`
- Analyses and questions use the OpenRouter key on the server, so a busy session costs a few
  cents of model usage on top of the instance.

### 4. Stop the demo

```bash
aws ec2 stop-instances --region us-east-1 --instance-ids $ID
aws ec2 wait instance-stopped --region us-east-1 --instance-ids $ID
aws ec2 describe-instances --region us-east-1 --instance-ids $ID --query "Reservations[0].Instances[0].State.Name" --output text
```

The last command should print `stopped`. Stopping keeps everything: analyses, chats, share
links, the access key, and the address. Testers just cannot reach the site until you start it
again.

While stopped, the instance itself costs nothing. Its disk and its fixed IP address still cost
about $5 a month together. To bring that to zero, tear the deployment down instead (see
[`deploy/aws.md`](deploy/aws.md#teardown)); that deletes the data and gives up the address.

### If something goes wrong

- **`remote.sh` says the instance is not connected.** Systems Manager can take a minute after a
  start. If it still fails after a few minutes, reboot once:
  `aws ec2 reboot-instances --region us-east-1 --instance-ids $ID`.
- **The site does not load after a start.** Give it two minutes, then check the services as in
  step 1. `sudo docker compose -f docker-compose.prod.yml --env-file .env.prod up -d` in
  `~/devlens-fullstack` starts any that are down.
- **An analysis stays queued.** Look at the worker's log (step 3).
- **Updating the code** is a separate procedure with a backup and migrations; follow
  [`deploy/aws.md`](deploy/aws.md#operations).
