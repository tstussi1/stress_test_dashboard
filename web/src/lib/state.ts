// Explorer state: defaults, quick views and the compact share code behind "Copy link".
//
// The page URL stays clean; "Copy link" produces `#c=<code>`, about 12-20 characters:
//   version | variable index | scenario mask | vintage mask | pin mask | flags
// Indexes refer to catalog.state_order, which is append-only (export_web_data.py refuses to
// reorder it), so old codes keep decoding after new vintages or variables are added. A code that
// cannot be read, or was made for another state_version, never decodes silently wrong: the caller
// receives notices naming what was ignored.
import type {
  Axis,
  Basis,
  Catalog,
  Defaults,
  ExplorerState,
  HistoryMode,
  RangeMode,
  Tab,
  ViewMode,
  VintageSpec
} from './types';

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
const VIEWS: ViewMode[] = ['published', 'level', 'deviation'];
const BASES: Basis[] = ['growth_gap', 'level_gap'];
const AXES: Axis[] = ['horizon', 'calendar'];
const HISTORIES: HistoryMode[] = ['off', 'latest', 'realtime'];
const RANGES: RangeMode[] = ['recent', 'full'];
const TABS: Tab[] = ['explorer', 'methodology'];

/** Vintage ids a spec stands for: 'all', the latest N in publication order, or an explicit list. */
export function resolveVintages(spec: VintageSpec, catalog: Catalog): string[] {
  const ids = catalog.vintages.map((v) => v.id);
  if (spec === 'all') return ids;
  if (Array.isArray(spec)) return spec;
  return ids.slice(-spec.latest);
}

/** A message naming the first thing wrong with a default or quick-view spec, or null. */
export function specProblem(spec: Partial<Defaults>, catalog: Catalog): string | null {
  const scenarios = new Set(catalog.scenarios.map((s) => s.name));
  const vintages = new Set(catalog.vintages.map((v) => v.id));
  if (spec.variable !== undefined && !catalog.variables.some((v) => v.id === spec.variable))
    return `variable '${spec.variable}' is not in the data`;
  for (const s of spec.scenarios ?? []) if (!scenarios.has(s)) return `scenario '${s}' is not in the data`;
  if (spec.vintages !== undefined) {
    const ids = resolveVintages(spec.vintages, catalog);
    if (ids.length === 0) return 'it selects no vintage';
    for (const v of ids) if (!vintages.has(v)) return `vintage '${v}' is not in the data`;
  }
  return null;
}

/** Level paths are indexed to each vintage's own start, so they only exist on the quarters-since axis. */
export function normalizeState(state: ExplorerState): ExplorerState {
  return state.view === 'level' && state.axis !== 'horizon' ? { ...state, axis: 'horizon' } : state;
}

/** Apply a (partial) default or quick-view spec to a state. Pins are cleared: they belong to the old selection. */
export function applySpec(state: ExplorerState, spec: Partial<Defaults>, catalog: Catalog): ExplorerState {
  const { vintages, ...rest } = spec;
  return normalizeState({
    ...state,
    ...rest,
    ...(vintages !== undefined ? { vintages: resolveVintages(vintages, catalog) } : {}),
    pins: []
  });
}

export function defaultState(catalog: Catalog): ExplorerState {
  const base: ExplorerState = { ...catalog.defaults, tab: 'explorer', vintages: [], pins: [] };
  return applySpec(base, catalog.defaults, catalog);
}

export interface Decoded {
  state: ExplorerState;
  notices: string[];
}

function maskToCode(indexes: number[]): string {
  if (indexes.length === 0) return ALPHABET[0]!;
  const chars = Math.ceil((Math.max(...indexes) + 1) / 6);
  const values = new Array<number>(chars).fill(0);
  for (const i of indexes) values[Math.floor(i / 6)]! |= 1 << (i % 6);
  return ALPHABET[chars]! + values.map((v) => ALPHABET[v]).join('');
}

class Reader {
  private pos = 0;
  constructor(private readonly code: string) {}
  next(): number {
    const c = this.code[this.pos++];
    const v = c === undefined ? -1 : ALPHABET.indexOf(c);
    if (v < 0) throw new Error(c === undefined ? 'the code is too short' : `unexpected character '${c}'`);
    return v;
  }
  mask(): number[] {
    const chars = this.next();
    const out: number[] = [];
    for (let k = 0; k < chars; k++) {
      const v = this.next();
      for (let b = 0; b < 6; b++) if (v & (1 << b)) out.push(k * 6 + b);
    }
    return out;
  }
  done(): boolean {
    return this.pos === this.code.length;
  }
}

const indexesOf = (ids: string[], order: string[]): number[] =>
  ids.map((id) => order.indexOf(id)).filter((i) => i >= 0);

export function encodeState(state: ExplorerState, catalog: Catalog): string {
  const order = catalog.state_order;
  const variable = order.variables.indexOf(state.variable);
  if (variable < 0) throw new Error(`variable '${state.variable}' is not in the share-code order`);
  const flags =
    VIEWS.indexOf(state.view) |
    (BASES.indexOf(state.basis) << 2) |
    (AXES.indexOf(state.axis) << 3) |
    (HISTORIES.indexOf(state.history) << 4) |
    (RANGES.indexOf(state.range) << 6) |
    ((state.band ? 1 : 0) << 7) |
    (TABS.indexOf(state.tab) << 8);
  return (
    ALPHABET[catalog.state_version]! +
    ALPHABET[variable]! +
    maskToCode(indexesOf(state.scenarios, order.scenarios)) +
    maskToCode(indexesOf(state.vintages, order.vintages)) +
    maskToCode(indexesOf(state.pins, order.vintages)) +
    ALPHABET[flags & 63]! +
    ALPHABET[flags >> 6]!
  );
}

export function decodeState(code: string, catalog: Catalog): Decoded {
  const fallback = (why: string): Decoded => ({
    state: defaultState(catalog),
    notices: [`This link could not be restored (${why}); showing the default view.`]
  });
  const order = catalog.state_order;
  const notices: string[] = [];
  try {
    const r = new Reader(code);
    if (r.next() !== catalog.state_version) {
      return fallback('it was made with an older version of the data');
    }
    const variableIdx = r.next();
    const scenarioIdx = r.mask();
    const vintageIdx = r.mask();
    const pinIdx = r.mask();
    const flagsLow = r.next();
    const flags = flagsLow | (r.next() << 6);
    if (!r.done()) return fallback('it has extra characters');

    const pick = (idx: number[], list: string[], what: string): string[] => {
      const unknown = idx.filter((i) => i >= list.length).length;
      if (unknown)
        notices.push(
          `${unknown} ${what}${unknown > 1 ? 's' : ''} in this link no longer exist${unknown > 1 ? '' : 's'} and ${unknown > 1 ? 'were' : 'was'} ignored.`
        );
      return idx.filter((i) => i < list.length).map((i) => list[i]!);
    };
    const d = defaultState(catalog);
    const variable = order.variables[variableIdx];
    const scenarios = pick(scenarioIdx, order.scenarios, 'scenario');
    // The code indexes the append-only order; the page works in chronological (display) order.
    const chronological = catalog.vintages.map((v) => v.id);
    const byTime = (ids: string[]): string[] =>
      [...ids].sort((x, y) => chronological.indexOf(x) - chronological.indexOf(y));
    const vintages = byTime(pick(vintageIdx, order.vintages, 'vintage'));
    const choice = <T>(list: T[], index: number, fallbackValue: T): T => list[index] ?? fallbackValue;
    const state = normalizeState({
      variable: variable ?? d.variable,
      scenarios: scenarios.length ? scenarios : d.scenarios,
      vintages: vintages.length ? vintages : d.vintages,
      pins: byTime(pick(pinIdx, order.vintages, 'pinned vintage')),
      view: choice(VIEWS, flags & 3, d.view),
      basis: BASES[(flags >> 2) & 1]!,
      axis: AXES[(flags >> 3) & 1]!,
      history: choice(HISTORIES, (flags >> 4) & 3, d.history),
      range: RANGES[(flags >> 6) & 1]!,
      band: ((flags >> 7) & 1) === 1,
      tab: TABS[(flags >> 8) & 1]!
    });
    if (!variable) notices.push('The variable in this link no longer exists; the default variable is shown.');
    if (!scenarios.length)
      notices.push('No scenario in this link could be restored; the default scenario is shown.');
    if (!vintages.length)
      notices.push('No vintage in this link could be restored; the default vintages are shown.');
    return { state, notices };
  } catch (error) {
    return fallback((error as Error).message);
  }
}

export const codeFromHash = (hash: string): string | null => (hash.startsWith('#c=') ? hash.slice(3) : null);
export const shareHash = (code: string): string => `#c=${code}`;
