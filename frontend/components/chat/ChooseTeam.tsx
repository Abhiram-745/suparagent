"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { BusinessProfileForm } from "./BusinessProfileForm";
import { EmptyPanel, ErrorState, LoadingState } from "./PanelState";
import {
  categoryLabel,
  groupByCategory,
  hireableChoices,
  hireSummary,
  MAX_HIRE,
  preTick,
  requirementBadges,
  SETUP_DEPTH_LABELS,
  starterRoutinesLabel,
  suggestionReasons,
  toggleChoice,
  type HireReceipt,
  type SuggestGoal,
  type TemplateCatalog,
} from "@/lib/templates";

const TAG = "rounded border border-line px-1.5 py-0.5 text-[11px] text-muted";

// Pick any number of ready-made workers and add them in one step. Nothing is created until
// Add is pressed; workers ask first, hold no connected-app access and their routines stay paused.
export function ChooseTeam({
  provider,
  model,
  skipLabel = "Skip",
  onSkip,
  onHired,
  onUndone,
}: {
  provider?: string;
  model?: string | null;
  skipLabel?: string;
  onSkip?: () => void;
  onHired?: (receipt: HireReceipt) => void;
  onUndone?: () => void;
}) {
  const [catalog, setCatalog] = useState<TemplateCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<HireReceipt | null>(null);
  const [undone, setUndone] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [goals, setGoals] = useState<SuggestGoal[]>([]);
  const [pickedGoals, setPickedGoals] = useState<string[]>([]);
  const [about, setAbout] = useState("");
  const [quickOnly, setQuickOnly] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [helpNote, setHelpNote] = useState<string | null>(null);
  const [profileDone, setProfileDone] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listTemplates()
      .then((value) => { if (!cancelled) setCatalog(value); })
      .catch(() => { if (!cancelled) setLoadError("Could not load the workers."); });
    return () => { cancelled = true; };
  }, [reload]);

  const groups = useMemo(() => (catalog ? groupByCategory(catalog.templates, catalog.categories) : []), [catalog]);
  const ticked = useMemo(() => hireableChoices(chosen, catalog?.templates ?? []), [chosen, catalog]);

  // "Help me choose": three short questions, answered by the bundled catalog. It only ticks cards for
  // the person to review; nothing is created or granted until Add is pressed.
  const openHelp = () => {
    setHelpOpen(true);
    if (goals.length === 0) api.suggestGoals().then(setGoals).catch(() => setHelpNote("Could not load the questions."));
  };

  const suggest = async () => {
    setBusy(true);
    setHelpNote(null);
    try {
      const { suggestions } = await api.suggestTemplates(pickedGoals, about.trim(), quickOnly ? "express" : "guided");
      const ids = preTick(suggestions, catalog?.templates ?? []);
      setChosen(ids);
      setReasons(suggestionReasons(suggestions.filter((s) => ids.includes(s.template_id))));
      setHelpNote(
        ids.length === 0
          ? "Nothing matched yet. Try another goal or describe the business."
          : `I ticked ${ids.length}. Change them as you like, then add.`,
      );
    } catch {
      setHelpNote("Could not get suggestions. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  };

  const hire = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.hireTemplates(ticked, provider, model);
      setReceipt(result);
      setUndone(false);
      setProfileDone(false);
      onHired?.(result);
    } catch (err) {
      // One message for the whole hire: nothing was added.
      setError(err instanceof ApiError ? err.message : "The workers could not be added. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!receipt) return;
    setBusy(true);
    setError(null);
    try {
      await api.undoHire(receipt.workers.map((w) => w.agent_id));
      setUndone(true);
      setReceipt(null);
      setChosen([]);
      onUndone?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not undo. The workers were left in place.");
    } finally {
      setBusy(false);
    }
  };

  if (loadError) return <ErrorState message={loadError} onRetry={() => { setLoadError(null); setReload((n) => n + 1); }} />;
  if (!catalog) return <LoadingState rows={4} />;

  if (receipt) {
    return (
      <div className="space-y-3 text-sm" role="status">
        <p>{hireSummary(receipt)}</p>
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
        <button type="button" disabled={busy} onClick={() => void undo()} className="cursor-pointer rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-hover disabled:opacity-50">
          {busy ? "Undoing…" : "Undo"}
        </button>
        <p className="text-xs text-muted">Undo works while a worker is unchanged and has not been used.</p>
        {!profileDone && (
          <section aria-label="Business profile" className="space-y-2 border-t border-line pt-3">
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted">Tell your workers about your business</h4>
            <BusinessProfileForm skipLabel="Later" onSkip={() => setProfileDone(true)} onSaved={() => setProfileDone(true)} />
          </section>
        )}
      </div>
    );
  }

  if (catalog.templates.length === 0) return <EmptyPanel title="No workers yet" description="Check back after an update." />;

  return (
    <div className="space-y-4">
      {undone && <p role="status" className="text-xs text-muted">Those workers were removed.</p>}
      <p className="text-sm text-muted">Tick any workers you want, or none. You can add more later from Templates.</p>
      {!helpOpen ? (
        <button type="button" onClick={openHelp} className="cursor-pointer rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-hover">
          Help me choose
        </button>
      ) : (
        <section aria-label="Help me choose" className="space-y-3 rounded-md border border-line p-3">
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium">What do you want help with?</legend>
            {goals.map((goal) => (
              <label key={goal.key} className="flex cursor-pointer items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={pickedGoals.includes(goal.key)}
                  onChange={() => setPickedGoals((now) => (now.includes(goal.key) ? now.filter((k) => k !== goal.key) : [...now, goal.key]))}
                />
                <span>{goal.label}</span>
              </label>
            ))}
          </fieldset>
          <label className="block space-y-1 text-xs">
            <span className="font-medium">What does your business do? (optional)</span>
            <input
              type="text"
              value={about}
              maxLength={500}
              onChange={(event) => setAbout(event.target.value)}
              className="w-full rounded-md border border-line bg-transparent px-2 py-1 text-xs"
            />
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs">
            <input type="checkbox" checked={quickOnly} onChange={() => setQuickOnly((v) => !v)} />
            <span>Only workers that start with no questions</span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || (pickedGoals.length === 0 && about.trim() === "")}
              onClick={() => void suggest()}
              className="cursor-pointer rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              Suggest workers
            </button>
            <button type="button" onClick={() => setHelpOpen(false)} className="cursor-pointer rounded-md px-3 py-1 text-xs text-muted hover:bg-hover">
              Close
            </button>
            {helpNote && <span role="status" className="text-xs text-muted">{helpNote}</span>}
          </div>
        </section>
      )}
      {groups.map((group) => (
        <section key={group.category} aria-label={categoryLabel(group.category)} className="space-y-2">
          <h4 className="text-xs font-medium uppercase tracking-wide text-muted">{categoryLabel(group.category)}</h4>
          <ul className="grid min-w-0 gap-3 sm:grid-cols-2">
            {group.templates.map((template) => {
              const isTicked = ticked.includes(template.id);
              const atLimit = !isTicked && ticked.length >= MAX_HIRE;
              return (
                <li key={template.id} className={`min-w-0 rounded-md border p-3 ${isTicked ? "border-accent bg-inset" : "border-line"}`}>
                  <label className={`flex items-start gap-2 ${template.available && !atLimit ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}>
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={isTicked}
                      disabled={busy || !template.available || atLimit}
                      onChange={() => setChosen(toggleChoice(ticked, template.id))}
                      aria-label={`Choose ${template.name}`}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{template.name}</span>
                      <span className="block text-xs text-muted">{template.role}</span>
                      <span className="mt-1 block text-xs">{template.description}</span>
                      {isTicked && reasons[template.id] && <span className="mt-1 block text-xs text-muted">{reasons[template.id]}</span>}
                    </span>
                  </label>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {requirementBadges(template).map((badge) =>
                      badge.connectHref ? (
                        <Link key={badge.requirement} href={badge.connectHref} className={`${TAG} underline hover:bg-hover`}>{badge.text}</Link>
                      ) : (
                        <span key={badge.requirement} className={TAG}>{badge.text}</span>
                      ),
                    )}
                    {template.routines.length > 0 && <span className={TAG}>{SETUP_DEPTH_LABELS[template.setup_depth]}</span>}
                    {starterRoutinesLabel(template.routines) && <span className={TAG}>{starterRoutinesLabel(template.routines)}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy || ticked.length === 0}
          onClick={() => void hire()}
          className="cursor-pointer rounded-md border border-line px-3 py-1 text-xs font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Adding…" : ticked.length === 0 ? "Add workers" : `Add ${ticked.length} worker${ticked.length === 1 ? "" : "s"}`}
        </button>
        {onSkip && (
          <button type="button" disabled={busy} onClick={onSkip} className="cursor-pointer rounded-md px-3 py-1 text-xs text-muted hover:bg-hover disabled:opacity-50">
            {skipLabel}
          </button>
        )}
        <span className="text-xs text-muted">{ticked.length} of up to {MAX_HIRE} chosen</span>
      </div>
    </div>
  );
}
