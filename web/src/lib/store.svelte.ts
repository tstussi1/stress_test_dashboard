// The page's reactive state. Everything the user can change lives in `explorer.state` and is
// replaced (never mutated) on each change. Nothing is written to the URL while working;
// "Copy link" produces the share code (see state.ts).
import { DataError, browserReader, loadData } from './data';
import {
  applySpec,
  codeFromHash,
  decodeState,
  defaultState,
  encodeState,
  normalizeState,
  shareHash
} from './state';
import type { ChartHandle } from './chart';
import type { Data, ExplorerState } from './types';

class Explorer {
  data = $state.raw<Data | null>(null);
  state = $state.raw<ExplorerState | null>(null);
  notices = $state.raw<string[]>([]);
  error = $state.raw<string | null>(null);
  copied = $state(false);
  linkToCopy = $state.raw<string | null>(null);
  hovered = $state.raw<string | null>(null);
  renderAllPanels = $state(false); // set while exporting, so panels below the fold are drawn too
  charts = new Map<string, ChartHandle>(); // variable id -> live chart (focus chart and grid panels), for PNG export

  async init(): Promise<void> {
    try {
      const data = await loadData(browserReader(import.meta.env.BASE_URL));
      this.data = data;
      this.applyHash();
    } catch (e) {
      this.error =
        e instanceof DataError ? e.message : `The dashboard could not start: ${(e as Error).message}`;
    }
  }

  /** Restore the state from a `#c=` share code in the address bar (also when a new link is pasted into an open tab). */
  applyHash(): void {
    const data = this.data!;
    const code = codeFromHash(window.location.hash);
    if (code === null) {
      this.state ??= defaultState(data.catalog);
      return;
    }
    const decoded = decodeState(code, data.catalog);
    this.state = decoded.state;
    this.notices = decoded.notices;
  }

  get s(): ExplorerState {
    if (!this.state) throw new Error('state read before data loaded');
    return this.state;
  }

  set(patch: Partial<ExplorerState>): void {
    this.state = normalizeState({ ...this.s, ...patch });
  }

  /** Make a variable the focus chart; used by the combobox and by clicking a panel in the grid. */
  focusVariable(id: string, scroll = false): void {
    this.set({ variable: id });
    if (scroll)
      document.getElementById('focus-figure')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /** Switch the grid between domestic and international variables; the focus moves to the first variable of that scope. */
  setScope(scope: 'domestic' | 'international'): void {
    const first = this.data!.catalog.variables.find((v) => v.scope === scope);
    if (first) this.set({ variable: first.id });
  }

  applyQuickView(id: string): void {
    const view = this.data!.catalog.quick_views.find((q) => q.id === id);
    if (!view) throw new Error(`unknown quick view '${id}'`);
    this.state = applySpec(this.s, view.state, this.data!.catalog);
    this.hovered = null;
  }

  toggleScenario(name: string): void {
    const has = this.s.scenarios.includes(name);
    if (has && this.s.scenarios.length === 1) return;
    const order = this.data!.catalog.scenarios.map((x) => x.name);
    const next = has ? this.s.scenarios.filter((x) => x !== name) : [...this.s.scenarios, name];
    this.set({ scenarios: next.sort((a, b) => order.indexOf(a) - order.indexOf(b)) });
  }

  setVintages(ids: string[]): void {
    if (ids.length === 0) return;
    const order = this.data!.catalog.vintages.map((v) => v.id);
    this.set({ vintages: [...ids].sort((a, b) => order.indexOf(a) - order.indexOf(b)) });
  }

  togglePin(vintage: string): void {
    const pins = this.s.pins.includes(vintage)
      ? this.s.pins.filter((p) => p !== vintage)
      : [...this.s.pins, vintage];
    this.hovered = null;
    this.set({ pins });
  }

  clearPins(): void {
    if (this.s.pins.length) this.set({ pins: [] });
  }

  reset(): void {
    this.state = defaultState(this.data!.catalog);
    this.notices = [];
  }

  dismissNotice(index: number): void {
    this.notices = this.notices.filter((_, i) => i !== index);
  }

  async copyLink(): Promise<void> {
    const url = `${window.location.origin}${window.location.pathname}${shareHash(encodeState(this.s, this.data!.catalog))}`;
    try {
      await navigator.clipboard.writeText(url);
      this.linkToCopy = null;
      this.copied = true;
      setTimeout(() => (this.copied = false), 2200);
    } catch {
      this.linkToCopy = url; // clipboard blocked (e.g. insecure context): show the link instead
    }
  }
}

export const explorer = new Explorer();
