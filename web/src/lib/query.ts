// The query layer: one pure function from (state, data, variable) to everything a chart needs.
// The chart, the data side panel, the summary and the CSV all read the same PlotModel, so what is
// drawn is exactly what is listed and downloaded. Transforms are never recomputed here; the
// exporter wrote published / level / dev / dev_level and this layer only selects a column, aligns
// quarters (calendar or quarters since the scenario started) and takes min/max across the user's
// selection. History (the Fed's own Historical data) is drawn only for the as-published view on the
// calendar axis; it has no deviation and no level path.
import { formatQuarter, formatSigned, formatValue } from './format';
import { qAdd, qNum, qStr } from './quarters';
import type {
  BandSeries,
  Catalog,
  CatalogVariable,
  Data,
  Envelope,
  ExplorerState,
  PlotModel,
  PlotRow,
  PlotSeries,
  PointInfo,
  Series,
  SeriesType,
  SummaryRow
} from './types';

const BAND_LABEL = 'all drawn lines';

type Field = 'published' | 'level' | 'dev' | 'dev_level';

export function fieldFor(
  view: ExplorerState['view'],
  basis: ExplorerState['basis'],
  measure: CatalogVariable['measure']
): Field {
  if (view === 'published') return 'published';
  if (view === 'level') return measure === 'growth' ? 'level' : 'published';
  if (measure === 'level') return 'dev';
  return basis === 'level_gap' ? 'dev_level' : 'dev';
}

export function unitFor(
  state: Pick<ExplorerState, 'view' | 'basis'>,
  variable: CatalogVariable,
  labels: Catalog['labels']
): string {
  if (state.view === 'published')
    return variable.measure === 'growth' ? labels.growth_unit : variable.unit_label;
  if (state.view === 'level') return variable.measure === 'growth' ? labels.level_index : variable.unit_label;
  if (variable.measure === 'growth')
    return state.basis === 'level_gap' ? labels.level_gap : 'percentage points';
  return variable.unit === 'percent'
    ? 'percentage points'
    : variable.unit === 'index'
      ? 'index points'
      : 'exchange-rate units';
}

const VIEW_TITLE = {
  published: 'as published',
  level: 'level path',
  deviation: 'deviation from baseline'
} as const;

const VIEW_TRANSFORM = {
  published: 'none; values exactly as published by the Federal Reserve',
  level:
    "calculated; annualized growth rates compounded into an index (100 = the quarter before each publication's scenario starts); level variables as published",
  deviation: "calculated; scenario minus the same publication's baseline"
} as const;

/** One line per publication-year label list that stays readable: all labels up to three, else first-last and the count. */
function yearsText(labels: string[]): string {
  if (labels.length === 0) return 'no publication selected';
  if (labels.length <= 3) return labels.join(', ');
  return `${labels.length} publications (${labels[0]}-${labels[labels.length - 1]})`;
}

/** A drawn scenario quarter that attains a band edge exactly. */
export interface BandHit {
  label: string;
  quarter: string;
  horizon: number;
}

export interface BandExtreme {
  value: number;
  /** x position on the chart axis (quarter number, or quarters since start) */
  x: number;
  hits: BandHit[];
}

type BandInput = Pick<PlotModel, 'envelopes' | 'series'>;

/**
 * Where the band reaches its lowest and highest value: the minimum of the lower edge and the maximum
 * of the upper edge over the band's points (the earliest x on a tie). Edge values are copies of line
 * values, so every extreme is attributed to the scenario quarters (not the jump-off anchors) that equal it
 * exactly. Nothing is interpolated or recomputed.
 */
export function bandExtremes(model: BandInput): { min: BandExtreme; max: BandExtreme } | null {
  const envelope = model.envelopes[0];
  if (!envelope) return null;
  const hitsAt = (x: number, value: number): BandHit[] =>
    model.series.flatMap((s) => {
      if (s.kind !== 'scenario') return [];
      const i = s.x.indexOf(x);
      const p = s.info[i];
      return i >= 0 && p && p.horizon >= 1 && s.y[i] === value
        ? [{ label: s.label, quarter: p.quarter, horizon: p.horizon }]
        : [];
    });
  const best = (edge: number[], higher: boolean): BandExtreme | null => {
    let found: BandExtreme | null = null;
    edge.forEach((value, k) => {
      if (found && (higher ? value <= found.value : value >= found.value)) return;
      const hits = hitsAt(envelope.x[k]!, value);
      if (hits.length > 0) found = { value, x: envelope.x[k]!, hits };
    });
    return found;
  };
  const min = best(envelope.lo, false);
  const max = best(envelope.hi, true);
  return min && max ? { min, max } : null;
}

const MAX_NAMED_HITS = 3;

/** The two sentences shown under the chart and in the CSV header, from bandExtremes(). */
export function bandReadout(
  model: BandInput & Pick<PlotModel, 'axis' | 'view' | 'unit'>
): { min: string; max: string } | null {
  const extremes = bandExtremes(model);
  if (!extremes) return null;
  const sentence = (name: string, e: BandExtreme): string => {
    const value = model.view === 'deviation' ? formatSigned(e.value) : formatValue(e.value);
    const named = e.hits.slice(0, MAX_NAMED_HITS).map((h) => {
      const where = `${formatQuarter(h.quarter)}${model.axis === 'horizon' ? ` (quarter ${h.horizon})` : ''}`;
      return `${h.label}, ${where}`;
    });
    const more = e.hits.length > MAX_NAMED_HITS ? ` and ${e.hits.length - MAX_NAMED_HITS} more` : '';
    return `${name} ${value} ${model.unit}: ${named.join('; ')}${more}.`;
  };
  return { min: sentence('Band minimum', extremes.min), max: sentence('Band maximum', extremes.max) };
}

export function buildPlotModel(state: ExplorerState, data: Data, variableId: string): PlotModel {
  const { catalog } = data;
  const variable = catalog.variables.find((v) => v.id === variableId);
  if (!variable) throw new Error(`unknown variable '${variableId}'`);
  const field = fieldFor(state.view, state.basis, variable.measure);
  const horizonAxis = state.axis === 'horizon';
  const vintages = catalog.vintages.filter((v) => state.vintages.includes(v.id));
  const scenarios = catalog.scenarios.filter(
    (s) => state.scenarios.includes(s.name) && s.name !== 'realized'
  );
  const shownScenarios =
    state.view === 'deviation' ? scenarios.filter((s) => s.name !== 'baseline') : scenarios;
  const xOf = (quarter: string, horizon: number): number => (horizonAxis ? horizon : qNum(quarter));

  const series: PlotSeries[] = [];
  const rows: PlotRow[] = [];
  const bands: BandSeries[] = [];
  const notes: string[] = [];
  const row = (
    type: SeriesType,
    vintage: string,
    scenario: string,
    quarter: string,
    horizon: number,
    value: number,
    estimated = false
  ) => rows.push({ series_type: type, vintage, scenario, quarter, horizon, value, fed_estimate: estimated });

  const pointInfo = (s: Series, i: number): PointInfo => ({
    quarter: qAdd(s.start, i),
    horizon: i + 1,
    published: s.published[i] ?? null,
    level: s.level?.[i] ?? null,
    dev: s.dev?.[i] ?? null,
    dev_level: s.dev_level?.[i] ?? null,
    estimated: s.estimated?.includes(i) ?? false,
    source: null
  });

  /** Plot line for a scenario, starting from the vintage's own jump-off point (horizon 0). */
  const pushLine = (s: Series, label: string): void => {
    const values = s[field];
    if (!values) return;
    const vintage = catalog.vintages.find((v) => v.id === s.vintage)!;
    const history = data.actualsBy.get(`${s.variable}|${s.vintage}`);
    const lastActual = history ? history.values[history.values.length - 1]! : null;
    const anchorValue =
      field === 'published'
        ? lastActual
        : field === 'level'
          ? 100
          : field === 'dev' || field === 'dev_level'
            ? 0
            : null;
    const x: number[] = [];
    const y: number[] = [];
    const info: PointInfo[] = [];
    if (anchorValue !== null && vintage.jump_off) {
      const estimated = history ? history.estimated.includes(history.values.length - 1) : false;
      x.push(xOf(vintage.jump_off, 0));
      y.push(anchorValue);
      info.push({
        quarter: vintage.jump_off,
        horizon: 0,
        published: lastActual,
        level: variable.measure === 'growth' ? 100 : null,
        dev: null,
        dev_level: null,
        estimated,
        source: null
      });
      row('anchor', s.vintage, s.scenario, vintage.jump_off, 0, anchorValue, estimated);
    }
    values.forEach((v, i) => {
      const p = pointInfo(s, i);
      x.push(xOf(p.quarter, p.horizon));
      y.push(v);
      info.push(p);
      row('scenario', s.vintage, s.scenario, p.quarter, p.horizon, v, p.estimated);
    });
    series.push({
      id: `scenario|${s.vintage}|${s.scenario}`,
      kind: 'scenario',
      vintage: s.vintage,
      scenario: s.scenario,
      label,
      x,
      y,
      info,
      firstProjected: anchorValue === null ? 0 : 1,
      origin: s.origin,
      knownTo: null,
      publishedName: vintage.published_names[s.scenario] ?? null
    });
    if (s.band && state.view === 'published') {
      const offset = anchorValue === null ? 0 : 1;
      bands.push({
        seriesId: series[series.length - 1]!.id,
        x: x.slice(offset),
        lo: s.band.lo,
        hi: s.band.hi,
        label: s.band.label
      });
      s.band.lo.forEach((v, i) => row('band_lo', s.vintage, s.scenario, info[i + offset]!.quarter, i + 1, v));
      s.band.hi.forEach((v, i) => row('band_hi', s.vintage, s.scenario, info[i + offset]!.quarter, i + 1, v));
    }
  };

  for (const vintage of vintages) {
    if (vintage.origin === 'fed' && !vintage.variable_ids.includes(variable.id)) {
      notes.push(`${variable.name} is not published in the ${vintage.label} publication.`);
      continue;
    }
    for (const scenario of shownScenarios) {
      const s = data.seriesBy.get(`${variable.id}|${vintage.id}|${scenario.name}`);
      if (s) pushLine(s, `${vintage.label} ${scenario.label}`);
    }
    if (state.view === 'deviation' && !vintage.has_baseline && shownScenarios.length > 0)
      notes.push(
        `${vintage.label}: no baseline was published in this year's report, so its deviation from baseline cannot be calculated (the line is not drawn).`
      );
  }
  const drawnVintages = catalog.vintages.filter((v) => series.some((s) => s.vintage === v.id));
  for (const vintage of drawnVintages) {
    const bound = vintage.derived_rounding_bound_pp[variable.id];
    if (bound !== undefined)
      notes.push(
        `${vintage.label} ${variable.name} is calculated from the published level (annualized percent change); other publications print it directly. Rounding of the published level can move it by up to ${bound.toFixed(2)} percentage points.`
      );
  }
  const ccar = drawnVintages.filter((v) => v.exercise !== null);
  if (ccar.length > 0) {
    const renamed = [
      ...new Set(series.flatMap((s) => (s.publishedName ? [`${s.scenario}|${s.publishedName}`] : [])))
    ];
    const exercise = [...new Set(ccar.map((v) => catalog.exercise_labels[v.exercise!] ?? v.exercise))].join(
      '; '
    );
    const names = renamed.map((r) => {
      const [scenario, published] = r.split('|');
      return `'${published}' (shown as ${catalog.scenarios.find((x) => x.name === scenario)!.label})`;
    });
    notes.push(
      `${ccar.map((v) => v.label).join(' and ')} ${ccar.length > 1 ? 'are' : 'is a'} ${exercise}.${names.length ? ` The Federal Reserve published the stress path as ${names.join(', ')}.` : ''}`
    );
  }
  if (state.view === 'level' && variable.measure === 'level') {
    notes.push(`${variable.name} is already a level; it is shown as published.`);
  }
  const scenarioLines = series.slice();

  // Peak and trough of every scenario line, read from the plotted numbers (the jump-off anchor is not a scenario quarter).
  const summary: SummaryRow[] = scenarioLines.map((line) => {
    const idx = line.info.map((_, i) => i).filter((i) => line.info[i]!.horizon >= 1);
    const peak = idx.reduce((m, i) => (line.y[i]! > line.y[m]! ? i : m), idx[0]!);
    const trough = idx.reduce((m, i) => (line.y[i]! < line.y[m]! ? i : m), idx[0]!);
    return {
      vintage: line.vintage!,
      scenario: line.scenario,
      peak: line.y[peak]!,
      peakQuarter: line.info[peak]!.quarter,
      trough: line.y[trough]!,
      troughQuarter: line.info[trough]!.quarter
    };
  });

  // History: the Fed's Historical data, only where it means something (as published, calendar axis).
  // It stops at the newest drawn year's start (its last actual quarter): later quarters are not part
  // of any selected year's story. Years that draw no line for this variable do not count.
  const historyApplies = state.view === 'published' && !horizonAxis;
  const showHistory = historyApplies && state.history !== 'off' && scenarioLines.length > 0;
  const drawnYears = [...new Set(scenarioLines.map((s) => s.vintage!))];
  const cuts = [
    ...new Set(
      drawnYears.flatMap((id) => {
        const jump = catalog.vintages.find((v) => v.id === id)!.jump_off;
        return jump ? [qNum(jump)] : [];
      })
    )
  ].sort((a, b) => a - b);
  if (showHistory && state.history === 'latest' && cuts.length > 0) {
    // Each quarter comes from the most recent publication that reports it; the publication is kept for the tooltip and CSV.
    const latest = new Map<number, { value: number; estimated: boolean; source: string }>();
    for (const vintage of catalog.vintages) {
      const a = data.actualsBy.get(`${variable.id}|${vintage.id}`);
      a?.values.forEach((v, i) =>
        latest.set(qNum(a.start) + i, { value: v, estimated: a.estimated.includes(i), source: vintage.id })
      );
    }
    const newest = cuts[cuts.length - 1]!;
    const quarters = [...latest.keys()].filter((n) => n <= newest).sort((a, b) => a - b);
    const infoOf = (n: number): PointInfo => ({
      quarter: qStr(n),
      horizon: 0,
      published: latest.get(n)!.value,
      level: null,
      dev: null,
      dev_level: null,
      estimated: latest.get(n)!.estimated,
      source: latest.get(n)!.source
    });
    // One series per stretch between consecutive jump-offs (neighbours share a boundary point), so the
    // chart can fade each stretch by how many of the highlighted years already knew it (focus.ts).
    const segments: PlotSeries[] = [];
    let previousEnd = -Infinity;
    let join: number | null = null;
    for (const end of cuts) {
      const own = quarters.filter((n) => n > previousEnd && n <= end);
      previousEnd = end;
      if (own.length === 0) continue;
      const stretch = join === null ? own : [join, ...own];
      join = own[own.length - 1]!;
      segments.push({
        id: `history|latest|${segments.length}`,
        kind: 'history',
        vintage: null,
        scenario: 'history',
        label: 'Historical data, latest Federal Reserve publication',
        x: stretch,
        y: stretch.map((n) => latest.get(n)!.value),
        firstProjected: stretch.length,
        origin: 'actual',
        knownTo: end,
        publishedName: null,
        info: stretch.map(infoOf)
      });
    }
    series.unshift(...segments);
    quarters.forEach((n) =>
      row(
        'history_latest',
        latest.get(n)!.source,
        'history',
        qStr(n),
        0,
        latest.get(n)!.value,
        latest.get(n)!.estimated
      )
    );
  }
  if (showHistory && state.history === 'realtime') {
    const own: PlotSeries[] = [];
    for (const vintage of vintages.filter((v) => drawnYears.includes(v.id))) {
      const a = data.actualsBy.get(`${variable.id}|${vintage.id}`);
      if (!a) continue;
      const quarters = a.values.map((_, i) => qAdd(a.start, i));
      own.push({
        id: `history|${vintage.id}`,
        kind: 'vintage_history',
        vintage: vintage.id,
        scenario: 'history',
        label: `${vintage.label} history, as published then`,
        x: quarters.map(qNum),
        y: a.values,
        firstProjected: quarters.length,
        origin: 'fed',
        knownTo: null,
        publishedName: null,
        info: quarters.map((q, i) => ({
          quarter: q,
          horizon: 0,
          published: a.values[i]!,
          level: null,
          dev: null,
          dev_level: null,
          estimated: a.estimated.includes(i),
          source: vintage.id
        }))
      });
      quarters.forEach((q, i) =>
        row('history_realtime', vintage.id, 'history', q, 0, a.values[i]!, a.estimated.includes(i))
      );
    }
    series.unshift(...own);
  }

  // Min-max band: at every x where at least two plotted scenario lines have a value, the lowest and the
  // highest of them, over every line drawn (any year, any scenario; history excluded). No interpolation.
  const bandX: number[] = [];
  const bandLo: number[] = [];
  const bandHi: number[] = [];
  for (const at of [...new Set(scenarioLines.flatMap((s) => s.x))].sort((a, b) => a - b)) {
    const values = scenarioLines.flatMap((s) => {
      const i = s.x.indexOf(at);
      return i >= 0 ? [s.y[i]!] : [];
    });
    if (values.length < 2) continue;
    bandX.push(at);
    bandLo.push(Math.min(...values));
    bandHi.push(Math.max(...values));
  }
  const bandReason =
    scenarioLines.length === 0
      ? null
      : scenarioLines.length < 2
        ? 'Only one line is drawn, so the minimum and the maximum coincide.'
        : bandX.length === 0
          ? 'The lines drawn do not overlap in time; use Quarters since start for a min-max band.'
          : null;
  if (state.band && bandReason) notes.push(bandReason);
  const bandMode = state.band && bandX.length > 0;
  const envelopes: Envelope[] = [];
  if (bandMode) {
    envelopes.push({ scenario: BAND_LABEL, x: bandX, lo: bandLo, hi: bandHi });
    bandX.forEach((at, i) => {
      const quarter = horizonAxis ? '' : qStr(at);
      const h = horizonAxis ? at : 0;
      row('envelope_min', '', BAND_LABEL, quarter, h, bandLo[i]!);
      row('envelope_max', '', BAND_LABEL, quarter, h, bandHi[i]!);
    });
  }

  // Calendar window: Recent = a configured number of quarters before the earliest selected scenario starts; Full = all the Fed reports.
  let window: PlotModel['window'] = null;
  if (!horizonAxis && series.length > 0) {
    const everyX = [...series.flatMap((s) => s.x), ...envelopes.flatMap((e) => e.x)];
    const first = Math.min(...everyX);
    const last = Math.max(...everyX);
    const scenarioFirst = Math.min(...scenarioLines.flatMap((s) => s.x));
    const from =
      state.range === 'full'
        ? first
        : Math.max(first, scenarioFirst - catalog.limits.calendar_context_quarters);
    window = { from, to: last, first, last };
  }

  const unit = unitFor(state, variable, catalog.labels);
  const drawn = scenarioLines.length > 0;
  const noneHere = vintages.every((v) => v.origin === 'fed' && !v.variable_ids.includes(variable.id));
  const empty = drawn
    ? null
    : noneHere
      ? `${variable.name} is not published in the selected years.`
      : state.view === 'deviation' && scenarios.every((s) => s.name === 'baseline')
        ? 'Deviation is measured against the baseline. Select another scenario to see it.'
        : 'None of the selected scenarios is published for the selected years.';
  const calculated =
    state.view === 'level' && variable.measure === 'growth'
      ? 'cumulated level index (annualized rates compounded from the quarter before the scenario starts)'
      : state.view === 'deviation'
        ? `scenario minus the same vintage's baseline${variable.measure === 'growth' && state.basis === 'level_gap' ? ', in cumulated levels' : ''}`
        : null;
  const years = yearsText(vintages.map((v) => v.label));
  const historyText = showHistory
    ? state.history === 'latest'
      ? "Historical data: for each quarter, the latest Federal Reserve publication that reports it, up to the newest selected year's start."
      : "Historical data: each publication's own history, as published then."
    : null;
  const axisText = horizonAxis ? 'quarters since the scenario starts' : 'calendar quarter';
  const transformLine = `Transform: ${VIEW_TRANSFORM[state.view]}${state.view === 'deviation' && variable.measure === 'growth' ? ` (gap measured as ${state.basis === 'level_gap' ? 'percent difference in cumulated level' : 'difference in growth rates, percentage points'})` : ''}`;
  const readout = bandMode
    ? bandReadout({ envelopes, series, axis: state.axis, view: state.view, unit })
    : null;
  return {
    variable,
    unit,
    series,
    envelopes,
    bands,
    rows,
    summary,
    notes,
    empty,
    axis: state.axis,
    view: state.view,
    basis: state.basis,
    band: bandMode,
    bandReadout: readout,
    bandReason,
    window,
    title: `${variable.name}: ${VIEW_TITLE[state.view]}`,
    subtitle: `${unit}; ${axisText}; ${vintages.length} publication${vintages.length === 1 ? '' : 's'}`,
    caption: `Source: Board of Governors of the Federal Reserve System, supervisory stress test scenarios (${years}).${calculated ? ` Calculated: ${calculated}.` : ''}${historyText ? ` ${historyText}` : ''}`,
    csvHeader: [
      `${variable.name}: ${VIEW_TITLE[state.view]}`,
      `Unit: ${unit}`,
      transformLine,
      `Axis: ${axisText}; scenarios: ${shownScenarios.map((s) => s.label).join(', ') || 'none'}; publications: ${vintages.map((v) => v.label).join(', ')}; min-max band: ${bandMode ? 'on (at each point the lowest and highest of all lines drawn; rows envelope_min and envelope_max)' : 'off'}${showHistory ? `; history: ${state.history === 'latest' ? 'latest publication per quarter (vintage_id = publication the quarter came from)' : 'as published in each publication'}, up to the newest selected year's start, all those quarters whichever window is zoomed` : ''}`,
      ...(readout ? [`${readout.min} ${readout.max}`] : []),
      `Source: Board of Governors of the Federal Reserve System, supervisory stress test scenarios. Values are as published unless the transform says calculated. Dashboard data built ${catalog.built_at} from database sha256 ${catalog.db_sha256.slice(0, 12)}`
    ]
  };
}
