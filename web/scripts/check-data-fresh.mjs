// Freshness check run before every build: the dashboard data must come from the current database.
//
// Purpose: a stale snapshot must never be built into the site. Compares catalog.json's db_sha256
// with the sha256 of the database file and requires the three JSON files to be newer than it.
// Inputs: public/data/{catalog,paths,actuals}.json; the database at STRESS_TEST_DB_PATH
// (default ../stress_test_scenarios.duckdb). Where the database is deliberately absent (CI of
// the standalone repository, which ships only the JSON) set ALLOW_MISSING_DB=1; the files are
// then only checked for presence and schema version. Exit status 1 on any problem.
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, '..', 'public', 'data');
const dbPath = resolve(
  process.env.STRESS_TEST_DB_PATH ?? resolve(here, '..', '..', 'stress_test_scenarios.duckdb')
);
const files = ['catalog.json', 'paths.json', 'actuals.json'].map((f) => resolve(dataDir, f));

const fail = (message) => {
  console.error(`STALE or incomplete dashboard data: ${message}`);
  process.exit(1);
};

for (const f of files) if (!existsSync(f)) fail(`${f} is missing; run export_web_data.py`);
const catalog = JSON.parse(readFileSync(files[0], 'utf8'));
if (catalog.schema_version !== 1) fail(`unsupported schema_version ${catalog.schema_version}`);

if (!existsSync(dbPath)) {
  if (process.env.ALLOW_MISSING_DB !== '1')
    fail(
      `database ${dbPath} not found (set STRESS_TEST_DB_PATH, or ALLOW_MISSING_DB=1 to skip the hash comparison)`
    );
  console.log('data files present (database hash comparison skipped: ALLOW_MISSING_DB=1)');
  process.exit(0);
}
const hash = createHash('sha256').update(readFileSync(dbPath)).digest('hex');
if (hash !== catalog.db_sha256)
  fail('built from a different database file than the current one; run export_web_data.py');
const dbTime = statSync(dbPath).mtimeMs;
if (files.some((f) => statSync(f).mtimeMs < dbTime)) fail('older than the database; run export_web_data.py');
console.log(`fresh: data built from database ${hash.slice(0, 12)}…`);
