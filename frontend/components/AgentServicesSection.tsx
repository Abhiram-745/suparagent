"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  agentNames, cleanAddress, describeServiceError, kindOf, OUTCOME_LABEL, outcomeTone, toggleAgent,
  type ServiceAudit, type ServiceKind, type ServicePreset, type ServiceProvider, type ServiceResource,
} from "@/lib/agent-services";
import { stateLabel, type CustomMcpConnection } from "@/lib/custom-mcp";
import type { MarketplaceAgent } from "@/lib/marketplace";
import { Badge } from "@/components/ui/Badge";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Field, Input, Select } from "@/components/ui/Input";
import { SkeletonList } from "@/components/ui/Skeleton";

type AddForm = { kind: ServiceKind; address: string; label: string };

export function AgentServicesSection({ agents }: { agents: MarketplaceAgent[] }) {
  const [presets, setPresets] = useState<ServicePreset[]>([]);
  const [providers, setProviders] = useState<ServiceProvider[] | null>(null);
  const [resources, setResources] = useState<ServiceResource[]>([]);
  const [connections, setConnections] = useState<CustomMcpConnection[]>([]);
  const [audit, setAudit] = useState<ServiceAudit[]>([]);
  const [forms, setForms] = useState<Record<string, AddForm>>({});
  const [limits, setLimits] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchAll = useCallback(() => Promise.all([
    api.listServiceProviders(), api.listServiceResources(), api.listCustomMcp(), api.listServiceAudit(20),
  ]), []);
  const reload = useCallback(async () => {
    const [list, found, mcp, calls] = await fetchAll();
    setProviders(list); setResources(found); setConnections(mcp); setAudit(calls);
  }, [fetchAll]);
  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key); setError(null); setNotice(null);
    try { await action(); } catch (reason) { setError(describeServiceError(reason)); } finally { setBusy(null); }
  };

  useEffect(() => {
    let live = true;
    api.listServicePresets().then((found) => { if (live) setPresets(found); }).catch(() => undefined);
    fetchAll().then(([list, found, mcp, calls]) => {
      if (live) { setProviders(list); setResources(found); setConnections(mcp); setAudit(calls); }
    }).catch((reason: unknown) => { if (live) { setError(describeServiceError(reason)); setProviders([]); } });
    return () => { live = false; };
  }, [fetchAll]);

  const off = busy !== null;
  const formFor = (provider: ServiceProvider): AddForm =>
    forms[provider.connection_id] ?? { kind: kindOf(provider.provider) ?? "email", address: "", label: "" };

  const card = (provider: ServiceProvider) => {
    const connection = connections.find((item) => item.id === provider.connection_id);
    const mine = resources.filter((item) => item.connection_id === provider.connection_id);
    const form = formFor(provider);
    const fixedKind = kindOf(provider.provider);
    const kind = fixedKind ?? form.kind;
    const cleaned = cleanAddress(kind, form.address);
    const full = provider.resource_count >= provider.resource_limit;
    const limitText = limits[provider.connection_id] ?? String(provider.resource_limit);
    const limitValue = Number(limitText);
    const setForm = (patch: Partial<AddForm>) => setForms((old) => ({ ...old, [provider.connection_id]: { ...form, ...patch } }));
    return <article key={provider.connection_id} className="space-y-4 rounded-lg border border-line p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold">{provider.connection_name}</h3>
          <p className="mt-1 text-xs text-muted">{fixedKind === "email" ? "Email addresses" : fixedKind === "phone" ? "Phone numbers" : "Email or phone"} · {provider.resource_count} of {provider.resource_limit} added</p>
        </div>
        {connection && <Badge tone={connection.enabled && connection.state === "connected" ? "success" : "neutral"}>{stateLabel(connection)}</Badge>}
      </div>
      {connection && !connection.enabled && <Banner tone="info">Sign in, test and turn this connection on under “Custom MCP servers” below. Until then no agent can use it.</Banner>}

      <div className="space-y-3">
        <p className="text-sm font-medium">Addresses</p>
        {mine.length === 0 && <p className="text-sm text-muted">None yet. Add one you already created at the service. Agents cannot create them.</p>}
        <ul className="space-y-3">{mine.map((resource) => <li key={resource.id} className="space-y-2 rounded-md border border-line p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0"><p className="break-all font-medium">{resource.address}</p><p className="text-xs text-muted">{resource.label} · {agentNames(resource.agent_ids, agents)}</p></div>
            {confirm === resource.id
              ? <div className="flex gap-2"><Button size="sm" variant="danger" disabled={off} onClick={() => void run(`rm:${resource.id}`, async () => {
                  await api.deleteServiceResource(resource.id); setConfirm(null); await reload(); setNotice(`${resource.address} removed here. It still exists at the service.`);
                })}>Confirm remove</Button><Button size="sm" disabled={off} onClick={() => setConfirm(null)}>Keep</Button></div>
              : <Button size="sm" disabled={off} onClick={() => setConfirm(resource.id)}>Remove</Button>}
          </div>
          {agents.length === 0 ? <p className="text-xs text-muted">Create an agent to give it this address.</p> : <div className="flex flex-wrap gap-x-4 gap-y-1">
            {agents.map((agent) => <Checkbox key={agent.id} label={agent.name} disabled={off} checked={resource.agent_ids.includes(agent.id)}
              onChange={(event) => void run(`assign:${resource.id}`, async () => {
                const next = await api.assignServiceResource(resource.id, toggleAgent(resource.agent_ids, agent.id, event.target.checked));
                setResources((old) => old.map((item) => item.id === next.id ? next : item));
              })} />)}
          </div>}
        </li>)}</ul>
        <div className="grid gap-3 sm:grid-cols-2">
          {!fixedKind && <Field label="Kind">{(props) => <Select {...props} value={form.kind} disabled={off} onChange={(event) => setForm({ kind: event.target.value as ServiceKind })}>
            <option value="email">Email address</option><option value="phone">Phone number</option></Select>}</Field>}
          <Field label={kind === "email" ? "Email address" : "Phone number"} hint={kind === "email" ? "For example helper@agentmail.to" : "With country code, such as +14155550100"}>
            {(props) => <Input {...props} value={form.address} maxLength={200} disabled={off || full} onChange={(event) => setForm({ address: event.target.value })} />}
          </Field>
          <Field label="Label" hint="A name for you, such as “Support inbox”.">
            {(props) => <Input {...props} value={form.label} maxLength={100} disabled={off || full} onChange={(event) => setForm({ label: event.target.value })} />}
          </Field>
        </div>
        {full && <p className="text-xs text-muted">This provider is at its limit of {provider.resource_limit}. Raise the limit below to add more.</p>}
        {form.address.trim() !== "" && cleaned === null && <p className="text-xs text-danger">That does not look like a valid {kind === "email" ? "email address" : "phone number"}.</p>}
        <Button variant="primary" disabled={off || full || cleaned === null || !form.label.trim()} onClick={() => void run(`add:${provider.connection_id}`, async () => {
          await api.addServiceResource({ connection_id: provider.connection_id, kind, address: cleaned ?? "", label: form.label.trim() });
          setForms((old) => { const copy = { ...old }; delete copy[provider.connection_id]; return copy; }); await reload();
          setNotice("Added. No agent has it yet: tick the agents above, then grant them tools under “Custom MCP servers”.");
        })}>{busy === `add:${provider.connection_id}` ? "Adding…" : "Add address"}</Button>
      </div>

      <div className="flex flex-wrap items-end gap-3 border-t border-line pt-4">
        <Field label="Most addresses allowed" hint="A cap you set. Nothing here creates addresses for you.">
          {(props) => <Input {...props} type="number" min={1} max={20} value={limitText} disabled={off} onChange={(event) => setLimits((old) => ({ ...old, [provider.connection_id]: event.target.value }))} />}
        </Field>
        <Button disabled={off || !Number.isInteger(limitValue) || limitValue < 1 || limitValue > 20 || limitValue === provider.resource_limit}
          onClick={() => void run(`limit:${provider.connection_id}`, async () => {
            await api.setServiceProviderLimit(provider.connection_id, provider.provider, limitValue); await reload();
            setLimits((old) => { const copy = { ...old }; delete copy[provider.connection_id]; return copy; }); setNotice("Limit saved.");
          })}>Save limit</Button>
        {confirm === provider.connection_id
          ? <div className="flex flex-wrap items-center gap-2">
              <span className="basis-full text-xs text-muted">This removes the addresses and which agents have them, and clears every agent&apos;s tool grants for this connection, so none of them keeps using it. The connection and its sign-in stay. The history below is kept.</span>
              <Button variant="danger" disabled={off} onClick={() => void run(`clear:${provider.connection_id}`, async () => {
                await api.clearServiceProvider(provider.connection_id); setConfirm(null); await reload(); setNotice("No longer an email or phone provider. Its tool grants were cleared.");
              })}>Yes, stop</Button><Button disabled={off} onClick={() => setConfirm(null)}>Cancel</Button>
            </div>
          : <Button disabled={off} onClick={() => setConfirm(provider.connection_id)}>Stop using as provider</Button>}
      </div>
    </article>;
  };

  return <section className="space-y-3" aria-labelledby="agent-services-heading">
    <div><h2 id="agent-services-heading" className="text-lg font-semibold">Agent email and phone</h2>
      <p className="mt-1 text-sm text-muted">Give an agent its own inbox or phone number on your own account with the service. An agent only gets what you assign, and it can only use the tools you grant. Every send or call asks for your approval and shows the exact address, and a call naming an address you did not assign is refused.</p></div>
    {error && <Banner tone="danger">{error}</Banner>}{notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    <div className="space-y-3 rounded-lg border border-line p-4">
      <p className="text-sm font-medium">Connect a service</p>
      <div className="grid gap-3 sm:grid-cols-2">{presets.map((preset) => <div key={preset.preset} className="space-y-2 rounded-md border border-line p-3">
        <p className="font-medium">{preset.label}</p><p className="text-xs text-muted">{preset.summary}</p>
        <Button variant="primary" disabled={off} onClick={() => void run(`preset:${preset.preset}`, async () => {
          await api.addServiceProvider(preset.preset, 3); await reload();
          setNotice(`${preset.label} added, switched off. Sign in and turn it on under “Custom MCP servers” below.`);
        })}>{busy === `preset:${preset.preset}` ? "Adding…" : `Connect ${preset.label}`}</Button>
      </div>)}</div>
    </div>
    {providers === null ? <SkeletonList rows={2} /> : providers.map(card)}
    <div className="space-y-2 rounded-lg border border-line p-4">
      <p className="text-sm font-medium">Recent activity</p>
      <p className="text-xs text-muted">Which agent used which address, through which tool. Message text and tool arguments are not kept here.</p>
      {audit.length === 0 ? <p className="text-sm text-muted">No calls yet.</p> : <ul className="divide-y divide-line">{audit.map((row) => <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
        <span className="min-w-0"><span className="font-medium">{row.agent_name || `Agent ${row.agent_id}`}</span> used <code>{row.tool_name}</code> as <span className="break-all">{row.resources.join(", ")}</span>
          <span className="block text-xs text-muted">{new Date(row.created_at).toLocaleString()}{row.approved_by ? ` · approved by ${row.approved_by}` : ""}</span></span>
        <Badge tone={outcomeTone(row.outcome)}>{OUTCOME_LABEL[row.outcome]}</Badge>
      </li>)}</ul>}
    </div>
  </section>;
}
