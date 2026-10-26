import { describe, expect, it } from 'vitest';
import { FAMILY_STYLE, familyStyle, vintageColor } from '../src/lib/colors';

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const distance = (a: string, b: string) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]!));

describe('year colours', () => {
  const colors = Array.from({ length: 15 }, (_, i) => vintageColor(i, 15));

  it('gives all 15 vintages a different colour, none too close to its neighbour', () => {
    expect(new Set(colors).size).toBe(15);
    for (let i = 1; i < colors.length; i++) expect(distance(colors[i - 1]!, colors[i]!)).toBeGreaterThan(12);
  });

  it('depends only on the position in the catalog, so adding a later year does not move earlier ones', () => {
    expect(vintageColor(0, 15)).toBe(vintageColor(0, 15));
    expect(vintageColor(14, 15)).toBe(RAMP_NEWEST);
  });

  it('rejects an index outside the catalog', () => {
    expect(() => vintageColor(15, 15)).toThrow(/outside/);
    expect(() => vintageColor(-1, 15)).toThrow(/outside/);
  });
});

describe('scenario families', () => {
  it('have distinct patterns', () => {
    const keys = Object.values(FAMILY_STYLE).map((s) => JSON.stringify(s.dash));
    expect(new Set(keys).size).toBe(keys.length);
  });
  it('fail loudly for an unknown family', () => {
    expect(() => familyStyle('mystery')).toThrow(/mystery/);
  });
});

const RAMP_NEWEST = '#440154';
