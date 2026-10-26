// Number formatting for axes, tooltips and tables. Formatting only: stored and downloaded values
// are never rounded.
export function formatValue(value: number, maxDecimals = 2): string {
  const abs = Math.abs(value);
  const decimals = abs >= 1000 ? 0 : abs >= 100 ? Math.min(maxDecimals, 1) : maxDecimals;
  const text = value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: decimals });
  return text === '-0' ? '0' : text;
}

export const formatSigned = (value: number, maxDecimals = 2): string =>
  (value > 0 ? '+' : '') + formatValue(value, maxDecimals);

export const formatQuarter = (q: string): string => `${q.slice(0, 4)} Q${q.slice(5)}`;
