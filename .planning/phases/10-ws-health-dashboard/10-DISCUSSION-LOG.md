# Phase 10: WS Health Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-01
**Phase:** 10-ws-health-dashboard
**Areas discussed:** Badge presentation, State detail display

---

## Badge Presentation

### Badge Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Same row, same style | Add "ProphetX WS" badge in same row with identical pill styling. Green/red. Consistent look. | ✓ |
| Same row, visually grouped | Subtle separator between poll workers and WS badge to distinguish source type. | |
| Separate row below | WS health on its own line. More room for detail but uses vertical space. | |

**User's choice:** Same row, same style (Recommended)
**Notes:** WS badge is a peer alongside the 5 existing poll worker badges.

### Color States

| Option | Description | Selected |
|--------|-------------|----------|
| Green/red only | Match existing badges — green for connected, red for everything else. | ✓ |
| Green/yellow/red | Add yellow/amber for transitional states (connecting, reconnecting). | |

**User's choice:** Green/red only (Recommended)
**Notes:** Consistent with existing binary badge pattern.

---

## State Detail Display

### Detail Surface Method

| Option | Description | Selected |
|--------|-------------|----------|
| Tooltip on hover | Hover over WS badge to see state name + "last changed: Xm ago". No extra space. | ✓ |
| Inline text next to badge | Show state + time in the header bar. More visible but takes horizontal space. | |
| Click to expand panel | Click to toggle dropdown with state, timestamp, sport_event_count, last_message_at. | |

**User's choice:** Tooltip on hover (Recommended)
**Notes:** Extends existing title attribute pattern.

### Tooltip Implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Native title attribute | Use existing HTML title pattern. Zero dependencies. Plain text. | ✓ |
| Styled tooltip component | Use shadcn/ui Tooltip for richer formatting. More polished. | |

**User's choice:** Native title attribute (Recommended)
**Notes:** Same approach already used on worker badges. No new components.

---

## Claude's Discretion

- Health endpoint response shape for WS data
- Relative time computation on frontend
- Whether to include sport_event_count/last_message_at in endpoint response

## Deferred Ideas

None — discussion stayed within phase scope
