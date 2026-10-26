<script lang="ts">
  import { explorer } from '../lib/store.svelte';
</script>

{#if explorer.notices.length}
  <div class="notices" role="status">
    {#each explorer.notices as notice, i (notice)}
      <p>
        <span>{notice}</span>
        <button type="button" aria-label="Dismiss notice" onclick={() => explorer.dismissNotice(i)}
          >&times;</button
        >
      </p>
    {/each}
  </div>
{/if}

<style>
  .notices {
    margin-bottom: 18px;
  }
  p {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin: 0 0 6px;
    padding: 8px 12px;
    background: var(--warn-bg);
    color: var(--warn-ink);
    border-left: 3px solid #d79a00;
    border-radius: var(--radius);
    font-size: 14px;
  }
  button {
    border: 0;
    background: none;
    font-size: 18px;
    line-height: 1;
    color: inherit;
  }
</style>
