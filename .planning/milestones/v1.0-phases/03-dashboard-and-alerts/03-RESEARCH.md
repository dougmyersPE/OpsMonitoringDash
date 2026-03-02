# Phase 3: Dashboard and Alerts - Research

**Researched:** 2026-02-26
**Domain:** React SPA (Vite + shadcn/ui), FastAPI SSE, Redis Pub/Sub, Slack SDK, Nginx SSE proxy
**Confidence:** HIGH for backend SSE + Slack patterns; HIGH for React stack; MEDIUM for SSE auth workaround

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | Real-time dashboard shows all ProphetX events with ProphetX status vs. real-world status; mismatches highlighted | React Vite SPA + TanStack Query for initial data fetch; SSE invalidation for live updates; conditional row highlight via Tailwind |
| DASH-02 | Dashboard shows all markets with current liquidity vs. threshold; below-threshold markets highlighted | Same pattern as DASH-01; Markets table with threshold column; red highlight when current_liquidity < threshold |
| DASH-03 | Dashboard updates via SSE within 30 seconds of any status or liquidity change | FastAPI SSE endpoint with sse-starlette; Redis pub/sub channel for worker→API fan-out; TanStack Query invalidateQueries on event received |
| DASH-04 | Dashboard shows system health indicator: polling workers active/stopped, last-checked timestamps per event | New `/api/v1/health/workers` endpoint reading Redis heartbeat keys written by each poll worker; display in header bar |
| ALERT-01 | System sends Slack webhook alerts for all alertable conditions | `send_alerts` Celery task (Phase 2 stub) wired to `slack_sdk` `WebhookClient.send()` with SLACK_WEBHOOK_URL config |
| ALERT-02 | Alert deduplication: max 1 alert per event per condition type per 5-minute window (Redis TTL) | Redis SETNX key `alert_dedup:{alert_type}:{entity_id}` with 300-second TTL; checked before every Slack call |
| ALERT-03 | Alert-only mode: when enabled, system detects but takes no write actions to ProphetX API | `system_config` key `alert_only_mode` already exists; `update_event_status` task reads it and short-circuits before API call |
| NOTIF-01 | In-app notification center: bell icon + sliding panel, all system events, read/unread state, navigation on click | `Notification` model already exists (Phase 2); new `/api/v1/notifications` endpoints for list/mark-read; Bell icon + Sheet from shadcn/ui |
</phase_requirements>

---

## Summary

Phase 3 has two clearly separated halves: a React frontend SPA and backend wiring for alerting. The backend alerting half (Plans 03-02 and partial 03-03) is almost entirely completing work already stubbed in Phase 2 — `send_alerts.py` exists and needs Slack SDK wired in, the `Notification` model exists and needs CRUD endpoints, `alert_only_mode` config key already exists and just needs to be respected in `update_event_status`. The main engineering work is the React frontend (Plan 03-01) and production Nginx/Docker hardening (Plan 03-03).

The React SPA uses the established 2025 stack: Vite 6+ with React 19, TypeScript, shadcn/ui + Tailwind CSS, TanStack Query v5 for server state, and Zustand for client state (auth token). The SSE integration follows the standard pattern: a FastAPI endpoint using `sse-starlette` streams events, a Celery worker publishes to a Redis pub/sub channel on any state change, and the SSE endpoint subscribes to that channel and fans out to connected browser clients. When the browser receives an SSE message it calls `queryClient.invalidateQueries()` to trigger a refetch.

The single significant gotcha across the whole phase is the **EventSource API cannot send Authorization headers** — the browser's native `EventSource` is header-blind. The clean solution for an internal ops tool is to pass the JWT as a short-lived query parameter on the SSE URL (`?token=...`) and validate it server-side in the FastAPI dependency. Nginx SSE support requires exactly four directives added to the `/api/v1/stream` location block: `proxy_buffering off`, `proxy_cache off`, `proxy_http_version 1.1`, and `proxy_read_timeout 86400s`.

**Primary recommendation:** Build the SSE backend endpoint and Redis pub/sub fan-out before building any React UI — this lets you validate the 30-second update window against real worker events before the frontend exists.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vite | 6.x (create-vite 8.x) | React SPA build tool + dev server | 40x faster than CRA; zero-config TypeScript; standard 2025 React scaffold |
| React | 19.x | UI framework | Latest stable; TanStack Query v5 confirmed compatible |
| TypeScript | 5.x | Type safety | Included in Vite react-ts template; no extra config |
| shadcn/ui | latest (CLI-based) | Accessible component primitives | Built on Radix UI + Tailwind; ships source files not node_modules; Table, Sheet, Badge, Button already needed |
| Tailwind CSS | 4.x (Vite plugin) | Utility-first styling | Required by shadcn/ui; Vite plugin handles JIT without PostCSS config |
| TanStack Query | 5.90.x | Server state management | Handles caching, refetch, stale-while-revalidate; invalidateQueries is the idiomatic SSE integration |
| Zustand | 5.x | Client state (auth token, alert-only toggle) | Minimal boilerplate; no provider needed; 2025 standard for auth stores in SPAs |
| React Router | 7.x (declarative mode) | SPA routing | Declarative mode = simple BrowserRouter; no SSR needed for this internal tool |
| axios | 1.x | HTTP client for API calls | Interceptors handle 401→redirect to login without per-call handling |
| sse-starlette | 3.2.x | FastAPI SSE endpoint (backend) | Production-ready; `EventSourceResponse` + `ping` heartbeat; actively maintained |
| slack-sdk | 3.x | Slack webhook delivery (backend) | Official Slack Python SDK; `WebhookClient.send()` is sync-safe in Celery |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Lucide React | latest | Icon set (Bell, CheckCircle, AlertTriangle, etc.) | Included with shadcn/ui scaffold; do not add a separate icon library |
| @tanstack/react-query-devtools | 5.x | Query cache inspector | Dev only; add to vite.config devDependencies |
| date-fns | 3.x | Timestamp formatting in tables | Lightweight; no moment.js |
| clsx + tailwind-merge | latest | Conditional className composition | shadcn/ui uses both internally via `cn()` helper |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| shadcn/ui + Tailwind | Ant Design / MUI | Ant/MUI bring full CSS-in-JS weight and opinionated themes; shadcn gives composable primitives and zero runtime CSS overhead |
| TanStack Query | SWR | Both work; TanStack Query v5 has stronger TypeScript types and the `invalidateQueries` pattern is more explicit for SSE use case |
| Zustand | React Context + useReducer | Context causes full tree re-renders on every auth change; Zustand uses selectors for surgical re-renders |
| sse-starlette | FastAPI `StreamingResponse` + manual SSE | sse-starlette handles ping/disconnect/spec compliance; hand-rolling misses edge cases |
| slack-sdk WebhookClient | httpx POST to webhook URL | slack-sdk adds rate-limit retry handler; httpx raw POST requires manual error handling |
| Token in query param | Cookie-based auth | Cookie approach requires `SameSite` + CSRF handling; query param is acceptable for an internal tool with short-lived tokens |

**Installation (frontend):**
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @tanstack/react-query @tanstack/react-query-devtools zustand react-router-dom axios date-fns
npx shadcn@latest init
npx shadcn@latest add table badge button sheet dialog toast
```

**Installation (backend, new dependencies only):**
```bash
cd backend
uv add sse-starlette slack-sdk
```

---

## Architecture Patterns

### Recommended Project Structure

```
frontend/
├── public/
├── src/
│   ├── api/                   # axios instance + per-resource fetchers
│   │   ├── client.ts          # axios instance with base URL + JWT interceptor
│   │   ├── events.ts          # fetchEvents(), syncEventStatus()
│   │   ├── markets.ts         # fetchMarkets()
│   │   ├── notifications.ts   # fetchNotifications(), markRead()
│   │   └── config.ts          # fetchConfig(), patchConfig()
│   ├── components/
│   │   ├── ui/                # shadcn/ui generated files (do not hand-edit)
│   │   ├── EventsTable.tsx    # TanStack Table + mismatch row highlighting
│   │   ├── MarketsTable.tsx   # liquidity vs threshold highlighting
│   │   ├── NotificationCenter.tsx  # Bell icon + Sheet sliding panel
│   │   ├── SystemHealth.tsx   # polling worker status indicator in header
│   │   └── SseProvider.tsx    # useEffect EventSource, calls invalidateQueries
│   ├── stores/
│   │   └── auth.ts            # Zustand store: token, user, login(), logout()
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── DashboardPage.tsx  # EventsTable + MarketsTable + SseProvider
│   │   └── AdminPage.tsx      # Config panel (polling interval, Slack URL, thresholds)
│   ├── hooks/
│   │   └── useSse.ts          # EventSource lifecycle hook (open, close, reconnect)
│   ├── lib/
│   │   └── utils.ts           # cn() helper (tailwind-merge + clsx)
│   ├── App.tsx                # Router + QueryClientProvider + Zustand
│   └── main.tsx
├── Dockerfile                 # Multi-stage: node build → nginx:alpine serve
├── nginx.conf                 # SPA fallback: try_files $uri /index.html
├── vite.config.ts
└── tsconfig.json

backend/app/api/v1/
├── stream.py                  # NEW — GET /api/v1/stream (SSE endpoint)
├── notifications.py           # NEW — GET /notifications, PATCH /notifications/{id}/read
└── (existing: auth, config, events, markets, audit, health, probe)

backend/app/workers/
└── send_alerts.py             # REPLACE stub with real Slack SDK call + deduplication
```

### Pattern 1: FastAPI SSE with Redis Pub/Sub Fan-Out

**What:** A single FastAPI endpoint subscribes to a Redis pub/sub channel. Celery workers publish to this channel whenever they detect a state change (mismatch, liquidity breach, status update). All connected browser clients receive the event within milliseconds.

**When to use:** Any time backend workers need to push state changes to browser clients without polling.

**Backend — SSE Endpoint:**
```python
# backend/app/api/v1/stream.py
# Source: sse-starlette 3.2.x docs + FastAPI async patterns

from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, Request, Depends
from app.db.redis import get_redis_client
from app.api.deps import verify_token_from_query   # query param auth for SSE

router = APIRouter(prefix="/stream", tags=["stream"])

@router.get("")
async def event_stream(
    request: Request,
    _user=Depends(verify_token_from_query),  # ?token=<jwt>
):
    """SSE endpoint: subscribes to Redis channel, streams events to browser."""
    async def generator():
        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe("prophet:updates")
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message:
                    yield {"event": "update", "data": message["data"]}
        finally:
            await pubsub.unsubscribe("prophet:updates")
            await pubsub.aclose()

    return EventSourceResponse(generator(), ping=20)
```

**Backend — Worker Publish (add to poll_prophetx and poll_sports_data):**
```python
# After writing a state change to the DB, publish to SSE channel
import json
from app.db.redis import get_redis_client  # sync version in Celery tasks

def _publish_update(update_type: str, entity_id: str):
    import redis as sync_redis
    from app.core.config import settings
    r = sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", json.dumps({
        "type": update_type,
        "entity_id": entity_id
    }))
```

### Pattern 2: React SSE Hook with TanStack Query Invalidation

**What:** A `useSse` hook manages the EventSource lifecycle. When a message arrives, it calls `queryClient.invalidateQueries()` to trigger a refetch of the affected data slice.

**When to use:** This project's primary update pattern — simpler and more robust than direct cache mutation for a dashboard.

```typescript
// frontend/src/hooks/useSse.ts
// Source: TanStack Query docs + fragmented thought blog 2025

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";

export function useSse() {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!token) return;

    const url = `/api/v1/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("update", () => {
      // Invalidate both tables — they refetch from /api/v1/events and /api/v1/markets
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["markets"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    });

    es.onerror = () => {
      // Browser auto-reconnects per SSE spec; we show a banner via connection state
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [token, queryClient]);

  return esRef;
}
```

### Pattern 3: SSE Auth via Query Parameter

**What:** Native `EventSource` cannot send `Authorization` headers. Pass the JWT as `?token=<jwt>` and validate it in a FastAPI dependency.

**Why:** This is a private internal ops tool. Token exposure in server logs is acceptable; add Nginx log filtering for the SSE path if needed.

```python
# backend/app/api/deps.py — add:
from fastapi import Query, HTTPException
from app.core.security import verify_access_token  # existing JWT decode

async def verify_token_from_query(token: str = Query(...)) -> dict:
    """Auth dependency for SSE endpoint — validates ?token= query parameter."""
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload
```

### Pattern 4: Slack Alert Deduplication with Redis SETNX

**What:** Before every Slack call, attempt `SET alert_dedup:{alert_type}:{entity_id} 1 EX 300 NX`. If the key already exists (NX fails), skip the send. Key expires after 300 seconds (5 minutes) automatically.

**When to use:** In `send_alerts.py` for every alert type.

```python
# backend/app/workers/send_alerts.py
# Source: Slack SDK docs (docs.slack.dev) + Redis SET NX EX pattern

import redis as sync_redis
from slack_sdk.webhook import WebhookClient
from app.workers.celery_app import celery_app
from app.core.config import settings
import structlog

log = structlog.get_logger()

@celery_app.task(name="app.workers.send_alerts.run", bind=True, max_retries=3)
def run(
    self,
    alert_type: str,
    entity_id: str,
    entity_type: str,
    message: str,
    metadata: dict | None = None,
):
    r = sync_redis.from_url(settings.REDIS_URL)
    dedup_key = f"alert_dedup:{alert_type}:{entity_id}"

    # SETNX pattern: only set if key does not exist, expire after 5 minutes
    acquired = r.set(dedup_key, "1", ex=300, nx=True)
    if not acquired:
        log.info("alert_deduplicated", alert_type=alert_type, entity_id=entity_id)
        return

    if not settings.SLACK_WEBHOOK_URL:
        log.warning("slack_webhook_not_configured")
        return

    webhook = WebhookClient(settings.SLACK_WEBHOOK_URL)
    response = webhook.send(
        text=message,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{alert_type}*\n{message}"},
            }
        ],
    )
    if response.status_code != 200:
        log.error("slack_send_failed", status=response.status_code, body=response.body)
        raise self.retry(countdown=60)

    log.info("alert_sent", alert_type=alert_type, entity_id=entity_id)
```

### Pattern 5: Multi-Stage Docker Build for React SPA

**What:** Stage 1 (node) runs `npm run build`. Stage 2 (nginx:alpine) copies the `dist/` folder and serves it as static files. This keeps the final image small and free of Node.js.

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

```nginx
# frontend/nginx.conf — SPA fallback for React Router
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### Pattern 6: Nginx SSE Proxy Configuration

**What:** Four directives must be added to the upstream Nginx location block that proxies SSE requests to FastAPI. Without these, Nginx buffers the SSE stream and clients see no real-time updates.

```nginx
# nginx/nginx.conf — add SSE-specific location block for /api/v1/stream
location /api/v1/stream {
    proxy_pass http://backend;
    proxy_buffering off;          # CRITICAL: disable response buffering
    proxy_cache off;              # no caching of SSE stream
    proxy_http_version 1.1;       # required for keep-alive
    proxy_set_header Connection '';
    chunked_transfer_encoding off;
    proxy_read_timeout 86400s;    # keep connection alive for 24h max
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Pattern 7: System Health Worker Heartbeat

**What:** Each poll worker writes a Redis key `worker:heartbeat:{worker_name}` with a TTL of 90 seconds on every successful task execution. A new `/api/v1/health/workers` endpoint reads these keys to report live/dead status.

```python
# In poll_prophetx.py and poll_sports_data.py — add at end of each task:
r.set("worker:heartbeat:poll_prophetx", "1", ex=90)
r.set("worker:heartbeat:poll_sports_data", "1", ex=90)

# In backend/app/api/v1/health.py — add:
@router.get("/health/workers")
async def worker_health():
    redis = await get_redis_client()
    return {
        "poll_prophetx": await redis.exists("worker:heartbeat:poll_prophetx") == 1,
        "poll_sports_data": await redis.exists("worker:heartbeat:poll_sports_data") == 1,
    }
```

### Anti-Patterns to Avoid

- **Polling the API from React instead of SSE:** Do not set a short `refetchInterval` on TanStack Query as the primary update mechanism. SSE delivers updates within 1-2 seconds vs. up to 30 seconds for polling-based approaches.
- **Calling `send_alerts` synchronously in an API route:** Always `.delay()` the Celery task — Slack's HTTP call can take 1-3 seconds and will block the request handler.
- **Using `EventSource` with full URL including domain in React:** Use relative paths (`/api/v1/stream?token=...`) so Nginx proxies correctly in all environments.
- **Writing SSE events directly from the Celery worker:** Workers cannot hold open HTTP connections. Use Redis pub/sub as the fan-out bus — workers publish, the FastAPI SSE endpoint subscribes.
- **Storing JWT in localStorage without considering XSS:** For an internal ops tool this is acceptable, but Zustand's persist middleware will write to localStorage. Acceptable tradeoff vs. cookie complexity.
- **Sending heartbeat from browser to detect SSE disconnect:** The SSE spec handles reconnection automatically. Only add the UI "reconnecting..." banner by detecting `onerror` on the `EventSource` object.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE heartbeat / keepalive ping | Custom asyncio sleep + comment emit | `sse-starlette` `ping=20` parameter | Correct SSE comment format, handles edge cases |
| Slack HTTP delivery + retries | httpx POST with manual retry loop | `slack_sdk.WebhookClient` + `RateLimitErrorRetryHandler` | Slack SDK handles 429 rate limits + exponential backoff |
| Alert deduplication timer | Celery periodic task that cleans up a DB table | Redis `SET NX EX 300` | Redis TTL is atomic and self-expiring; zero cleanup code |
| React data table | Hand-coded `<table>` with sorting | `shadcn/ui` Table + `@tanstack/react-table` | Accessibility, sorting, pagination built-in |
| Notification sliding panel | Custom CSS drawer | `shadcn/ui` Sheet component | Radix UI handles focus trap, keyboard dismiss, animation |
| JWT decode on frontend | Custom base64 parse | `jose` or just trust Zustand state | Server validates JWT on every API call; frontend only needs the token string |
| React Router auth guard | Manual `if (!token) return null` in every component | Layout route with `<ProtectedRoute>` using React Router 7 loader | Centralized, no scattered guard code |

**Key insight:** The backend alerting half of this phase is largely filling in stubs. The frontend is the primary engineering effort. Resist the urge to build custom UI primitives — shadcn/ui provides every component this phase needs.

---

## Common Pitfalls

### Pitfall 1: Nginx Buffering Breaks SSE Silently

**What goes wrong:** SSE stream appears to work in development (direct uvicorn) but events never arrive in production (behind Nginx). No errors — the connection is open, events just batch and flush on disconnect.

**Why it happens:** Nginx's default `proxy_buffering on` accumulates the entire response before forwarding. SSE never "completes" so the buffer never flushes.

**How to avoid:** Add the dedicated `/api/v1/stream` location block with `proxy_buffering off` before any other testing. Verify in production before building any frontend UI that depends on it.

**Warning signs:** SSE events appear in a burst when you close the tab; browser DevTools shows "pending" on the SSE request with no events in the EventStream tab.

### Pitfall 2: Redis Pub/Sub Message Lost if No Subscriber

**What goes wrong:** A Celery worker publishes an update to `prophet:updates` but no browser client is connected yet. The message is lost — Redis pub/sub does not persist messages.

**Why it happens:** Redis pub/sub is fire-and-forget. Unlike Redis Streams, pub/sub has no consumer groups or message history.

**How to avoid:** This is acceptable for this use case — the dashboard always fetches full state on load via TanStack Query. An SSE event just triggers a refetch; missing an event during disconnection means the user sees slightly stale data until reconnect, at which point TanStack Query auto-fetches. Do NOT try to implement message replay; it adds complexity the requirements don't need.

**Warning signs:** If you see this as a problem, requirements have changed. Flag to the user before adding Redis Streams.

### Pitfall 3: Multiple EventSource Connections per Browser Tab

**What goes wrong:** `useSse` hook is used in multiple components or without proper cleanup. Browser opens multiple simultaneous SSE connections to the same endpoint. Server resources accumulate.

**Why it happens:** React StrictMode double-invokes effects in development; missing cleanup function in `useEffect` leaves old connections open on re-render.

**How to avoid:** Keep `useSse` as a single hook called once at the `DashboardPage` level (not inside table sub-components). Always return a cleanup function in `useEffect` that calls `es.close()`.

**Warning signs:** Network tab shows multiple connections to `/api/v1/stream`; server logs show duplicate pub/sub subscriptions.

### Pitfall 4: EventSource 401 Crashes Silently with Auto-Reconnect Loop

**What goes wrong:** Token expires while SSE connection is open. EventSource's `onerror` fires, it auto-reconnects, immediately gets 401, fires `onerror` again. Infinite reconnect loop consuming server resources.

**Why it happens:** Native `EventSource` treats all errors (including 401) as transient and retries with exponential backoff, but the 401 is permanent until the user re-authenticates.

**How to avoid:** On `onerror`, check if the main API is returning 401 (TanStack Query axios interceptor will redirect to login). Close the EventSource explicitly in the `onerror` handler if `event.target.readyState === EventSource.CLOSED` after several retries. The axios interceptor already handles 401 for API calls; SSE tokens expiry causes a page-level redirect.

**Warning signs:** Server logs show rapid repeated connections from the same client IP to `/api/v1/stream`.

### Pitfall 5: alert_only_mode Not Checked in update_event_status

**What goes wrong:** Alert-only mode is toggled on in admin config but status updates still fire to ProphetX API because the worker doesn't check the flag.

**Why it happens:** `system_config` key `alert_only_mode` exists but `update_event_status.py` was written before the flag existed (Phase 2 stub note).

**How to avoid:** In Plan 03-02, explicitly add the check to `update_event_status.py`. Read `system_config` from the DB at the start of the task and return early if `alert_only_mode` is `true`. The alert/notification should still be written.

**Warning signs:** Operators enable alert-only mode but see ProphetX status changes continue. Check `update_event_status.py` for the guard.

### Pitfall 6: Slack Webhook URL Exposed in Frontend Bundle

**What goes wrong:** `SLACK_WEBHOOK_URL` accidentally included in Vite env vars (prefixed with `VITE_`). Appears in the compiled JavaScript bundle, publicly visible.

**Why it happens:** Developer adds `VITE_SLACK_WEBHOOK_URL` thinking the frontend admin config panel needs it.

**How to avoid:** The admin config panel reads and patches the webhook URL via `/api/v1/config` (server-side). The frontend never needs the raw webhook URL. `SLACK_WEBHOOK_URL` is a backend-only env var.

**Warning signs:** `grep -r "VITE_SLACK" frontend/src/` returns any results.

---

## Code Examples

Verified patterns from official sources:

### shadcn/ui Vite Init (Official)
```bash
# Source: https://ui.shadcn.com/docs/installation/vite
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install -D tailwindcss @tailwindcss/vite
# Add Tailwind plugin to vite.config.ts
npx shadcn@latest init
# Prompts: style (Default/New York), base color, CSS variables
```

### TanStack Query Provider Setup
```typescript
// Source: https://tanstack.com/query/v5/docs/framework/react/installation
// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // treat data as fresh for 30s
      refetchOnWindowFocus: false,  // SSE handles updates; no polling needed
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
```

### Zustand Auth Store
```typescript
// frontend/src/stores/auth.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  email: string | null;
  role: string | null;
  login: (token: string, email: string, role: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      role: null,
      login: (token, email, role) => set({ token, email, role }),
      logout: () => set({ token: null, email: null, role: null }),
    }),
    { name: "prophet-auth" }  // localStorage key
  )
);
```

### axios Client with 401 Intercept
```typescript
// frontend/src/api/client.ts
import axios from "axios";
import { useAuthStore } from "../stores/auth";

const apiClient = axios.create({ baseURL: "/api/v1" });

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### Mismatch Row Highlight (Tailwind conditional class)
```typescript
// frontend/src/components/EventsTable.tsx
<TableRow
  key={event.id}
  className={event.status_match ? "" : "bg-red-50 border-l-4 border-l-red-500"}
>
  <TableCell>{event.name}</TableCell>
  <TableCell>{event.prophetx_status}</TableCell>
  <TableCell>{event.real_world_status}</TableCell>
</TableRow>
```

### Notification Bell with Badge
```typescript
// frontend/src/components/NotificationCenter.tsx
// Uses shadcn/ui Sheet + Badge + Lucide BellIcon
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";

const unreadCount = notifications.filter((n) => !n.is_read).length;

<Sheet>
  <SheetTrigger asChild>
    <button className="relative">
      <Bell className="h-5 w-5" />
      {unreadCount > 0 && (
        <Badge
          variant="destructive"
          className="absolute -top-1 -right-2 h-4 w-4 rounded-full p-0 flex items-center justify-center text-xs"
        >
          {unreadCount > 99 ? "99+" : unreadCount}
        </Badge>
      )}
    </button>
  </SheetTrigger>
  <SheetContent side="right" className="w-96">
    {/* notification list */}
  </SheetContent>
</Sheet>
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Create React App | Vite 6+ | 2023 (CRA deprecated) | 40x faster HMR; no webpack config; Vite is now the scaffold standard |
| WebSockets for push updates | SSE for server-to-client only | 2022+ for dashboards | SSE is simpler, auto-reconnects, HTTP/1.1 compatible, no library on client |
| Redux for client state | Zustand 5 | 2022+ | No boilerplate; no provider; works with React 19 transitions |
| React Query v3/v4 | TanStack Query v5 | Late 2023 | Simplified API; single object params; better TypeScript; suspense-native |
| Long-polling for real-time | Redis pub/sub → SSE | Industry standard | Pub/sub scales horizontally; SSE keeps connections stateless on the app server |
| Separate CSS files | Tailwind CSS 4 | 2024 (v4 Vite plugin) | No PostCSS config; JIT-only; CSS custom properties for themes |

**Deprecated / Outdated:**
- `create-react-app`: Officially deprecated; do not use for new projects.
- `python-slack-sdk` < 3.x: Use `slack-sdk` 3.x (same package, renamed); `slackclient` PyPI package is the old name.
- `EventSource` polyfills for modern browsers: All 2025 browser targets support native EventSource; no polyfill needed.
- `react-query` (old package name): Now `@tanstack/react-query`; old package is a shim.

---

## Open Questions

1. **SLACK_WEBHOOK_URL configuration entry**
   - What we know: `system_config` table already exists; admin can set key-value pairs via `/api/v1/config`.
   - What's unclear: Is `SLACK_WEBHOOK_URL` stored in `system_config` (editable via UI) or in `.env` (server restart required to change)?
   - Recommendation: Store in `.env` (already where all secrets live). The admin config panel shows the masked URL but only the env var change takes effect. This matches the existing `system_config` pattern where alerting policy flags live in DB and secrets live in env.

2. **SSE connection limit under load**
   - What we know: Each connected browser tab holds one long-lived HTTP connection to FastAPI. With an ops team of 3-5 people, this is 3-10 connections — negligible.
   - What's unclear: uvicorn's default worker count (1 per `docker compose up`).
   - Recommendation: No action needed for v1. If the team grows past 20 concurrent users, add `--workers 2` to the uvicorn command.

3. **ProphetX write endpoint still unconfirmed for alert_only_mode testing**
   - What we know: `update_event_status.py` stubs the write call as log-only (Phase 2 decision). Alert-only mode adds another guard layer.
   - What's unclear: Whether ProphetX write endpoint will be confirmed before Phase 3 is deployed.
   - Recommendation: Alert-only mode guard should be implemented regardless. The two stubs (log-only write + alert-only guard) compose correctly — they don't conflict.

4. **Notification table user scoping**
   - What we know: `Notification` model has no `user_id` column — all notifications are system-wide.
   - What's unclear: Should read/unread state be per-user or global?
   - Recommendation: Global read/unread is fine for v1 (small ops team, shared context). `is_read` on the `Notification` model is the correct design. Do not add `user_id` FK unless explicitly requested.

---

## Sources

### Primary (HIGH confidence)
- `sse-starlette` 3.2.x PyPI + GitHub README — `EventSourceResponse` API, `ping` parameter, async generator pattern, disconnect detection
- `https://ui.shadcn.com/docs/installation/vite` — Official shadcn/ui Vite install steps, components.json, Tailwind integration
- `https://tanstack.com/query/v5/docs/framework/react/` — QueryClient, invalidateQueries v5 API
- `https://docs.slack.dev/tools/python-slack-sdk/webhook/index.html` — WebhookClient.send() sync API, response.status_code, RateLimitErrorRetryHandler
- `https://oneuptime.com/blog/post/2025-12-16-server-sent-events-nginx/view` — Nginx SSE directives (proxy_buffering off, proxy_read_timeout, Connection header, chunked_transfer_encoding off)
- Existing codebase: `backend/app/models/notification.py`, `backend/app/workers/send_alerts.py`, `backend/app/core/config.py` — confirmed existing structure

### Secondary (MEDIUM confidence)
- `https://fragmentedthought.com/blog/2025/react-query-caching-with-server-side-events` — SSE + TanStack Query EventSource lifecycle pattern, verified against TanStack Query docs
- WebSearch (multi-source agreement): EventSource cannot send Authorization headers — confirmed by W3C issue #2177 + multiple implementation guides recommending query param workaround
- WebSearch (multi-source agreement): Zustand 5 + TanStack Query is the 2025 React state standard — confirmed by multiple 2025 blog posts and pmndrs documentation

### Tertiary (LOW confidence)
- WebSearch: Vite 7 / React 19 latest versions — npm package pages cited but not fetched directly; versions may have minor patches. Use `npm create vite@latest` to get current.
- WebSearch: `npm create vite@latest` creates Vite 6.x scaffold with React 19 by default — stated across multiple 2026 guides; verify at scaffold time.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — shadcn/ui, TanStack Query, Zustand, sse-starlette verified against official docs
- Architecture: HIGH — SSE pub/sub fan-out is a well-documented pattern; backend stubs confirmed by reading existing code
- Pitfalls: HIGH — Nginx buffering and EventSource auth limitations verified by multiple independent sources
- Slack SDK: HIGH — Official Slack developer docs fetched directly
- Frontend versions: MEDIUM — npm version numbers cited from search results; verify at scaffold time

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — Vite/shadcn/ui stable; React Router 7 stable; slack-sdk 3.x stable)
