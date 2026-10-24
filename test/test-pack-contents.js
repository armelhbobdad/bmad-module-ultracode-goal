/**
 * What the npm package ships
 *
 * `npm run test:pack` runs this file. It packs the working tree with
 * `npm pack --dry-run --json --ignore-scripts` and reads the file list npm
 * would publish, because nothing else does: `npm publish --dry-run` in
 * release.yaml exits 0 whatever the list holds, and the install smoke test
 * only runs `--version`. A pattern in .npmignore that caught a skill
 * directory would publish a package whose `update` installs no copy of that
 * skill, and preflight then refuses every run.
 *
 * Shipped:
 * - every skill the installer copies to an IDE (UCG_SKILLS in
 *   tools/cli/lib/ide-skills.js): its SKILL.md, and every tracked file under
 *   it that the installer's own filter copies, save the maintainer note
 *   .npmignore keeps out;
 * - every tracked file under tools/cli/, the npx wrapper, and the files
 *   package.json's `main` and `bin` name;
 * - every tracked file under docs/, the learning material `install` copies,
 *   save the release runbook; STABILITY.md, the public contract, among them.
 *
 * Kept out: test/, each skill's scripts/tests/, changes/, website/,
 * release-audits/, the release runbook, every maintainer tool directly under
 * tools/, root Markdown files other than README.md, Python bytecode and the
 * BMad Builder's skills/reports/.
 *
 * The tracked files come from `git ls-files`, so an untracked file in a
 * working tree changes nothing here.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const { UCG_SKILLS } = require('../tools/cli/lib/ide-skills');
const { shippedCopyFilter } = require('../tools/cli/lib/installer');
const pkg = require('../package.json');

const WRAPPER = 'tools/ucg-npx-wrapper.js';
const RUNBOOK = 'docs/_internal/RELEASING.md';
// A maintainer note inside a skill: tracked, passed by the installer's filter
// in a checkout, and kept out of the package by .npmignore.
const MAINTAINER_NOTES = new Set(['skills/ultracode-goal/assets/ucg-awareness/shaping-decision.md']);

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

/** The paths `npm pack` would publish, as npm prints them (forward slashes). */
function packedPaths() {
  const args = ['pack', '--dry-run', '--json', '--ignore-scripts'];
  // Under `npm run`, npm_execpath is npm's own CLI script: run it with this Node,
  // which needs no shell on Windows. Run directly, fall back to npm on PATH.
  const npmCli = process.env.npm_execpath;
  const result =
    npmCli && npmCli.endsWith('.js')
      ? spawnSync(process.execPath, [npmCli, ...args], { cwd: ROOT, encoding: 'utf8' })
      : spawnSync('npm', args, { cwd: ROOT, encoding: 'utf8', shell: process.platform === 'win32' });
  if (result.status !== 0) throw new Error(`npm pack --dry-run failed (exit ${result.status}): ${result.stderr}`);
  const [entry] = JSON.parse(result.stdout);
  return new Set(entry.files.map((file) => file.path));
}

function tracked(dir) {
  return execFileSync('git', ['ls-files', '-z', '--', dir], { cwd: ROOT, encoding: 'utf8' }).split('\0').filter(Boolean);
}

/** True when the installer's filter copies every directory on the way down to `file`, and the file. */
function installerCopies(file, skillDir) {
  const parts = path.posix.relative(skillDir, file).split('/');
  return parts.every((_, index) => shippedCopyFilter(path.join(ROOT, skillDir, ...parts.slice(0, index + 1))));
}

function missingFrom(packed, files) {
  const missing = files.filter((file) => !packed.has(file));
  const more = missing.length > 10 ? `, and ${missing.length - 10} more` : '';
  return missing.length === 0 ? '' : `not in the package: ${missing.slice(0, 10).join(', ')}${more}`;
}

const packed = packedPaths();
const all = [...packed];

test('every UCG skill ships with its SKILL.md', () => {
  const missing = [...UCG_SKILLS].map((name) => `skills/${name}/SKILL.md`).filter((file) => !packed.has(file));
  assert.ok(missing.length === 0, `not in the package: ${missing.join(', ')}`);
});

test('every file the installer copies from a UCG skill ships', () => {
  for (const name of UCG_SKILLS) {
    const skillDir = `skills/${name}`;
    const files = tracked(skillDir).filter((file) => installerCopies(file, skillDir) && !MAINTAINER_NOTES.has(file));
    assert.ok(files.length > 0, `${skillDir} has no tracked file`);
    const missing = missingFrom(packed, files);
    assert.ok(!missing, `${skillDir}: ${missing}`);
  }
});

test('the installer CLI, the npx wrapper and the main and bin files ship', () => {
  const files = [...tracked('tools/cli'), WRAPPER, pkg.main, ...Object.values(pkg.bin)];
  assert.ok(tracked('tools/cli').length > 0, 'tools/cli has no tracked file');
  const missing = missingFrom(packed, files);
  assert.ok(!missing, missing);
});

test('the docs ship as learning material, STABILITY.md among them, without the runbook', () => {
  const files = tracked('docs').filter((file) => file !== RUNBOOK);
  assert.ok(files.includes('docs/_internal/STABILITY.md'), 'docs/_internal/STABILITY.md is not tracked');
  const missing = missingFrom(packed, files);
  assert.ok(!missing, missing);
  assert.ok(packed.has('README.md'), 'README.md is not in the package');
});

const KEPT_OUT = [
  ['test/', (file) => file.startsWith('test/')],
  ["a skill's scripts/tests/", (file) => /(^|\/)scripts\/tests\//.test(file)],
  ['changes/', (file) => file.startsWith('changes/')],
  ['website/', (file) => file.startsWith('website/')],
  ['release-audits/', (file) => file.startsWith('release-audits/')],
  ['the release runbook', (file) => file === RUNBOOK],
  ['a maintainer note inside a skill', (file) => MAINTAINER_NOTES.has(file)],
  ['a maintainer tool under tools/', (file) => file.startsWith('tools/') && !file.startsWith('tools/cli/') && file !== WRAPPER],
  ['a root Markdown file other than README.md', (file) => /^[^/]+\.md$/.test(file) && file !== 'README.md'],
  ['Python bytecode', (file) => /(^|\/)__pycache__\//.test(file) || file.endsWith('.pyc')],
  ['skills/reports/', (file) => file.startsWith('skills/reports/')],
];

for (const [label, matches] of KEPT_OUT) {
  test(`kept out: ${label}`, () => {
    const found = all.filter((file) => matches(file));
    const more = found.length > 10 ? `, and ${found.length - 10} more` : '';
    assert.ok(found.length === 0, `in the package: ${found.slice(0, 10).join(', ')}${more}`);
  });
}

console.log(`\n${passed} passed, ${failed} failed (${packed.size} files in the package)`);
if (failed > 0) process.exit(1);
