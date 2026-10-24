/**
 * Tests for tools/validate-no-em-dash.js
 *
 * `npm run validate:em-dash` runs this tool with --strict in CI. These tests
 * pin its three checks (the clean published docs, the lines a branch adds and
 * the branch's commit messages), the generated files they skip, the context
 * index rows of the root CLAUDE.md they exempt and the base-branch fallback.
 *
 * The pure helpers are called directly; the exit-code tests drive the tool
 * against throwaway git repositories through its --root and --base flags.
 * Every em dash here is written as an escape, because this file's own added
 * lines are checked too.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'validate-no-em-dash.js');
const { hasEmDash, inCleanSet, findAddedEmDashes } = require(TOOL);

const D = '\u2014';
// Entity spellings are assembled so that this file does not trip the check it tests.
const AMP = '&';

let passed = 0;
let failed = 0;
const tmpRoots = [];

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

/** Environment for git and the tool: no CI markers, no inherited repository. */
function cleanEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of [
    'GITHUB_ACTIONS',
    'GITHUB_BASE_REF',
    'GITHUB_STEP_SUMMARY',
    'CI',
    'EM_DASH_BASE',
    'GIT_DIR',
    'GIT_INDEX_FILE',
    'GIT_WORK_TREE',
  ]) {
    delete env[key];
  }
  return {
    ...env,
    GIT_AUTHOR_NAME: 'Test',
    GIT_AUTHOR_EMAIL: 'test@example.com',
    GIT_COMMITTER_NAME: 'Test',
    GIT_COMMITTER_EMAIL: 'test@example.com',
    GIT_CONFIG_NOSYSTEM: '1',
    ...extra,
  };
}

function write(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(root, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
}

function git(root, args) {
  execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(),
    stdio: 'pipe',
  });
}

function commitAll(root, message) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message]);
}

/**
 * A repository whose `main` holds `base` files, with a `feature` branch
 * checked out on top of it.
 */
function makeRepo(base) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vned-'));
  tmpRoots.push(root);
  git(root, ['init', '-q', '-b', 'main']);
  write(root, base);
  commitAll(root, 'base');
  git(root, ['switch', '-q', '-c', 'feature']);
  return root;
}

function run(root, flags = ['--strict', '--base', 'main'], env = {}) {
  const result = spawnSync(process.execPath, [TOOL, '--root', root, ...flags], { encoding: 'utf8', env: cleanEnv(env) });
  return { status: result.status, out: result.stdout + result.stderr };
}

const BASE = {
  'skills/demo/SKILL.md': `old line ${D} left alone\n`,
  'docs/page.md': 'A clean page.\n',
  'CHANGELOG.md': '# Changelog\n',
};

// --- Pure helpers ---

test('hasEmDash: the character and its three HTML entities', () => {
  assert.strictEqual(hasEmDash(`a ${D} b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}mdash; b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}#8212; b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}#X2014; b`), true);
});

test('hasEmDash: hyphens and en dashes pass', () => {
  assert.strictEqual(hasEmDash('steps 2\u201310 - see below'), false);
});

test('hasEmDash: context index rows of CLAUDE.md are exempt', () => {
  assert.strictEqual(hasEmDash(`|IMPORTANT: tool v1.2.0 ${D} read SKILL.md before writing tool code.`, 'CLAUDE.md'), false);
  assert.strictEqual(hasEmDash(`  |IMPORTANT: x v1 ${D} read SKILL.md`, 'CLAUDE.md'), false);
  assert.strictEqual(hasEmDash(`|quick-start:{SKILL.md#quick-start} ${D} run the tool`, 'CLAUDE.md'), false);
  assert.strictEqual(hasEmDash(`|key-types:{SKILL.md#key-types} ${D} exit 0 ok, 1 failed`, 'CLAUDE.md'), false);
  assert.strictEqual(hasEmDash(`Note |IMPORTANT: x ${D} y`, 'CLAUDE.md'), true);
});

test('hasEmDash: the same row in another file or a commit message is checked', () => {
  const row = `|IMPORTANT: tool v1.2.0 ${D} read SKILL.md`;
  assert.strictEqual(hasEmDash(row), true);
  assert.strictEqual(hasEmDash(row, 'docs/reference.md'), true);
  assert.strictEqual(hasEmDash(row, 'skills/ultracode-goal/CLAUDE.md'), true);
});

test('hasEmDash: a Markdown table row is not a context index row', () => {
  assert.strictEqual(hasEmDash(`| Name | Value ${D} note |`, 'CLAUDE.md'), true);
  assert.strictEqual(hasEmDash(`| quick-start: value ${D} note |`, 'CLAUDE.md'), true);
  assert.strictEqual(hasEmDash(`|| Name ${D} note |`, 'CLAUDE.md'), true);
});

test('inCleanSet: README, docs and website, minus docs/_internal and generated files', () => {
  assert.strictEqual(inCleanSet('README.md'), true);
  assert.strictEqual(inCleanSet('docs/gate-model.md'), true);
  assert.strictEqual(inCleanSet('docs/assets/diagram.svg'), true);
  assert.strictEqual(inCleanSet('website/astro.config.mjs'), true);
  assert.strictEqual(inCleanSet('docs/_internal/RELEASING.md'), false);
  assert.strictEqual(inCleanSet('website/package-lock.json'), false);
  assert.strictEqual(inCleanSet('skills/ultracode-goal/SKILL.md'), false);
  assert.strictEqual(inCleanSet('CHANGELOG.md'), false);
  assert.strictEqual(inCleanSet('skills/README.md'), false);
});

test('findAddedEmDashes: counts new-file line numbers across hunks and skips removed lines', () => {
  const diff = [
    'diff --git a/skills/a.md b/skills/a.md',
    '--- a/skills/a.md',
    '+++ b/skills/a.md',
    '@@ -2,0 +3,2 @@',
    '+clean',
    `+dirty ${D} here`,
    '@@ -9 +10 @@',
    `-old ${D} gone`,
    `+new ${D} line`,
    'diff --git a/CHANGELOG.md b/CHANGELOG.md',
    '--- a/CHANGELOG.md',
    '+++ b/CHANGELOG.md',
    '@@ -1,0 +2 @@',
    `+generated ${D} entry`,
    'diff --git a/skf-skills/tool/1.0.0/tool/SKILL.md b/skf-skills/tool/1.0.0/tool/SKILL.md',
    '--- a/skf-skills/tool/1.0.0/tool/SKILL.md',
    '+++ b/skf-skills/tool/1.0.0/tool/SKILL.md',
    '@@ -1,0 +2 @@',
    `+generated ${D} skill`,
  ].join('\n');
  assert.deepStrictEqual(
    findAddedEmDashes(diff).map((f) => `${f.file}:${f.line}`),
    ['skills/a.md:4', 'skills/a.md:10'],
  );
});

test('findAddedEmDashes: an added line that starts with "++ " is not a file header', () => {
  const diff = [
    'diff --git a/skills/a.md b/skills/a.md',
    '--- a/skills/a.md',
    '+++ b/skills/a.md',
    '@@ -1,0 +1,2 @@',
    '+++ b/docs/x.md',
    `+dirty ${D} here`,
  ].join('\n');
  assert.deepStrictEqual(
    findAddedEmDashes(diff).map((f) => `${f.file}:${f.line}`),
    ['skills/a.md:2'],
  );
});

// --- The tool against real repositories ---

test('a branch that adds no em dash passes', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nnew clean line\n` });
  commitAll(root, 'feat: add a clean line');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
  assert.match(out, /No em dashes/);
});

test('an added line with an em dash fails, and an untouched old one does not', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nnew ${D} line\n` });
  commitAll(root, 'feat: add a line');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/demo\/SKILL\.md:2: new/);
  assert.doesNotMatch(out, /skills\/demo\/SKILL\.md:1:/);
});

test('a line after an added "++ " line is still checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/other.md': `++ b/docs/x.md\nnew ${D} line\n` });
  commitAll(root, 'feat: add a file');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/demo\/other\.md:2: new/);
});

test('an HTML entity in an added line fails', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/other.md': `a ${AMP}mdash; b\n` });
  commitAll(root, 'feat: add a file');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/demo\/other\.md:1:/);
});

test('an em dash already in the clean set fails even when the branch did not add it', () => {
  const root = makeRepo({ ...BASE, 'docs/page.md': `Title ${D} subtitle\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /docs\/page\.md:1:/);
});

test('docs/_internal is outside the clean set', () => {
  const root = makeRepo({ ...BASE, 'docs/_internal/RELEASING.md': `old ${D} note\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('the generated reference skills are not checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'skf-skills/tool/1.0.0/tool/SKILL.md': `# Tool\n\nRead this first ${D} it is generated.\n` });
  commitAll(root, 'chore: regenerate a reference skill');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('a reference-skill path outside skf-skills/ is checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/skf-skills/note.md': `copied ${D} line\n` });
  commitAll(root, 'docs: add a note');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/skf-skills\/note\.md:1:/);
});

test('the vendored engine scripts are not checked, the README beside them is', () => {
  const dir = 'skills/ultracode-goal/scripts/tests/fixtures/engine-6.12';
  const root = makeRepo(BASE);
  write(root, { [`${dir}/resolve_customization.py`]: `# upstream ${D} comment\n` });
  commitAll(root, 'test: vendor the engine');
  assert.strictEqual(run(root).status, 0);

  write(root, { [`${dir}/README.md`]: `# Engine ${D} fixture\n` });
  commitAll(root, 'test: describe the engine');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /engine-6\.12\/README\.md:1:/);
});

test('a Python file below a vendored engine folder is checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/ultracode-goal/scripts/tests/fixtures/engine/nested/x.py': `# ours ${D} line\n` });
  commitAll(root, 'test: add a helper');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /engine\/nested\/x\.py:1:/);
});

test('in CLAUDE.md the context index rows are skipped, a prose line and a table row are not', () => {
  const index = `|[tool v1.2.0]|root: .claude/skills/tool/\n|quick-start:{SKILL.md#quick-start} ${D} run the tool\n`;
  const root = makeRepo(BASE);
  write(root, { 'CLAUDE.md': index });
  commitAll(root, 'chore: track CLAUDE.md');
  assert.strictEqual(run(root).status, 0);

  write(root, { 'CLAUDE.md': `${index}\nRead the index ${D} it is short.\n\n| Library | Note ${D} |\n` });
  commitAll(root, 'docs: add notes below the index');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /CLAUDE\.md:4: Read the index/);
  assert.match(out, /CLAUDE\.md:6: \| Library/);
  assert.doesNotMatch(out, /CLAUDE\.md:2:/);
  assert.match(out, /2 em dash finding/);
});

test('outside the root CLAUDE.md a context index row is checked, in files and commit messages', () => {
  const row = `|quick-start:{SKILL.md#quick-start} ${D} run the tool\n`;
  const root = makeRepo(BASE);
  write(root, { 'notes/index.md': row, 'skills/demo/CLAUDE.md': row });
  commitAll(root, `chore: copy the index\n\n${row}`);
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /notes\/index\.md:1: \|quick-start:/);
  assert.match(out, /skills\/demo\/CLAUDE\.md:1: \|quick-start:/);
  assert.match(out, /commit [0-9a-f]{8} "chore: copy the index" \(message line 3\): \|quick-start:/);
  assert.match(out, /3 em dash finding/);
});

test('CHANGELOG.md is not checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'CHANGELOG.md': `# Changelog\n\n- fix ${D} generated entry\n` });
  commitAll(root, 'chore: changelog');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('a commit message with an em dash fails', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/new.md': 'clean\n' });
  commitAll(root, `feat: add a file\n\nWhy ${D} because.`);
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /commit [0-9a-f]{8} "feat: add a file" \(message line 3\)/);
});

test('an uncommitted working-tree line is checked too', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nwip ${D} line\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/demo\/SKILL\.md:2: wip/);
});

test('without --strict findings are reported and the exit code is 0', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nnew ${D} line\n` });
  const { status, out } = run(root, ['--base', 'main']);
  assert.strictEqual(status, 0, out);
  assert.match(out, /1 em dash finding/);
});

test('a missing base skips the diff checks locally and fails in CI', () => {
  const root = makeRepo(BASE);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nnew ${D} line\n` });
  const local = run(root, ['--strict', '--base', 'origin/nope']);
  assert.strictEqual(local.status, 0, local.out);
  assert.match(local.out, /skipped: origin\/nope not found/);
  const ci = run(root, ['--strict', '--base', 'origin/nope'], { CI: 'true' });
  assert.strictEqual(ci.status, 2, ci.out);
  assert.match(ci.out, /base origin\/nope not found/);
});

test('on a pull request the base comes from GITHUB_BASE_REF', () => {
  const root = makeRepo(BASE);
  git(root, ['update-ref', 'refs/remotes/origin/main', 'main']);
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\nnew ${D} line\n` });
  commitAll(root, 'feat: add a line');
  const { status, out } = run(root, ['--strict'], { GITHUB_BASE_REF: 'main', CI: 'true' });
  assert.strictEqual(status, 1, out);
  assert.match(out, /since origin\/main/);
});

test('on a push to main, EM_DASH_BASE set to the commit before the push checks the pushed commits', () => {
  const root = makeRepo(BASE);
  git(root, ['switch', '-q', 'main']);
  const before = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, env: cleanEnv(), encoding: 'utf8' }).trim();
  write(root, { 'skills/demo/SKILL.md': `old line ${D} left alone\npushed ${D} line\n` });
  commitAll(root, 'feat: push straight to main');
  // After the push, origin/main is the pushed commit itself: diffing against it finds nothing.
  git(root, ['update-ref', 'refs/remotes/origin/main', 'main']);
  const self = run(root, ['--strict'], { CI: 'true' });
  assert.strictEqual(self.status, 0, self.out);
  const pushed = run(root, ['--strict'], { CI: 'true', EM_DASH_BASE: before });
  assert.strictEqual(pushed.status, 1, pushed.out);
  assert.match(pushed.out, /skills\/demo\/SKILL\.md:2: pushed/);
  assert.match(pushed.out, new RegExp(`since ${before}`));
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
