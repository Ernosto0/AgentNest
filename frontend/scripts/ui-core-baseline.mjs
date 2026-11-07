// Preserve the original fixture suites and their historical artifacts.
import { readFile, writeFile, mkdir, unlink } from 'node:fs/promises';
import { spawn } from 'node:child_process';
await mkdir('../docs/ui-core-redesign/before', { recursive: true });
if (await readFile('../docs/ui-core-redesign/before/results.json', 'utf8').then(() => true).catch(() => false)) {
  throw new Error('Baseline evidence already exists. Preserve it; this script requires the original bundle.');
}
const results = [];
for (const suite of ['today', 'conversation', 'voice-delegation', 'content-detail']) {
  const source = await readFile(`scripts/ui-${suite}.mjs`, 'utf8');
  const file = `scripts/.core-before-${suite}.mjs`;
  await writeFile(file, source.replaceAll(/\.\.\/\.\.\/docs\/implementation\/phase-8\.5-sessions\/evidence\/s\d+\//g, `../../docs/ui-core-redesign/before/${suite}/`));
  const child = spawn(process.execPath, [file], { stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  const code = await new Promise(resolve => child.on('close', resolve));
  await writeFile(`../docs/ui-core-redesign/before/${suite}.log`, log);
  results.push({ suite, code });
  console.log(suite, code, log.slice(-700));
  await unlink(file);
}
await writeFile('../docs/ui-core-redesign/before/results.json', JSON.stringify(results, null, 2));
