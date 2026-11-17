// Spending limits for paid marketplace tools: types and the small pure helpers the screens share.

export type SpendLimits = { per_call_cents: number; per_run_cents: number; per_worker_month_cents: number };
export type WorkerSpend = { agent_id: number; name: string; scheduled_paid_use: boolean; month_cents: number };
export type SpendOverview = { limits: SpendLimits; workers: WorkerSpend[] };

// What a run that paid, or was stopped by a limit, records in its outcome details.
export type RunSpend = { cents: number; calls: number; refused: string[] };

// Cents are whole numbers everywhere, so nothing drifts between what is shown and what is enforced.
export function centsToDollars(cents: number): string {
  const whole = Math.max(0, Math.round(cents));
  return `$${(whole / 100).toFixed(2)}`;
}

// "0.50" or "$2" to cents; null when it is not a plain non-negative amount with at most two decimals.
export function dollarsToCents(text: string): number | null {
  const match = /^\s*\$?\s*(\d{1,7})(?:\.(\d{1,2}))?\s*$/.exec(text);
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0") || 0);
  return Number.isSafeInteger(cents) ? cents : null;
}

export function limitsSentence(limits: SpendLimits): string {
  return `${centsToDollars(limits.per_call_cents)} per call, ${centsToDollars(limits.per_run_cents)} per run and ${centsToDollars(limits.per_worker_month_cents)} per worker each month`;
}

const OUTCOME_LABELS: Record<string, string> = {
  no_change: "No changes",
  report: "Reported",
  unknown: "Finished",
  source_failed: "A source failed",
  failed: "Failed",
  interrupted: "Interrupted",
  partial: "Partly done: a spending limit stopped some work",
};

export function outcomeLabel(outcome: string | null | undefined): string | null {
  if (!outcome) return null;
  return OUTCOME_LABELS[outcome] ?? null;
}

const PAUSE_REASON_LABELS: Record<string, string> = {
  spend_limit: "Paused: this worker reached its monthly spending limit",
};

// Known reasons read as a sentence; any other reason is shown as the server wrote it.
export function pauseReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return PAUSE_REASON_LABELS[reason] ?? reason;
}

const REFUSAL_LABELS: Record<string, string> = {
  per_call: "over the per-call limit",
  per_run: "over the per-run limit",
  monthly: "over the monthly limit",
};

// The spend line shown on a run. Null when the run neither paid nor was refused.
export function spendLine(details: Record<string, unknown> | null | undefined): string | null {
  const raw = details?.spend;
  if (!raw || typeof raw !== "object") return null;
  const spend = raw as Partial<RunSpend>;
  const cents = typeof spend.cents === "number" ? spend.cents : 0;
  const calls = typeof spend.calls === "number" ? spend.calls : 0;
  const refused = Array.isArray(spend.refused) ? spend.refused.filter((r): r is string => typeof r === "string") : [];
  if (calls === 0 && refused.length === 0) return null;
  const parts: string[] = [];
  if (calls > 0) parts.push(`Spent ${centsToDollars(cents)} on ${calls} paid call${calls === 1 ? "" : "s"}`);
  if (refused.length > 0) {
    const reasons = [...new Set(refused.map((r) => REFUSAL_LABELS[r] ?? r))];
    parts.push(`${refused.length} call${refused.length === 1 ? "" : "s"} refused (${reasons.join(", ")})`);
  }
  return parts.join(" · ");
}
