---
phase: 03-dashboard-and-alerts
plan: "01"
subsystem: ui
tags: [react, vite, tailwind, shadcn, tanstack-query, zustand, axios, typescript, sse]

# Dependency graph
requires:
  - phase: 02-monitoring-engine
    provides: events, markets, audit-log API endpoints at /api/v1/events, /api/v1/markets, /api/v1/health/workers
provides:
  - Vite + React 19 + TypeScript SPA at frontend/ with full build toolchain
  - Zustand auth store with localStorage persistence and JWT token management
  - axios instance with JWT Bearer interceptor and 401 redirect to /login
  - LoginPage with OAuth2 form-encoded POST (OAuth2PasswordRequestForm format)
  - DashboardPage with ProtectedRoute guard behind Zustand token check
  - EventsTable with TanStack Query fetch and red left-border highlight on status mismatch
  - MarketsTable with TanStack Query fetch and red left-border highlight on below-threshold
  - SystemHealth component polling /api/v1/health/workers every 30s with green/red dots
  - useSse hook connecting to /api/v1/stream?token=... with invalidateQueries on update events
  - SseProvider rendering reconnecting banner when EventSource.CLOSED
affects:
  - 03-02-PLAN.md (SSE endpoint that useSse connects to)
  - 03-03-PLAN.md (notifications, Slack alerts that dashboard will display)

# Tech tracking
tech-stack:
  added:
    - vite 7.x with @vitejs/plugin-react and @tailwindcss/vite
    - tailwindcss v4 (CSS import mode, no config file required)
    - shadcn/ui 3.x (table, badge, button, input, label components)
    - "@tanstack/react-query" v5 with ReactQueryDevtools
    - zustand with persist middleware
    - react-router-dom v6
    - axios with request/response interceptors
    - date-fns for timestamp formatting
    - clsx + tailwind-merge for cn() class merging
  patterns:
    - TanStack Query v5 queryKey arrays (["events"], ["markets"], ["worker-health"], ["notifications"])
    - Zustand persist middleware storing token + email + role to localStorage under "prophet-auth"
    - axios interceptor pattern for automatic JWT attachment and 401 redirect
    - ProtectedRoute component wrapping authenticated pages, reads from Zustand token
    - SSE hook (useSse) mounted once at DashboardPage level to prevent duplicate connections
    - shadcn/ui component aliases via @/* path alias pointing to ./src

key-files:
  created:
    - frontend/src/App.tsx
    - frontend/src/stores/auth.ts
    - frontend/src/api/client.ts
    - frontend/src/api/events.ts
    - frontend/src/api/markets.ts
    - frontend/src/pages/LoginPage.tsx
    - frontend/src/pages/DashboardPage.tsx
    - frontend/src/components/EventsTable.tsx
    - frontend/src/components/MarketsTable.tsx
    - frontend/src/components/SystemHealth.tsx
    - frontend/src/components/SseProvider.tsx
    - frontend/src/hooks/useSse.ts
    - frontend/src/lib/utils.ts
    - frontend/vite.config.ts
    - frontend/tsconfig.app.json
    - frontend/components.json
  modified:
    - frontend/src/index.css (Tailwind v4 CSS import + shadcn CSS variables)
    - frontend/tsconfig.json (added paths for @ alias)

key-decisions:
  - "shadcn/ui requires paths alias in root tsconfig.json (not just tsconfig.app.json) for v4 Tailwind detection to succeed"
  - "Tailwind v4 uses CSS import (@import 'tailwindcss') instead of config file — no tailwind.config.ts needed"
  - "Task 1b and Task 2 components implemented together in same pass — DashboardPage imports components so they must exist for build to pass"
  - "useSse mounted once in SseProvider at DashboardPage level — never inside sub-components per RESEARCH.md Pitfall 3 (duplicate connections)"
  - "SSE onerror handled silently in hook; reconnect banner shown by SseProvider via es.readyState polling every 5s"

patterns-established:
  - "TanStack Query: queryKey naming convention — ['events'], ['markets'], ['worker-health'], ['notifications']"
  - "Auth: useAuthStore.getState() (not hook) used in axios interceptors (outside React component)"
  - "Highlighting: cn() with conditional Tailwind classes — bg-red-50 border-l-4 border-l-red-500 for mismatches"
  - "API modules: each domain (events, markets) has its own file with typed interfaces and fetch functions"

requirements-completed: [DASH-01, DASH-02, DASH-03, DASH-04]

# Metrics
duration: 4min
completed: 2026-02-26
---

# Phase 3 Plan 01: React SPA Dashboard Summary

**Vite + React 19 + TypeScript SPA with Zustand auth, TanStack Query, EventsTable/MarketsTable with mismatch highlighting, SSE hook, and shadcn/ui components**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-26T15:12:46Z
- **Completed:** 2026-02-26T15:17:08Z
- **Tasks:** 3 (1a scaffold, 1b auth/routing, 2 components)
- **Files modified:** 17

## Accomplishments
- Vite react-ts SPA scaffold with Tailwind v4 CSS plugin and /api proxy to localhost:80
- Auth layer: Zustand store with persist, axios JWT interceptor, 401 auto-redirect, OAuth2 login form
- Dashboard components: EventsTable and MarketsTable with red left-border row highlighting, SystemHealth worker dots
- SSE integration: useSse hook with invalidateQueries on update event, SseProvider with reconnecting banner

## Task Commits

Each task was committed atomically:

1. **Task 1a: React SPA Scaffold** - `a7225a3` (feat)
2. **Task 1b: Auth Store, API Modules, Pages, App Router** - `9a56a37` (feat)
3. **Task 2: Dashboard Components + SSE Hook** - `0e188eb` (feat)

## Files Created/Modified
- `frontend/vite.config.ts` - Tailwind v4 plugin + /api proxy to backend
- `frontend/tsconfig.app.json` + `frontend/tsconfig.json` - TypeScript with @ path alias
- `frontend/src/lib/utils.ts` - cn() helper for shadcn class merging
- `frontend/src/stores/auth.ts` - Zustand auth store, persisted to localStorage "prophet-auth"
- `frontend/src/api/client.ts` - axios instance with JWT Bearer + 401 redirect interceptors
- `frontend/src/api/events.ts` - fetchEvents() and syncEventStatus() with typed EventRow interface
- `frontend/src/api/markets.ts` - fetchMarkets() with typed MarketRow interface
- `frontend/src/pages/LoginPage.tsx` - Login form using URLSearchParams (OAuth2 form encoding)
- `frontend/src/pages/DashboardPage.tsx` - Dashboard shell with header, SseProvider mount
- `frontend/src/App.tsx` - QueryClientProvider + BrowserRouter + ProtectedRoute + Routes
- `frontend/src/hooks/useSse.ts` - EventSource at /api/v1/stream?token=..., invalidateQueries on update
- `frontend/src/components/SseProvider.tsx` - Mounts useSse, reconnecting banner via readyState poll
- `frontend/src/components/EventsTable.tsx` - Status mismatch table with red highlight + Sync button
- `frontend/src/components/MarketsTable.tsx` - Liquidity threshold table with red highlight
- `frontend/src/components/SystemHealth.tsx` - Worker health dots polling /api/v1/health/workers
- `frontend/src/index.css` - Tailwind v4 CSS import + shadcn design tokens
- `frontend/src/components/ui/` - shadcn table, badge, button, input, label components

## Decisions Made
- shadcn/ui v3 requires the paths alias in the root `tsconfig.json` (not just `tsconfig.app.json`) for its Vite init flow to detect the alias; adding it to tsconfig.app.json alone caused init to fail
- Tailwind v4 with `@tailwindcss/vite` plugin uses CSS `@import "tailwindcss"` — no `tailwind.config.ts` file is needed or generated
- Task 1b components (EventsTable, MarketsTable, SseProvider, SystemHealth, useSse) were created in the same implementation pass as Task 2 because DashboardPage imports them — deferring to Task 2 would have broken the Task 1b build

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added @types/node for vite.config.ts path alias**
- **Found during:** Task 1a (Vite config with path alias)
- **Issue:** `import path from "path"` in vite.config.ts requires @types/node for TypeScript to resolve the `path` module types
- **Fix:** Ran `npm install -D @types/node`
- **Files modified:** frontend/package.json, frontend/package-lock.json
- **Verification:** Build passed with zero TypeScript errors
- **Committed in:** a7225a3 (Task 1a commit)

**2. [Rule 3 - Blocking] shadcn/ui requires paths in root tsconfig.json**
- **Found during:** Task 1a (shadcn/ui init)
- **Issue:** `npx shadcn@latest init --defaults` failed with "No import alias found in your tsconfig.json file" when alias was only in tsconfig.app.json
- **Fix:** Added `compilerOptions.paths` to root tsconfig.json (the file shadcn checks)
- **Files modified:** frontend/tsconfig.json
- **Verification:** shadcn init succeeded, components added successfully
- **Committed in:** a7225a3 (Task 1a commit)

**3. [Rule 3 - Blocking] Implemented Task 2 components before Task 1b commit**
- **Found during:** Task 1b (DashboardPage creation)
- **Issue:** DashboardPage imports EventsTable, MarketsTable, SseProvider, SystemHealth — these don't exist yet so `npm run build` would fail after Task 1b
- **Fix:** Created all Task 2 components (full implementations per plan) before running Task 1b build verification
- **Files modified:** All frontend/src/components/*.tsx and frontend/src/hooks/useSse.ts
- **Verification:** Build passed with 580 modules transformed
- **Committed in:** 0e188eb (as Task 2 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 3 - Blocking)
**Impact on plan:** All three are build blockers resolved by following the plan spec exactly; no scope creep.

## Issues Encountered
- None beyond the auto-fixed blocking issues above.

## User Setup Required
None - no external service configuration required for the frontend build. The dev server `/api` proxy points to `localhost:80` (nginx) which the backend Docker stack provides.

## Next Phase Readiness
- Frontend SPA builds clean with zero TypeScript errors
- useSse hook is ready to connect once Plan 03-02 implements the /api/v1/stream SSE endpoint
- SystemHealth component will show worker status once /api/v1/health/workers endpoint is live (Plan 03-02)
- All TanStack Query cache keys established: ["events"], ["markets"], ["worker-health"], ["notifications"]

---
*Phase: 03-dashboard-and-alerts*
*Completed: 2026-02-26*

## Self-Check: PASSED

- All 13 source files verified to exist on disk
- All 3 task commits (a7225a3, 9a56a37, 0e188eb) verified in git log
- `npm run build` exits 0 with 580 modules transformed, zero TypeScript errors
