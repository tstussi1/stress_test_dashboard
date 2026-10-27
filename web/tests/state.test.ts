import { describe, expect, it } from 'vitest';
import {
  applySpec,
  codeFromHash,
  decodeState,
  defaultState,
  encodeState,
  normalizeState,
  resolveVintages,
  shareHash,
  specProblem
} from '../src/lib/state';
import type { ExplorerState } from '../src/lib/types';
import { realData } from './helpers';

describe('share code', async () => {
  const { catalog } = await realData();

  it('round-trips the default state in a short code', () => {
    const state = defaultState(catalog);
    const code = encodeState(state, catalog);
    expect(code.length).toBeLessThanOrEqual(20);
    expect(decodeState(code, catalog)).toEqual({ state, notices: [] });
  });

  it('round-trips 300 pseudo-random states and keeps typical codes under 20 characters', () => {
    let seed = 12345;
    const rnd = (n: number) => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % n;
    };
    const subset = <T>(items: T[], min: number, max: number): T[] => {
      const count = min + rnd(max - min + 1);
      const chosen = new Set<number>();
      while (chosen.size < Math.min(count, items.length)) chosen.add(rnd(items.length));
      return [...chosen].sort((a, b) => a - b).map((i) => items[i]!);
    };
    let longest = 0;
    for (let k = 0; k < 300; k++) {
      const state: ExplorerState = {
        tab: rnd(2) ? 'methodology' : 'explorer',
        variable: catalog.state_order.variables[rnd(catalog.state_order.variables.length)]!,
        scenarios: subset(catalog.state_order.scenarios, 1, 4),
        vintages: subset(
          catalog.vintages.map((v) => v.id),
          1,
          catalog.vintages.length
        ),
        view: (['published', 'level', 'deviation'] as const)[rnd(3)]!,
        basis: rnd(2) ? 'level_gap' : 'growth_gap',
        axis: rnd(2) ? 'calendar' : 'horizon',
        history: (['off', 'latest', 'realtime'] as const)[rnd(3)]!,
        range: rnd(2) ? 'full' : 'recent',
        band: rnd(2) === 1,
        pins: subset(
          catalog.vintages.map((v) => v.id),
          0,
          3
        )
      };
      const normalized = normalizeState(state);
      const code = encodeState(normalized, catalog);
      longest = Math.max(longest, code.length);
      expect(decodeState(code, catalog)).toEqual({ state: normalized, notices: [] });
    }
    expect(longest).toBeLessThanOrEqual(30);
  });

  it('keeps the share-code bit that version 2 used for Range (lines = 0, range = 1) for the min-max band, so existing links still open', () => {
    const state = defaultState(catalog);
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    const high = (band: boolean) => alphabet.indexOf(encodeState({ ...state, band }, catalog).at(-1)!);
    expect([high(false) & 2, high(true) & 2]).toEqual([0, 2]);
    expect(decodeState(encodeState({ ...state, band: true }, catalog), catalog).state.band).toBe(true);
  });

  it('shows the default view with a notice for a code made for another data version', () => {
    const code = encodeState(defaultState(catalog), catalog);
    const other = { ...catalog, state_version: catalog.state_version + 1 };
    const stale = code; // made for the current version, read by a catalog one version newer
    const decoded = decodeState(stale, other);
    expect(decoded.state).toEqual(defaultState(other));
    expect(decoded.notices[0]).toMatch(/older version of the data/);
  });

  it.each([
    '',
    'Z',
    '!!!!',
    code0(catalog) + 'A'.repeat(3),
    encodeState(defaultState(catalog), catalog) + 'A'
  ])('never decodes malformed code %j silently', (code) => {
    const decoded = decodeState(code, catalog);
    expect(decoded.state).toEqual(defaultState(catalog));
    expect(decoded.notices.length).toBeGreaterThan(0);
  });

  it('ignores entries that no longer exist and says so', () => {
    const code = encodeState(defaultState(catalog), catalog);
    const fewer = { ...catalog, state_order: { ...catalog.state_order, variables: [] as string[] } };
    const decoded = decodeState(code, fewer);
    expect(decoded.notices.join(' ')).toMatch(/variable/);
    expect(decoded.state.variable).toEqual(defaultState(catalog).variable);
  });

  it('reads the code from a location hash', () => {
    expect(codeFromHash(shareHash('CAB'))).toBe('CAB');
    expect(codeFromHash('')).toBeNull();
    expect(codeFromHash('#other')).toBeNull();
  });
});

describe('landing state and quick views', async () => {
  const { catalog } = await realData();

  it('opens on the latest vintage as published, on the calendar axis', () => {
    const s = defaultState(catalog);
    expect(s.vintages).toEqual([catalog.vintages.at(-1)!.id]);
    expect([s.view, s.axis, s.history, s.range, s.band]).toEqual([
      'published',
      'calendar',
      'latest',
      'recent',
      false
    ]);
  });

  it('resolves vintage specs in publication order', () => {
    const ids = catalog.vintages.map((v) => v.id);
    expect(resolveVintages('all', catalog)).toEqual(ids);
    expect(resolveVintages({ latest: 6 }, catalog)).toEqual(ids.slice(-6));
    expect(resolveVintages(['2014'], catalog)).toEqual(['2014']);
  });

  it('"Compare years" gives the deviation view on the quarters-since axis for six vintages and clears pins', () => {
    const quick = catalog.quick_views.find((q) => q.id === 'compare_years')!;
    const s = applySpec({ ...defaultState(catalog), pins: ['2024'] }, quick.state, catalog);
    expect([s.view, s.axis, s.vintages.length, s.pins.length]).toEqual(['deviation', 'horizon', 6, 0]);
  });

  it('level paths only exist on the quarters-since axis', () => {
    const s = normalizeState({ ...defaultState(catalog), view: 'level', axis: 'calendar' });
    expect(s.axis).toBe('horizon');
    expect(normalizeState({ ...defaultState(catalog), view: 'published' }).axis).toBe('calendar');
  });

  it('names what is wrong with a spec', () => {
    expect(specProblem({ variable: 'nope' }, catalog)).toMatch(/nope/);
    expect(specProblem({ vintages: ['1999'] }, catalog)).toMatch(/1999/);
    expect(specProblem({ scenarios: ['x'] }, catalog)).toMatch(/'x'/);
  });
});

function code0(catalog: Parameters<typeof defaultState>[0]): string {
  return encodeState(defaultState(catalog), catalog)[0]!;
}

describe('links made before 2011 and 2012 were added', async () => {
  const { catalog } = await realData();

  it('an old share code (made on the 15-vintage catalog) opens to the same selections', () => {
    const decoded = decodeState('CEBFDA8HDAAEWD', catalog);
    expect(decoded.notices).toEqual([]);
    expect(decoded.state).toEqual({
      tab: 'explorer',
      variable: 'unemployment_rate',
      scenarios: ['baseline', 'severely_adverse'],
      vintages: ['2020_sep', '2021', '2022', '2023', '2024', '2025', '2026'],
      view: 'deviation',
      basis: 'level_gap',
      axis: 'horizon',
      history: 'latest',
      range: 'full',
      band: true,
      pins: ['2026']
    });
  });

  it('the new years take the end of the committed order and round-trip', () => {
    const order = catalog.state_order.vintages;
    expect(order.slice(0, 15)[0]).toBe('2013');
    expect(order.slice(15).sort()).toEqual(['2011', '2012']);
    const state = { ...defaultState(catalog), vintages: ['2011', '2012', '2013'], pins: ['2011'] };
    expect(decodeState(encodeState(state, catalog), catalog)).toEqual({ state, notices: [] });
  });
});
