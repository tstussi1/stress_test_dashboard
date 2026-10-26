// Size budgets, run after every build.
//
// Purpose: keep the page light. Measures the gzip size (level 9) of the built JavaScript, CSS and
// the three data files and fails if one exceeds its budget.
// Inputs: dist/ (run `vite build` first); the budgets in package.json under "budgets" (KB, gzip).
// Outputs: one line per group on stdout; exit status 1 if any budget is exceeded or dist is missing.
// Assumptions: sizes are gzip of the files as served (fonts are loaded on demand per unicode range
// and are not part of the JS budget); 1 KB = 1000 bytes. The raw-size warning of Vite
// (chunkSizeWarningLimit) is aligned with the JS budget in vite.config.ts, not silenced separately.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = resolve(root, 'dist');
const budgets = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).budgets;
if (!budgets) throw new Error('package.json has no "budgets" entry');
if (!existsSync(dist)) throw new Error(`${dist} not found; run "vite build" first`);

const list = (dir) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? list(resolve(dir, e.name)) : [resolve(dir, e.name)]
  );
const files = list(dist);
const gzipKb = (selected) =>
  selected.reduce((sum, f) => sum + gzipSync(readFileSync(f), { level: 9 }).length, 0) / 1000;

const groups = {
  js_gzip_kb: files.filter((f) => extname(f) === '.js'),
  css_gzip_kb: files.filter((f) => extname(f) === '.css'),
  data_gzip_kb: files.filter((f) => extname(f) === '.json')
};

let failed = false;
for (const [key, selected] of Object.entries(groups)) {
  if (!selected.length) throw new Error(`no files found for budget ${key}`);
  if (typeof budgets[key] !== 'number') throw new Error(`package.json budgets.${key} is missing`);
  const size = gzipKb(selected);
  const ok = size <= budgets[key];
  failed ||= !ok;
  console.log(
    `${ok ? 'ok  ' : 'OVER'} ${key}: ${size.toFixed(1)} KB of ${budgets[key]} KB (${selected.length} files)`
  );
}
process.exit(failed ? 1 : 0);
