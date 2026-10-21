/** A number as people read it: whole counts, or minutes with one decimal for the median. */
export function formatValue(value: number, language: string): string {
  return value.toLocaleString(language, { maximumFractionDigits: 1 });
}
