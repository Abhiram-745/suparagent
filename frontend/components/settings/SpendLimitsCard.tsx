"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { centsToDollars, dollarsToCents, type SpendOverview } from "@/lib/spend";
import { SettingsCard } from "./SettingsCard";

// The owner's spending limits for paid marketplace tools, and each worker's month so far. Changing the limits works in
// the desktop app only; anywhere else the server answers 404 and this page says so.
export function SpendLimitsCard() {
  const [overview, setOverview] = useState<SpendOverview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [perCall, setPerCall] = useState("");
  const [perRun, setPerRun] = useState("");
  const [perMonth, setPerMonth] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const show = (o: SpendOverview) => {
    setOverview(o);
    setPerCall((o.limits.per_call_cents / 100).toFixed(2));
    setPerRun((o.limits.per_run_cents / 100).toFixed(2));
    setPerMonth((o.limits.per_worker_month_cents / 100).toFixed(2));
  };

  useEffect(() => {
    let live = true;
    api.getSpend().then((o) => { if (live) show(o); }).catch((e) => { if (live) setLoadError(e instanceof Error ? e.message : "Could not load the limits."); });
    return () => { live = false; };
  }, []);

  const save = async () => {
    const a = dollarsToCents(perCall);
    const b = dollarsToCents(perRun);
    const c = dollarsToCents(perMonth);
    if (a === null || b === null || c === null) {
      setMessage({ kind: "error", text: "Enter each limit as dollars and cents, for example 0.50." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const limits = await api.saveSpendLimits({ per_call_cents: a, per_run_cents: b, per_worker_month_cents: c });
      if (overview) show({ ...overview, limits });
      setMessage({ kind: "ok", text: "Limits saved. They apply to the next paid call." });
    } catch (e) {
      const text = e instanceof ApiError && e.status === 404
        ? "Spending limits are changed in the desktop app. Headless installs use environment configuration."
        : e instanceof Error ? e.message : "Could not save the limits.";
      setMessage({ kind: "error", text });
    } finally {
      setBusy(false);
    }
  };

  const field = (label: string, value: string, set: (v: string) => void) => (
    <label className="flex items-center justify-between gap-3 text-sm">
      <span>{label}</span>
      <span className="flex items-center gap-1">$<input inputMode="decimal" value={value} onChange={(e) => set(e.target.value)} className="w-24 rounded-md border border-line bg-transparent px-2 py-1 text-right" /></span>
    </label>
  );

  return (
    <SettingsCard title="Spending limits" description="Paid tools from connected apps, such as MuAPI data calls, are refused above these limits. Searches and estimates are free.">
      {loadError && <p role="alert" className="text-xs text-danger">{loadError}</p>}
      {overview && (
        <div className="space-y-3">
          {field("Most a single call may cost", perCall, setPerCall)}
          {field("Most a single run may spend", perRun, setPerRun)}
          {field("Most one worker may spend each month", perMonth, setPerMonth)}
          <div className="flex items-center gap-3">
            <button type="button" disabled={busy} onClick={() => void save()} className="cursor-pointer rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-hover disabled:opacity-50">
              {busy ? "Saving…" : "Save limits"}
            </button>
            {message && <p role={message.kind === "error" ? "alert" : "status"} className={`text-xs ${message.kind === "error" ? "text-danger" : "text-muted"}`}>{message.text}</p>}
          </div>
          {overview.workers.some((w) => w.month_cents > 0 || w.scheduled_paid_use) && (
            <ul className="space-y-1 border-t border-line pt-3 text-xs">
              {overview.workers.filter((w) => w.month_cents > 0 || w.scheduled_paid_use).map((w) => (
                <li key={w.agent_id} className="flex justify-between gap-3">
                  <span>{w.name}{w.scheduled_paid_use ? " · scheduled runs may spend" : ""}</span>
                  <span className="text-muted">{centsToDollars(w.month_cents)} this month</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </SettingsCard>
  );
}
