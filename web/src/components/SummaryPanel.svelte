<script lang="ts">
  // Peak and trough of every scenario line, read from the plotted numbers (no new calculation).
  import { formatQuarter, formatSigned, formatValue } from '../lib/format';
  import { explorer } from '../lib/store.svelte';
  import type { PlotModel } from '../lib/types';

  let { model, onclose }: { model: PlotModel; onclose: () => void } = $props();

  const catalog = $derived(explorer.data!.catalog);
  const label = (id: string) => catalog.vintages.find((v) => v.id === id)?.label ?? id;
  const scenarioLabel = (name: string) => catalog.scenarios.find((s) => s.name === name)?.label ?? name;
  const fmt = (v: number) => (model.view === 'deviation' ? formatSigned(v) : formatValue(v));
  let panel: HTMLElement;
  $effect(() => panel.focus({ preventScroll: true }));
</script>

<div
  class="panel"
  role="dialog"
  aria-modal="false"
  bind:this={panel}
  tabindex="-1"
  aria-label={`Peak and trough, ${model.title}`}
  onkeydown={(e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onclose();
    }
  }}
>
  <header>
    <h3>Peak and trough</h3>
    <button type="button" class="close" onclick={onclose} aria-label="Close summary panel">&times;</button>
  </header>
  <p class="lead">
    Highest and lowest value of each scenario line inside its scenario window, in {model.unit}. Read from the
    plotted numbers; nothing is recalculated.
  </p>
  <div class="scroll">
    <table>
      <thead>
        <tr
          ><th>Year</th><th>Scenario</th><th class="num">Peak</th><th>Quarter</th><th class="num">Trough</th
          ><th>Quarter</th></tr
        >
      </thead>
      <tbody>
        {#each model.summary as r (`${r.vintage}|${r.scenario}`)}
          <tr>
            <td>{label(r.vintage)}</td>
            <td>{scenarioLabel(r.scenario)}</td>
            <td class="num">{fmt(r.peak)}</td>
            <td>{formatQuarter(r.peakQuarter)}</td>
            <td class="num">{fmt(r.trough)}</td>
            <td>{formatQuarter(r.troughQuarter)}</td>
          </tr>
        {:else}
          <tr><td colspan="6">No scenario line to summarise.</td></tr>
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
    max-height: 640px;
    min-height: 220px;
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
  .lead {
    margin: 0;
    padding: 10px 14px;
    font-size: 12px;
    color: var(--muted);
    border-bottom: 1px solid var(--rule);
  }
  .scroll {
    overflow: auto;
    flex: 1;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
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
  }
  .num {
    text-align: right;
  }
</style>
