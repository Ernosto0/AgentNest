// i18n catalog checks (AC-X3, ADR-016). Fails the build when:
//   - the tr and en catalogs do not have identical key sets (per file),
//   - a value is not a non-empty string,
//   - {{placeholders}} differ between languages for the same key,
//   - source code calls t("some.key") with a literal key missing from the catalogs.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const localesDir = join(root, "src", "i18n", "locales");
const srcDir = join(root, "src");
const problems = [];

const languages = readdirSync(localesDir).filter((name) =>
  statSync(join(localesDir, name)).isDirectory(),
);
if (languages.length < 2) problems.push(`expected at least two languages, found: ${languages}`);

/** Flatten nested JSON into { "a.b.c": "value" }; non-string leaves are reported. */
function flatten(value, prefix, file, out) {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, file, out);
    }
  } else if (typeof value === "string") {
    out[prefix] = value;
  } else {
    problems.push(`${file}: "${prefix}" must be a string (found ${typeof value})`);
  }
  return out;
}

const placeholders = (text) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

const catalogs = {}; // language -> file -> flat keys
const files = new Set();
for (const language of languages) {
  catalogs[language] = {};
  for (const file of readdirSync(join(localesDir, language)).filter((f) => f.endsWith(".json"))) {
    files.add(file);
    const where = `${language}/${file}`;
    let parsed;
    try {
      parsed = JSON.parse(readFileSync(join(localesDir, language, file), "utf8"));
    } catch (error) {
      problems.push(`${where}: invalid JSON (${error.message})`);
      continue;
    }
    const flat = flatten(parsed, "", where, {});
    for (const [key, text] of Object.entries(flat)) {
      if (text.trim() === "") problems.push(`${where}: "${key}" is empty`);
    }
    catalogs[language][file] = flat;
  }
}

const [reference, ...others] = languages;
for (const file of files) {
  const base = catalogs[reference]?.[file];
  if (!base) {
    problems.push(`${reference}/${file} is missing`);
    continue;
  }
  for (const language of others) {
    const other = catalogs[language]?.[file];
    if (!other) {
      problems.push(`${language}/${file} is missing`);
      continue;
    }
    for (const key of Object.keys(base)) {
      if (!(key in other)) problems.push(`${language}/${file}: missing key "${key}"`);
      else if (placeholders(base[key]).join() !== placeholders(other[key]).join()) {
        problems.push(`${file}: "${key}" has different {{placeholders}} in ${reference} and ${language}`);
      }
    }
    for (const key of Object.keys(other)) {
      if (!(key in base)) problems.push(`${reference}/${file}: missing key "${key}" (present in ${language})`);
    }
  }
}

// Literal keys used in source must exist (typos would otherwise show the raw key to users).
const known = new Set(Object.values(catalogs[reference] ?? {}).flatMap((flat) => Object.keys(flat)));
const hasPluralVariant = (key) => ["_zero", "_one", "_two", "_few", "_many", "_other"].some((s) => known.has(key + s));

function* sourceFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "locales" && name !== "test") yield* sourceFiles(path);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.(test|d)\.(ts|tsx)$/.test(name)) {
      yield path;
    }
  }
}

let usages = 0;
for (const path of sourceFiles(srcDir)) {
  const text = readFileSync(path, "utf8");
  for (const match of text.matchAll(/\bt\(\s*(["'])([A-Za-z0-9_.-]+)\1/g)) {
    usages += 1;
    const key = match[2];
    if (!known.has(key) && !hasPluralVariant(key)) {
      problems.push(`${relative(root, path)}: unknown translation key "${key}"`);
    }
  }
}

if (problems.length > 0) {
  console.error(`i18n check failed (${problems.length} problem${problems.length === 1 ? "" : "s"}):`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
console.log(
  `i18n check passed: ${languages.join(", ")} | ${known.size} keys | ${usages} literal t() calls verified`,
);
