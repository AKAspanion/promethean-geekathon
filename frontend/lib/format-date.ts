import { format, formatDistanceToNow } from "date-fns";

/** Parse to a valid Date or return null. */
function toSafeDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  try {
    const d = value instanceof Date ? value : new Date(value);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

/**
 * Safely format a date string/Date via date-fns `format()`.
 * Returns the fallback if the value is missing or invalid.
 */
export function formatDate(
  value: string | Date | null | undefined,
  pattern: string,
  fallback = "—",
): string {
  const d = toSafeDate(value);
  if (!d) return fallback;
  try {
    return format(d, pattern);
  } catch {
    return fallback;
  }
}

/**
 * Safely call date-fns `formatDistanceToNow()`.
 * Returns the fallback if the value is missing or invalid.
 */
export function safeFormatDistanceToNow(
  value: string | Date | null | undefined,
  options?: { addSuffix?: boolean },
  fallback = "—",
): string {
  const d = toSafeDate(value);
  if (!d) return fallback;
  try {
    return formatDistanceToNow(d, options);
  } catch {
    return fallback;
  }
}

/**
 * Safely call `toLocaleDateString()` on a date value.
 * Returns the fallback if the value is missing or invalid.
 */
export function safeLocaleDateString(
  value: string | Date | null | undefined,
  locales?: string | string[],
  options?: Intl.DateTimeFormatOptions,
  fallback = "—",
): string {
  const d = toSafeDate(value);
  if (!d) return fallback;
  try {
    return d.toLocaleDateString(locales, options);
  } catch {
    return fallback;
  }
}
