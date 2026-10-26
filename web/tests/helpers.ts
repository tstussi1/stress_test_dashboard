import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadData } from '../src/lib/data';
import { defaultState } from '../src/lib/state';
import type { Data, ExplorerState } from '../src/lib/types';

const dataDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'data');

export const realData = (): Promise<Data> =>
  loadData(async (name) => JSON.parse(readFileSync(resolve(dataDir, name), 'utf8')));

export async function stateWith(
  patch: Partial<ExplorerState>
): Promise<{ data: Data; state: ExplorerState }> {
  const data = await realData();
  return { data, state: { ...defaultState(data.catalog), ...patch } };
}
