
export type TemplateSkill = { name: string; description: string; body: string };

export type TemplateRoutine = {
  id: string;
  skill: string;
  days: string[];
  window: string;
  budget_minutes: number;
  note: string;
  // Always false: choosing a template never creates or switches on a routine.
  enabled_after_install: boolean;
};

export type SetupDepth = "express" | "standard" | "guided";

export type AgentTemplate = {
  id: string;
  name: string;
  role: string;
  category: string;
  description: string;
  instructions: string;
  color: string;
  example_requests: string[];
  requires: string[];
  available: boolean;
  // Required connections not ready in this workspace; empty when everything is ready.
  missing: string[];
  starter_notes: string | null;
  skills: TemplateSkill[];
  routines: TemplateRoutine[];
  suggested_tools: string[];
  setup_depth: SetupDepth;
  setup_text: string | null;
};

export type TemplateCatalog = { version: number; categories: string[]; templates: AgentTemplate[] };

export const CATEGORY_LABELS: Record<string, string> = {
  everyday: "Everyday",
  work: "Work",
  writing: "Writing",
  design: "Design",
  sales: "Sales",
  marketing: "Marketing",
  personal: "Personal",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.charAt(0).toUpperCase() + category.slice(1);
}

// Templates whose name, role, description or category contain every word typed
// (ignoring case), within one category or all of them. Mirrors the backend search,
// so the gallery filters as the person types without another request.
export function filterTemplates(templates: AgentTemplate[], query: string, category: string | null): AgentTemplate[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return templates.filter((template) => {
    if (category && template.category !== category) return false;
    const text = `${template.name} ${template.role} ${template.description} ${template.category}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
}

// "Helper", then "Helper 2", "Helper 3" ... the first name no live agent has, within the 80 characters a name may have.
export function uniqueAgentName(name: string, taken: Iterable<string>, max = 80): string {
  const used = new Set(Array.from(taken, (n) => n.trim().toLowerCase()));
  const base = name.trim().slice(0, max);
  if (!used.has(base.toLowerCase())) return base;
  for (let n = 2; ; n += 1) {
    const suffix = ` ${n}`;
    const candidate = base.slice(0, max - suffix.length).trimEnd() + suffix;
    if (!used.has(candidate.toLowerCase())) return candidate;
  }
}

const REQUIREMENT_LABELS: Record<string, string> = { muapi: "MuAPI" };

export function requirementLabel(requirement: string): string {
  return REQUIREMENT_LABELS[requirement] ?? requirement.charAt(0).toUpperCase() + requirement.slice(1);
}

// Where a missing connection is set up inside the app. A requirement with no entry cannot be connected yet.
const CONNECT_PATHS: Record<string, string> = { muapi: "/marketplace/" };

export type RequirementBadge = { requirement: string; text: string; connectHref: string | null };

// How each requirement of a template reads on its card: "Needs MuAPI · Connect" while a connectable one is missing
// (Add stays enabled), "Needs Email · not available yet" for one that cannot be connected, and plain "Needs X"
// once it is ready.
export function requirementBadges(template: AgentTemplate): RequirementBadge[] {
  const missing = new Set(template.missing ?? (template.available ? [] : template.requires));
  return template.requires.map((requirement) => {
    const label = `Needs ${requirementLabel(requirement)}`;
    if (!missing.has(requirement)) return { requirement, text: label, connectHref: null };
    const connectHref = CONNECT_PATHS[requirement] ?? null;
    return connectHref
      ? { requirement, text: `${label} · Connect`, connectHref }
      : { requirement, text: `${label} · not available yet`, connectHref: null };
  });
}

export const SETUP_DEPTH_LABELS: Record<SetupDepth, string> = {
  express: "Express setup",
  standard: "Standard setup",
  guided: "Guided setup",
};

// "2 starter routines (paused)": routines a template describes. Choosing a template creates none of them.
export function starterRoutinesLabel(routines: TemplateRoutine[]): string | null {
  if (routines.length === 0) return null;
  return `${routines.length} starter routine${routines.length === 1 ? "" : "s"} (paused)`;
}

export type SkillInstallResult = { installed: string[]; failed: string[]; unsupported: boolean };

// Installs each chosen skill (`install` is api.installTemplateSkill) on the new agent, one at a time. Never throws: a
// missing skills library (404/405) or any other refusal is reported, and the agent stays.
export async function installTemplateSkills(
  agentId: number,
  templateId: string,
  skills: TemplateSkill[],
  install: (agentId: number, templateId: string, skill: TemplateSkill) => Promise<unknown>,
): Promise<SkillInstallResult> {
  const result: SkillInstallResult = { installed: [], failed: [], unsupported: false };
  for (const skill of skills) {
    try {
      await install(agentId, templateId, skill);
      result.installed.push(skill.name);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 404 || status === 405) {
        result.unsupported = true;
        result.failed.push(...skills.slice(skills.indexOf(skill)).map((s) => s.name));
        break;
      }
      result.failed.push(skill.name);
    }
  }
  return result;
}

export function skillInstallNotice(result: SkillInstallResult): string | null {
  if (result.failed.length === 0) return null;
  if (result.unsupported) return "The agent was created, but this version has no skills library, so the suggested skills were not added.";
  return `The agent was created, but these skills were not added: ${result.failed.join(", ")}.`;
}

export type HiredRoutine = { template_routine_id: string; routine_id: number; name: string; paused: boolean };
export type HiredWorker = { template_id: string; agent_id: number; name: string; skills: string[]; routines: HiredRoutine[] };
export type HireReceipt = { workers: HiredWorker[] };

// The most workers one hire may add; the server enforces the same limit.
export const MAX_HIRE = 8;

// Templates grouped by category, in the catalog's category order, skipping empty groups.
export function groupByCategory(templates: AgentTemplate[], categories: string[]): { category: string; templates: AgentTemplate[] }[] {
  const order = [...categories, ...templates.map((t) => t.category).filter((c) => !categories.includes(c))];
  return [...new Set(order)]
    .map((category) => ({ category, templates: templates.filter((t) => t.category === category) }))
    .filter((group) => group.templates.length > 0);
}

// Tick or untick one worker. Ticking past the limit changes nothing.
export function toggleChoice(chosen: string[], id: string): string[] {
  if (chosen.includes(id)) return chosen.filter((item) => item !== id);
  return chosen.length >= MAX_HIRE ? chosen : [...chosen, id];
}

// Only workers the server will accept can stay ticked (for example after the list reloads).
export function hireableChoices(chosen: string[], templates: AgentTemplate[]): string[] {
  const ok = new Set(templates.filter((t) => t.available).map((t) => t.id));
  return chosen.filter((id) => ok.has(id));
}

export function hireSummary(receipt: HireReceipt): string {
  const names = receipt.workers.map((w) => w.name).join(", ");
  const count = receipt.workers.length;
  return `Added ${count} worker${count === 1 ? "" : "s"}: ${names}. Their routines are paused until you switch them on.`;
}

export type SuggestGoal = { key: string; label: string };
export type Suggestion = { template_id: string; reason: string };

// The tick set "Help me choose" proposes: suggested workers the server would accept, in suggestion
// order, within the hire limit. It only proposes; the person edits the ticks and confirms.
export function preTick(suggestions: Suggestion[], templates: AgentTemplate[]): string[] {
  return hireableChoices(suggestions.map((s) => s.template_id), templates).slice(0, MAX_HIRE);
}

export function suggestionReasons(suggestions: Suggestion[]): Record<string, string> {
  return Object.fromEntries(suggestions.map((s) => [s.template_id, s.reason]));
}
