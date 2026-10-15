/**
 * Locale-aware money input (ADR-016) and display.
 *
 * `parseMoneyInput` is a port of the backend `parse_money`; both run the vectors in
 * `shared/money-cases.json`, so the two cannot drift apart. Amounts are handled as integer
 * hundredths (BigInt), never as floating point numbers.
 */

export type MoneyLocale = "tr" | "en";

export interface Money {
  /** Canonical decimal string with two decimals, e.g. "7000.00". */
  amount: string;
  currency: string;
}

export type MoneyParse =
  | { kind: "money"; money: Money }
  | { kind: "ambiguous"; alternatives: Money[]; reason: string }
  | { kind: "error"; code: string };

const CURRENCY_TOKENS: [string, string][] = [
  ["₺", "TRY"],
  ["tl", "TRY"],
  ["try", "TRY"],
  ["lira", "TRY"],
  ["turk lirasi", "TRY"],
  ["€", "EUR"],
  ["eur", "EUR"],
  ["euro", "EUR"],
  ["$", "USD"],
  ["usd", "USD"],
  ["dolar", "USD"],
  ["dollar", "USD"],
  ["dollars", "USD"],
  ["£", "GBP"],
  ["gbp", "GBP"],
  ["sterlin", "GBP"],
];
const MULTIPLIERS: [string, bigint][] = [
  ["bin", 1000n],
  ["k", 1000n],
  ["thousand", 1000n],
  ["milyon", 1_000_000n],
  ["million", 1_000_000n],
];
const GROUPING: Record<MoneyLocale, string> = { tr: ".", en: "," };

class ParseFailure extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

const ASCII_MAP: Record<string, string> = {
  ç: "c",
  ğ: "g",
  ı: "i",
  ö: "o",
  ş: "s",
  ü: "u",
  â: "a",
  î: "i",
  û: "u",
};

/** Case- and diacritic-insensitive form for loose token matching (LİRA, LIRA, lıra). */
export function asciiFold(text: string): string {
  return text
    .normalize("NFC")
    .replace(/İ/g, "i")
    .replace(/I/g, "i")
    .toLowerCase()
    .replace(/[çğıöşüâîû]/g, (c) => ASCII_MAP[c] ?? c);
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function splitTokens(text: string, defaultCurrency: string): [string, string, bigint] {
  let work = asciiFold(text.replace(/\s/g, " ")).trim();
  let currency = defaultCurrency;
  const tokens = [...CURRENCY_TOKENS].sort((a, b) => b[0].length - a[0].length);
  for (const [token, code] of tokens) {
    const symbol = token.length === 1 && !/[a-z]/.test(token);
    const pattern = new RegExp(symbol ? escapeRe(token) : `(?<![a-z])${escapeRe(token)}(?![a-z])`);
    if (pattern.test(work)) {
      currency = code;
      work = work.replace(pattern, " ");
      break;
    }
  }
  let multiplier = 1n;
  for (const [word, factor] of MULTIPLIERS) {
    const pattern = new RegExp(word.length > 1 ? `(?<![a-z])${word}(?![a-z])` : "(?<=\\d)k(?![a-z])");
    if (pattern.test(work)) {
      multiplier = factor;
      work = work.replace(pattern, " ");
      break;
    }
  }
  return [work.trim(), currency, multiplier];
}

/** A non-negative decimal as digits / 10^scale. */
interface Decimal {
  digits: bigint;
  scale: number;
}

const decimal = (integer: string, fraction = ""): Decimal => ({
  digits: BigInt(integer + fraction),
  scale: fraction.length,
});

function onlyGroupsOfThree(parts: string[]): boolean {
  const [head, ...rest] = parts;
  return (
    head !== undefined &&
    head.length >= 1 &&
    head.length <= 3 &&
    head !== "0" &&
    rest.every((group) => group.length === 3)
  );
}

function readNumber(raw: string, locale: MoneyLocale): [Decimal[], string | null] {
  let number = raw;
  if (/\d\s+\d/.test(number)) {
    const compact = number.replace(/(?<=\d)\s+(?=\d{3}(?!\d))/g, "");
    if (/\d\s+\d/.test(compact)) throw new ParseFailure("invalid_number");
    number = compact;
  }
  number = number.replace(/ /g, "");
  if (!number || !/^\d[\d.,\s]*$/.test(number)) throw new ParseFailure("invalid_number");

  const dots = number.split(".").length - 1;
  const commas = number.split(",").length - 1;
  if (dots === 0 && commas === 0) return [[decimal(number)], null];

  if (dots > 0 && commas > 0) {
    const decimalSep = number.lastIndexOf(".") > number.lastIndexOf(",") ? "." : ",";
    const groupSep = decimalSep === "." ? "," : ".";
    const at = number.lastIndexOf(decimalSep);
    const integer = number.slice(0, at);
    const fraction = number.slice(at + 1);
    const groups = integer.split(groupSep);
    if (fraction.includes(groupSep) || integer.includes(decimalSep) || !onlyGroupsOfThree(groups)) {
      throw new ParseFailure("invalid_number");
    }
    if (!fraction || fraction.length > 2) {
      throw new ParseFailure(fraction ? "too_many_decimals" : "invalid_number");
    }
    return [[decimal(groups.join(""), fraction)], null];
  }

  const separator = dots > 0 ? "." : ",";
  const parts = number.split(separator);
  if (parts.length > 2) {
    if (!onlyGroupsOfThree(parts)) throw new ParseFailure("invalid_number");
    return [[decimal(parts.join(""))], null];
  }
  const [integer = "", fraction = ""] = parts;
  if (!fraction) throw new ParseFailure("invalid_number");
  if (fraction.length <= 2) return [[decimal(integer, fraction)], null];
  if (fraction.length > 3 || integer === "0") throw new ParseFailure("too_many_decimals");
  if (!onlyGroupsOfThree([integer, fraction])) throw new ParseFailure("too_many_decimals");
  const grouped = decimal(integer + fraction);
  if (separator === GROUPING[locale]) return [[grouped], null];
  const readings = [grouped];
  const asDecimal = decimal(integer, fraction);
  if (asDecimal.digits % 10n === 0n) readings.push(asDecimal);
  return [readings, "foreign_notation"];
}

/** Scale to exactly two decimals ("7000.00"); more precision than that is an error. */
function toCents(value: Decimal, multiplier: bigint): string {
  let digits = value.digits * multiplier;
  let scale = value.scale;
  while (scale > 2) {
    if (digits % 10n !== 0n) throw new ParseFailure("too_many_decimals");
    digits /= 10n;
    scale -= 1;
  }
  while (scale < 2) {
    digits *= 10n;
    scale += 1;
  }
  const text = digits.toString().padStart(3, "0");
  return `${text.slice(0, -2)}.${text.slice(-2)}`;
}

export function parseMoneyInput(text: string, locale: MoneyLocale, defaultCurrency: string): MoneyParse {
  try {
    const [number, currency, multiplier] = splitTokens(text, defaultCurrency);
    if (!number) throw new ParseFailure("invalid_number");
    const [readings, reason] = readNumber(number, locale);
    const alternatives = readings.map((r) => ({ amount: toCents(r, multiplier), currency }));
    const [first] = alternatives;
    if (first === undefined) throw new ParseFailure("invalid_number");
    if (reason !== null) return { kind: "ambiguous", alternatives, reason };
    return { kind: "money", money: first };
  } catch (error) {
    if (error instanceof ParseFailure) return { kind: "error", code: error.code };
    return { kind: "error", code: "invalid_number" };
  }
}

/** `6000.00` TRY -> `6.000 ₺` (tr), `1200.00` EUR -> `€1,200` (en); whole amounts without decimals. */
export function formatMoneyAmount(amount: string, currency: string, locale: MoneyLocale): string {
  const [whole = "0", cents = "00"] = amount.split(".");
  const isWhole = /^0*$/.test(cents);
  const tag = locale === "tr" ? "tr-TR" : "en";
  const number = new Intl.NumberFormat(tag, {
    minimumFractionDigits: isWhole ? 0 : 2,
    maximumFractionDigits: isWhole ? 0 : 2,
  }).format(Number(isWhole ? whole : `${whole}.${cents}`));
  const symbol =
    new Intl.NumberFormat(tag, { style: "currency", currency })
      .formatToParts(0)
      .find((part) => part.type === "currency")?.value ?? currency;
  if (locale === "tr") return `${number} ${symbol}`;
  return symbol.length === 1 ? `${symbol}${number}` : `${symbol} ${number}`;
}

/** Normalise a phone number to E.164 (port of the backend `parse_phone`); null when invalid. */
export function parsePhone(text: string): string | null {
  const raw = text.trim();
  if (!raw) return null;
  const digits = raw.replace(/\D/g, "");
  let candidate: string;
  if (raw.startsWith("+")) candidate = `+${digits}`;
  else if (digits.startsWith("00")) candidate = `+${digits.slice(2)}`;
  else if (digits.startsWith("90") && digits.length === 12) candidate = `+${digits}`;
  else if (digits.startsWith("0") && digits.length === 11) candidate = `+90${digits.slice(1)}`;
  else if (digits.length === 10 && !digits.startsWith("0")) candidate = `+90${digits}`;
  else return null;
  if (!/^\+[1-9]\d{7,14}$/.test(candidate)) return null;
  if (candidate.startsWith("+90") && (candidate.length !== 13 || !"23458".includes(candidate[3] ?? ""))) {
    return null;
  }
  return candidate;
}
