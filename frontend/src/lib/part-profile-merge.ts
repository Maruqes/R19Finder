import type { Fact } from "./types.ts";
export interface Change {
  id: string;
  value: string;
  previous: Fact[];
}
/* Pure three-way merge shared by the browser and behavioral tests. */

export function merge(
  current: Fact[],
  original: Fact[],
  suggestions: Fact[],
  multipleFields: string[],
  handledIds: string[] = [],
) {
  const facts = structuredClone(current);
  const pending: Fact[] = [],
    undo: Change[] = [],
    handled = new Set(handledIds);
  const multiple = new Set(multipleFields);
  for (const suggestion of suggestions) {
    if (handled.has(suggestion.id) || facts.some((f) => f.id === suggestion.id))
      continue;
    handled.add(suggestion.id);
    const active = facts.filter(
      (f) => f.field === suggestion.field && f.value.trim(),
    );
    if (
      active.some(
        (f) =>
          f.value.trim().toLowerCase() ===
          suggestion.value.trim().toLowerCase(),
      )
    )
      continue;
    const arrival = current.filter(
      (f) => f.field === suggestion.field && f.value.trim(),
    );
    const before = original.filter(
      (f) => f.field === suggestion.field && f.value.trim(),
    );
    const unchanged =
      JSON.stringify(arrival.map((f) => f.value)) ===
      JSON.stringify(before.map((f) => f.value));
    if (unchanged && (multiple.has(suggestion.field) || !active.length)) {
      for (let i = facts.length - 1; i >= 0; i--) {
        if (facts[i].field === suggestion.field && !facts[i].value.trim())
          facts.splice(i, 1);
      }
      facts.push(structuredClone(suggestion));
      undo.push({ id: suggestion.id, value: suggestion.value, previous: [] });
    } else pending.push(structuredClone(suggestion));
  }
  return { facts, pending, undo, handled: [...handled].slice(-200) };
}
export function undoFill(current: Fact[], changes: Change[]) {
  let facts = structuredClone(current);
  for (const change of [...changes].reverse()) {
    const fact = facts.find((f) => f.id === change.id);
    if (
      !fact ||
      fact.value !== change.value ||
      fact.verification_status === "user_confirmed"
    )
      continue;
    facts = facts.filter((f) => f.id !== change.id);
    for (const previous of change.previous || [])
      if (!facts.some((f) => f.id === previous.id)) facts.push(previous);
  }
  return facts;
}
