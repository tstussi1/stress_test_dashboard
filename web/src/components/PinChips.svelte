<script lang="ts">
  import { vintageColor } from '../lib/colors';
  import { explorer } from '../lib/store.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const pins = $derived(catalog.vintages.filter((v) => explorer.s.pins.includes(v.id)));
</script>

{#if pins.length}
  <div class="pins" role="group" aria-label="Pinned years">
    <span class="eyebrow">Pinned</span>
    {#each pins as v (v.id)}
      <span class="pin">
        <span
          class="swatch"
          style:background={vintageColor(catalog.vintages.indexOf(v), catalog.vintages.length)}
        ></span>{v.label}
        <button type="button" aria-label={`Unpin ${v.label}`} onclick={() => explorer.togglePin(v.id)}
          >&times;</button
        >
      </span>
    {/each}
    <button type="button" class="clear" onclick={() => explorer.clearPins()}>Clear (Esc)</button>
  </div>
{/if}

<style>
  .pins {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .pin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--navy);
    color: #fff;
    border-radius: 12px;
    padding: 1px 4px 1px 8px;
    font-size: 12.5px;
    font-weight: 600;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 1.5px solid #fff;
  }
  .pin button {
    border: 0;
    background: transparent;
    color: #fff;
    font-size: 15px;
    line-height: 1;
    padding: 0 5px;
    border-radius: 50%;
  }
  .pin button:hover {
    background: rgba(255, 255, 255, 0.25);
  }
  .clear {
    border: 0;
    background: none;
    color: var(--navy-soft);
    font-size: 12.5px;
    text-decoration: underline;
    padding: 0 4px;
  }
</style>
