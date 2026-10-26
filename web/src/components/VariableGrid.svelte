<script lang="ts">
  // The overview: every variable of one scope (domestic or international) as a small panel,
  // grouped under the catalog's themes. Controls above apply to all panels at once.
  import { tick } from 'svelte';
  import { composeFigures, download, pngFilename } from '../lib/export';
  import { buildPlotModel } from '../lib/query';
  import { explorer } from '../lib/store.svelte';
  import GridPanel from './GridPanel.svelte';
  import SegmentedControl from './SegmentedControl.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const scope = $derived(catalog.variables.find((v) => v.id === explorer.s.variable)!.scope);
  const variables = $derived(catalog.variables.filter((v) => v.scope === scope));
  const themes = $derived([...new Set(variables.map((v) => v.theme))]);
  let closed = $state<string[]>([]);
  let busy = $state(false);

  const toggle = (theme: string) =>
    (closed = closed.includes(theme) ? closed.filter((t) => t !== theme) : [...closed, theme]);

  async function downloadAll() {
    busy = true;
    try {
      explorer.renderAllPanels = true;
      await tick();
      await new Promise((resolve) => setTimeout(resolve, 600)); // let the panels that were off screen draw
      const items = variables.flatMap((v) => {
        const chart = explorer.charts.get(`panel|${v.id}`);
        const model = buildPlotModel(explorer.s, explorer.data!, v.id);
        return chart && model.series.length ? [{ png: chart.png(), model }] : [];
      });
      if (!items.length) return;
      download(
        pngFilename(
          items.map((i) => i.model),
          catalog.built_at
        ),
        await composeFigures(items, 4)
      );
    } finally {
      explorer.renderAllPanels = false;
      busy = false;
    }
  }
</script>

<section class="grid" aria-labelledby="grid-title">
  <header>
    <div>
      <h2 id="grid-title">All {scope} variables</h2>
      <p>Same years, scenarios and view as above. Click a panel to enlarge it.</p>
    </div>
    <div class="controls">
      <SegmentedControl
        label="Variables shown"
        value={scope}
        options={[
          { value: 'domestic', label: 'Domestic' },
          { value: 'international', label: 'International' }
        ]}
        onchange={(next) => explorer.setScope(next)}
      />
      <button type="button" class="text-button" disabled={busy} onclick={downloadAll}>PNG, all panels</button>
    </div>
  </header>
  {#each themes as theme (theme)}
    {@const open = !closed.includes(theme)}
    <div class="group">
      <button type="button" class="theme" aria-expanded={open} onclick={() => toggle(theme)}>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>{theme}
      </button>
      {#if open}
        <div class="cells">
          {#each variables.filter((v) => v.theme === theme) as v (v.id)}
            <GridPanel variableId={v.id} />
          {/each}
        </div>
      {/if}
    </div>
  {/each}
</section>

<style>
  .grid {
    margin-top: 44px;
    padding-top: 20px;
    border-top: 1px solid var(--rule);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  h2 {
    font-size: 20px;
  }
  header p {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .controls {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .group {
    margin-top: 14px;
  }
  .theme {
    border: 0;
    background: none;
    padding: 2px 0;
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    display: flex;
    gap: 6px;
  }
  .theme:hover {
    color: var(--navy);
  }
  .cells {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-top: 6px;
  }
  @media (max-width: 1100px) {
    .cells {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
  @media (max-width: 760px) {
    .cells {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
