// Encodings. Colour = publication year (one ordered ramp, fixed per vintage so a year keeps its
// colour whichever years are selected); line pattern and weight = scenario family. Neither is the
// only cue: lines are also labelled at their end, named in the tooltip and listed in the year key.
export const HISTORY_COLOR = '#3a3f4b';

/** The min-max band: one neutral grey for every scenario, behind the year lines. */
export const BAND_COLOR = '#8a94a3';

/** Dash pattern (px) and width per scenario family; the patterns differ in rhythm so they survive grey-scale printing. */
export const FAMILY_STYLE: Record<string, { dash: number[] | 'solid'; width: number; tag: string | null }> = {
  baseline: { dash: [2, 3], width: 1.5, tag: 'baseline' },
  adverse: { dash: [8, 4], width: 1.9, tag: 'adverse' },
  severely_adverse: { dash: 'solid', width: 2.4, tag: 'sev. adverse' },
  other: { dash: [10, 3, 2, 3], width: 1.9, tag: null }
};

// Newest -> oldest. A truncated viridis: perceptually ordered and safe under colour-vision deficiency.
const RAMP = ['#440154', '#3b528b', '#21918c', '#35b779', '#8fd744'];

const channel = (hex: string, i: number): number => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
const toHex = (n: number): string => Math.round(n).toString(16).padStart(2, '0');

/** Colour of a vintage from its position in the whole catalog (0 = oldest), never from the current selection. */
export function vintageColor(catalogIndex: number, catalogCount: number): string {
  if (catalogCount < 1 || catalogIndex < 0 || catalogIndex >= catalogCount)
    throw new Error(`vintage index ${catalogIndex} is outside 0..${catalogCount - 1}`);
  const age = catalogCount === 1 ? 0 : 1 - catalogIndex / (catalogCount - 1); // 0 = newest
  const scaled = age * (RAMP.length - 1);
  const k = Math.min(Math.floor(scaled), RAMP.length - 2);
  const f = scaled - k;
  const a = RAMP[k]!;
  const b = RAMP[k + 1]!;
  return '#' + [0, 1, 2].map((i) => toHex(channel(a, i) + (channel(b, i) - channel(a, i)) * f)).join('');
}

/** Pattern, width and band colour for a scenario family; every family of the catalog has one (checked when the data loads). */
export function familyStyle(family: string): (typeof FAMILY_STYLE)[string] {
  const style = FAMILY_STYLE[family];
  if (!style) throw new Error(`No line style defined for scenario family '${family}'`);
  return style;
}
