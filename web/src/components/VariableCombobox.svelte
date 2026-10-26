<script lang="ts">
  import type { CatalogVariable } from '../lib/types';

  let {
    variables,
    selected,
    onchange
  }: { variables: CatalogVariable[]; selected: string; onchange: (id: string) => void } = $props();

  let query = $state('');
  let open = $state(false);
  let active = $state(0);
  let root: HTMLDivElement;

  const matches = $derived(
    variables.filter(
      (v) =>
        !query.trim() ||
        `${v.name} ${v.theme} ${v.id.replaceAll('_', ' ')}`.toLowerCase().includes(query.trim().toLowerCase())
    )
  );
  const themes = $derived([...new Set(matches.map((v) => v.theme))]);
  const current = $derived(variables.find((v) => v.id === selected));

  function choose(id: string) {
    onchange(id);
    open = false;
    query = '';
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      open = true;
      active = Math.min(active + 1, matches.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = Math.max(active - 1, 0);
    } else if (e.key === 'Enter' && open && matches[active]) {
      e.preventDefault();
      choose(matches[active]!.id);
    } else if (e.key === 'Escape') {
      open = false;
      query = '';
    }
  }
  $effect(() => {
    void query;
    active = 0;
  });
</script>

<div
  class="combo"
  bind:this={root}
  onfocusout={(e) => {
    if (!root.contains(e.relatedTarget as Node | null)) {
      open = false;
      query = '';
    }
  }}
>
  <input
    type="text"
    role="combobox"
    aria-expanded={open}
    aria-controls="variable-listbox"
    aria-autocomplete="list"
    aria-activedescendant={open && matches[active] ? `opt-${matches[active]?.id}` : undefined}
    aria-label="Search variables"
    placeholder={current?.name ?? 'Search variables'}
    title={current?.definition ?? undefined}
    autocomplete="off"
    value={query}
    onfocus={() => (open = true)}
    oninput={(e) => {
      query = e.currentTarget.value;
      open = true;
    }}
    {onkeydown}
  />
  <span class="current" class:hidden={query !== ''}>{current?.name}</span>
  {#if open}
    <div class="list" id="variable-listbox" role="listbox" aria-label="Variables">
      {#each themes as theme (theme)}
        <div class="group" role="presentation">{theme}</div>
        {#each matches.filter((v) => v.theme === theme) as v (v.id)}
          <div
            id={`opt-${v.id}`}
            role="option"
            tabindex="-1"
            aria-selected={selected === v.id}
            class:active={matches[active]?.id === v.id}
            class:chosen={selected === v.id}
            onmousedown={(e) => {
              e.preventDefault();
              choose(v.id);
            }}
            onmouseenter={() => (active = matches.findIndex((m) => m.id === v.id))}
          >
            <span class="tick" aria-hidden="true">{selected === v.id ? '✓' : ''}</span>{v.name}
          </div>
        {/each}
      {:else}
        <div class="empty">No variable matches “{query}”.</div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .combo {
    position: relative;
    min-width: 250px;
  }
  input {
    width: 100%;
    border: 1px solid var(--rule-strong);
    border-radius: var(--radius);
    padding: 6px 28px 6px 10px;
    background: var(--paper)
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%235b6573' stroke-width='1.5'/%3E%3C/svg%3E")
      no-repeat right 10px center;
  }
  input::placeholder {
    color: transparent;
  }
  .current {
    position: absolute;
    left: 11px;
    top: 7px;
    right: 28px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    pointer-events: none;
    font-weight: 600;
    color: var(--navy);
  }
  .current.hidden {
    visibility: hidden;
  }
  .list {
    position: absolute;
    z-index: 30;
    left: 0;
    min-width: 100%;
    width: max-content;
    max-width: 420px;
    top: 100%;
    max-height: 360px;
    overflow: auto;
    background: var(--paper);
    border: 1px solid var(--rule-strong);
    border-radius: var(--radius);
    margin-top: 2px;
    box-shadow: 0 6px 18px rgba(19, 41, 75, 0.14);
  }
  .group {
    padding: 8px 10px 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  [role='option'] {
    padding: 6px 10px 6px 4px;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    gap: 4px;
  }
  [role='option'].active {
    background: var(--panel);
  }
  [role='option'].chosen {
    font-weight: 600;
    color: var(--navy);
  }
  .tick {
    display: inline-block;
    width: 18px;
    text-align: center;
  }
  .empty {
    padding: 12px;
    color: var(--muted);
    font-size: 14px;
  }
</style>
