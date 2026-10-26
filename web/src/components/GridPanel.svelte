<script lang="ts">
  // One small panel of the all-variables grid: the same years, scenarios, view and axis as the focus chart.
  import { buildPlotModel } from '../lib/query';
  import { explorer } from '../lib/store.svelte';
  import ChartCanvas from './ChartCanvas.svelte';

  let { variableId }: { variableId: string } = $props();

  // A panel is drawn once it is near the viewport (or while exporting), which keeps the first paint fast.
  let seen = $state(false);
  let element: HTMLElement;
  $effect(() => {
    const observer = new IntersectionObserver(
      (entries) => entries.some((e) => e.isIntersecting) && (seen = true),
      { rootMargin: '400px' }
    );
    observer.observe(element);
    return () => observer.disconnect();
  });
  $effect(() => {
    if (explorer.renderAllPanels) seen = true;
  });
  const visible = $derived(seen || explorer.renderAllPanels);
  const variable = $derived(explorer.data!.catalog.variables.find((v) => v.id === variableId)!);
  const model = $derived(visible ? buildPlotModel(explorer.s, explorer.data!, variableId) : null);
  const focused = $derived(explorer.s.variable === variableId);
  const focus = () => explorer.focusVariable(variableId, true);
</script>

<section class="panel" class:focused aria-label={variable.name} bind:this={element}>
  <button
    type="button"
    class="title"
    aria-pressed={focused}
    title={`Show ${variable.name} in the large chart`}
    onclick={focus}
  >
    <span class="name">{variable.name}</span>
    <span class="unit">{model?.unit ?? ''}</span>
  </button>
  <div class="plot" style:min-height="170px">
    {#if model}
      <ChartCanvas {model} mode="panel" {variableId} height={170} onbackground={focus} />
      {#if model.empty}<p class="empty-note">{model.empty}</p>{/if}
    {/if}
  </div>
</section>

<style>
  .panel {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 8px 8px 4px;
    background: var(--paper);
    min-width: 0;
  }
  .panel.focused {
    border-color: var(--navy);
    box-shadow: inset 0 0 0 1px var(--navy);
  }
  .title {
    display: block;
    width: 100%;
    text-align: left;
    border: 0;
    background: none;
    padding: 0 2px;
    min-width: 0;
  }
  .name {
    display: block;
    font-size: 13.5px;
    font-weight: 600;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .focused .name {
    color: var(--navy);
  }
  .title:hover .name {
    color: var(--navy);
    text-decoration: underline;
  }
  .unit {
    display: block;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
    padding: 10px;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.9);
  }
</style>
