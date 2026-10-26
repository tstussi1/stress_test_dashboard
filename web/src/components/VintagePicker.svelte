<script lang="ts">
  import { vintageColor } from '../lib/colors';
  import { explorer } from '../lib/store.svelte';

  const vintages = $derived(explorer.data!.catalog.vintages);
  const selected = $derived(explorer.s.vintages);
  const n = $derived(vintages.length);
  const indexes = $derived(vintages.map((v, i) => (selected.includes(v.id) ? i : -1)).filter((i) => i >= 0));
  const lo = $derived(Math.min(...indexes));
  const hi = $derived(Math.max(...indexes));
  const contiguous = $derived(indexes.length === hi - lo + 1);
  const presets = [
    { label: 'All', count: () => n },
    { label: 'Latest 6', count: () => 6 },
    { label: 'Latest 3', count: () => 3 },
    { label: 'Latest', count: () => 1 }
  ];

  function toggle(id: string) {
    explorer.setVintages(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  }
  const THUMB = 24; // px; the touch target of each handle (WCAG 2.2 target size, 24 x 24 CSS px)
  let rail: HTMLDivElement;

  /** Select the contiguous range `from..to` of vintages; the first handle never passes the last. */
  function setRange(from: number, to: number) {
    explorer.setVintages(vintages.slice(from, to + 1).map((v) => v.id));
  }
  /** Move one handle to `index`, clamped so that the range keeps at least one vintage. */
  function move(first: boolean, index: number) {
    if (first) setRange(Math.min(Math.max(index, 0), hi), hi);
    else setRange(lo, Math.max(Math.min(index, n - 1), lo));
  }
  function onThumbKey(e: KeyboardEvent, first: boolean) {
    const current = first ? lo : hi;
    const target =
      e.key === 'ArrowRight' || e.key === 'ArrowUp'
        ? current + 1
        : e.key === 'ArrowLeft' || e.key === 'ArrowDown'
          ? current - 1
          : e.key === 'PageUp'
            ? current + 4
            : e.key === 'PageDown'
              ? current - 4
              : e.key === 'Home'
                ? 0
                : e.key === 'End'
                  ? n - 1
                  : null;
    if (target === null) return;
    e.preventDefault();
    move(first, target);
  }
  const startDrag = (e: PointerEvent, first: boolean) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag(e, first);
  };
  function drag(e: PointerEvent, first: boolean) {
    if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
    const box = rail.getBoundingClientRect();
    const fraction = (e.clientX - box.left - THUMB / 2) / (box.width - THUMB);
    move(first, Math.round(Math.min(Math.max(fraction, 0), 1) * (n - 1)));
  }
</script>

<div class="picker">
  <div class="top">
    <span class="eyebrow">Years</span>
    <div class="presets" role="group" aria-label="Year presets">
      {#each presets as p (p.label)}
        <button
          type="button"
          class="link"
          onclick={() => explorer.setVintages(vintages.slice(-p.count()).map((v) => v.id))}>{p.label}</button
        >
      {/each}
    </div>
    <div class="range-label">
      {vintages[lo]?.label}<span class="to">to</span>{vintages[hi]?.label}
      {#if !contiguous}<em>(custom)</em>{/if}
    </div>
  </div>
  <div class="range" bind:this={rail}>
    <div class="track">
      <div
        class="fill"
        style:left="{(lo / (n - 1)) * 100}%"
        style:width="{((hi - lo) / (n - 1)) * 100}%"
      ></div>
    </div>
    {#each [{ name: 'First vintage', value: lo, which: 'lo' }, { name: 'Last vintage', value: hi, which: 'hi' }] as thumb (thumb.which)}
      <div
        class="thumb"
        role="slider"
        tabindex="0"
        aria-label={thumb.name}
        aria-orientation="horizontal"
        aria-valuemin={thumb.which === 'lo' ? 0 : lo}
        aria-valuemax={thumb.which === 'lo' ? hi : n - 1}
        aria-valuenow={thumb.value}
        aria-valuetext={vintages[thumb.value]?.label}
        style:left="calc((100% - {THUMB}px) * {thumb.value / (n - 1)})"
        style:z-index={thumb.which === 'lo' && lo === hi && lo > (n - 1) / 2 ? 2 : 1}
        onkeydown={(e) => onThumbKey(e, thumb.which === 'lo')}
        onpointerdown={(e) => startDrag(e, thumb.which === 'lo')}
        onpointermove={(e) => drag(e, thumb.which === 'lo')}
        onpointerup={(e) => e.currentTarget.releasePointerCapture(e.pointerId)}
      >
        <span class="knob"></span>
      </div>
    {/each}
  </div>
  <div class="chips" role="group" aria-label="Years">
    {#each vintages as v, i (v.id)}
      <button
        type="button"
        class="chip"
        class:on={selected.includes(v.id)}
        aria-pressed={selected.includes(v.id)}
        title={`${v.label}: ${v.scenarios.length} scenario${v.scenarios.length === 1 ? '' : 's'} published`}
        onclick={() => toggle(v.id)}
        ><span class="swatch" style:background={vintageColor(i, n)}></span>{v.label}</button
      >
    {/each}
  </div>
</div>

<style>
  .picker {
    min-width: 0;
  }
  .top {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 6px 14px;
    margin-bottom: 2px;
  }
  .presets {
    display: flex;
    gap: 12px;
  }
  .range-label {
    margin-left: auto;
    font-size: 13px;
    font-weight: 600;
    color: var(--navy);
  }
  .to {
    font-weight: 400;
    color: var(--muted);
    margin: 0 6px;
  }
  em {
    font-weight: 400;
    color: var(--muted);
    margin-left: 6px;
  }
  .range {
    position: relative;
    height: 26px;
  }
  .track {
    position: absolute;
    top: 11px;
    left: 12px;
    right: 12px;
    height: 4px;
    border-radius: 2px;
    background: var(--rule);
  }
  .fill {
    position: absolute;
    height: 100%;
    background: var(--navy);
    border-radius: 2px;
  }
  .thumb {
    position: absolute;
    top: 1px;
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    cursor: grab;
    touch-action: none;
    border-radius: 50%;
  }
  .thumb:active {
    cursor: grabbing;
  }
  .knob {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid var(--navy);
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--navy-soft);
    font-size: 13px;
    text-decoration: underline;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid var(--rule-strong);
    background: var(--paper);
    border-radius: 12px;
    padding: 2px 10px 2px 7px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .chip .swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    opacity: 0.35;
  }
  .chip.on {
    color: var(--ink);
    font-weight: 600;
    border-color: var(--navy);
    box-shadow: inset 0 0 0 1px var(--navy);
  }
  .chip.on .swatch {
    opacity: 1;
  }
</style>
