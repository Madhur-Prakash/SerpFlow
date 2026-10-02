/** Formatting helpers. Credits, durations, ages and identifiers. */

import { formatDistanceToNowStrict, parseISO } from "date-fns";

export function credits(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value);
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "-";
  return (value * 100).toFixed(digits) + "%";
}

export function ratio(numerator: number, denominator: number): string {
  if (!denominator) return "0%";
  return percent(numerator / denominator);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 1) return "<1ms";
  if (value < 1000) return Math.round(value) + "ms";
  if (value < 60_000) return (value / 1000).toFixed(2) + "s";
  return Math.floor(value / 60_000) + "m " + Math.round((value % 60_000) / 1000) + "s";
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 60) return Math.round(value) + "s";
  if (value < 3600) return Math.round(value / 60) + "m";
  if (value < 86_400) return Math.round(value / 3600) + "h";
  return Math.round(value / 86_400) + "d";
}

export function bytes(value: number | null | undefined): string {
  if (!value) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB"];
  let index = 0;
  let size = value;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return size.toFixed(index === 0 ? 0 : 1) + " " + units[index];
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    return formatDistanceToNowStrict(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function datetime(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    return new Intl.DateTimeFormat("en", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(parseISO(iso));
  } catch {
    return iso;
  }
}

/** Shorten an identifier for a table cell without losing its prefix. */
export function shortId(id: string | null | undefined, tail = 6): string {
  if (!id) return "-";
  const [prefix, rest] = id.includes("_") ? id.split(/_(.*)/s) : ["", id];
  if (!rest) return id.slice(0, tail + 4);
  return (prefix ? prefix + "_" : "") + rest.slice(-tail);
}

export function engineLabel(engine: string): string {
  return engine.replace(/_/g, " ");
}

export function chain(engines: string[]): string {
  return engines.join("  ->  ");
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function plural(count: number, singular: string, pluralForm?: string): string {
  return count === 1 ? singular : (pluralForm ?? singular + "s");
}
