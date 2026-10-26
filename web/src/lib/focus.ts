// Which lines are bright and which are in the background. One rule for default, pins and hover.
//
// A year "owns" its scenario lines and the history up to its own start (jump-off). The active set A is
// the pinned years plus the hovered year, restricted to years that draw a line in this chart (so a pin
// on a year that does not publish a variable never blanks that chart). With no active year everything
// is bright, except latest-report history, which is graded: a stretch of history is as strong as the
// share of the reference years that already knew it, where the reference years are A, or all drawn
// years when A is empty. opacity = FADE + (1 - FADE) x share, so history only newer years know recedes
// behind the older years the eye should read.
import { qNum } from './quarters';
import type { Catalog, PlotModel } from './types';

export const FADE = 0.15;

export interface SeriesFocus {
  opacity: number;
  /** drawn on top, thicker, end-labelled: the series belongs to an active year */
  bold: boolean;
  /** pushed to the background because other years are active (no end label) */
  faded: boolean;
}

export function focusFor(
  model: PlotModel,
  catalog: Catalog,
  pins: string[],
  hovered: string | null
): Map<string, SeriesFocus> {
  const drawn = [...new Set(model.series.filter((s) => s.kind === 'scenario').map((s) => s.vintage!))];
  const active = drawn.filter((id) => pins.includes(id) || id === hovered);
  const unset = active.length === 0;
  const reference = unset ? drawn : active;
  const jumpOff = (id: string): number | null => {
    const jump = catalog.vintages.find((v) => v.id === id)?.jump_off;
    return jump ? qNum(jump) : null;
  };
  const result = new Map<string, SeriesFocus>();
  for (const s of model.series) {
    if (s.kind === 'history') {
      const knownTo = s.knownTo ?? Infinity;
      const knew = reference.filter((id) => (jumpOff(id) ?? -Infinity) >= knownTo).length;
      result.set(s.id, { opacity: FADE + (1 - FADE) * (knew / reference.length), bold: false, faded: false });
      continue;
    }
    const mine = unset || active.includes(s.vintage!);
    result.set(s.id, { opacity: mine ? 1 : FADE, bold: !unset && mine, faded: !mine });
  }
  return result;
}
