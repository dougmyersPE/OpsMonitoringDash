# Phase 6: ApiUsagePage - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Full-page API Usage view accessible from sidebar navigation. Operators and Admins see provider quota status, per-worker call volume (today + 7-day stacked bar chart), and projected monthly burn rate computed from current poll intervals. Admins additionally get inline interval controls per worker. The page auto-refreshes via react-query polling.

</domain>

<decisions>
## Implementation Decisions

### Page layout and navigation
- New sidebar nav item "API Usage" at `/usage` route (third item after Events, Markets)
- Stacked sections layout, top to bottom: Provider Quotas -> Call Volume (chart + projection) -> Poll Intervals (admin only)
- Section headers with zinc-900 card containers and subtle borders (matches dark theme)
- Data auto-refreshes via react-query `refetchInterval` (~30s), not SSE

### Quota display format
- Odds API: progress bar with color shift (green -> amber -> red) plus used/limit numbers and remaining count
- Sports API: expandable card — shows aggregate total by default, click to expand per-sport breakdown (NBA, NFL, MLB, NHL, NCAAB, NCAAF)
- Quota limits are DB-configurable (stored in system_config table, admin can update via PATCH /config)
- Unavailable data shown as plain dash "—" with no additional indicator or tooltip

### Chart and projections
- 7-day stacked bar chart (one bar per day, segments colored by worker) using Recharts
- Chart takes ~70% width, projection summary card on the right side
- Projection card shows projected monthly total + per-worker breakdown
- Monthly projection = interval-based calculation: `seconds_per_month / current_interval` per worker — updates instantly when interval changes
- Days with no data: show available bars (fewer than 7 is fine), if zero days show "Collecting data — chart populates as polls run"

### Interval controls (Admin only)
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

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for the Recharts integration and component structure.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Layout.tsx`: Sidebar nav with NAV_ITEMS array — add new entry for /usage
- `useAuthStore`: Zustand store with `role` field — use for admin-only section visibility
- `apiClient` (axios): Pre-configured with JWT auth and /api/v1 base — use for all API calls
- shadcn/ui components: `table`, `button`, `input`, `badge` — use for interval controls table
- `GET /api/v1/usage`: Returns today's call counts per worker from Redis counters (Phase 4)
- `GET /api/v1/config` + `PATCH /api/v1/config/{key}`: Admin-only config endpoints with interval validation (Phase 5)

### Established Patterns
- React Query with 30s staleTime for data fetching (QueryClient in App.tsx)
- Protected routes via `ProtectedRoute` component checking auth token
- Dark zinc theme (zinc-950 bg, zinc-900 cards, zinc-800 borders)
- Each page is a simple component wrapped in `<Layout>` (DashboardPage, MarketsPage)

### Integration Points
- `App.tsx`: Add new Route for /usage -> ApiUsagePage
- `Layout.tsx`: Add "API Usage" to NAV_ITEMS array
- Backend: Needs new endpoint(s) for 7-day historical data and quota info (existing /usage only returns today)
- `system_config` table: Store quota limit values (new rows alongside interval config)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-apiusagepage*
*Context gathered: 2026-03-02*
