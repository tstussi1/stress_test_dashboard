<script lang="ts">
  import { familyStyle } from '../lib/colors';
  import { explorer } from '../lib/store.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const scenarios = $derived(catalog.scenarios.filter((s) => s.name !== 'realized'));
  const count = (name: string) => catalog.vintages.filter((v) => v.scenarios.includes(name)).length;
  const deviation = $derived(explorer.s.view === 'deviation');
</script>

<div class="chips" role="group" aria-label="Scenarios">
  {#each scenarios as s (s.name)}
    {@const off = deviation && s.name === 'baseline'}
    <button
      type="button"
      class="chip"
      class:on={explorer.s.scenarios.includes(s.name)}
      aria-pressed={explorer.s.scenarios.includes(s.name)}
      disabled={off}
      title={off
        ? 'The deviation view measures every scenario against the baseline, so the baseline itself is not drawn.'
        : `${s.label}: published in ${count(s.name)} year${count(s.name) === 1 ? '' : 's'}`}
      onclick={() => explorer.toggleScenario(s.name)}
    >
      <svg class="swatch" width="22" height="8" viewBox="0 0 22 8" aria-hidden="true"
        ><line
          x1="0"
          y1="4"
          x2="22"
          y2="4"
          stroke="#3a3f4b"
          stroke-width={familyStyle(s.family).width + 0.4}
          stroke-dasharray={familyStyle(s.family).dash === 'solid'
            ? ''
            : (familyStyle(s.family).dash as number[]).join(' ')}
        /></svg
      >
      {s.label}
      <span class="count">{count(s.name)}</span>
    </button>
  {/each}
</div>

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--rule-strong);
    background: var(--paper);
    border-radius: 14px;
    padding: 3px 10px 3px 8px;
    font-size: 13px;
  }
  .chip.on {
    border-color: var(--navy);
    box-shadow: inset 0 0 0 1px var(--navy);
    font-weight: 600;
  }
  .chip:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .swatch {
    flex: none;
  }
  .count {
    font-size: 11px;
    color: var(--muted);
    font-weight: 400;
  }
</style>
