<script lang="ts">
  // "How to use this dashboard": the one place that explains the controls. Open on a first visit,
  // collapsed behind this header afterwards; the masthead's "How to use" button reopens it.
  import { GUIDE } from '../lib/guide';
  import { explorer } from '../lib/store.svelte';
</script>

<section class="guide" id="usage-guide" aria-labelledby="guide-title">
  <h2 id="guide-title">
    <button
      type="button"
      class="head"
      aria-expanded={explorer.guideOpen}
      aria-controls="guide-body"
      onclick={() => explorer.setGuide(!explorer.guideOpen)}
    >
      How to use this dashboard <span aria-hidden="true">{explorer.guideOpen ? '–' : '+'}</span>
    </button>
  </h2>
  <div id="guide-body" class="body" hidden={!explorer.guideOpen}>
    {#each GUIDE as section (section.id)}
      <div class="block">
        <h3>{section.title}</h3>
        <ul>
          {#each section.items as item (item.text)}
            <li>
              {#if item.control}<strong>{item.control}.</strong>{/if}
              {item.text}
            </li>
          {/each}
        </ul>
      </div>
    {/each}
    <p class="more">
      Formulas, the Federal Reserve’s definitions and what is not available are on the
      <button type="button" class="link" onclick={() => explorer.set({ tab: 'methodology' })}
        >Methodology</button
      > tab.
    </p>
  </div>
</section>

<style>
  .guide {
    border: 1px solid var(--rule);
    border-left: 4px solid var(--navy);
    border-radius: var(--radius);
    background: var(--paper);
    margin: 0 0 16px;
  }
  h2 {
    font-size: 16px;
    margin: 0;
  }
  .head {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border: 0;
    background: none;
    padding: 10px 14px;
    font: inherit;
    font-weight: 600;
    color: var(--navy);
    text-align: left;
  }
  .body {
    columns: 320px;
    column-gap: 28px;
    padding: 0 14px 12px;
  }
  .body[hidden] {
    display: none;
  }
  h3 {
    font-size: 13px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 10px 0 4px;
    break-after: avoid;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    font-size: 13.5px;
    line-height: 1.45;
    margin-bottom: 5px;
    break-inside: avoid;
  }
  .more {
    column-span: all;
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--navy-soft);
    font: inherit;
    text-decoration: underline;
  }
</style>
