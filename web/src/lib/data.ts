// Loads the three JSON files the exporter writes and indexes them. Any problem stops the page
// with an explicit message (see App.svelte); there are no partial or silent fallbacks.
import { FAMILY_STYLE } from './colors';
import { specProblem } from './state';
import type { ActualSeries, Catalog, Data, Series } from './types';

export class DataError extends Error {}

export type JsonReader = (name: string) => Promise<unknown>;

export function browserReader(baseUrl: string): JsonReader {
  return async (name) => {
    const url = `${baseUrl}data/${name}`;
    const response = await fetch(url);
    if (!response.ok) throw new DataError(`Could not load ${url} (HTTP ${response.status}).`);
    return response.json();
  };
}

export async function loadData(read: JsonReader): Promise<Data> {
  const [catalog, paths, actuals] = (await Promise.all([
    read('catalog.json'),
    read('paths.json'),
    read('actuals.json')
  ])) as [
    Catalog,
    { schema_version: number; series: Series[] },
    { schema_version: number; series: ActualSeries[] }
  ];
  for (const [name, version] of [
    ['catalog.json', catalog.schema_version],
    ['paths.json', paths.schema_version],
    ['actuals.json', actuals.schema_version]
  ] as const) {
    if (version !== 1)
      throw new DataError(`${name} has schema version ${version}; this page reads version 1.`);
  }
  const variables = new Set(catalog.variables.map((v) => v.id));
  const vintages = new Set(catalog.vintages.map((v) => v.id));
  const scenarios = new Set(catalog.scenarios.map((s) => s.name));
  for (const s of catalog.scenarios)
    if (s.name !== 'realized' && !(s.family in FAMILY_STYLE))
      throw new DataError(
        `Scenario '${s.name}' has family '${s.family}', which has no line style in colors.ts.`
      );
  const specs = [
    ['The default view', catalog.defaults] as const,
    ...catalog.quick_views.map((q) => [`Quick view '${q.id}'`, q.state] as const)
  ];
  for (const [name, spec] of specs) {
    const problem = specProblem(spec, catalog);
    if (problem) throw new DataError(`${name} is invalid: ${problem}.`);
  }

  const seriesBy = new Map<string, Series>();
  for (const s of paths.series) {
    if (!variables.has(s.variable) || !vintages.has(s.vintage) || !scenarios.has(s.scenario)) {
      throw new DataError(
        `paths.json holds a series (${s.variable}, ${s.vintage}, ${s.scenario}) that the catalog does not list.`
      );
    }
    seriesBy.set(`${s.variable}|${s.vintage}|${s.scenario}`, s);
  }
  const actualsBy = new Map<string, ActualSeries>();
  for (const a of actuals.series) actualsBy.set(`${a.variable}|${a.vintage}`, a);
  return { catalog, series: paths.series, actuals: actuals.series, seriesBy, actualsBy };
}
