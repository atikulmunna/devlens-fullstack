export function plural(count: number, word: string): string {
  return `${count.toLocaleString("en-US")} ${word}${count === 1 ? "" : "s"}`;
}

export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

// "the past year" for a 365-day window, otherwise its length in days.
export function windowLabel(days: number | null | undefined): string {
  if (!days || days === 365) {
    return "the past year";
  }
  return `the past ${plural(days, "day")}`;
}
