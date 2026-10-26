import { describe, expect, it } from 'vitest';
import { FADE, focusFor } from '../src/lib/focus';
import { buildPlotModel } from '../src/lib/query';
import type { ExplorerState } from '../src/lib/types';
import { stateWith } from './helpers';

const view = {
  variable: 'unemployment_rate',
  scenarios: ['severely_adverse'],
  view: 'published',
  axis: 'calendar'
} satisfies Partial<ExplorerState>;
const share = (n: number) => FADE + (1 - FADE) * n;

async function twoYears(history: 'latest' | 'realtime' = 'latest') {
  const { data, state } = await stateWith({ ...view, vintages: ['2017', '2026'], history });
  const model = buildPlotModel(state, data, 'unemployment_rate');
  return { model, catalog: data.catalog };
}
const opacities = (focus: ReturnType<typeof focusFor>, ids: string[]) =>
  ids.map((id) => focus.get(id)!.opacity);

describe('focus rule: one rule for default, pins and hover', () => {
  const ids = [
    'history|latest|0',
    'history|latest|1',
    'scenario|2017|severely_adverse',
    'scenario|2026|severely_adverse'
  ];

  it('with nothing active, lines are bright and history newer than the older year is graded lighter', async () => {
    const { model, catalog } = await twoYears();
    const f = focusFor(model, catalog, [], null);
    expect(opacities(f, ids)).toEqual([1, share(0.5), 1, 1]);
    expect([...f.values()].some((x) => x.bold || x.faded)).toBe(false);
  });

  it('pinning 2017 keeps its path and the history it knew bright and sends the rest to the background', async () => {
    const { model, catalog } = await twoYears();
    const f = focusFor(model, catalog, ['2017'], null);
    expect(opacities(f, ids)).toEqual([1, FADE, 1, FADE]);
    expect(f.get(ids[2]!)!.bold).toBe(true);
    expect(f.get(ids[3]!)!.faded).toBe(true);
  });

  it('pinning 2026 keeps all history bright (it knew all of it) and fades the 2017 path', async () => {
    const { model, catalog } = await twoYears();
    expect(opacities(focusFor(model, catalog, ['2026'], null), ids)).toEqual([1, 1, FADE, 1]);
  });

  it('pinning every drawn year, or pinning plus hovering both, equals the default history grading', async () => {
    const { model, catalog } = await twoYears();
    const expected = [1, share(0.5), 1, 1];
    expect(opacities(focusFor(model, catalog, ['2017', '2026'], null), ids)).toEqual(expected);
    expect(opacities(focusFor(model, catalog, ['2017'], '2026'), ids)).toEqual(expected);
  });

  it('hover alone isolates a year like a pin, and leaving restores the default', async () => {
    const { model, catalog } = await twoYears();
    expect(opacities(focusFor(model, catalog, [], '2017'), ids)).toEqual([1, FADE, 1, FADE]);
    expect(opacities(focusFor(model, catalog, [], null), ids)).toEqual([1, share(0.5), 1, 1]);
  });

  it('a pin on a year that draws no line in this chart is ignored, never blanking it', async () => {
    const { model, catalog } = await twoYears();
    expect(opacities(focusFor(model, catalog, ['2013'], null), ids)).toEqual([1, share(0.5), 1, 1]);
  });

  it('with fifteen years the history fades smoothly from full to one year of fifteen', async () => {
    const all = (await stateWith({})).data.catalog.vintages.map((v) => v.id);
    const { data, state } = await stateWith({ ...view, vintages: all, history: 'latest' });
    const model = buildPlotModel(state, data, 'unemployment_rate');
    const stretches = model.series.filter((s) => s.kind === 'history');
    const o = stretches.map((s) => focusFor(model, data.catalog, [], null).get(s.id)!.opacity);
    expect(stretches).toHaveLength(15);
    expect(o[0]).toBe(1);
    expect(o[14]).toBeCloseTo(share(1 / 15), 10);
    expect(o.every((v, i) => i === 0 || v < o[i - 1]!)).toBe(true);
  });

  it("with 'as published then' each year's own history line follows its owner", async () => {
    const { model, catalog } = await twoYears('realtime');
    const own = ['history|2017', 'history|2026'];
    expect(opacities(focusFor(model, catalog, [], null), own)).toEqual([1, 1]);
    expect(opacities(focusFor(model, catalog, ['2017'], null), own)).toEqual([1, FADE]);
  });
});
