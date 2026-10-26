<script lang="ts">
  // Controls, in two rows: what to show (quick views, variable, scenarios, view, axis, band) and
  // which years / how much history. The first row stays visible while the grid scrolls.
  import { resolveVintages } from '../lib/state';
  import { buildPlotModel } from '../lib/query';
  import { explorer } from '../lib/store.svelte';
  import ScenarioChips from './ScenarioChips.svelte';
  import SegmentedControl from './SegmentedControl.svelte';
  import Switch from './Switch.svelte';
  import VariableCombobox from './VariableCombobox.svelte';
  import VintagePicker from './VintagePicker.svelte';

  const catalog = $derived(explorer.data!.catalog);
  const s = $derived(explorer.s);
  const variable = $derived(catalog.variables.find((v) => v.id === s.variable)!);
  const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);
  const quickActive = (id: string) => {
    const spec = catalog.quick_views.find((q) => q.id === id)!.state;
    const { vintages, scenarios, ...rest } = spec;
    return (
      Object.entries(rest).every(([key, value]) => s[key as keyof typeof s] === value) &&
      (vintages === undefined || sameList(s.vintages, resolveVintages(vintages, catalog))) &&
      (scenarios === undefined || sameList(s.scenarios, scenarios))
    );
  };
  const bandReason = $derived(buildPlotModel(s, explorer.data!, s.variable).bandReason);
  const historyApplies = $derived(s.view === 'published' && s.axis === 'calendar');
  const historyReason = $derived(
    historyApplies
      ? ''
      : s.view !== 'published'
        ? 'History is shown in the As published view only'
        : 'History is shown on the calendar axis only'
  );
  const wide = typeof window !== 'undefined' ? window.matchMedia('(min-width: 961px)') : null;
  let open = $state(wide?.matches ?? true);
  $effect(() => {
    const sync = () => (open = wide?.matches ?? true);
    wide?.addEventListener('change', sync);
    return () => wide?.removeEventListener('change', sync);
  });
</script>

<div class="bar primary" aria-label="Controls">
  <button
    type="button"
    class="toggle"
    aria-expanded={open}
    aria-controls="control-sections"
    onclick={() => (open = !open)}
  >
    Controls <span aria-hidden="true">{open ? '–' : '+'}</span>
  </button>
  <div id="control-sections" class="row" hidden={!open}>
    <div class="group">
      <span class="eyebrow">Quick views</span>
      <div class="quick" role="group" aria-label="Quick views">
        {#each catalog.quick_views as q (q.id)}
          <button
            type="button"
            class="text-button"
            class:on={quickActive(q.id)}
            aria-pressed={quickActive(q.id)}
            title={q.description}
            onclick={() => explorer.applyQuickView(q.id)}>{q.label}</button
          >
        {/each}
      </div>
    </div>
    <div class="group variable">
      <span class="eyebrow">Variable</span>
      <VariableCombobox
        variables={catalog.variables}
        selected={s.variable}
        onchange={(id) => explorer.focusVariable(id)}
      />
    </div>
    <div class="group">
      <span class="eyebrow">View</span>
      <SegmentedControl
        label="View"
        value={s.view}
        options={[
          {
            value: 'published',
            label: 'As published',
            title: 'The numbers exactly as the Federal Reserve published them'
          },
          {
            value: 'level',
            label: 'Level path',
            title:
              'Calculated: growth rates compounded into an index (100 = quarter before the scenario starts); level variables are shown as published'
          },
          {
            value: 'deviation',
            label: 'Deviation from baseline',
            title: 'Calculated: scenario minus the same year’s baseline'
          }
        ]}
        onchange={(view) => explorer.set({ view })}
      />
      {#if s.view === 'deviation' && variable.measure === 'growth'}
        <div class="basis">
          <SegmentedControl
            label="Basis of the deviation for growth variables"
            value={s.basis}
            options={[
              {
                value: 'growth_gap',
                label: 'Growth-rate gap (pp)',
                title: 'Difference between the scenario’s and the baseline’s annualized growth rates'
              },
              {
                value: 'level_gap',
                label: 'Level gap (%)',
                title:
                  'Percentage difference between the cumulated levels, i.e. total output lost against baseline'
              }
            ]}
            onchange={(basis) => explorer.set({ basis })}
          />
        </div>
      {/if}
    </div>
    <div class="group">
      <span class="eyebrow">Time axis</span>
      <SegmentedControl
        label="Time axis"
        value={s.axis}
        options={[
          {
            value: 'calendar',
            label: 'Calendar',
            title: 'Lines placed at their calendar quarters',
            disabled: s.view === 'level'
          },
          {
            value: 'horizon',
            label: 'Quarters since start',
            title: 'Lines aligned at the quarter each scenario starts'
          }
        ]}
        onchange={(axis) => explorer.set({ axis })}
      />
      {#if s.view === 'level'}<small
          >Level paths are indexed to each year’s own start, so they need this axis.</small
        >{/if}
    </div>
    <div class="group">
      <span class="eyebrow">Band</span>
      <Switch
        label="Min-max band"
        checked={s.band}
        disabled={!s.band && bandReason !== null}
        hint={bandReason ??
          'Shade the lowest to the highest value among all the lines drawn, behind the lines'}
        onchange={(band) => explorer.set({ band })}
      />
    </div>
  </div>
</div>
<div class="bar secondary" hidden={!open}>
  <div class="left">
    <div class="group">
      <span class="eyebrow">Scenarios</span>
      <ScenarioChips />
    </div>
    <div class="years"><VintagePicker /></div>
  </div>
  <div class="group history">
    <span class="eyebrow">History</span>
    <div class="history-controls" title={historyReason}>
      <SegmentedControl
        label="History source"
        value={s.history}
        options={[
          { value: 'off', label: 'Off', disabled: !historyApplies },
          {
            value: 'latest',
            label: 'Latest report',
            title: 'Each quarter from the newest Federal Reserve publication that reports it',
            disabled: !historyApplies
          },
          {
            value: 'realtime',
            label: 'As published then',
            title: 'Each selected year’s own history, as that report printed it',
            disabled: !historyApplies
          }
        ]}
        onchange={(history) => explorer.set({ history })}
      />
      <SegmentedControl
        label="History range"
        value={s.range}
        options={[
          {
            value: 'recent',
            label: 'Recent',
            title: 'A few years of history before the earliest selected scenario',
            disabled: !historyApplies
          },
          {
            value: 'full',
            label: 'Full history',
            title: 'Everything the Federal Reserve published for this variable',
            disabled: !historyApplies
          }
        ]}
        onchange={(range) => explorer.set({ range })}
      />
    </div>
    {#if !historyApplies}<small>{historyReason}.</small>{/if}
  </div>
</div>

<style>
  .bar {
    background: var(--panel);
    border: 1px solid var(--rule);
  }
  .primary {
    border-radius: var(--radius) var(--radius) 0 0;
    padding: 10px 14px 12px;
  }
  .secondary {
    border-top: 0;
    border-radius: 0 0 var(--radius) var(--radius);
    padding: 10px 14px 12px;
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    align-items: flex-start;
    margin-bottom: 26px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 22px;
    align-items: flex-start;
  }
  .group {
    display: grid;
    gap: 4px;
    align-content: start;
  }
  .variable {
    min-width: 250px;
  }
  .quick {
    display: flex;
    gap: 6px;
  }
  .quick .text-button.on {
    background: var(--navy);
    border-color: var(--navy);
    color: #fff;
  }
  .left {
    flex: 1 1 560px;
    min-width: 0;
    display: grid;
    gap: 12px;
  }
  .years {
    min-width: 0;
  }
  .history {
    flex: 0 1 auto;
  }
  .history-controls {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .basis {
    margin-top: 4px;
  }
  small {
    font-size: 11.5px;
    color: var(--muted);
    max-width: 280px;
  }
  .toggle {
    display: none;
    width: 100%;
    justify-content: space-between;
    border: 0;
    background: none;
    padding: 2px 0;
    font-weight: 600;
    font-size: 15px;
    color: var(--navy);
  }
  [hidden] {
    display: none;
  }
  @media (min-width: 1300px) {
    .primary {
      position: sticky;
      top: 0;
      z-index: 15;
    }
  }
  @media (max-width: 960px) {
    .toggle {
      display: flex;
    }
    .secondary {
      margin-bottom: 18px;
    }
  }
</style>
