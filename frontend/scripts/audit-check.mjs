// CI dependency audit: fails on any advisory at or above moderate severity,
// except the advisories listed in audit-allowlist.json (each with a reason and a review date).
// Usage: node scripts/audit-check.mjs   (run from frontend/)
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const LEVELS = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 }
const THRESHOLD = LEVELS.moderate

const allowlist = JSON.parse(readFileSync(new URL('./audit-allowlist.json', import.meta.url), 'utf8'))
const allowed = new Map(allowlist.map((entry) => [entry.id, entry]))

// A fixed command string (no user input); a shell is needed for npm.cmd on Windows.
const run = spawnSync('npm audit --json', { encoding: 'utf8', shell: true, maxBuffer: 64 * 1024 * 1024 })
let report
try {
  report = JSON.parse(run.stdout)
} catch {
  console.error('npm audit did not return JSON:\n' + run.stdout + run.stderr)
  process.exit(1)
}
if (report.error) {
  console.error('npm audit failed: ' + JSON.stringify(report.error))
  process.exit(1)
}

// Each vulnerable package lists its own advisories as objects in `via`;
// string entries only point at another vulnerable package, whose advisories are counted there.
const advisories = new Map()
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via) {
    if (typeof via !== 'object') continue
    const id = (via.url ?? '').split('/').pop() || String(via.source)
    advisories.set(id, { id, name: via.name, severity: via.severity, title: via.title, url: via.url })
  }
}

const blocking = []
const ignored = new Set()
for (const advisory of advisories.values()) {
  if ((LEVELS[advisory.severity] ?? 0) < THRESHOLD) continue
  if (allowed.has(advisory.id)) ignored.add(advisory.id)
  else blocking.push(advisory)
}

for (const entry of allowlist) {
  if (ignored.has(entry.id)) {
    console.log(`Ignored ${entry.id} (${entry.package}): ${entry.reason} Review by ${entry.reviewBy}.`)
  } else {
    console.log(`Allowlist entry ${entry.id} no longer matches any advisory; remove it from audit-allowlist.json.`)
  }
}
if (blocking.length > 0) {
  console.error(`\n${blocking.length} advisory(ies) at or above moderate:`)
  for (const a of blocking) console.error(`- [${a.severity}] ${a.name}: ${a.title} (${a.url})`)
  process.exit(1)
}
console.log('npm audit: no blocking advisories.')
