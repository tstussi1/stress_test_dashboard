<script lang="ts">
  let {
    label,
    checked,
    disabled = false,
    hint = '',
    onchange
  }: {
    label: string;
    checked: boolean;
    disabled?: boolean;
    hint?: string;
    onchange: (checked: boolean) => void;
  } = $props();
</script>

<label class="switch" class:disabled title={hint}>
  <input
    type="checkbox"
    role="switch"
    {checked}
    {disabled}
    onchange={(e) => onchange(e.currentTarget.checked)}
  />
  <span class="track" aria-hidden="true"><span class="thumb"></span></span>
  <span class="text"
    >{label}{#if disabled && hint}<small>{hint}</small>{/if}</span
  >
</label>

<style>
  .switch {
    position: relative;
    display: flex;
    gap: 10px;
    align-items: flex-start;
    cursor: pointer;
    font-size: 14px;
  }
  .switch.disabled {
    cursor: not-allowed;
    color: var(--muted);
  }
  input {
    position: absolute;
    left: 0;
    top: 2px;
    width: 34px;
    height: 18px;
    margin: 0;
    opacity: 0;
    cursor: inherit;
    z-index: 1;
  }
  .track {
    flex: none;
    width: 34px;
    height: 18px;
    margin-top: 2px;
    border-radius: 9px;
    background: var(--rule-strong);
    position: relative;
    transition: background 0.15s;
  }
  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    transition: transform 0.15s;
  }
  input:checked + .track {
    background: var(--navy);
  }
  input:checked + .track .thumb {
    transform: translateX(16px);
  }
  input:focus-visible + .track {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }
  small {
    display: block;
    font-size: 12px;
    color: var(--muted);
  }
</style>
