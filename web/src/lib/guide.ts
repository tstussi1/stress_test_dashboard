// The text of "How to use this dashboard", as data. `control` is the exact on-page label of the
// control an entry explains (checked against the live page by the e2e test, so the guide cannot
// drift from the controls); entries without one explain something on the chart itself.
// Formulas, definitions and data gaps are not repeated here: the Methodology tab holds them.

export interface GuideItem {
  control: string | null;
  text: string;
}

export interface GuideSection {
  id: string;
  title: string;
  items: GuideItem[];
}

export const GUIDE: GuideSection[] = [
  {
    id: 'start',
    title: 'Start here',
    items: [
      {
        control: null,
        text: '1. Pick a variable: use the Variable box, or click any small chart in the grid below the large one.'
      },
      {
        control: null,
        text: '2. Pick years and scenarios. A year is one Federal Reserve publication of scenario paths; its colour never changes. A scenario is baseline, adverse, severely adverse or another path; its line pattern never changes.'
      },
      {
        control: null,
        text: '3. Pick a view. As published shows the Federal Reserve’s numbers untouched; the other two are calculated from them.'
      }
    ]
  },
  {
    id: 'controls',
    title: 'Controls',
    items: [
      {
        control: 'Quick views',
        text: 'One-click starting points, for example every year’s severely adverse path against its own baseline.'
      },
      { control: 'Variable', text: 'Type to search the variables; they are grouped by theme.' },
      {
        control: 'As published',
        text: 'The numbers exactly as the Federal Reserve printed them, in its units.'
      },
      {
        control: 'Level path',
        text: 'Growth rates compounded into an index (100 = the quarter before the scenario starts), so you see the total fall, not the quarterly rate.'
      },
      {
        control: 'Deviation from baseline',
        text: 'The scenario minus the same year’s baseline. For growth variables you can measure the gap in growth-rate points or as a percentage gap in the level.'
      },
      { control: 'Calendar', text: 'Lines sit at their calendar quarters.' },
      {
        control: 'Quarters since start',
        text: 'Lines are aligned at the quarter each scenario starts, so different years can be compared shape against shape.'
      },
      {
        control: 'Min-max band',
        text: 'Shades the lowest to the highest value among all the lines drawn. Below the chart a strip names the band’s minimum and maximum, the year and quarter where each occurs, and two small markers show them on the chart; hovering a line also gives the band at that point.'
      },
      { control: 'Scenarios', text: 'Choose which scenarios to draw. At least one stays selected.' },
      {
        control: 'Years',
        text: 'Choose publications with the presets (All, Latest 6, Latest 3, Latest), the slider, or the chips. A CCAR tag marks the 2011 and 2012 exercises, which came before the first stress test under the Dodd-Frank Act in 2013.'
      },
      {
        control: 'Latest report',
        text: 'History drawn from the newest Federal Reserve publication that reports each quarter.'
      },
      { control: 'As published then', text: 'Each selected year’s own history, as that report printed it.' },
      { control: 'Recent', text: 'A few years of history before the earliest selected scenario.' },
      { control: 'Full history', text: 'Everything the Federal Reserve published for the variable.' }
    ]
  },
  {
    id: 'reading',
    title: 'Reading the chart',
    items: [
      {
        control: null,
        text: 'Colour is the year, line pattern is the scenario; each line is also labelled at its end.'
      },
      {
        control: null,
        text: 'Hover a line to see its year, scenario, quarter and value, and to isolate that year. Click a line or a year in the key to pin it; Esc clears the pins.'
      },
      { control: null, text: 'On the calendar axis, drag the strip under the chart to zoom.' },
      {
        control: null,
        text: 'A hollow dot marks a value the Federal Reserve itself labels an estimate. Lighter history is a quarter that the highlighted year did not yet know.'
      }
    ]
  },
  {
    id: 'taking',
    title: 'Taking numbers with you',
    items: [
      {
        control: 'Data',
        text: 'Lists, and lets you download as CSV, exactly the numbers plotted, under header lines that state every transform.'
      },
      { control: 'Summary', text: 'Peak and trough of each line, as plotted.' },
      { control: 'PNG', text: 'The chart as an image, with its source line.' },
      { control: 'Copy link', text: 'A short link that restores everything you selected.' },
      { control: 'Reset', text: 'Back to the opening view.' }
    ]
  },
  {
    id: 'grid',
    title: 'The grid below the chart',
    items: [
      {
        control: 'Domestic',
        text: 'Every domestic variable as a small chart with the same selections; click one to make it the large chart.'
      },
      {
        control: 'International',
        text: 'The same for the international variables. A year that did not publish a variable shows a message instead of a line.'
      }
    ]
  }
];

export const GUIDE_STORAGE_KEY = 'stress-test-guide-v1';
