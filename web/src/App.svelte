<script lang="ts">
  import { onMount } from 'svelte';
  import FocusFigure from './components/FocusFigure.svelte';
  import MethodologyTab from './components/MethodologyTab.svelte';
  import Notices from './components/Notices.svelte';
  import SourcesBlock from './components/SourcesBlock.svelte';
  import Toolbar from './components/Toolbar.svelte';
  import VariableGrid from './components/VariableGrid.svelte';
  import { explorer } from './lib/store.svelte';

  onMount(() => {
    void explorer.init();
  });

  const tabs = [
    { id: 'explorer', label: 'Explorer' },
    { id: 'methodology', label: 'Methodology' }
  ] as const;

  /** ARIA tabs pattern: Left/Right (wrapping), Home and End move focus to a tab and select it. */
  function onTabKeydown(e: KeyboardEvent) {
    const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const current = tabs.findIndex((t) => t.id === explorer.s.tab);
    const next =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? tabs.length - 1
          : (current + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    explorer.set({ tab: tabs[next]!.id });
    document.getElementById(`tab-${tabs[next]!.id}`)?.focus();
  }
</script>

<svelte:window
  onkeydown={(e) => e.key === 'Escape' && explorer.state && explorer.clearPins()}
  onhashchange={() => explorer.data && explorer.applyHash()}
/>

{#if explorer.error}
  <main class="fatal" role="alert">
    <h1>Stress Test Scenario Explorer</h1>
    <p>{explorer.error}</p>
    <p>
      The page cannot show numbers it could not load completely. Reload the page; if this persists the data
      files are missing or out of date.
    </p>
  </main>
{:else if !explorer.data || !explorer.state}
  <main class="loading"><p>Loading scenario data…</p></main>
{:else}
  <header class="masthead">
    <div class="inner">
      <div>
        <h1>Stress Test Scenario Explorer</h1>
        <p>Federal Reserve supervisory scenarios, 2013–2026</p>
      </div>
      <div class="actions">
        <button type="button" class="text-button" onclick={() => explorer.copyLink()}
          >{explorer.copied ? 'Link copied' : 'Copy link'}</button
        >
        <button type="button" class="text-button" onclick={() => explorer.reset()}>Reset</button>
      </div>
      <nav aria-label="Sections">
        <div role="tablist" tabindex="-1" onkeydown={onTabKeydown}>
          {#each tabs as tab (tab.id)}
            <button
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={explorer.s.tab === tab.id}
              tabindex={explorer.s.tab === tab.id ? 0 : -1}
              aria-controls={`panel-${tab.id}`}
              class:active={explorer.s.tab === tab.id}
              onclick={() => explorer.set({ tab: tab.id })}
            >
              {tab.label}
            </button>
          {/each}
        </div>
      </nav>
    </div>
  </header>

  <main class="page">
    <Notices />
    {#if explorer.s.tab === 'explorer'}
      <div role="tabpanel" id="panel-explorer" aria-labelledby="tab-explorer">
        {#if explorer.linkToCopy}
          <p class="manual">
            Your browser blocked copying. Copy this link:
            <input
              readonly
              value={explorer.linkToCopy}
              aria-label="Share link"
              onfocus={(e) => e.currentTarget.select()}
            />
          </p>
        {/if}
        <Toolbar />
        <FocusFigure />
        <VariableGrid />
      </div>
      <SourcesBlock />
    {:else}
      <div role="tabpanel" id="panel-methodology" aria-labelledby="tab-methodology">
        <MethodologyTab />
      </div>
    {/if}
  </main>
{/if}

<style>
  .masthead {
    border-top: 5px solid var(--navy);
    border-bottom: 1px solid var(--rule);
    background: var(--paper);
  }
  .inner {
    max-width: var(--page-width);
    margin: 0 auto;
    padding: 12px 32px 0;
    display: flex;
    align-items: flex-end;
    gap: 20px;
    flex-wrap: wrap;
  }
  .inner > div:first-child {
    margin-right: auto;
  }
  h1 {
    font-size: 25px;
    letter-spacing: -0.005em;
  }
  .masthead p {
    margin: 2px 0 10px;
    color: var(--muted);
    font-size: 14px;
  }
  .actions {
    display: flex;
    gap: 8px;
    padding-bottom: 10px;
  }
  [role='tablist'] {
    display: flex;
    gap: 22px;
  }
  [role='tab'] {
    border: 0;
    border-bottom: 3px solid transparent;
    background: none;
    padding: 8px 2px 11px;
    font-size: 15px;
    color: var(--muted);
    font-weight: 600;
  }
  [role='tab']:hover {
    color: var(--navy);
  }
  [role='tab'].active {
    color: var(--navy);
    border-bottom-color: var(--navy);
  }
  .page {
    max-width: var(--page-width);
    margin: 0 auto;
    padding: 20px 32px 56px;
  }
  .manual {
    font-size: 13px;
    margin: 0 0 12px;
  }
  .manual input {
    width: 100%;
    margin-top: 4px;
    font-size: 13px;
  }
  .fatal,
  .loading {
    max-width: 640px;
    margin: 12vh auto;
    padding: 0 24px;
  }
  .fatal p {
    color: var(--ink);
  }
  @media (max-width: 960px) {
    .inner,
    .page {
      padding-left: 18px;
      padding-right: 18px;
    }
  }
</style>
