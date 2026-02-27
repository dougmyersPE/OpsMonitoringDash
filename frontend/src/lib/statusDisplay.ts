/**
 * Display-only status normalization — maps all source status values to
 * ProphetX naming conventions (Not Started / Live / Ended).
 *
 * Does NOT affect mismatch detection logic; raw values remain in the DB.
 */

const STATUS_LABELS: Record<string, string> = {
  // ProphetX
  not_started: "Not Started",
  upcoming:    "Not Started",
  live:        "Live",
  suspended:   "Live",
  settled:     "Ended",
  ended:       "Ended",

  // ESPN
  pre:  "Not Started",
  in:   "Live",
  post: "Ended",

  // Odds API
  scheduled:  "Not Started",
  inprogress: "Live",
  final:      "Ended",

  // SportsDataIO
  "f/ot": "Ended",
  "f/so": "Ended",

  // Sports API (api-sports.io) — not started
  ns:  "Not Started",
  tbd: "Not Started",
  // Sports API — live (soccer periods, basketball quarters, hockey periods)
  "1h": "Live",
  ht:   "Live",
  "2h": "Live",
  et:   "Live",
  bt:   "Live",
  p:    "Live",
  int:  "Live",
  // basketball
  q1: "Live",
  q2: "Live",
  q3: "Live",
  q4: "Live",
  ot: "Live",
  // hockey
  p1: "Live",
  p2: "Live",
  p3: "Live",
  ap: "Live",
  so: "Live",
  // Sports API — finished
  ft:   "Ended",
  aet:  "Ended",
  pen:  "Ended",
  aot:  "Ended",
  canc: "Ended",
  awd:  "Ended",
  wo:   "Ended",
};

export function normalizeStatus(status: string | null | undefined): string {
  if (!status) return "—";
  return STATUS_LABELS[status.toLowerCase()] ?? status;
}
