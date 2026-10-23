// Fails when a page asks to translate a phrase that has no row in src/i18n-dict.ts.
// Run from frontend/:  node scripts/check-i18n.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))
const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p)
    else if (/\.tsx?$/.test(name) && !name.startsWith('i18n-dict')) files.push(p)
  }
}
walk(SRC)

const patterns = [/\bt\(\s*'((?:\\.|[^'\\])*)'/gs, /\bt\(\s*"((?:\\.|[^"\\])*)"/gs, /\bt\(\s*`((?:\\.|[^`\\])*)`/gs]
const keys = new Set()
for (const f of files) {
  const text = readFileSync(f, 'utf8')
  for (const re of patterns) for (const m of text.matchAll(re)) keys.add(m[1].replace(/\\'/g, "'").replace(/\\"/g, '"'))
}
const dict = readFileSync(join(SRC, 'i18n-dict.ts'), 'utf8')
// A phrase counts when it starts a row
const missing = [...keys].filter((k) => !dict.includes(`['${k}',`) && !dict.includes(`["${k}",`))
console.log(`${keys.size} phrases, ${missing.length} without a translation`)
if (missing.length) {
  for (const k of missing) console.log('  -', k)
  process.exit(1)
}
