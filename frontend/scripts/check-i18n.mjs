// Verifies that all locale files define exactly the same set of keys.
// Plural suffixes (_one, _few, ...) are ignored: languages have different plural forms.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = join(import.meta.dirname, '..', 'src', 'i18n');
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function flatten(value, prefix = '') {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return [prefix.replace(PLURAL_SUFFIX, '')];
  }
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

const locales = Object.fromEntries(
  readdirSync(dir)
    .filter((file) => file.endsWith('.json'))
    .map((file) => [file, new Set(flatten(JSON.parse(readFileSync(join(dir, file), 'utf8'))))]),
);

const allKeys = new Set(Object.values(locales).flatMap((keys) => [...keys]));
let failed = false;
for (const [file, keys] of Object.entries(locales)) {
  const missing = [...allKeys].filter((key) => !keys.has(key)).sort();
  if (missing.length > 0) {
    failed = true;
    console.error(`${file}: missing ${missing.length} key(s):\n  ${missing.join('\n  ')}`);
  }
}

if (failed) {
  process.exit(1);
}
console.log(`i18n: ${Object.keys(locales).join(', ')} — ${allKeys.size} keys, all in sync`);
