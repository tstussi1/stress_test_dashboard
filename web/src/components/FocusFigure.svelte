<script lang="ts">
  // The large "focus" chart: title, toolbar (PNG, Summary, Data), year key, pinned years, the chart,
  // the key to line patterns, notes and the one-line caption.
  import { familyStyle, vintageColor } from '../lib/colors';
  import { focusFor } from '../lib/focus';
  import { composeFigures, download, pngFilename } from '../lib/export';
  import { buildPlotModel } from '../lib/query';
  import { explorer } from '../lib/store.svelte';
  import ChartCanvas from './ChartCanvas.svelte';
  import DataPanel from './DataPanel.svelte';
  import PinChips from './PinChips.svelte';
  import SummaryPanel from './SummaryPanel.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const model = $derived(buildPlotModel(explorer.s, explorer.data!, explorer.s.variable));
  const keyVintages = $derived(catalog.vintages.filter((v) => model.summary.some((r) => r.vintage === v.id)));
  const families = $derived(
    catalog.scenarios.filter((sc) => model.summary.some((r) => r.scenario === sc.name))
  );
  const hasHistory = $derived(model.series.some((s) => s.kind !== 'scenario'));
  const fadedHistory = $derived.by(() => {
    const focus = focusFor(model, catalog, explorer.s.pins, null);
    return model.series.some((s) => s.kind === 'history' && focus.get(s.id)!.opacity < 1);
  });
  const hasEstimate = $derived(model.series.some((s) => s.info.some((p) => p.estimated)));

  let panel = $state<'data' | 'summary' | null>(null);
  let busy = $state(false);
  let toolbar: HTMLDivElement;

  async function downloadPng() {
    const chart = explorer.charts.get(`focus|${model.variable.id}`);
    if (!chart || model.rows.length === 0) return;
    busy = true;
    try {
      download(
        pngFilename([model], catalog.built_at),
        await composeFigures([{ png: chart.png(), model }], 1)
      );
    } finally {
      busy = false;
    }
  }
  function close() {
    const opener = toolbar.querySelector<HTMLButtonElement>(`[data-panel="${panel}"]`);
    panel = null;
    opener?.focus();
  }
  const dash = (family: string) => {
    const d = familyStyle(family).dash;
    return d === 'solid' ? '' : d.join(' ');
  };
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && panel && close()} />

<figure class="card" id="focus-figure">
  <header>
    <div class="titles">
      <h2>{model.title}</h2>
      <p class="sub">{model.subtitle}</p>
      {#if model.variable.definition}<p class="definition" title={model.variable.definition}>
          {model.variable.definition}
        </p>{/if}
    </div>
    <div class="toolbar" bind:this={toolbar}>
      <button
        type="button"
        class="text-button"
        disabled={model.rows.length === 0 || busy}
        onclick={downloadPng}>PNG</button
      >
      <button
        type="button"
        class="text-button"
        data-panel="summary"
        aria-expanded={panel === 'summary'}
        disabled={model.summary.length === 0}
        onclick={() => (panel = panel === 'summary' ? null : 'summary')}>Summary</button
      >
      <button
        type="button"
        class="text-button"
        data-panel="data"
        aria-expanded={panel === 'data'}
        disabled={model.rows.length === 0}
        onclick={() => (panel = panel === 'data' ? null : 'data')}>Data</button
      >
    </div>
  </header>

  {#if keyVintages.length}
    <div class="key" role="group" aria-label="Years: select to pin">
      {#each keyVintages as v (v.id)}
        <button
          type="button"
          class="year"
          class:pinned={explorer.s.pins.includes(v.id)}
          aria-pressed={explorer.s.pins.includes(v.id)}
          title="Hover to isolate this year; click to pin"
          onmouseenter={() => (explorer.hovered = v.id)}
          onmouseleave={() => (explorer.hovered = null)}
          onfocus={() => (explorer.hovered = v.id)}
          onblur={() => (explorer.hovered = null)}
          onclick={() => explorer.togglePin(v.id)}
        >
          <span
            class="swatch"
            style:background={vintageColor(catalog.vintages.indexOf(v), catalog.vintages.length)}
          ></span>{v.label}{#if v.exercise}<span class="tag">{v.exercise}</span>{/if}
        </button>
      {/each}
    </div>
  {/if}
  <div class="pinrow"><PinChips /></div>

  <div class="body" class:with-panel={panel !== null}>
    <div class="plot">
      <ChartCanvas
        {model}
        mode="focus"
        variableId={model.variable.id}
        height={model.axis === 'calendar' ? 470 : 430}
      />
      {#if model.empty}<p class="empty-note">{model.empty}</p>{/if}
    </div>
    {#if panel === 'data'}<DataPanel {model} onclose={close} />{/if}
    {#if panel === 'summary'}<SummaryPanel {model} onclose={close} />{/if}
  </div>

  {#if model.bandReadout}
    <p class="band-readout" data-testid="band-readout">
      <span>{model.bandReadout.min}</span><span>{model.bandReadout.max}</span>
    </p>
  {/if}

  {#if keyVintages.length}
    <p class="hint">
      Hover a line to isolate a year. Click to pin it. Esc clears pins.{#if fadedHistory}<span class="lighter"
          >Lighter history = quarters after the highlighted year's start, which that year did not yet know.</span
        >{/if}
    </p>
    <p class="key-line">
      {#each families as sc (sc.name)}
        <span
          ><svg width="26" height="8" aria-hidden="true"
            ><line
              x1="0"
              y1="4"
              x2="26"
              y2="4"
              stroke="#3a3f4b"
              stroke-width={familyStyle(sc.family).width + 0.4}
              stroke-dasharray={dash(sc.family)}
            /></svg
          >{sc.label}</span
        >
      {/each}
      {#if hasHistory}<span
          ><svg width="26" height="8" aria-hidden="true"
            ><line x1="0" y1="4" x2="26" y2="4" stroke="#3a3f4b" stroke-width="2.2" /></svg
          >Historical data</span
        >{/if}
      {#if model.band}<span><i class="band-swatch"></i>lowest to highest of the lines drawn</span>{/if}
      {#if hasEstimate}<span><i class="hollow"></i>value the Federal Reserve marks as an estimate</span>{/if}
    </p>
  {/if}
  {#each model.notes as note (note)}<p class="note">{note}</p>{/each}
  <figcaption>{model.caption}</figcaption>
</figure>

<style>
  .card {
    margin: 0;
    min-width: 0;
    scroll-margin-top: 150px;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }
  .toolbar {
    display: flex;
    gap: 6px;
    flex: none;
  }
  h2 {
    font-size: 23px;
  }
  .sub {
    margin: 2px 0 0;
    color: var(--muted);
    font-size: 13.5px;
  }
  .definition {
    margin: 4px 0 0;
    color: var(--muted);
    font-size: 12.5px;
    max-width: 900px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .key {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px;
    margin-top: 12px;
  }
  .year {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--rule-strong);
    background: var(--paper);
    border-radius: 12px;
    padding: 1px 10px 1px 7px;
    font-size: 12.5px;
  }
  .year:hover {
    border-color: var(--navy);
  }
  .year.pinned {
    border-color: var(--navy);
    box-shadow: inset 0 0 0 1px var(--navy);
    font-weight: 600;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .tag {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: var(--muted);
    border: 1px solid var(--rule-strong);
    border-radius: 3px;
    padding: 0 3px;
    line-height: 1.3;
  }
  .pinrow {
    margin-top: 6px;
    min-height: 0;
  }
  .body {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    margin-top: 6px;
  }
  .body.with-panel {
    grid-template-columns: minmax(0, 1fr) 440px;
  }
  @media (max-width: 1280px) {
    .body.with-panel {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .plot {
    position: relative;
  }
  .empty-note {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    margin: 0;
    padding: 24px;
    text-align: center;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.85);
  }
  .band-readout {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 24px;
    margin: 8px 0 0;
    padding: 6px 10px;
    border-left: 3px solid #8a94a3;
    background: #f2f4f7;
    font-size: 13px;
    color: var(--ink);
  }
  .hint {
    margin: 4px 0 0;
    font-size: 12.5px;
    color: var(--muted);
  }
  .key-line {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    margin: 6px 0 0;
    font-size: 12.5px;
    color: var(--muted);
  }
  .key-line span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .lighter {
    margin-left: 0.4em;
  }
  .hollow {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 2px solid var(--muted);
    background: #fff;
  }
  .band-swatch {
    width: 26px;
    height: 10px;
    background: rgba(138, 148, 163, 0.28);
    border-top: 1px solid rgba(138, 148, 163, 0.7);
    border-bottom: 1px solid rgba(138, 148, 163, 0.7);
  }
  .note {
    margin: 8px 0 0;
    padding: 6px 10px;
    background: var(--warn-bg);
    color: var(--warn-ink);
    border-radius: var(--radius);
    font-size: 13px;
  }
  figcaption {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.45;
  }
</style>
