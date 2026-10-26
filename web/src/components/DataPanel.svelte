<script lang="ts">
  import { downloadCsv, downloadDataset } from '../lib/export';
  import { formatQuarter } from '../lib/format';
  import { buildPlotModel } from '../lib/query';
  import { explorer } from '../lib/store.svelte';
  import type { PlotModel } from '../lib/types';

  let { model, onclose }: { model: PlotModel; onclose: () => void } = $props();

  const catalog = $derived(explorer.data!.catalog);
  const label = (id: string) => catalog.vintages.find((v) => v.id === id)?.label ?? id;
  const scenarioLabel = (name: string) => catalog.scenarios.find((s) => s.name === name)?.label ?? name;
  const typeLabel: Record<string, string> = {
    scenario: 'Scenario',
    history_latest: 'History (latest)',
    history_realtime: 'History (as then)',
    anchor: 'Start point',
    envelope_min: 'Minimum',
    envelope_max: 'Maximum',
    band_lo: 'Band low',
    band_hi: 'Band high'
  };
  const scopeIds = $derived(
    catalog.variables.filter((v) => v.scope === model.variable.scope).map((v) => v.id)
  );
  const allModels = () =>
    scopeIds.map((id) => buildPlotModel(explorer.s, explorer.data!, id)).filter((m) => m.series.length > 0);
  let panel: HTMLElement;
  $effect(() => panel.focus({ preventScroll: true }));
</script>

<div
  class="panel"
  role="dialog"
  aria-modal="false"
  bind:this={panel}
  tabindex="-1"
  aria-label={`Data behind ${model.title}`}
  onkeydown={(e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onclose();
    }
  }}
>
  <header>
    <h3>Chart data</h3>
    <button type="button" class="close" onclick={onclose} aria-label="Close data panel">&times;</button>
  </header>
  <div class="widget">
    <span class="eyebrow">Download chart data</span>
    <div class="buttons">
      <button type="button" class="text-button" onclick={() => downloadCsv([model], catalog.built_at)}
        >CSV, this chart</button
      >
      <button type="button" class="text-button" onclick={() => downloadCsv(allModels(), catalog.built_at)}
        >CSV, all {model.variable.scope} variables</button
      >
    </div>
    <p>
      {model.rows.length.toLocaleString()} rows: exactly the numbers plotted, unrounded, with the publication, scenario
      and quarter of each. The file starts with lines stating the transform.
    </p>
    <p class="dataset">
      Need everything the Fed published, for modelling?
      <button type="button" class="linklike" onclick={() => downloadDataset(explorer.data!)}
        >Download the complete dataset (CSV)</button
      >: all scenarios and each year's own history.
    </p>
  </div>
  <div class="scroll">
    <table>
      <thead>
        <tr><th>Line</th><th>Year</th><th>Scenario</th><th>Quarter</th><th class="num">Value</th></tr>
      </thead>
      <tbody>
        {#each model.rows as r, i (i)}
          <tr>
            <td>{typeLabel[r.series_type]}</td>
            <td>{r.vintage ? label(r.vintage) : 'all years'}</td>
            <td>{r.scenario === 'history' ? '' : scenarioLabel(r.scenario)}</td>
            <td
              >{r.quarter ? formatQuarter(r.quarter) : `quarter ${r.horizon}`}{r.series_type === 'anchor'
                ? ' (start)'
                : ''}</td
            >
            <td class="num"
              >{r.value}{#if r.fed_estimate}<sup title="The Federal Reserve marks this value as an estimate"
                  >e</sup
                >{/if}</td
            >
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .panel {
    border: 1px solid var(--rule-strong);
    border-radius: var(--radius);
    background: var(--paper);
    display: flex;
    flex-direction: column;
    height: 100%;
    max-height: 640px;
    min-height: 320px;
    outline: none;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid var(--rule);
    background: var(--panel);
  }
  h3 {
    margin: 0;
    font-family: var(--font-serif);
    color: var(--navy);
    font-size: 17px;
  }
  .close {
    border: 0;
    background: none;
    font-size: 22px;
    line-height: 1;
    color: var(--muted);
  }
  .widget {
    padding: 12px 14px;
    border-bottom: 1px solid var(--rule);
  }
  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0;
  }
  .dataset {
    margin-top: 8px !important;
  }
  .linklike {
    border: 0;
    background: none;
    padding: 0;
    color: var(--navy-soft);
    text-decoration: underline;
    font-size: inherit;
  }
  .widget p {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .scroll {
    overflow: auto;
    flex: 1;
  }
  table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    font-size: 12px;
  }
  th:nth-child(1) {
    width: 21%;
  }
  th:nth-child(2) {
    width: 17%;
  }
  th:nth-child(3) {
    width: 24%;
  }
  th:nth-child(4) {
    width: 18%;
  }
  th {
    position: sticky;
    top: 0;
    background: var(--panel);
    text-align: left;
    padding: 6px;
    font-size: 10.5px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--rule-strong);
  }
  td {
    padding: 3px 6px;
    border-bottom: 1px solid #eef0f3;
    overflow-wrap: anywhere;
  }
  .num {
    text-align: right;
  }
  sup {
    color: var(--warn-ink);
    font-weight: 600;
    margin-left: 2px;
  }
</style>
