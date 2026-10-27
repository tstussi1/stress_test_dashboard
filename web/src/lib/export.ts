// Downloads: CSV of exactly the plotted numbers and PNG figures with the title, subtitle and
// source caption drawn into the image. The CSV is built from the same PlotModel.rows that feed
// the chart and the data side panel.
import { qAdd } from './quarters';
import type { Data, PlotModel, PlotRow } from './types';

export const CSV_COLUMNS = [
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
] as const;

const quote = (cell: string | number | boolean): string => {
  const text = String(cell);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

export function csvRows(model: PlotModel): (string | number | boolean)[][] {
  const basis = model.view === 'deviation' && model.variable.measure === 'growth' ? model.basis : '';
  return model.rows.map((r: PlotRow) => [
    model.variable.id,
    model.variable.name,
    model.unit,
    model.view,
    basis,
    r.series_type,
    r.vintage,
    r.scenario,
    r.quarter,
    r.horizon,
    r.value,
    r.fed_estimate
  ]);
}

/**
 * CSV with a UTF-8 byte-order mark so Excel opens it correctly, `#` header lines stating what the
 * numbers are and which transform was applied, then the column header and the plotted rows.
 * Values are the stored numbers, unrounded. With several charts the shared lines are written once.
 */
export function toCsv(models: PlotModel[]): string {
  const [first] = models;
  const header = [
    models.length === 1
      ? first!.csvHeader[0]!
      : `${models.length} charts: ${models.map((m) => m.variable.name).join('; ')}`,
    ...first!.csvHeader.slice(1)
  ].map((line) => `# ${line}`);
  const lines = [
    ...header,
    CSV_COLUMNS.join(','),
    ...models.flatMap(csvRows).map((row) => row.map(quote).join(','))
  ];
  return '\ufeff' + lines.join('\r\n') + '\r\n';
}

const DATASET_COLUMNS = [
  'record_type',
  'variable_id',
  'variable',
  'vintage_id',
  'scenario',
  'quarter',
  'horizon',
  'published',
  'level_index_calculated',
  'gap_to_baseline_calculated',
  'level_gap_percent_calculated',
  'fed_estimate',
  'calculated'
] as const;

/**
 * Everything the dashboard holds, as published: every scenario path of every publication and each
 * publication's own history (real-time data). `published` is the Fed's number; the three calculated
 * columns are the exporter's, empty where they do not apply. One row per stored number.
 */
export function completeDatasetCsv(data: Data): string {
  const { catalog } = data;
  const name = new Map(catalog.variables.map((v) => [v.id, v.name]));
  const table: (string | number | boolean)[][] = [];
  const derived = new Map(catalog.vintages.map((v) => [v.id, new Set(v.derived_variable_ids)]));
  const num = (v: number | null | undefined): string | number => (v === null || v === undefined ? '' : v);
  for (const s of data.series) {
    if (s.scenario === 'realized') continue; // a derived view of the history rows below, not a separate publication
    s.published.forEach((value, i) => {
      const estimated = s.estimated?.includes(i) ?? false;
      table.push([
        'scenario',
        s.variable,
        name.get(s.variable)!,
        s.vintage,
        s.scenario,
        qAdd(s.start, i),
        i + 1,
        value,
        num(s.level?.[i]),
        num(s.dev?.[i]),
        num(s.dev_level?.[i]),
        estimated,
        derived.get(s.vintage)?.has(s.variable) ?? false
      ]);
    });
  }
  for (const a of data.actuals)
    a.values.forEach((value, i) =>
      table.push([
        'history',
        a.variable,
        name.get(a.variable)!,
        a.vintage,
        '',
        qAdd(a.start, i),
        '',
        value,
        '',
        '',
        '',
        a.estimated.includes(i),
        derived.get(a.vintage)?.has(a.variable) ?? false
      ])
    );
  const header = [
    'Stress Test Scenario Explorer: complete dataset',
    'Board of Governors of the Federal Reserve System, supervisory stress test scenarios; one row per stored number.',
    "record_type scenario = a projected quarter of a scenario (horizon = quarter since the scenario starts); history = a quarter of that publication's own Historical data (real-time data).",
    "published = the Federal Reserve's number, unrounded. The three *_calculated columns are calculated: level index (growth variables only; 100 = quarter before the scenario starts), gap to the same publication's baseline, and percent gap in level.",
    "calculated = true where the stored published value is itself calculated from a level the Federal Reserve printed (2011 real GDP, CPI and real disposable income growth: annualized percent change of consecutive levels); false where the value is the Fed's own number.",
    `Dashboard data built ${catalog.built_at} from database sha256 ${catalog.db_sha256}`
  ].map((line) => `# ${line}`);
  const lines = [...header, DATASET_COLUMNS.join(','), ...table.map((r) => r.map(quote).join(','))];
  return '\ufeff' + lines.join('\r\n') + '\r\n';
}

export const datasetFilename = (builtAt: string): string =>
  `stress-scenarios_complete-dataset_${builtAt.slice(0, 10)}.csv`;

export const downloadDataset = (data: Data): void =>
  download(
    datasetFilename(data.catalog.built_at),
    new Blob([completeDatasetCsv(data)], { type: 'text/csv;charset=utf-8' })
  );

export const csvFilename = (models: PlotModel[], builtAt: string): string => {
  const what = models.length === 1 ? models[0]!.variable.id : `${models.length}-variables`;
  return `stress-scenarios_${what}_${models[0]!.view}_${builtAt.slice(0, 10)}.csv`;
};

export function download(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const downloadCsv = (models: PlotModel[], builtAt: string): void =>
  download(csvFilename(models, builtAt), new Blob([toCsv(models)], { type: 'text/csv;charset=utf-8' }));

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  return line ? [...lines, line] : lines;
}

const loadImage = (src: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('could not read the chart image'));
    image.src = src;
  });

/** Stack chart images (already at 2x) under one title/subtitle/caption block each, on a white canvas. */
export async function composeFigures(
  items: { png: string; model: PlotModel }[],
  columns: number
): Promise<Blob> {
  await document.fonts.ready;
  const images = await Promise.all(items.map((i) => loadImage(i.png)));
  const scale = 2;
  const margin = 24 * scale;
  const cellWidth = Math.max(...images.map((i) => i.width));
  const probe = document.createElement('canvas').getContext('2d')!;
  probe.font = `${12.5 * scale}px "Source Sans 3 Variable", sans-serif`;
  const captions = items.map((i) => wrap(probe, i.model.caption, cellWidth));
  const headHeight = 62 * scale;
  const cells = items.map((_, k) => headHeight + images[k]!.height + (captions[k]!.length * 17 + 14) * scale);
  const rows = Math.ceil(items.length / columns);
  const rowHeights = Array.from({ length: rows }, (_, r) =>
    Math.max(...cells.slice(r * columns, r * columns + columns))
  );
  const canvas = document.createElement('canvas');
  canvas.width = margin * 2 + columns * cellWidth + (columns - 1) * margin;
  canvas.height = margin * 2 + rowHeights.reduce((a, b) => a + b, 0) + (rows - 1) * margin;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  items.forEach(({ model }, k) => {
    const x = margin + (k % columns) * (cellWidth + margin);
    const y = margin + rowHeights.slice(0, Math.floor(k / columns)).reduce((a, b) => a + b + margin, 0);
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#13294b';
    ctx.font = `600 ${21 * scale}px "Source Serif 4 Variable", Georgia, serif`;
    ctx.fillText(model.title, x, y);
    ctx.fillStyle = '#5b6573';
    ctx.font = `${13 * scale}px "Source Sans 3 Variable", sans-serif`;
    ctx.fillText(model.subtitle, x, y + 30 * scale);
    ctx.drawImage(images[k]!, x, y + headHeight);
    ctx.font = `${12.5 * scale}px "Source Sans 3 Variable", sans-serif`;
    captions[k]!.forEach((line, n) =>
      ctx.fillText(line, x, y + headHeight + images[k]!.height + (8 + n * 17) * scale)
    );
  });
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('could not create the PNG'))),
      'image/png'
    )
  );
}

export const pngFilename = (models: PlotModel[], builtAt: string): string => {
  const what = models.length === 1 ? models[0]!.variable.id : `${models.length}-variables`;
  return `stress-scenarios_${what}_${models[0]!.view}_${builtAt.slice(0, 10)}.png`;
};
