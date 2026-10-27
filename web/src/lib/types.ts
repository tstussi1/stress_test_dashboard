// Types mirroring the JSON written by export_web_data.py (see SCHEMA.md "Export contract").
// Python computes every number; nothing in the page re-derives a transform.

export type ViewMode = 'published' | 'level' | 'deviation';
export type Basis = 'growth_gap' | 'level_gap';
export type Axis = 'horizon' | 'calendar';
export type HistoryMode = 'off' | 'latest' | 'realtime';
export type RangeMode = 'recent' | 'full';
export type Tab = 'explorer' | 'methodology';

export interface CatalogVariable {
  id: string;
  name: string;
  scope: 'domestic' | 'international';
  measure: 'growth' | 'level';
  unit: string;
  unit_label: string;
  theme: string;
  definition: string | null;
}

export interface EstimateStatement {
  quarter: string;
  wording: string;
  sentence: string;
}

export interface CatalogVintage {
  id: string;
  cycle_year: number;
  label: string;
  horizon_start: string;
  horizon_end: string;
  jump_off: string | null;
  origin: string;
  n_variables: number;
  variable_ids: string[];
  scenarios: string[];
  estimate_statement: EstimateStatement | null;
  estimate_statement_note: string | null;
  /** 'CCAR' for the 2011-2012 exercises (before the first DFAST), else null */
  exercise: string | null;
  /** false when the publication has no baseline scenario, so no deviation exists */
  has_baseline: boolean;
  /** the Federal Reserve's own scenario title where it differs from the standard name */
  published_names: Record<string, string>;
  /** variables whose stored growth rate is calculated from a published level, with the rounding bound (pp) */
  derived_variable_ids: string[];
  derived_rounding_bound_pp: Record<string, number>;
}

export interface CatalogScenario {
  name: string;
  label: string;
  family: string;
  order: number;
}

export interface Gap {
  id: string;
  title: string;
  reason: string;
}

export interface DataNote {
  id: string;
  variables: string[];
  vintages: string[];
  title: string;
  text: string;
}

export type VintageSpec = 'all' | { latest: number } | string[];

export interface Defaults {
  variable: string;
  scenarios: string[];
  vintages: VintageSpec;
  view: ViewMode;
  basis: Basis;
  axis: Axis;
  history: HistoryMode;
  range: RangeMode;
  band: boolean;
}

export interface QuickView {
  id: string;
  label: string;
  description: string;
  state: Partial<Defaults>;
}

export interface Catalog {
  schema_version: number;
  state_version: number;
  built_at: string;
  db_sha256: string;
  exercise_labels: Record<string, string>;
  variables: CatalogVariable[];
  vintages: CatalogVintage[];
  scenarios: CatalogScenario[];
  sources: { vintage: string; file: string; url: string; retrieved: string | null }[];
  reports: { vintage: string; url: string; retrieved: string | null }[];
  methodology: { rounding_bound_percent: number };
  gaps: Gap[];
  data_notes: DataNote[];
  defaults: Defaults;
  quick_views: QuickView[];
  limits: { calendar_context_quarters: number };
  labels: { growth_unit: string; level_index: string; level_gap: string };
  state_order: { variables: string[]; scenarios: string[]; vintages: string[] };
}

export interface Series {
  variable: string;
  vintage: string;
  scenario: string;
  origin: 'fed' | 'actual' | 'bvar';
  start: string;
  published: number[];
  level: number[] | null;
  dev: number[] | null;
  dev_level: number[] | null;
  estimated?: number[];
  band?: { lo: number[]; hi: number[]; label: string };
}

export interface ActualSeries {
  vintage: string;
  variable: string;
  start: string;
  values: number[];
  estimated: number[];
}

export interface ExplorerState {
  tab: Tab;
  variable: string;
  scenarios: string[];
  vintages: string[];
  view: ViewMode;
  basis: Basis;
  axis: Axis;
  history: HistoryMode;
  range: RangeMode;
  band: boolean;
  pins: string[];
}

export interface Data {
  catalog: Catalog;
  series: Series[];
  actuals: ActualSeries[];
  seriesBy: Map<string, Series>; // `${variable}|${vintage}|${scenario}`
  actualsBy: Map<string, ActualSeries>; // `${variable}|${vintage}`
}

// ---- the plotted model (what the chart, the data panel and the CSV all read) ----

export type SeriesType =
  | 'scenario'
  | 'anchor'
  | 'history_latest'
  | 'history_realtime'
  | 'envelope_min'
  | 'envelope_max'
  | 'band_lo'
  | 'band_hi';

/** One plotted number. For history_latest rows `vintage` is the publication the quarter was taken from. */
export interface PlotRow {
  series_type: SeriesType;
  vintage: string;
  scenario: string;
  quarter: string;
  horizon: number;
  value: number;
  fed_estimate: boolean;
}

export interface PointInfo {
  quarter: string;
  horizon: number;
  published: number | null;
  level: number | null;
  dev: number | null;
  dev_level: number | null;
  estimated: boolean;
  /** publication (vintage id) a history value was taken from; null for scenario points */
  source: string | null;
}

export interface PlotSeries {
  id: string;
  kind: 'scenario' | 'history' | 'vintage_history';
  vintage: string | null;
  scenario: string;
  label: string;
  x: number[];
  y: number[];
  info: PointInfo[];
  /** index of the first projected point; earlier points are history (solid), later ones projection */
  firstProjected: number;
  origin: string;
  /** last quarter number a latest-report history stretch covers (the jump-off that ends it); null otherwise */
  knownTo: number | null;
  /** the Federal Reserve's own scenario title where it differs from the standard name (scenario lines only) */
  publishedName: string | null;
}

export interface Envelope {
  scenario: string;
  x: number[];
  lo: number[];
  hi: number[];
}

export interface BandSeries {
  seriesId: string;
  x: number[];
  lo: number[];
  hi: number[];
  label: string;
}

/** Peak and trough of one plotted scenario line, read straight from the plotted numbers. */
export interface SummaryRow {
  vintage: string;
  scenario: string;
  peak: number;
  peakQuarter: string;
  trough: number;
  troughQuarter: string;
}

export interface PlotModel {
  variable: CatalogVariable;
  title: string;
  subtitle: string;
  caption: string;
  /** `#` header lines of the CSV: what the numbers are and how they were transformed */
  csvHeader: string[];
  unit: string;
  series: PlotSeries[];
  envelopes: Envelope[];
  bands: BandSeries[];
  rows: PlotRow[];
  summary: SummaryRow[];
  notes: string[];
  empty: string | null;
  axis: Axis;
  view: ViewMode;
  basis: Basis;
  /** the min-max band is drawn */
  band: boolean;
  /** the band's lowest and highest value and where each occurs (two sentences), or null when no band is drawn */
  bandReadout: { min: string; max: string } | null;
  /** why a band cannot be drawn for the current lines, or null */
  bandReason: string | null;
  /** visible calendar window (quarter numbers) and the full span of the data, for the calendar axis */
  window: { from: number; to: number; first: number; last: number } | null;
}
