import { describe, expect, it } from 'vitest';
import { completeDatasetCsv, csvFilename, toCsv } from '../src/lib/export';
import { buildPlotModel } from '../src/lib/query';
import { stateWith, realData } from './helpers';

/** Minimal RFC 4180 parser for the round trip; `#` header lines are returned separately. */
function parseCsv(text: string): { comments: string[]; rows: string[][] } {
  const comments: string[] = [];
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  let atLineStart = true;
  for (let i = 0; i < text.length; i++) {
    const c = text[i]!;
    if (atLineStart && !quoted && c === '#') {
      const end = text.indexOf('\r\n', i);
      comments.push(text.slice(i + 2, end));
      i = end + 1;
      continue;
    }
    atLineStart = false;
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') {
      row.push(cell);
      cell = '';
    } else if (c === '\r') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i++;
      atLineStart = true;
    } else cell += c;
  }
  return { comments, rows };
}

describe('CSV download', () => {
  it('lists exactly the plotted numbers, unrounded, under header lines that state the transform, with a byte-order mark', async () => {
    const { data, state } = await stateWith({
      variable: 'devasia_usd_exchange_rate',
      vintages: ['2018', '2019'],
      scenarios: ['severely_adverse', 'adverse'],
      view: 'published',
      axis: 'calendar',
      history: 'latest',
      band: true
    });
    const model = buildPlotModel(state, data, 'devasia_usd_exchange_rate');
    const text = toCsv([model]);
    expect(text.charCodeAt(0)).toBe(0xfeff);
    const { comments, rows } = parseCsv(text.slice(1));
    expect(comments[0]).toBe(model.title);
    expect(comments.join('\n')).toMatch(/Transform: none; values exactly as published/);
    expect(comments.join('\n')).toMatch(/publications: 2018, 2019/);
    expect(comments.join('\n')).toMatch(/min-max band: on/);
    expect(rows[0]).toEqual([
      'variable_id',
      'variable',
      'unit',
      'view',
      'basis',
      'series_type',
      'vintage_id',
      'scenario',
      'quarter',
      'horizon',
      'value',
      'fed_estimate'
    ]);
    expect(rows).toHaveLength(model.rows.length + 1);
    expect(rows[1]![1]).toBe(model.variable.name); // the name contains a comma and survives quoting
    expect(model.variable.name).toContain(',');
    model.rows.forEach((r, i) => {
      const line = rows[i + 1]!;
      expect(Number(line[10])).toBe(r.value); // exact, not rounded
      expect(line[5]).toBe(r.series_type);
      expect(line[6]).toBe(r.vintage);
      expect(line[8]).toBe(r.quarter);
    });
  });

  it('states a calculated transform for a deviation and carries no history rows there', async () => {
    const { data, state } = await stateWith({
      variable: 'real_gdp_growth',
      view: 'deviation',
      basis: 'level_gap',
      axis: 'horizon',
      vintages: ['2025', '2026']
    });
    const gdp = buildPlotModel(state, data, 'real_gdp_growth');
    const { comments, rows } = parseCsv(toCsv([gdp]).slice(1));
    expect(comments.join('\n')).toMatch(
      /Transform: calculated; scenario minus the same publication's baseline \(gap measured as percent difference in cumulated level\)/
    );
    expect(rows[1]![4]).toBe('level_gap');
    expect(rows.slice(1).some((r) => r[5]!.startsWith('history'))).toBe(false);
    const level = buildPlotModel({ ...state, variable: 'unemployment_rate' }, data, 'unemployment_rate');
    expect(parseCsv(toCsv([level]).slice(1)).rows[1]![4]).toBe('');
    expect(csvFilename([gdp], '2026-10-23T12:00:00+00:00')).toBe(
      'stress-scenarios_real_gdp_growth_deviation_2026-10-23.csv'
    );
    expect(csvFilename([gdp, level], '2026-10-23T12:00:00+00:00')).toBe(
      'stress-scenarios_2-variables_deviation_2026-10-23.csv'
    );
  });
});

describe('complete dataset download', () => {
  it('has one row per stored number: 14,846 scenario rows and 34,397 history rows, with the published numbers untouched', async () => {
    const data = await realData();
    const { comments, rows } = parseCsv(completeDatasetCsv(data).slice(1));
    expect(comments.join('\n')).toContain(data.catalog.db_sha256);
    const [header, ...body] = rows;
    expect(header![0]).toBe('record_type');
    expect(body.filter((r) => r[0] === 'scenario')).toHaveLength(14846);
    expect(body.filter((r) => r[0] === 'history')).toHaveLength(34397);
    const sample = data.series.find(
      (s) => s.variable === 'unemployment_rate' && s.vintage === '2026' && s.scenario === 'severely_adverse'
    )!;
    const line = body.find(
      (r) =>
        r[1] === 'unemployment_rate' && r[3] === '2026' && r[4] === 'severely_adverse' && r[5] === '2027Q3'
    )!;
    expect(Number(line[7])).toBe(sample.published[6]!);
    expect(Number(line[7])).toBe(10);
    expect(Number(line[9])).toBeCloseTo(5.7, 6);
    const hist = data.actualsBy.get('unemployment_rate|2013')!;
    const first = body.find((r) => r[0] === 'history' && r[1] === 'unemployment_rate' && r[3] === '2013')!;
    expect(first[5]).toBe(hist.start);
    expect(Number(first[7])).toBe(hist.values[0]);
  });
});
