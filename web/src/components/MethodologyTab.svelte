<script lang="ts">
  import { explorer } from '../lib/store.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const label = (id: string) => catalog.vintages.find((v) => v.id === id)?.label ?? id;
  const scenarioLabel = (name: string) => catalog.scenarios.find((s) => s.name === name)?.label ?? name;
  const variableName = (id: string) => catalog.variables.find((v) => v.id === id)?.name ?? id;
  const sourcesOf = (vintage: string) => catalog.sources.filter((s) => s.vintage === vintage);
  const reportOf = (vintage: string) => catalog.reports.find((r) => r.vintage === vintage);
  const nVariables = $derived(catalog.variables.length);
</script>

<article class="method">
  <h2>Methodology</h2>
  <p class="lead">
    This page shows the macroeconomic paths in the Federal Reserve’s supervisory stress-test scenarios, one
    set per annual publication (a “vintage”). Every number labelled “as published” is the number in the
    Federal Reserve’s own tables. Everything else is calculated from those numbers as described below, and
    says so where it appears.
  </p>

  <section>
    <h3>Vintages and scenarios</h3>
    <p>
      Each vintage is one Federal Reserve publication of scenario paths for 13 quarters, together with the
      historical data the Fed published alongside them. {nVariables} variables are published in total (26 in 2013;
      28 from 2014 on). The June 2020 publication and the September 2020 resubmission are separate vintages with
      separate scenarios and separate histories, and are never combined. The 2024 exploratory exercises A and B
      share one published international file; the 2025 exploratory conditions are published as equal to the severely
      adverse scenario, which was checked numerically.
    </p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr
            ><th>Vintage</th><th>Scenario window</th><th>Scenarios</th><th class="num">Variables</th><th
              >Estimated values marked by the Fed</th
            ><th>Sources</th></tr
          >
        </thead>
        <tbody>
          {#each catalog.vintages as v (v.id)}
            <tr>
              <th scope="row">{v.label}</th>
              <td>{v.horizon_start} to {v.horizon_end}</td>
              <td>{v.scenarios.map(scenarioLabel).join(', ')}</td>
              <td class="num">{v.n_variables}</td>
              <td>
                {#if v.estimate_statement}
                  {v.estimate_statement.quarter} values marked with an asterisk are “{v.estimate_statement
                    .wording}”
                {:else}
                  {v.estimate_statement_note ?? '—'}
                {/if}
              </td>
              <td class="links">
                {#if reportOf(v.id)}<a href={reportOf(v.id)!.url} rel="noopener">report</a>{/if}
                {#each sourcesOf(v.id) as s (s.file)}<a href={s.url} rel="noopener">{s.file}</a>{/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <h3>The three views</h3>
    <dl>
      <dt>As published</dt>
      <dd>
        The values exactly as the Federal Reserve printed them, in their own units. Growth variables (GDP,
        disposable income, CPI inflation and the international GDP and inflation series) are quarterly percent
        changes expressed at an annualized rate; the other variables are levels or rates. The Fed’s own
        wording for each variable is listed below.
      </dd>
      <dt>Level path (calculated)</dt>
      <dd>
        For growth variables only: the annualized rates are compounded into an index that equals 100 in the
        quarter before the scenario starts (the vintage’s last historical quarter). An annualized rate g
        compounds one quarter by the fourth root of 1 + g/100:
        <math
          display="block"
          aria-label="L t equals 100 times the product over s up to t of (1 plus g s over 100) to the power one quarter"
        >
          <mrow>
            <msub><mi>L</mi><mi>t</mi></msub><mo>=</mo><mn>100</mn><mo>×</mo>
            <munder><mo>∏</mo><mrow><mi>s</mi><mo>≤</mo><mi>t</mi></mrow></munder>
            <msup
              ><mrow
                ><mo>(</mo><mn>1</mn><mo>+</mo><mfrac><msub><mi>g</mi><mi>s</mi></msub><mn>100</mn></mfrac><mo
                  >)</mo
                ></mrow
              ><mfrac><mn>1</mn><mn>4</mn></mfrac></msup
            >
          </mrow>
        </math>
        It is a relative index, not a dollar level: the Federal Reserve publishes no level for these series. It
        shows, for example, how far real GDP falls in total, which a quarterly growth rate hides. Because each vintage’s
        index starts at 100 in its own jump-off quarter, level paths of different vintages cannot be placed on one
        calendar; this view is therefore available on the quarters-since-start axis only, and it is not chained
        to the historical data. Variables that are already levels are shown as published in this view.
      </dd>
      <dt>Deviation from baseline (calculated)</dt>
      <dd>
        The scenario minus the same vintage’s baseline, quarter by quarter (the baseline of one vintage is
        never compared with another vintage’s scenario).
        <math display="block" aria-label="d t equals x t scenario minus x t baseline">
          <mrow
            ><msub><mi>d</mi><mi>t</mi></msub><mo>=</mo><msubsup
              ><mi>x</mi><mi>t</mi><mtext>scenario</mtext></msubsup
            ><mo>−</mo><msubsup><mi>x</mi><mi>t</mi><mtext>baseline</mtext></msubsup></mrow
          >
        </math>
        In native units this is percentage points for rates and growth rates, and index points for index levels.
        For growth variables you can instead choose the percentage difference of the cumulated levels, which is
        the total output (or income, or price level) lost against the baseline:
        <math display="block" aria-label="gap equals 100 times (L scenario over L baseline minus 1)">
          <mrow
            ><mn>100</mn><mo>×</mo><mrow
              ><mo>(</mo><mfrac
                ><msubsup><mi>L</mi><mi>t</mi><mtext>scenario</mtext></msubsup><msubsup
                  ><mi>L</mi><mi>t</mi><mtext>baseline</mtext></msubsup
                ></mfrac
              ><mo>−</mo><mn>1</mn><mo>)</mo></mrow
            ></mrow
          >
        </math>
      </dd>
    </dl>
    <p>
      <strong>Precision.</strong> The Fed rounds growth rates to (usually) one decimal. If every published
      rate were off by the largest possible rounding error, a 13-quarter cumulated level could be off by at
      most about {catalog.methodology.rounding_bound_percent}% of its value. Calculated values are computed
      from the published numbers without any other adjustment, and are never rounded in downloads; only the
      display is rounded.
    </p>
    <p>
      <strong>Min-max band.</strong> With the band switched on, a grey band is drawn behind the lines: at each point
      of the time axis (each quarter since the scenario started, or each calendar quarter) it runs from the lowest
      to the highest value among all the scenario lines drawn there, whatever their year or scenario, and only where
      at least two lines have a value. One year with a baseline and a severely adverse scenario therefore gives
      the band between the two; six years of one scenario give the minimum and maximum across the years. Nothing
      is interpolated or smoothed, history is not part of the band, and every line stays visible.
    </p>
  </section>

  <section>
    <h3>Historical data and estimated values</h3>
    <p>
      The Federal Reserve publishes, with each vintage, a table of “historical data” up to the quarter before
      the scenario starts (the “jump-off quarter”). Most vintages start that table in 2000 or 2001; the 2013
      report’s separate historical workbook reaches back to 1976 for most variables (1990 for the VIX, 1996 to
      1999 for some international series). The page uses only these tables, never another data source.
    </p>
    <p>
      History is drawn in the As published view on the calendar axis, because a deviation or a level path
      exists only inside each vintage’s 13-quarter scenario window. You can choose between two sources.
      <strong>Latest report</strong> draws one line: for each quarter, the value in the historical-data table
      of the most recent vintage that reports that quarter, exactly as the Fed printed it; the tooltip and the
      downloaded file name the report each quarter came from, so the part before 2000 is labelled as coming
      from the 2013 workbook. <strong>As published then</strong> draws, for each selected year, that vintage’s own
      table as it was printed (real-time data); the two differ only where the Fed revised history. A scenario line
      starts at its own vintage’s last historical value, which can therefore sit slightly off the latest-report
      line where that quarter was later revised. “Recent” shows a few years of history before the earliest selected
      scenario; “Full history” shows everything the Fed published for the variable.
    </p>
    <p>
      History stops at the start of the newest selected year, that is at the last quarter that year’s report
      knew, so later quarters never appear as if they belonged to an older year’s story. Where several years
      are selected, history is drawn in stretches between their start quarters and shaded by how many of the
      highlighted years already knew it: history known to every highlighted year is dark, history only newer
      years knew is lighter. Pinning or hovering a year makes that year’s scenario lines and the history it
      knew bright and everything else recedes. With “As published then”, each year’s own history line follows
      its own year instead.
    </p>
    <p>
      In each report the Federal Reserve marks some values of the last historical quarter with an asterisk and
      states that they are “projected” (reports 2014–2020) or “estimates” (2021 onward). Those values are
      drawn with a hollow marker and flagged in the tooltip and the data table. For 2013 the Federal Reserve’s
      files make no such statement, so nothing is flagged for that vintage. The 2026 report adds that the 2025
      Q4 unemployment rate and CPI inflation reflect an average of the November and December 2025 readings
      because the October 2025 data were not published.
    </p>
  </section>

  <section>
    <h3>Variables as the Federal Reserve defines them</h3>
    <div class="table-wrap">
      <table>
        <thead
          ><tr><th>Variable</th><th>Type</th><th>Unit</th><th>Definition in the most recent report</th></tr
          ></thead
        >
        <tbody>
          {#each catalog.variables as v (v.id)}
            <tr>
              <th scope="row">{v.name}</th>
              <td>{v.measure === 'growth' ? 'Annualized percent change' : 'Level or rate'}</td>
              <td>{v.unit_label}</td>
              <td class="def">{v.definition ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <h3>What is not available</h3>
    <ul>
      {#each catalog.gaps as gap (gap.id)}
        <li><strong>{gap.title}.</strong> {gap.reason}</li>
      {/each}
    </ul>
  </section>

  <section>
    <h3>Notes on the Federal Reserve’s numbers</h3>
    <p>
      These are kept exactly as published; they are listed so that a surprising value is not mistaken for an
      error in this page.
    </p>
    <ul>
      {#each catalog.data_notes as note (note.id)}
        <li>
          <strong>{note.title}.</strong>
          {note.text}
          <span class="muted"
            >({note.variables.map(variableName).join(', ')}; {note.vintages.map(label).join(', ')}.)</span
          >
        </li>
      {/each}
    </ul>
    <p>
      The Federal Reserve corrected some published tables after release (for example the 5-year Treasury yield
      in the 2014 report and the BBB corporate yield in the 2017 report). The corrected values are used, and
      every number shown was compared with both the Fed’s data files and the tables printed in its report.
    </p>
  </section>

  <section>
    <h3>Sharing and citing</h3>
    <p>
      “Copy link” creates a short link that restores your selections (variable, scenarios, years, view, axis,
      display, history and pinned years) when it is opened. The “Data” button beside the large chart lists,
      and lets you download, exactly the numbers plotted, under header lines that state the transform;
      “Summary” lists each line’s peak and trough. The complete dataset (every scenario and each vintage’s own
      history, as published, with the calculated columns labelled) is available from the Data panel and below
      the charts. Cite the underlying source as: Board of Governors of the Federal Reserve System, supervisory
      stress test scenarios, for the vintages shown (see Sources).
    </p>
    <p class="muted">
      Data built {catalog.built_at.replace('T', ' ').replace('+00:00', ' UTC')} from database {catalog.db_sha256.slice(
        0,
        12
      )}; schema {catalog.schema_version}, share-link version {catalog.state_version}.
    </p>
  </section>
</article>

<style>
  .method {
    max-width: 1100px;
  }
  h2 {
    font-size: 28px;
    margin-bottom: 10px;
  }
  h3 {
    font-size: 21px;
    margin: 0 0 10px;
  }
  .lead {
    font-size: 17px;
    max-width: 75ch;
    margin: 0 0 8px;
  }
  section {
    padding: 26px 0 8px;
    border-top: 1px solid var(--rule);
    margin-top: 22px;
  }
  p,
  dd,
  li {
    max-width: 80ch;
  }
  dt {
    font-weight: 600;
    color: var(--navy);
    margin-top: 14px;
  }
  dd {
    margin: 4px 0 0;
  }
  math {
    display: block;
    margin: 10px 0 6px 6px;
    font-size: 19px;
  }
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    margin-top: 12px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
  }
  th,
  td {
    text-align: left;
    padding: 6px 10px;
    border-bottom: 1px solid var(--rule);
    vertical-align: top;
  }
  thead th {
    background: var(--panel);
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  tbody th {
    font-weight: 600;
    white-space: nowrap;
  }
  .num {
    text-align: right;
  }
  .links a {
    display: block;
    white-space: nowrap;
  }
  .def {
    max-width: 62ch;
  }
  .muted {
    color: var(--muted);
  }
  li {
    margin-bottom: 6px;
  }
</style>
