<script lang="ts">
  import { downloadDataset } from '../lib/export';
  import { explorer } from '../lib/store.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const label = (id: string) => catalog.vintages.find((v) => v.id === id)?.label ?? id;
</script>

<section class="sources" aria-labelledby="sources-title">
  <h2 id="sources-title">Sources</h2>
  <p class="lead">
    Board of Governors of the Federal Reserve System, supervisory stress test scenarios. Values are shown as
    published unless labelled as calculated; formulas and conventions are on the Methodology tab.
  </p>
  <ol>
    {#each catalog.reports as r (r.vintage)}
      <li>
        <a href={r.url} rel="noopener"
          >Federal Reserve Board, supervisory scenarios report, {label(r.vintage)}</a
        >{r.retrieved ? `, retrieved ${r.retrieved}` : ''}.
      </li>
    {/each}
  </ol>
  <p class="dataset">
    <button type="button" class="text-button" onclick={() => downloadDataset(explorer.data!)}
      >Download the complete dataset (CSV)</button
    >
    Every scenario path and each vintage’s own history, exactly as published.
  </p>
</section>

<style>
  .sources {
    margin-top: 56px;
    padding-top: 22px;
    border-top: 1px solid var(--rule);
  }
  h2 {
    font-size: 18px;
    margin-bottom: 8px;
  }
  .lead {
    margin: 0 0 10px;
    max-width: 78ch;
    color: var(--muted);
    font-size: 14px;
  }
  ol {
    columns: 2 380px;
    margin: 0;
    padding-left: 22px;
    font-size: 13px;
    color: var(--muted);
  }
  .dataset {
    margin: 14px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  li {
    margin-bottom: 3px;
    break-inside: avoid;
  }
</style>
