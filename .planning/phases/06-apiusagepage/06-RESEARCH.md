# Phase 6: ApiUsagePage - Research

**Researched:** 2026-03-02
**Domain:** Frontend API usage dashboard with backend data pipeline (quota capture, 7-day history, projected usage)
**Confidence:** HIGH

## Summary

Phase 6 builds the ApiUsagePage frontend and the backend data pipeline it depends on. The frontend is a React page with three sections: provider quota status, 7-day call volume chart, and admin-only interval controls. The backend work includes: (1) extending the existing `/api/v1/usage` endpoint to serve quota data, 7-day history, interval info, and projected monthly usage; (2) adding quota header capture to the Odds API and Sports API clients; (3) creating the `api_usage_snapshots` DB table with an Alembic migration; and (4) adding a nightly rollup worker to persist Redis counters to PostgreSQL.

Phase 4 already built Redis INCRBY call counters in all 5 workers and a basic `/api/v1/usage` endpoint returning today's counts. Phase 5 built DB-backed intervals with RedBeat propagation and minimum enforcement. Phase 6 extends these foundations into a complete operator-facing page.

**Primary recommendation:** Build backend data pipeline first (quota capture, DB table, rollup worker, extended usage endpoint), then build the frontend page against real data.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New sidebar nav item "API Usage" at `/usage` route (third item after Events, Markets)
- Stacked sections layout, top to bottom: Provider Quotas -> Call Volume (chart + projection) -> Poll Intervals (admin only)
- Section headers with zinc-900 card containers and subtle borders (matches dark theme)
- Data auto-refreshes via react-query `refetchInterval` (~30s), not SSE
- Odds API: progress bar with color shift (green -> amber -> red) plus used/limit numbers and remaining count
- Sports API: expandable card — shows aggregate total by default, click to expand per-sport breakdown (NBA, NFL, MLB, NHL, NCAAB, NCAAF)
- Quota limits are DB-configurable (stored in system_config table, admin can update via PATCH /config)
- Unavailable data shown as plain dash "—" with no additional indicator or tooltip
- 7-day stacked bar chart (one bar per day, segments colored by worker) using Recharts
- Chart takes ~70% width, projection summary card on the right side
- Projection card shows projected monthly total + per-worker breakdown
- Monthly projection = interval-based calculation: `seconds_per_month / current_interval` per worker — updates instantly when interval changes
- Days with no data: show available bars (fewer than 7 is fine), if zero days show "Collecting data — chart populates as polls run"
- Inline table: columns for worker name, current interval, minimum, and Edit/Save action button
- Edit button per row switches to inline input; Save calls PATCH /config/{key}
- Validation errors shown as inline red text below the input (e.g., "Must be at least 600s")
- Successful save: brief green checkmark flash, input returns to read-only mode — no propagation delay message
- Section completely hidden from Operator and Read-Only users (not greyed out, just absent)

### Claude's Discretion
- Recharts configuration details (colors, tooltip formatting, axis labels)
- Exact responsive breakpoints and card sizing
- Loading skeleton design while data fetches
- Worker display names and color assignments in chart legend

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| USAGE-02 | Operator can see provider-reported quota (used/remaining/limit) for Odds API and Sports API on the API Usage tab | Quota header capture in clients + Redis storage + extended /usage endpoint + frontend QuotaCards |
| USAGE-03 | Operator can see a 7-day call volume history chart per worker on the API Usage tab | api_usage_snapshots DB table + rollup worker + extended /usage endpoint + Recharts frontend |
| USAGE-04 | Operator can see projected monthly call volume at current polling rate on the API Usage tab | Interval-based calculation in /usage endpoint response + frontend ProjectionCard |
| FREQ-01 | Admin can adjust poll frequency per worker from the API Usage tab with changes taking effect within seconds | Frontend WorkerFrequencyPanel using existing PATCH /config endpoint with RedBeat propagation (Phase 5) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| recharts | ^3.7.0 | 7-day stacked bar chart | Most popular React charting library; native React 19 support in v3.x; SVG-based composable API |
| @tanstack/react-query | ^5.90.21 | Data fetching + cache | Already in project; 30s refetchInterval for auto-refresh |
| shadcn/ui | v3 | UI components (table, button, input, badge, card) | Already in project; matches dark zinc theme |
| lucide-react | ^0.575.0 | Icons | Already in project; Gauge, Clock, BarChart3 icons |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| date-fns | ^4.1.0 | Date formatting for chart axis labels | Already in project |
| axios | ^1.13.5 | HTTP client via apiClient | Already in project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| recharts | chart.js + react-chartjs-2 | More flexible but heavier; less React-idiomatic |
| recharts | visx | Lower-level; more control but more code for a simple bar chart |
| recharts | nivo | Good but larger bundle; recharts is simpler for stacked bars |

**Installation:**
```bash
cd frontend && npm install recharts@^3.7.0
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── pages/
│   └── ApiUsagePage.tsx           # Page component (layout + sections)
├── components/
│   ├── usage/
│   │   ├── QuotaSection.tsx       # Provider quota cards (Odds API + Sports API)
│   │   ├── OddsApiQuotaCard.tsx   # Progress bar + used/remaining/limit
│   │   ├── SportsApiQuotaCard.tsx # Expandable per-sport breakdown
│   │   ├── CallVolumeSection.tsx  # Chart + projection side by side
│   │   ├── CallVolumeChart.tsx    # Recharts stacked bar chart
│   │   ├── ProjectionCard.tsx     # Monthly projection summary
│   │   └── IntervalSection.tsx    # Admin-only interval controls table
│   └── ui/                        # shadcn components (existing)
├── api/
│   └── usage.ts                   # API functions: fetchUsageData, updateInterval
└── stores/
    └── auth.ts                    # Existing — role check for admin sections
```

### Pattern 1: React Query Hook per Data Domain
**What:** Single `useQuery` hook fetching from the extended `/api/v1/usage` endpoint
**When to use:** All usage page data comes from one endpoint; no need for separate queries
**Example:**
```typescript
function useUsageData() {
  return useQuery({
    queryKey: ["usage"],
    queryFn: () => apiClient.get("/usage").then(r => r.data),
    refetchInterval: 30_000,
  });
}
```

### Pattern 2: Optimistic Mutation for Interval Save
**What:** `useMutation` with optimistic update for interval changes
**When to use:** When admin saves a new interval value
**Example:**
```typescript
const mutation = useMutation({
  mutationFn: (data: { key: string; value: string }) =>
    apiClient.patch(`/config/${data.key}`, { value: data.value }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["usage"] }),
});
```

### Pattern 3: Role-Gated Section Rendering
**What:** Check `useAuthStore(s => s.role)` to conditionally render admin-only sections
**When to use:** IntervalSection is admin-only
**Example:**
```typescript
const role = useAuthStore(s => s.role);
// ... render quota + chart sections for all users
{role === "admin" && <IntervalSection ... />}
```

### Anti-Patterns to Avoid
- **Separate queries for each section:** The usage endpoint returns all data in one response; splitting into multiple queries wastes network round-trips
- **Client-side projection calculation only:** Projection should come from the API response (uses DB-stored intervals) — frontend recalculates only when interval is changed locally before save
- **Storing quota limits in frontend constants:** Limits are DB-configurable via system_config; must come from the API response

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bar chart | Custom SVG rendering | recharts `<BarChart>` + `<Bar>` | Handles responsive sizing, tooltips, legends, axis labels |
| Progress bar with color shift | Custom CSS animation | Tailwind utility classes with conditional coloring | Simple: green < 50%, amber 50-80%, red > 80% of limit |
| Inline edit pattern | Custom state management | Local component state with edit/save toggle | Simple enough for one field per row |

## Common Pitfalls

### Pitfall 1: Recharts and React 19 Peer Dependency
**What goes wrong:** recharts < 3.x has a peer dependency on react-is which conflicts with React 19
**Why it happens:** react-is was pinned to React 18 in older recharts versions
**How to avoid:** Install recharts@^3.7.0 (v3.x removed the react-is dependency); verify with `npm ls react-is`
**Warning signs:** npm peer dependency warnings during install; "react-is" in node_modules

### Pitfall 2: Empty Chart on Day One
**What goes wrong:** Chart renders blank because api_usage_snapshots has no historical rows yet
**Why it happens:** Rollup worker only writes yesterday's data; today's data is in Redis only
**How to avoid:** The /usage endpoint includes today's Redis counter in the 7-day array (today = live from Redis, days 1-6 = from DB). On day one the chart shows one bar (today). Frontend handles zero-day case with a message.
**Warning signs:** Chart area is completely empty; "No data" state not handled

### Pitfall 3: Sports API Quota Per-Sport Not Per-Provider
**What goes wrong:** Displaying a single "Sports API: 47/100" number that represents only one sport family
**Why it happens:** api-sports.io has separate daily quotas per sport base URL (basketball, hockey, etc.)
**How to avoid:** Capture quota headers per sport family in the client; store as `api_quota:sports_api:{sport}:remaining`; display expandable per-sport breakdown in the UI
**Warning signs:** Quota numbers seem too low or inconsistent across refreshes

### Pitfall 4: Stale Quota Display
**What goes wrong:** Quota numbers from yesterday still shown today after provider daily reset
**Why it happens:** Redis quota keys have no expiry or very long expiry
**How to avoid:** 25-hour TTL on all quota Redis keys; frontend shows "—" when key is null (expired)
**Warning signs:** Quota numbers don't change after midnight; "remaining" count looks unreasonably high

### Pitfall 5: Interval Save Error Not Visible
**What goes wrong:** Admin saves an interval below minimum, gets 422, but UI doesn't show the error
**Why it happens:** Error response not handled in the mutation's onError callback
**How to avoid:** Parse 422 response body for `detail` field; display inline below the input
**Warning signs:** Save appears to fail silently; no visual feedback on validation error

## Code Examples

### Extended /api/v1/usage Endpoint Response Shape
```python
# Expected response from the extended usage endpoint
{
    "date": "2026-03-02",
    "calls_today": {
        "poll_prophetx": 48,
        "poll_sports_data": 2880,
        "poll_odds_api": 144,
        "poll_sports_api": 48,
        "poll_espn": 144,
    },
    "history": [
        {"date": "2026-02-24", "poll_prophetx": 45, "poll_sports_data": 2820, ...},
        {"date": "2026-02-25", "poll_prophetx": 47, "poll_sports_data": 2870, ...},
        # ... up to 7 days
    ],
    "quota": {
        "odds_api": {
            "used": 80,
            "remaining": 420,
            "limit": 500,
            "updated_at": "2026-03-02T14:22:00Z"
        },
        "sports_api": {
            "basketball": {"remaining": 88, "limit": 100, "updated_at": "..."},
            "hockey": {"remaining": 95, "limit": 100, "updated_at": "..."},
            "baseball": {"remaining": 100, "limit": 100, "updated_at": "..."},
            "american-football": {"remaining": 100, "limit": 100, "updated_at": "..."},
        }
    },
    "intervals": {
        "poll_prophetx": {"current": 300, "minimum": 60},
        "poll_sports_data": {"current": 30, "minimum": 15},
        "poll_odds_api": {"current": 600, "minimum": 600},
        "poll_sports_api": {"current": 1800, "minimum": 600},
        "poll_espn": {"current": 600, "minimum": 60},
        "poll_critical_check": {"current": 30, "minimum": 15},
    },
    "projections": {
        "monthly_total": 432000,
        "per_worker": {
            "poll_prophetx": 8640,
            "poll_sports_data": 86400,
            "poll_odds_api": 4320,
            "poll_sports_api": 1440,
            "poll_espn": 4320,
        }
    }
}
```

### Recharts Stacked Bar Chart
```typescript
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const WORKER_COLORS: Record<string, string> = {
  poll_prophetx: "#6366f1",     // indigo
  poll_sports_data: "#22c55e",  // green
  poll_odds_api: "#f59e0b",     // amber
  poll_sports_api: "#3b82f6",   // blue
  poll_espn: "#ec4899",         // pink
};

function CallVolumeChart({ data }: { data: HistoryEntry[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <XAxis dataKey="date" tickFormatter={(d) => format(new Date(d), "MMM d")} />
        <YAxis />
        <Tooltip />
        <Legend />
        {Object.entries(WORKER_COLORS).map(([key, color]) => (
          <Bar key={key} dataKey={key} stackId="calls" fill={color} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
```

### Quota Header Capture (Odds API)
```python
# In clients/odds_api.py — override _get or add post-response hook
import redis as _sync_redis
from datetime import datetime, timezone

def _capture_odds_api_quota(headers) -> None:
    remaining = headers.get("x-requests-remaining")
    used = headers.get("x-requests-used")
    if remaining is None:
        return
    r = _sync_redis.from_url(settings.REDIS_URL)
    pipe = r.pipeline()
    pipe.set("api_quota:odds_api:remaining", remaining, ex=25 * 3600)
    pipe.set("api_quota:odds_api:used", used or "0", ex=25 * 3600)
    pipe.set("api_quota:odds_api:updated_at",
             datetime.now(timezone.utc).isoformat(), ex=25 * 3600)
    pipe.execute()
```

### Sports API Quota Capture (per sport family)
```python
# In clients/sports_api.py — inside get_games() after resp.raise_for_status()
remaining = resp.headers.get("x-ratelimit-requests-remaining")
limit = resp.headers.get("x-ratelimit-requests-limit")
if remaining is not None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    pipe = r.pipeline()
    pipe.set(f"api_quota:sports_api:{sport}:remaining", remaining, ex=25 * 3600)
    pipe.set(f"api_quota:sports_api:{sport}:limit", limit or "100", ex=25 * 3600)
    pipe.set(f"api_quota:sports_api:{sport}:updated_at",
             datetime.now(timezone.utc).isoformat(), ex=25 * 3600)
    pipe.execute()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| recharts v2 (react-is peer dep) | recharts v3 (no react-is) | 2025 | Safe with React 19 |
| Manual SVG charts | Composable chart components | Standard | Less code, better maintainability |
| Full API call log in DB | Redis INCRBY counters + nightly rollup | v1.1 design | O(1) per-cycle cost vs O(N) DB writes |

## Open Questions

1. **Odds API quota limit value**
   - What we know: Response headers include `x-requests-remaining` and `x-requests-used`
   - What's unclear: Whether `x-requests-last` contains the total limit or the last request timestamp
   - Recommendation: Store the limit in system_config as a DB-configurable value (e.g., `quota_limit_odds_api = 500`); use header values for used/remaining only. This way operators can update the limit if their plan changes.

2. **Sports API per-sport quota aggregation for summary view**
   - What we know: Each sport family has separate daily quota; CONTEXT.md says "aggregate total by default, click to expand"
   - What's unclear: Whether the aggregate should sum all sport remainders or show "lowest remaining"
   - Recommendation: Sum remainders for the aggregate total (e.g., "380/500 remaining across all sports"); expand shows each sport's individual remaining/limit

3. **Today's data in the 7-day chart**
   - What we know: Historical data comes from api_usage_snapshots (DB); today's data is in Redis only
   - What's unclear: N/A — design is clear
   - Recommendation: The /usage endpoint appends today's Redis counters as the last entry in the history array, creating a seamless 7+1 day view (6 days from DB + today from Redis, or fewer if no DB rows yet)

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: all files listed in existing code insights section of CONTEXT.md
- Recharts v3 documentation: composable BarChart + stacked Bar API confirmed
- The Odds API v4 docs: `x-requests-remaining`, `x-requests-used` headers confirmed
- api-sports.io rate limit docs: `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` per sport confirmed

### Secondary (MEDIUM confidence)
- Recharts React 19 compatibility: v3.7.0 release notes claim full React 19 support; verify post-install
- api-sports.io per-sport quota independence: documented but not confirmed from live headers yet

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - recharts v3 is well-documented; all other deps already in project
- Architecture: HIGH - extends established patterns (React Query, apiClient, role gating, dark theme)
- Pitfalls: HIGH - all identified pitfalls have clear mitigations

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (30 days - stable stack)
