import { describe, expect, it } from 'vitest';
import { buildPlotModel, fieldFor, unitFor } from '../src/lib/query';
import { qNum, qStr } from '../src/lib/quarters';
import { stateWith } from './helpers';

const allVintages = (data: { catalog: { vintages: { id: string }[] } }) =>
  data.catalog.vintages.map((v) => v.id);

describe('query layer on the real exported data', () => {
  it('deviation, quarters since start: one line per vintage, values exactly as exported, baseline excluded', async () => {
    const { data, state } = await stateWith({
      variable: 'unemployment_rate',
      vintages: allVintages(await stateWith({}).then((r) => r.data)),
      scenarios: ['baseline', 'severely_adverse'],
      view: 'deviation',
      axis: 'horizon'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    expect(m.series).toHaveLength(15);
    expect(m.series.every((s) => s.scenario === 'severely_adverse')).toBe(true);
    const s2026 = m.series.find((s) => s.vintage === '2026')!;
    expect(s2026.x.slice(0, 3)).toEqual([0, 1, 2]);
    expect(s2026.y[0]).toBe(0); // anchor at the jump-off quarter
    expect(s2026.y[7]).toBeCloseTo(5.7, 6); // 10.0 peak minus 4.3 baseline
    expect(m.unit).toBe('percentage points');
    expect(m.window).toBeNull();
  });

  it('baseline alone in the deviation view is an explicit empty state', async () => {
    const { data, state } = await stateWith({ scenarios: ['baseline'], view: 'deviation' });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    expect(m.series).toHaveLength(0);
    expect(m.empty).toMatch(/baseline/i);
  });

  it('level path of a growth variable starts at 100 and reproduces the exported index, on the quarters-since axis', async () => {
    const { data, state } = await stateWith({
      variable: 'real_gdp_growth',
      vintages: ['2026'],
      scenarios: ['severely_adverse'],
      view: 'level',
      axis: 'horizon'
    });
    const s = buildPlotModel(state, data, 'real_gdp_growth').series[0]!;
    expect(s.y[0]).toBe(100);
    expect(s.y[6]).toBeCloseTo(95.39, 2); // 2027Q2 is horizon 6
    expect(s.info[6]!.quarter).toBe('2027Q2');
  });

  it('level path of a variable that is already a level is shown as published, with a note', async () => {
    const { data, state } = await stateWith({
      vintages: ['2026'],
      scenarios: ['severely_adverse'],
      view: 'level',
      axis: 'horizon'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    expect(m.notes.join(' ')).toMatch(/already a level/);
    expect(m.series[0]!.y[7]).toBe(10);
  });

  it('history is drawn only in the as-published view on the calendar axis, never as per-vintage spikes', async () => {
    const base = { vintages: ['2025', '2026'], scenarios: ['severely_adverse'] };
    for (const [view, axis, histories] of [
      ['published', 'horizon', 0],
      ['deviation', 'horizon', 0],
      ['deviation', 'calendar', 0],
      ['level', 'horizon', 0],
      ['published', 'calendar', 1]
    ] as const) {
      const { data, state } = await stateWith({ ...base, view, axis, history: 'latest' });
      const m = buildPlotModel(state, data, 'unemployment_rate');
      const stretches = m.series.filter((s) => s.kind === 'history');
      expect(stretches.length > 0).toBe(histories === 1);
      expect(m.rows.filter((r) => r.series_type.startsWith('history'))).toHaveLength(
        new Set(stretches.flatMap((s) => s.x)).size
      );
    }
  });

  it('latest-publication history takes each quarter from the newest publication that reports it and names it', async () => {
    const { data, state } = await stateWith({ view: 'published', axis: 'calendar', history: 'latest' });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    const stretches = m.series.filter((s) => s.kind === 'history');
    expect(stretches).toHaveLength(1); // one selected year, one jump-off, one stretch
    const h = stretches[0]!;
    expect(h.x[h.x.length - 1]).toBe(qNum('2025Q4'));
    expect(h.info[h.info.length - 1]!.source).toBe('2026');
    const rows = m.rows.filter((r) => r.series_type === 'history_latest');
    expect(rows).toHaveLength(h.x.length);
    expect(rows[0]!.vintage).toBe(h.info[0]!.source);
    expect(h.info[0]!.source).toBe('2013'); // pre-2000 quarters exist only in the 2013 workbook
  });

  it("real-time history draws each selected vintage's own history, as published then", async () => {
    const { data, state } = await stateWith({
      vintages: ['2020_feb', '2020_sep'],
      view: 'published',
      axis: 'calendar',
      history: 'realtime'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    const own = m.series.filter((s) => s.kind === 'vintage_history');
    expect(own.map((s) => s.vintage)).toEqual(['2020_feb', '2020_sep']);
    const feb = data.actualsBy.get('unemployment_rate|2020_feb')!;
    expect(own[0]!.y).toEqual(feb.values);
    expect(own[1]!.x.length).toBeGreaterThan(own[0]!.x.length); // the September publication knows more quarters
  });

  it('calendar window: Recent is a configured number of quarters of context, Full starts at the first quarter the Fed reports for that variable', async () => {
    const recent = await stateWith({ view: 'published', axis: 'calendar', range: 'recent' });
    const full = await stateWith({ view: 'published', axis: 'calendar', range: 'full' });
    const context = recent.data.catalog.limits.calendar_context_quarters;
    const wr = buildPlotModel(recent.state, recent.data, 'unemployment_rate').window!;
    const wf = buildPlotModel(full.state, full.data, 'unemployment_rate').window!;
    expect(wr.from).toBe(qNum('2025Q4') - context);
    expect(wf.from).toBe(qNum('1976Q1'));
    expect(wf.to).toBe(wr.to);
    // each variable starts where its own history starts, not at a fixed year
    const vix = buildPlotModel(full.state, full.data, 'vix').window!;
    expect(qStr(vix.first)).toBe('1990Q1');
    const prime = buildPlotModel(full.state, full.data, 'prime_rate').window!;
    expect(qStr(prime.first)).toBe('2000Q1');
  });

  it("history stops at the newest selected year's start: 2017 alone ends at 2016 Q4 and the chart ends with its scenario", async () => {
    const { data, state } = await stateWith({
      variable: 'unemployment_rate',
      vintages: ['2017'],
      scenarios: ['severely_adverse'],
      view: 'published',
      axis: 'calendar',
      history: 'latest',
      range: 'full'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    const h = m.series.filter((s) => s.kind === 'history');
    expect(h).toHaveLength(1);
    expect(h[0]!.x[h[0]!.x.length - 1]).toBe(qNum('2016Q4'));
    expect(h[0]!.knownTo).toBe(qNum('2016Q4'));
    expect(m.window!.to).toBe(qNum('2020Q1'));
    expect(
      m.rows.filter((r) => r.series_type === 'history_latest').every((r) => qNum(r.quarter) <= qNum('2016Q4'))
    ).toBe(true);
    expect(m.series.some((s) => s.vintage === '2026')).toBe(false);
  });

  it('with two years the history is split at their starts, the stretches join without a gap and each quarter is listed once', async () => {
    const { data, state } = await stateWith({
      variable: 'unemployment_rate',
      vintages: ['2017', '2026'],
      scenarios: ['severely_adverse'],
      view: 'published',
      axis: 'calendar',
      history: 'latest'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    const [first, second] = m.series.filter((s) => s.kind === 'history');
    expect([first!.knownTo, second!.knownTo]).toEqual([qNum('2016Q4'), qNum('2025Q4')]);
    expect(second!.x[0]).toBe(first!.x[first!.x.length - 1]); // shared boundary point
    expect(second!.x[second!.x.length - 1]).toBe(qNum('2025Q4'));
    const quarters = m.rows.filter((r) => r.series_type === 'history_latest').map((r) => qNum(r.quarter));
    expect(quarters).toEqual([...new Set([...first!.x, ...second!.x])]);
    expect(quarters.every((q, i) => i === 0 || q === quarters[i - 1]! + 1)).toBe(true);
    expect([...first!.y, ...second!.y.slice(1)]).toEqual(
      quarters.map(
        (q) => m.rows.find((r) => r.series_type === 'history_latest' && qNum(r.quarter) === q)!.value
      )
    );
  });

  it('a year that does not publish the variable neither draws nor lengthens the history', async () => {
    const both = await stateWith({
      vintages: ['2013', '2014'],
      scenarios: ['severely_adverse'],
      view: 'published',
      axis: 'calendar',
      history: 'latest'
    });
    const only = { ...both.state, vintages: ['2014'] };
    const m = buildPlotModel(both.state, both.data, 'prime_rate');
    expect(m.series.some((s) => s.vintage === '2013')).toBe(false);
    expect(m.series.filter((s) => s.kind === 'history')).toEqual(
      buildPlotModel(only, both.data, 'prime_rate').series.filter((s) => s.kind === 'history')
    );
    const none = buildPlotModel({ ...both.state, vintages: ['2013'] }, both.data, 'prime_rate');
    expect(none.series).toHaveLength(0);
  });

  it('the min-max band is the lowest and highest of every line drawn at each x, for one year with two scenarios and for six years, keeping every line', async () => {
    const { data } = await stateWith({});
    const cases = [
      {
        vintages: ['2026'],
        scenarios: ['baseline', 'severely_adverse'],
        view: 'published',
        axis: 'calendar'
      },
      {
        vintages: allVintages({ catalog: data.catalog }).slice(-6),
        scenarios: ['adverse', 'severely_adverse'],
        view: 'deviation',
        axis: 'horizon'
      },
      {
        vintages: allVintages({ catalog: data.catalog }),
        scenarios: ['severely_adverse'],
        view: 'published',
        axis: 'horizon'
      }
    ] as const;
    for (const c of cases) {
      const base = (
        await stateWith({ ...c, vintages: [...c.vintages], scenarios: [...c.scenarios], history: 'off' })
      ).state;
      const off = buildPlotModel({ ...base, band: false }, data, 'real_gdp_growth');
      const on = buildPlotModel({ ...base, band: true, pins: ['2026'] }, data, 'real_gdp_growth');
      expect(off.envelopes).toHaveLength(0);
      expect(on.band).toBe(true);
      expect(on.series.map((s) => s.id)).toEqual(off.series.map((s) => s.id)); // every line stays
      const e = on.envelopes[0]!;
      expect(e.x.length).toBeGreaterThan(5);
      e.x.forEach((x, i) => {
        const values = off.series.flatMap((s) => (s.x.includes(x) ? [s.y[s.x.indexOf(x)]!] : []));
        expect(values.length).toBeGreaterThanOrEqual(2);
        expect(e.lo[i]).toBe(Math.min(...values));
        expect(e.hi[i]).toBe(Math.max(...values));
      });
      expect(on.rows.filter((r) => r.series_type === 'envelope_min')).toHaveLength(e.x.length);
      expect(on.rows.filter((r) => r.series_type === 'envelope_max')).toHaveLength(e.x.length);
    }
  });

  it('the band says why it is unavailable: one line drawn, or lines that never share a quarter', async () => {
    const one = await stateWith({ band: true, vintages: ['2026'], scenarios: ['severely_adverse'] });
    const m1 = buildPlotModel(one.state, one.data, 'unemployment_rate');
    expect([m1.band, m1.envelopes.length]).toEqual([false, 0]);
    expect(m1.bandReason).toMatch(/Only one line/);
    expect(m1.notes.join(' ')).toMatch(/Only one line/);
    const apart = await stateWith({
      band: true,
      vintages: ['2017', '2026'],
      scenarios: ['severely_adverse'],
      axis: 'calendar'
    });
    const m2 = buildPlotModel(apart.state, apart.data, 'unemployment_rate');
    expect(m2.band).toBe(false);
    expect(m2.bandReason).toMatch(/do not overlap/);
    const aligned = buildPlotModel({ ...apart.state, axis: 'horizon' }, apart.data, 'unemployment_rate');
    expect([aligned.band, aligned.bandReason]).toEqual([true, null]);
    const off = buildPlotModel({ ...one.state, band: false }, one.data, 'unemployment_rate');
    expect(off.bandReason).toMatch(/Only one line/); // known even while the band is off, so the switch can say why it is disabled
    expect(off.notes.join(' ')).not.toMatch(/Only one line/);
  });

  it('every plotted point is listed exactly once in the rows (what is drawn is what is downloaded)', async () => {
    const { data, state } = await stateWith({
      variable: 'real_gdp_growth',
      vintages: allVintages(await stateWith({}).then((r) => r.data)),
      scenarios: ['adverse', 'severely_adverse'],
      view: 'published',
      axis: 'calendar',
      history: 'latest'
    });
    const m = buildPlotModel(state, data, 'real_gdp_growth');
    const history = m.series.filter((s) => s.kind === 'history');
    // stretches of history share their boundary point, which is listed once
    const plotted =
      m.series.filter((s) => s.kind !== 'history').reduce((n, s) => n + s.x.length, 0) +
      new Set(history.flatMap((s) => s.x)).size;
    const rows = m.rows.filter(
      (r) => !r.series_type.startsWith('envelope') && !r.series_type.startsWith('band')
    );
    expect(rows).toHaveLength(plotted);
  });

  it("summary lists each scenario line's peak and trough from the plotted numbers", async () => {
    const { data, state } = await stateWith({
      vintages: ['2026'],
      scenarios: ['severely_adverse'],
      view: 'published'
    });
    const m = buildPlotModel(state, data, 'unemployment_rate');
    expect(m.summary).toHaveLength(1);
    expect(m.summary[0]).toMatchObject({
      vintage: '2026',
      scenario: 'severely_adverse',
      peak: 10,
      peakQuarter: '2027Q3'
    });
    const line = m.series.find((s) => s.kind === 'scenario')!;
    expect(m.summary[0]!.trough).toBe(Math.min(...line.y.slice(1)));
  });

  it('a variable not published in a vintage produces a note, not a silent gap', async () => {
    const { data, state } = await stateWith({
      vintages: allVintages(await stateWith({}).then((r) => r.data)),
      scenarios: ['severely_adverse'],
      view: 'published',
      axis: 'horizon'
    });
    const m = buildPlotModel(state, data, 'treasury_5y_yield');
    expect(m.notes.join(' ')).toMatch(/not published in the 2013 publication/);
    expect(m.series).toHaveLength(14);
  });

  it('a variable published in none of the selected vintages is an explicit empty state', async () => {
    const { data, state } = await stateWith({ vintages: ['2013'] });
    expect(buildPlotModel(state, data, 'treasury_5y_yield').empty).toMatch(
      /not published in the selected years/
    );
  });

  it('chooses the exported column and unit for each view and basis', async () => {
    const { data } = await stateWith({});
    const gdp = data.catalog.variables.find((v) => v.id === 'real_gdp_growth')!;
    const house = data.catalog.variables.find((v) => v.id === 'house_price_index')!;
    expect(fieldFor('deviation', 'growth_gap', 'growth')).toBe('dev');
    expect(fieldFor('deviation', 'level_gap', 'growth')).toBe('dev_level');
    expect(fieldFor('deviation', 'level_gap', 'level')).toBe('dev');
    expect(fieldFor('level', 'growth_gap', 'level')).toBe('published');
    expect(unitFor({ view: 'deviation', basis: 'level_gap' }, gdp, data.catalog.labels)).toMatch(
      /difference in level/
    );
    expect(unitFor({ view: 'deviation', basis: 'growth_gap' }, house, data.catalog.labels)).toBe(
      'index points'
    );
  });
});
