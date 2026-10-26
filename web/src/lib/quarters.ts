// Quarter helpers. A quarter is 'YYYYQn'; its number is year * 4 + n - 1 (consecutive quarters differ by 1).
export const qNum = (q: string): number => Number(q.slice(0, 4)) * 4 + Number(q.slice(5)) - 1;
export const qStr = (n: number): string => `${Math.floor(n / 4)}Q${(n % 4) + 1}`;
export const qAdd = (q: string, k: number): string => qStr(qNum(q) + k);
