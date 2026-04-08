# Project Instructions

## Deployment (CRITICAL — READ FIRST)

This project runs on a **remote Hetzner VPS**, not locally. The user views the app at `http://100.111.249.12`. Local `docker compose up` does NOT update production.

**After ANY code change, you MUST deploy to the VPS.** Do not tell the user "it's working" based on local verification alone — they are looking at the remote server.

### Deploy steps
```bash
# 1. Sync code to VPS (excludes node_modules, .git, __pycache__, .env, .planning, .claude)
rsync -avz --delete \
  --exclude node_modules --exclude .git --exclude __pycache__ \
  --exclude .env --exclude .planning --exclude .claude \
  ./ root@46.225.233.32:/root/prophet-monitor/

# 2. Stop ALL containers (old and new) to free host ports
#    The local dir is OpsMonitoringDash but VPS dir is prophet-monitor.
#    Docker Compose uses the directory name as the project name, so old
#    containers may be named opsmonitoringdash-* while new ones are
#    prophet-monitor-*. Both use network_mode: host, so port conflicts
#    will cause restart loops if old containers aren't stopped first.
ssh root@46.225.233.32 "cd /root/prophet-monitor && docker compose down; docker ps -q | xargs -r docker stop; docker ps -aq | xargs -r docker rm"

# 3. Rebuild and restart on VPS
ssh root@46.225.233.32 "cd /root/prophet-monitor && docker compose build --no-cache frontend backend worker beat ws-consumer && docker compose up -d"

# 4. Verify all containers are running (not restarting)
sleep 15 && ssh root@46.225.233.32 "docker compose -f /root/prophet-monitor/docker-compose.yml ps"
```

### Post-deploy verification
After deploy, confirm services are healthy — don't just check container status:
```bash
# Check backend can reach DB and serve requests
ssh root@46.225.233.32 "curl -s http://127.0.0.1:8000/api/v1/health/workers" | python3 -m json.tool

# Check all workers are polling (not skipping)
ssh root@46.225.233.32 "docker compose -f /root/prophet-monitor/docker-compose.yml logs worker --tail 20 2>&1 | grep -E 'complete|skipped'"
```

## Production .env (HANDS OFF)

**NEVER use `sed`, `awk`, `>`, or any destructive edit on `/root/prophet-monitor/.env`.** This file contains API keys and secrets that cannot be recovered if deleted.

- To add a new key: `ssh root@46.225.233.32 "echo 'KEY=value' >> /root/prophet-monitor/.env"`
- To change an existing key: tell the user to edit manually via SSH
- To check current values: `ssh root@46.225.233.32 "grep SOME_KEY /root/prophet-monitor/.env"`

Past incidents:
- `sed -i` to fix duplicate Redis URLs also deleted the `OPTICODDS_API_KEY` line, breaking the OpticOdds poller
- `scp .env` overwrote all production credentials with local placeholders, taking down all workers

### Production .env required overrides (network_mode: host)
The production `.env` MUST have these values because all containers use `network_mode: host` (Docker service names like `postgres` and `redis` don't resolve):
- `POSTGRES_HOST=127.0.0.1`
- `REDIS_URL=redis://127.0.0.1:6379`
- `CELERY_BROKER_URL=redis://127.0.0.1:6379/0`
- `CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1`
- `REDBEAT_REDIS_URL=redis://127.0.0.1:6379/0`

If backend crashes with asyncpg `TimeoutError`, check these values first.

## Docker Compose gotchas

- **`docker compose restart` does NOT re-read `.env`**. If you changed `.env`, you must `docker compose up -d --force-recreate <service>` to pick up new env vars.
- **Ghost containers from different project names:** Local dir is `OpsMonitoringDash`, VPS dir is `prophet-monitor`. Docker Compose names containers after the directory. Old `opsmonitoringdash-*` containers can persist and hold host ports. Always kill all containers before starting new ones (step 2 in deploy).
- **Startup order:** Postgres and Redis must be healthy before backend starts. If backend crash-loops with connection errors after a full restart, just `docker compose restart backend worker beat ws-consumer` once Postgres shows `(healthy)`.

## Source Toggle Key Files

When modifying source toggles, these three lists MUST stay in sync:
- `backend/app/seed.py` — `SOURCE_ENABLED_DEFAULTS` dict
- `backend/app/api/v1/usage.py` — `source_toggle_keys` list
- `frontend/src/components/usage/SourceToggleSection.tsx` — `SOURCE_DISPLAY` map
