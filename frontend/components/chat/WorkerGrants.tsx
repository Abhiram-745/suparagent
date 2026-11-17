"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { limitsSentence, type SpendLimits } from "@/lib/spend";
import type { HiredWorker } from "@/lib/templates";

// After a hire: for each worker that suggests paid MuAPI tools, an explicit "Grant these tools" step and the
// per-worker switch for scheduled runs. Hiring never grants anything; nothing here happens unless the person clicks.

type Row = { worker: HiredWorker; tools: string[] };

type Status = { granted: boolean; paidUse: boolean; busy: boolean; error: string | null };
const NEW_STATUS: Status = { granted: false, paidUse: false, busy: false, error: null };

export function WorkerGrants({ workers, suggestedTools }: { workers: HiredWorker[]; suggestedTools: Record<string, string[]> }) {
  const rows: Row[] = workers
    .map((worker) => ({ worker, tools: suggestedTools[worker.template_id] ?? [] }))
    .filter((row) => row.tools.length > 0);
  const [limits, setLimits] = useState<SpendLimits | null>(null);
  const [connectionId, setConnectionId] = useState<string | null | undefined>(undefined);
  const [status, setStatus] = useState<Record<number, Status>>({});

  useEffect(() => {
    if (rows.length === 0) return;
    let live = true;
    api.getSpend().then((overview) => { if (live) setLimits(overview.limits); }).catch(() => undefined);
    api.listMarketplaceConnections()
      .then((connections) => { if (live) setConnectionId(connections.find((c) => c.slug === "muapi" && c.credential_configured)?.id ?? null); })
      .catch(() => { if (live) setConnectionId(null); });
    return () => { live = false; };
  }, [rows.length]);

  if (rows.length === 0) return null;

  const update = (agentId: number, change: Partial<Status>) =>
    setStatus((now) => ({ ...now, [agentId]: { ...(now[agentId] ?? NEW_STATUS), ...change } }));

  const grant = async (row: Row) => {
    if (!connectionId) return;
    const id = row.worker.agent_id;
    update(id, { busy: true, error: null });
    try {
      const discovered = await api.discoverMarketplaceTools(connectionId);
      const wanted = discovered.filter((tool) => row.tools.includes(tool.name));
      if (wanted.length === 0) throw new Error("MuAPI does not list these tools yet, so nothing was granted.");
      await api.saveMarketplaceAgentGrants(connectionId, id, wanted.map((tool) => ({ name: tool.name, schema_digest: tool.schema_digest })));
      update(id, { granted: true, busy: false });
    } catch (e) {
      update(id, { busy: false, error: e instanceof ApiError || e instanceof Error ? e.message : "Could not grant the tools." });
    }
  };

  const setPaidUse = async (row: Row, on: boolean) => {
    const id = row.worker.agent_id;
    update(id, { busy: true, error: null });
    try {
      await api.setWorkerPaidUse(id, on);
      update(id, { paidUse: on, busy: false });
    } catch (e) {
      update(id, { busy: false, error: e instanceof ApiError || e instanceof Error ? e.message : "Could not change this setting." });
    }
  };

  return (
    <section aria-label="Tools and spending" className="space-y-3 border-t border-line pt-3">
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted">Let your workers use MuAPI</h4>
      <p className="text-xs text-muted">
        Workers can search and estimate for free. Paid calls cost MuAPI credits and are refused above{" "}
        {limits ? limitsSentence(limits) : "your spending limits"}. Nothing is granted until you click.
      </p>
      {connectionId === null && (
        <p className="text-xs text-muted">
          Connect your MuAPI account first. <Link href="/marketplace/" className="underline">Open the marketplace</Link>, then come back to Agents to grant tools.
        </p>
      )}
      <ul className="space-y-2">
        {rows.map((row) => {
          const s = status[row.worker.agent_id] ?? NEW_STATUS;
          return (
            <li key={row.worker.agent_id} className="space-y-1 rounded-md border border-line p-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{row.worker.name}</span>
                {s.granted ? (
                  <span className="text-success">Tools granted</span>
                ) : (
                  <button
                    type="button"
                    disabled={s.busy || !connectionId}
                    onClick={() => void grant(row)}
                    className="cursor-pointer rounded-md border border-line px-2 py-0.5 font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {s.busy ? "Granting…" : "Grant these tools"}
                  </button>
                )}
              </div>
              {s.granted && (
                <label className="flex cursor-pointer items-start gap-2">
                  <input type="checkbox" className="mt-0.5" checked={s.paidUse} disabled={s.busy} onChange={(e) => void setPaidUse(row, e.target.checked)} />
                  <span>Let scheduled runs spend within these limits, without asking each time. Off by default. Chats still ask before every paid call.</span>
                </label>
              )}
              {s.error && <p role="alert" className="text-danger">{s.error}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
