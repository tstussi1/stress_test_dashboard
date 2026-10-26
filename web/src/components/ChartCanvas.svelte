<script lang="ts">
  // One ECharts canvas for a PlotModel. Used by the focus figure and by every panel of the grid, so
  // hover isolation, click-to-pin and PNG export behave identically everywhere.
  import { onMount } from 'svelte';
  import { createChart, type ChartHandle, type ChartMode } from '../lib/chart';
  import { explorer } from '../lib/store.svelte';
  import type { PlotModel } from '../lib/types';

  let {
    model,
    mode,
    variableId,
    height,
    onbackground
  }: {
    model: PlotModel;
    mode: ChartMode;
    variableId: string;
    height: number;
    onbackground?: () => void;
  } = $props();

  const catalog = $derived(explorer.data!.catalog);
  const summary = $derived(`${model.title}. ${model.series.length} lines, ${model.unit}.`);
  let element: HTMLDivElement;
  let chart = $state.raw<ChartHandle>();
  const reduced =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  onMount(() => {
    chart = createChart(element);
    chart.onSeriesClick((name) => {
      const vintage = name.split('|')[1];
      if (vintage && catalog.vintages.some((v) => v.id === vintage)) explorer.togglePin(vintage);
    });
    chart.onBackgroundClick(() => (onbackground ? onbackground() : explorer.clearPins()));
    chart.onHover((vintage) => (explorer.hovered = vintage));
    const observer = new ResizeObserver(() => chart?.resize());
    observer.observe(element);
    return () => {
      observer.disconnect();
      chart?.dispose();
    };
  });

  $effect(() => {
    if (!chart) return;
    const key = `${mode}|${variableId}`;
    explorer.charts.set(key, chart);
    return () => explorer.charts.delete(key);
  });
  $effect(() => {
    chart?.update(model, { catalog, mode, pins: explorer.s.pins, reducedMotion: reduced });
  });
  $effect(() => {
    chart?.setFocus(explorer.hovered);
  });
</script>

<div class="canvas" bind:this={element} style:height="{height}px" role="img" aria-label={summary}></div>
<p class="visually-hidden" aria-live="polite">{summary}</p>

<style>
  .canvas {
    width: 100%;
  }
</style>
