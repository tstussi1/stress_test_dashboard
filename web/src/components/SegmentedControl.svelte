<script lang="ts" generics="T extends string">
  interface Option {
    value: T;
    label: string;
    title?: string;
    disabled?: boolean;
  }
  let {
    label,
    options,
    value,
    onchange
  }: { label: string; options: Option[]; value: T; onchange: (value: T) => void } = $props();
</script>

<div class="segmented" role="radiogroup" aria-label={label}>
  {#each options as option (option.value)}
    <button
      type="button"
      role="radio"
      aria-checked={value === option.value}
      class:active={value === option.value}
      disabled={option.disabled}
      title={option.title}
      onclick={() => onchange(option.value)}
    >
      {option.label}
    </button>
  {/each}
</div>

<style>
  .segmented {
    display: flex;
    border: 1px solid var(--rule-strong);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--paper);
  }
  button {
    flex: 1;
    border: 0;
    border-right: 1px solid var(--rule);
    background: transparent;
    padding: 6px 8px;
    font-size: 13px;
    line-height: 1.25;
    white-space: nowrap;
    color: var(--ink);
  }
  button:last-child {
    border-right: 0;
  }
  button:hover:not(:disabled):not(.active) {
    background: var(--panel);
  }
  button.active {
    background: var(--navy);
    color: #fff;
    font-weight: 600;
  }
  button:disabled {
    color: var(--muted);
    opacity: 0.55;
    cursor: not-allowed;
  }
</style>
