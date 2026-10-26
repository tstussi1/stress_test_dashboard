// The only file that imports ECharts. Turns a PlotModel into an ECharts option and wraps the
// chart's lifecycle. Swapping the charting library means rewriting this file only.
//
// Two densities share one option builder: `focus` (the large chart, with end labels, an overview
// strip on the calendar axis and a full tooltip) and `panel` (a grid cell: no labels, no strip).
// Colour = publication year, pattern and weight = scenario family (see colors.ts).
import { LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption, SeriesOption } from 'echarts';
import { BAND_COLOR, HISTORY_COLOR, familyStyle, vintageColor } from './colors';
import { focusFor, type SeriesFocus } from './focus';
import { formatQuarter, formatSigned, formatValue } from './format';
import type { Catalog, PlotModel, PlotSeries } from './types';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer
]);

export type ChartMode = 'focus' | 'panel';

export interface ChartContext {
  catalog: Catalog;
  mode: ChartMode;
  pins: string[];
  reducedMotion: boolean;
}

const MAX_LABELLED_LINES = 12;
const INK = '#5b6573';

const quarterLabel = (n: number): string => `${Math.floor(n / 4)}Q${(n % 4) + 1}`;

/** Tick positions at January of every k-th year, with k chosen so a window of any length shows about `labels` ticks. */
function yearTicks(from: number, to: number, labels: number): number[] {
  const step = 4 * Math.max(1, Math.ceil((to - from) / 4 / labels));
  const ticks: number[] = [];
  for (let v = Math.ceil(from / step) * step; v <= to; v += step) ticks.push(v);
  return ticks;
}

function describe(model: PlotModel, ctx: ChartContext, s: PlotSeries, pointIndex: number): string {
  const p = s.info[pointIndex]!;
  const vintageLabel = (id: string | null) => ctx.catalog.vintages.find((v) => v.id === id)?.label ?? '';
  const where = model.axis === 'horizon' && s.kind === 'scenario' ? ` (quarter ${p.horizon})` : '';
  const lines = [
    `<div class="tt-title">${s.kind === 'scenario' ? s.label : s.kind === 'history' ? 'Historical data' : s.label}</div>`,
    `<div class="tt-sub">${formatQuarter(p.quarter)}${where}</div>`
  ];
  const measure = model.variable.measure;
  const shown = s.y[pointIndex]!;
  lines.push(
    `<div class="tt-main"><b>${model.view === 'deviation' ? formatSigned(shown) : formatValue(shown)}</b> <span>${model.unit}</span></div>`
  );
  const extras: string[] = [];
  if (s.kind !== 'scenario' && p.source)
    extras.push(
      s.kind === 'history'
        ? `From the ${vintageLabel(p.source)} report (the latest to report this quarter)`
        : `As published in the ${vintageLabel(p.source)} report`
    );
  if (
    s.kind === 'scenario' &&
    p.published !== null &&
    !(model.view === 'published' || (model.view === 'level' && measure === 'level'))
  )
    extras.push(`Published: ${formatValue(p.published)}`);
  if (s.kind === 'scenario' && measure === 'growth' && p.level !== null && model.view !== 'level')
    extras.push(`Level index: ${formatValue(p.level)}`);
  if (
    s.kind === 'scenario' &&
    p.dev !== null &&
    !(model.view === 'deviation' && (measure === 'level' || model.basis === 'growth_gap'))
  )
    extras.push(`Gap to baseline: ${formatSigned(p.dev)}`);
  if (
    s.kind === 'scenario' &&
    p.dev_level !== null &&
    !(model.view === 'deviation' && model.basis === 'level_gap')
  )
    extras.push(`Level gap: ${formatSigned(p.dev_level)}%`);
  if (extras.length) lines.push(`<div class="tt-extra">${extras.join('<br>')}</div>`);
  if (p.estimated)
    lines.push(`<div class="tt-flag">The Federal Reserve marks this value as an estimate.</div>`);
  return lines.join('');
}

/** Width, stacking and end-label visibility of one line, from its focus state; shared by the full option and by hover updates. */
function lookOf(model: PlotModel, ctx: ChartContext, s: PlotSeries, f: SeriesFocus) {
  const focus = ctx.mode === 'focus';
  const scenarioCount = model.series.filter((x) => x.kind === 'scenario').length;
  const isScenario = s.kind === 'scenario';
  const base = isScenario
    ? familyStyle(ctx.catalog.scenarios.find((x) => x.name === s.scenario)!.family).width
    : s.kind === 'history'
      ? 2
      : 1.3;
  return {
    opacity: f.opacity,
    width: (f.bold ? base + 1 : base) * (focus ? 1 : 0.75),
    z: f.bold ? 6 : isScenario ? 3 : 2,
    label: isScenario && focus && !f.faded && (scenarioCount <= MAX_LABELLED_LINES || f.bold)
  };
}

export function makeOption(
  model: PlotModel,
  ctx: ChartContext,
  hovered: string | null = null
): EChartsOption {
  const focus = ctx.mode === 'focus';
  const horizon = model.axis === 'horizon';
  const catalog = ctx.catalog;
  const count = catalog.vintages.length;
  const real = catalog.scenarios.filter((s) => s.name !== 'realized'); // 'realized' is not a scenario
  const familyOf = new Map(real.map((s) => [s.name, s.family]));
  const tagOf = new Map(real.map((s) => [s.name, familyStyle(s.family).tag ?? s.label.toLowerCase()]));
  const scenarioLines = model.series.filter((s) => s.kind === 'scenario');
  const manyScenarios = new Set(scenarioLines.map((s) => s.scenario)).size > 1;
  const fontSize = focus ? 12 : 10.5;
  const options: SeriesOption[] = [];
  const focusOf = focusFor(model, catalog, ctx.pins, hovered);
  const colorOf = (vintage: string): string =>
    vintageColor(
      catalog.vintages.findIndex((v) => v.id === vintage),
      count
    );

  // The overview strip draws the shape of its first series; history is split into stretches, so a hidden
  // whole-history series comes first.
  const stretches = model.series.filter((s) => s.kind === 'history');
  if (focus && !horizon && stretches.length > 0) {
    const points = new Map(stretches.flatMap((s) => s.x.map((x, i) => [x, s.y[i]!] as const)));
    options.push({
      type: 'line',
      name: 'history|overview',
      data: [...points.entries()].sort((a, b) => a[0] - b[0]),
      symbol: 'none',
      silent: true,
      lineStyle: { opacity: 0 },
      tooltip: { show: false },
      z: 0
    });
  }

  // Min-max band: lowest to highest of every line drawn, one neutral grey behind the year lines.
  model.envelopes.forEach((e) => {
    const stack = 'band-all';
    const edge = { color: BAND_COLOR, width: 1, opacity: 0.55 };
    options.push({
      type: 'line',
      name: `${stack}-lo`,
      stack,
      stackStrategy: 'all',
      data: e.x.map((x, i) => [x, e.lo[i]!]),
      symbol: 'none',
      silent: true,
      lineStyle: edge,
      z: 1,
      tooltip: { show: false }
    });
    options.push({
      type: 'line',
      name: `${stack}-hi`,
      stack,
      stackStrategy: 'all',
      data: e.x.map((x, i) => [x, e.hi[i]! - e.lo[i]!]),
      symbol: 'none',
      silent: true,
      lineStyle: edge,
      areaStyle: { color: BAND_COLOR, opacity: 0.2 },
      z: 1,
      tooltip: { show: false }
    });
  });
  model.bands.forEach((b) => {
    const owner = model.series.find((s) => s.id === b.seriesId)!;
    const color = colorOf(owner.vintage!);
    const stack = `band-${b.seriesId}`;
    options.push({
      type: 'line',
      name: `${stack}-lo`,
      stack,
      stackStrategy: 'all',
      data: b.x.map((x, i) => [x, b.lo[i]!]),
      symbol: 'none',
      silent: true,
      lineStyle: { opacity: 0 },
      z: 1,
      tooltip: { show: false }
    });
    options.push({
      type: 'line',
      name: `${stack}-hi`,
      stack,
      stackStrategy: 'all',
      data: b.x.map((x, i) => [x, b.hi[i]! - b.lo[i]!]),
      symbol: 'none',
      silent: true,
      lineStyle: { opacity: 0 },
      areaStyle: { color, opacity: 0.18 },
      z: 1,
      tooltip: { show: false }
    });
  });

  // Lines: scenario lines, history stretches and per-year history, styled by focus.ts.
  model.series.forEach((s, seriesIndex) => {
    const isScenario = s.kind === 'scenario';
    const style = isScenario ? familyStyle(familyOf.get(s.scenario)!) : null;
    const look = lookOf(model, ctx, s, focusOf.get(s.id)!);
    const color = s.kind === 'history' ? HISTORY_COLOR : colorOf(s.vintage!);
    const label = s.vintage ? catalog.vintages.find((v) => v.id === s.vintage)!.label : '';
    const endText = isScenario ? (manyScenarios ? `${label} ${tagOf.get(s.scenario)}` : label) : '';
    const data = s.x.map((x, i) => {
      const info = s.info[i]!;
      const estimated = info.estimated;
      const marked = isScenario && i === s.firstProjected;
      // Every point is a (mostly invisible) hoverable circle so the tooltip works anywhere on a line.
      // Visible markers take their opacity from the series, so they fade with their line.
      return {
        value: [x, s.y[i]!],
        seriesIndex,
        pointIndex: i,
        symbol: 'circle',
        symbolSize: estimated ? 8 : marked ? 5 : focus ? 12 : 9,
        itemStyle: estimated
          ? { color: '#ffffff', borderColor: color, borderWidth: 2 }
          : marked
            ? { color }
            : { color, opacity: 0 }
      };
    });
    options.push({
      type: 'line',
      id: s.id,
      name: s.id,
      data,
      showSymbol: true,
      symbol: 'none',
      lineStyle: { color, width: look.width, type: style ? style.dash : 'solid', opacity: look.opacity },
      itemStyle: { color, opacity: look.opacity },
      emphasis: { disabled: true },
      endLabel: {
        show: look.label,
        formatter: () => endText,
        color,
        fontSize,
        fontWeight: 600,
        distance: 6
      },
      labelLayout: { moveOverlap: 'shiftY' },
      z: look.z,
      clip: true
    });
  });

  const xs = [...model.series.flatMap((s) => s.x), ...model.envelopes.flatMap((e) => e.x)];
  const win = model.window;
  // The large chart keeps the whole span on its axis and moves a window over it (overview strip);
  // a panel has no strip, so its axis is the window itself.
  const xMin = horizon ? Math.min(0, ...xs) : win ? (focus ? win.first : win.from) : Math.min(...xs);
  const xMax = horizon ? Math.max(1, ...xs) : win ? win.last : Math.max(...xs);

  // Panels have no zoom strip, so give them a y-range that fits only the visible window.
  let yRange: { min?: number; max?: number; interval?: number } = {};
  if (!focus && win) {
    const visible = [
      ...model.series.flatMap((s) => s.y.filter((_, i) => s.x[i]! >= win.from && s.x[i]! <= win.to)),
      ...model.envelopes.flatMap((e) => [...e.lo, ...e.hi])
    ];
    if (visible.length) {
      // Round the extent to tidy tick values (1, 2, 5 x 10^k) so the few axis labels read cleanly.
      const lo = Math.min(...visible);
      const hi = Math.max(...visible);
      const raw = (hi - lo || Math.abs(hi) || 1) / 3;
      const magnitude = 10 ** Math.floor(Math.log10(raw));
      const step = [1, 2, 5, 10].map((m) => m * magnitude).find((v) => v >= raw)!;
      yRange = { min: Math.floor(lo / step) * step, max: Math.ceil(hi / step) * step, interval: step };
    }
  }

  const guides = [
    ...(horizon ? [{ xAxis: 0.5, name: focus ? 'Scenario starts' : '' }] : []),
    ...(model.view === 'deviation'
      ? [
          {
            yAxis: 0,
            name: '',
            lineStyle: { color: '#8a94a3', type: 'solid' as const, width: 1 },
            label: { show: false }
          }
        ]
      : [])
  ];
  options.push({
    type: 'line',
    name: 'guides',
    data: [],
    silent: true,
    tooltip: { show: false },
    markLine: {
      silent: true,
      symbol: 'none',
      animation: false,
      lineStyle: { color: '#8a94a3', type: 'dashed', width: 1 },
      label: { show: focus, color: INK, fontSize: 11, position: 'insideEndTop', formatter: '{b}' },
      data: guides
    }
  });

  const zoomFrom = win ? win.from : xMin;
  const zoomTo = win ? win.to : xMax;
  const ticks = horizon ? null : yearTicks(zoomFrom, zoomTo, focus ? 9 : 4);
  return {
    animation: !ctx.reducedMotion,
    animationDuration: 250,
    textStyle: { fontFamily: 'Source Sans 3 Variable, system-ui, sans-serif' },
    grid: focus
      ? {
          left: 58,
          right: 96,
          top: 16,
          bottom: horizon ? 46 : 78,
          containLabel: false
        }
      : { left: 40, right: 10, top: 8, bottom: 22, containLabel: false },
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: '#ffffff',
      borderColor: '#b9c1cc',
      borderWidth: 1,
      padding: 10,
      textStyle: { color: '#1a1f2b', fontSize: 13 },
      extraCssText: 'box-shadow:none;border-radius:4px;',
      formatter: (params) => {
        const raw = (params as unknown as { data?: { seriesIndex: number; pointIndex: number } }).data;
        if (!raw) return '';
        const s = model.series[raw.seriesIndex];
        return s ? `<div class="tt">${describe(model, ctx, s, raw.pointIndex)}</div>` : '';
      }
    },
    xAxis: {
      type: 'value',
      min: xMin,
      max: xMax,
      ...(horizon ? { interval: focus ? 1 : 3 } : {}),
      name: horizon && focus ? 'Quarters since the scenario starts (0 = last historical quarter)' : '',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: INK, fontSize: 12 },
      axisLine: { lineStyle: { color: '#b9c1cc' } },
      axisTick: { lineStyle: { color: '#b9c1cc' }, ...(ticks ? { customValues: ticks } : {}) },
      axisLabel: {
        color: INK,
        fontSize,
        ...(ticks ? { customValues: ticks } : {}),
        formatter: (v: number) => (horizon ? String(v) : String(Math.floor(v / 4)))
      },
      splitLine: { show: false },
      axisPointer: { show: false }
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitNumber: focus ? 5 : 3,
      ...yRange,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: INK, fontSize, formatter: (v: number) => formatValue(v, 1) },
      splitLine: { lineStyle: { color: '#e8ebf0' } }
    },
    dataZoom:
      focus && !horizon
        ? [
            {
              type: 'slider',
              xAxisIndex: 0,
              startValue: zoomFrom,
              endValue: zoomTo,
              height: 26,
              bottom: 8,
              filterMode: 'filter',
              brushSelect: false,
              labelFormatter: (v: number | string) => quarterLabel(Number(v)),
              borderColor: '#d9dee5',
              fillerColor: 'rgba(19,41,75,0.10)',
              dataBackground: {
                lineStyle: { color: '#9aa3b2', width: 1 },
                areaStyle: { color: '#e3e7ed', opacity: 0.8 }
              },
              selectedDataBackground: {
                lineStyle: { color: '#13294b', width: 1 },
                areaStyle: { color: '#c9d3e4', opacity: 0.8 }
              },
              handleSize: '90%',
              textStyle: { color: INK, fontSize: 11 }
            }
          ]
        : [],
    series: options
  };
}

export interface ChartHandle {
  update(model: PlotModel, ctx: ChartContext): void;
  resize(): void;
  dispose(): void;
  png(): string;
  /** The hovered year joins the pinned years as the bright ones; every other line recedes (focus.ts). */
  setFocus(hovered: string | null): void;
  onSeriesClick(handler: (seriesName: string) => void): void;
  onBackgroundClick(handler: () => void): void;
  onHover(handler: (vintage: string | null) => void): void;
}

const vintageOfSeries = (name: string): string | null => {
  const [kind, id] = name.split('|');
  return kind === 'scenario' || (kind === 'history' && id !== 'latest' && id !== 'overview')
    ? (id ?? null)
    : null;
};

export function createChart(element: HTMLElement): ChartHandle {
  const chart = echarts.init(element, undefined, { renderer: 'canvas' });
  let current: { model: PlotModel; ctx: ChartContext } | null = null;
  let hovered: string | null = null;
  let frame = 0;
  let span: { first: number; last: number } | null = null;
  // The year ticks follow the zoom window, so re-space them when the window moves.
  chart.on('datazoom', (e) => {
    if (!span || current?.ctx.mode !== 'focus') return;
    const { start, end } = ((e as { batch?: { start: number; end: number }[] }).batch?.[0] ?? e) as {
      start: number;
      end: number;
    };
    if (!Number.isFinite(start) || !Number.isFinite(end))
      throw new Error(`datazoom event without a range: ${JSON.stringify(e)}`);
    const width = span.last - span.first;
    const ticks = yearTicks(span.first + (width * start) / 100, span.first + (width * end) / 100, 9);
    chart.setOption({ xAxis: { axisTick: { customValues: ticks }, axisLabel: { customValues: ticks } } });
  });
  // End labels of lines that finish at similar heights would overprint; push the shown ones apart by whole pixels.
  function dodgeEndLabels(shown: PlotSeries[]) {
    const gap = 13;
    const ends = shown
      .map((s) => {
        const last = s.x.length - 1;
        const [, py] = chart.convertToPixel({ seriesId: s.id }, [s.x[last]!, s.y[last]!]) as number[];
        return { id: s.id, py: py! };
      })
      .filter((e) => Number.isFinite(e.py))
      .sort((a, b) => a.py - b.py);
    const placed: number[] = [];
    ends.forEach((e, i) => placed.push(Math.max(e.py, i ? placed[i - 1]! + gap : e.py)));
    chart.setOption({
      series: ends.map((e, i) => ({ id: e.id, endLabel: { offset: [0, placed[i]! - e.py] } }))
    });
  }
  /** Re-style the lines for the current pins and hover without rebuilding the chart. */
  function applyFocus() {
    frame = 0;
    if (!current) return;
    const { model, ctx } = current;
    const focusOf = focusFor(model, ctx.catalog, ctx.pins, hovered);
    const looks = model.series.map((s) => ({ s, look: lookOf(model, ctx, s, focusOf.get(s.id)!) }));
    chart.setOption({
      series: looks.map(({ s, look }) => ({
        id: s.id,
        lineStyle: { opacity: look.opacity, width: look.width },
        itemStyle: { opacity: look.opacity },
        endLabel: { show: look.label },
        z: look.z
      }))
    });
    if (ctx.mode === 'focus') dodgeEndLabels(looks.filter((l) => l.look.label).map((l) => l.s));
  }
  return {
    update(model, ctx) {
      current = { model, ctx };
      span = model.axis === 'calendar' && model.window ? model.window : null;
      if (model.series.length === 0 && model.envelopes.length === 0) chart.clear();
      else {
        chart.setOption(makeOption(model, ctx, hovered), { notMerge: true });
        if (ctx.mode === 'focus') {
          const focusOf = focusFor(model, ctx.catalog, ctx.pins, hovered);
          dodgeEndLabels(model.series.filter((s) => lookOf(model, ctx, s, focusOf.get(s.id)!).label));
        }
      }
    },
    resize: () => chart.resize(),
    dispose: () => {
      cancelAnimationFrame(frame);
      chart.dispose();
    },
    png: () =>
      chart.getDataURL({
        type: 'png',
        pixelRatio: 2,
        backgroundColor: '#ffffff',
        excludeComponents: ['dataZoom']
      }),
    setFocus(next) {
      if (next === hovered) return;
      hovered = next;
      if (!frame) frame = requestAnimationFrame(applyFocus);
    },
    onSeriesClick: (handler) =>
      chart.on('click', (p) => typeof p.seriesName === 'string' && handler(p.seriesName)),
    onBackgroundClick: (handler) => chart.getZr().on('click', (e) => !e.target && handler()),
    onHover(handler) {
      chart.on('mouseover', (p) => {
        if (typeof p.seriesName === 'string') handler(vintageOfSeries(p.seriesName));
      });
      chart.on('mouseout', () => handler(null));
      chart.on('globalout', () => handler(null));
    }
  };
}
