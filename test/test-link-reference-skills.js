/**
 * Tests for tools/link-reference-skills.js
 *
 * The linker runs from npm's postprepare hook on every `npm install` in a
 * checkout, so a bug in it either leaves contributors without the reference
 * skills or damages .claude/skills/, which the BMAD and UCG installers also
 * write. These tests drive it against throwaway checkouts, never the real one.
 *
 * Fixture links fall back to junctions where directory symlinks are not allowed
 * (Windows without Developer Mode), and `active` falls back to the plain-file form
 * git uses on such checkouts, so the suite runs on both CI platforms.
 */

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { run, readActive, frontmatterName } = require('../tools/link-reference-skills.js');

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

function tmpRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'lrs-'));
  tmpRoots.push(root);
  return root;
}

/**
 * Link a directory, falling back to a junction where symlinks are not allowed.
 *
 * @param {string} target - Link target (relative targets are resolved for junctions)
 * @param {string} linkPath - Link to create
 * @returns {'symlink'|'junction'} Which kind was created
 */
function linkDir(target, linkPath) {
  try {
    fs.symlinkSync(target, linkPath, 'dir');
    return 'symlink';
  } catch {
    fs.symlinkSync(path.resolve(path.dirname(linkPath), target), linkPath, 'junction');
    return 'junction';
  }
}

/**
 * Point a group's `active` entry at a version: a real link when possible, else the
 * plain-file form a Windows checkout without core.symlinks produces.
 *
 * @param {string} root - Checkout root
 * @param {string} group - Skill group
 * @param {string} version - Version folder name
 * @param {{asFile?: boolean}} options - Force the plain-file form
 */
function setActive(root, group, version, { asFile = false } = {}) {
  const activePath = path.join(root, 'skf-skills', group, 'active');
  fs.rmSync(activePath, { force: true });
  if (!asFile) {
    try {
      fs.symlinkSync(version, activePath, 'dir');
      return;
    } catch {
      // fall through to the plain-file form
    }
  }
  fs.writeFileSync(activePath, version);
}

/**
 * Add a skill version to a fixture checkout.
 *
 * @param {string} root - Checkout root
 * @param {string} group - Skill group (also the inner folder name)
 * @param {string} version - Version folder name
 * @param {{name?: string, skillMd?: boolean}} options - Frontmatter name; skillMd false omits SKILL.md
 * @returns {string} The version's skill folder
 */
function addSkill(root, group, version, { name = group, skillMd = true } = {}) {
  const dir = path.join(root, 'skf-skills', group, version, group);
  fs.mkdirSync(dir, { recursive: true });
  if (skillMd) {
    fs.writeFileSync(path.join(dir, 'SKILL.md'), `---\nname: ${name}\ndescription: Fixture ${version}.\n---\n\n# ${name} ${version}\n`);
  }
  return dir;
}

const linkPath = (root, name) => path.join(root, '.claude', 'skills', name);
const isLink = (p) => {
  try {
    return fs.lstatSync(p).isSymbolicLink();
  } catch {
    return false;
  }
};
const resolves = (root, name) => fs.realpathSync(linkPath(root, name));

test('links each active skill under its frontmatter name', () => {
  const root = tmpRoot();
  const a = addSkill(root, 'alpha', '1.0.0');
  const b = addSkill(root, 'beta', '2.1.0');
  setActive(root, 'alpha', '1.0.0');
  setActive(root, 'beta', '2.1.0');
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(result.linked.sort(), ['alpha', 'beta']);
  assert.strictEqual(resolves(root, 'alpha'), fs.realpathSync(a));
  assert.strictEqual(resolves(root, 'beta'), fs.realpathSync(b));
  assert.ok(fs.lstatSync(linkPath(root, 'alpha')).isSymbolicLink());
});

test('a second run changes nothing', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  run({ repoRoot: root });
  const second = run({ repoRoot: root });
  assert.deepStrictEqual(second.unchanged, ['alpha']);
  assert.deepStrictEqual([...second.linked, ...second.updated, ...second.removed], []);
});

test('follows a newly activated version', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  const v2 = addSkill(root, 'alpha', '2.0.0');
  setActive(root, 'alpha', '1.0.0');
  run({ repoRoot: root });
  setActive(root, 'alpha', '2.0.0');
  const result = run({ repoRoot: root });
  assert.strictEqual(resolves(root, 'alpha'), fs.realpathSync(v2));
  // A link through a real `active` link follows on its own; a junction is re-pointed.
  assert.deepStrictEqual([...result.unchanged, ...result.updated], ['alpha']);
});

test('reads a plain-file active entry, as a Windows checkout has it', () => {
  const root = tmpRoot();
  const v = addSkill(root, 'alpha', '1.27.2');
  setActive(root, 'alpha', '1.27.2', { asFile: true });
  assert.deepStrictEqual(readActive(path.join(root, 'skf-skills', 'alpha', 'active')), { version: '1.27.2', viaLink: false });
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(result.linked, ['alpha']);
  assert.strictEqual(resolves(root, 'alpha'), fs.realpathSync(v));
});

test('leaves a real directory with the same name alone', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  fs.mkdirSync(linkPath(root, 'alpha'), { recursive: true });
  fs.writeFileSync(path.join(linkPath(root, 'alpha'), 'SKILL.md'), 'someone else');
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(
    result.skipped.map((s) => s.name),
    ['alpha'],
  );
  assert.match(result.skipped[0].reason, /is a real directory/);
  assert.strictEqual(fs.readFileSync(path.join(linkPath(root, 'alpha'), 'SKILL.md'), 'utf8'), 'someone else');
});

test('leaves a link to somewhere else alone', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  const elsewhere = fs.mkdtempSync(path.join(os.tmpdir(), 'lrs-other-'));
  tmpRoots.push(elsewhere);
  fs.mkdirSync(path.join(root, '.claude', 'skills'), { recursive: true });
  linkDir(elsewhere, linkPath(root, 'alpha'));
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(
    result.skipped.map((s) => s.name),
    ['alpha'],
  );
  assert.match(result.skipped[0].reason, /is a link to somewhere else/);
  assert.strictEqual(resolves(root, 'alpha'), fs.realpathSync(elsewhere));
});

test('removes its own link when a skill group is deleted, and nothing else', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  addSkill(root, 'beta', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  setActive(root, 'beta', '1.0.0');
  fs.mkdirSync(path.join(root, '.claude', 'skills', 'installer-owned'), { recursive: true });
  run({ repoRoot: root });
  fs.rmSync(path.join(root, 'skf-skills', 'beta'), { recursive: true, force: true });
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(result.removed, ['beta']);
  assert.ok(!fs.existsSync(linkPath(root, 'beta')));
  assert.ok(fs.existsSync(path.join(root, '.claude', 'skills', 'installer-owned')));
  assert.ok(fs.existsSync(linkPath(root, 'alpha')));
});

test('removes its link when the last skill group is deleted', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  run({ repoRoot: root });
  fs.rmSync(path.join(root, 'skf-skills', 'alpha'), { recursive: true, force: true });
  assert.deepStrictEqual(run({ repoRoot: root, check: true }).problems, ['alpha: stale link']);
  assert.deepStrictEqual(run({ repoRoot: root }).removed, ['alpha']);
  assert.ok(!fs.existsSync(linkPath(root, 'alpha')) && !isLink(linkPath(root, 'alpha')));
});

test('follows a plain-file active entry to a new version', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  const v2 = addSkill(root, 'alpha', '2.0.0');
  setActive(root, 'alpha', '1.0.0', { asFile: true });
  run({ repoRoot: root });
  setActive(root, 'alpha', '2.0.0', { asFile: true });
  assert.deepStrictEqual(run({ repoRoot: root, check: true }).problems, ['alpha: points at an inactive version']);
  assert.deepStrictEqual(run({ repoRoot: root }).updated, ['alpha']);
  assert.strictEqual(resolves(root, 'alpha'), fs.realpathSync(v2));
  assert.deepStrictEqual(run({ repoRoot: root }).unchanged, ['alpha']);
});

test('a link to a plain-file active version survives moving the checkout', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0', { asFile: true });
  run({ repoRoot: root });
  if (process.platform === 'win32' && path.isAbsolute(fs.readlinkSync(linkPath(root, 'alpha')).replace(/^\\\\\?\\/, ''))) {
    // A junction (no symlink rights) must hold an absolute path; the linker then reports it after a move.
    return;
  }
  const moved = `${root}-moved`;
  fs.renameSync(root, moved);
  tmpRoots.push(moved);
  assert.deepStrictEqual(run({ repoRoot: moved }).unchanged, ['alpha']);
});

test('refuses to write into a .claude folder that is itself a link', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  const shared = fs.mkdtempSync(path.join(os.tmpdir(), 'lrs-shared-'));
  tmpRoots.push(shared);
  linkDir(shared, path.join(root, '.claude'));
  assert.throws(() => run({ repoRoot: root }), /\.claude is a link/);
  assert.deepStrictEqual(fs.readdirSync(shared), []);
});

test('a second group declaring the same name is left out, and runs stay stable', () => {
  const root = tmpRoot();
  const a = addSkill(root, 'alpha', '1.0.0', { name: 'shared' });
  addSkill(root, 'beta', '1.0.0', { name: 'shared' });
  setActive(root, 'alpha', '1.0.0');
  setActive(root, 'beta', '1.0.0');
  const first = run({ repoRoot: root });
  assert.deepStrictEqual(first.linked, ['shared']);
  assert.match(first.skipped[0].reason, /alpha already declares that name, so skf-skills\/beta is left out/);
  const second = run({ repoRoot: root });
  assert.deepStrictEqual([second.unchanged, second.updated], [['shared'], []]);
  assert.strictEqual(resolves(root, 'shared'), fs.realpathSync(a));
});

test('ignores run-record folders, dot folders and groups without a SKILL.md', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  addSkill(root, 'broken', '1.0.0', { skillMd: false });
  setActive(root, 'broken', '1.0.0');
  fs.mkdirSync(path.join(root, 'skf-skills', '_batch'), { recursive: true });
  fs.mkdirSync(path.join(root, 'skf-skills', '.hidden'), { recursive: true });
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(result.linked, ['alpha']);
  assert.deepStrictEqual(result.ignored, ['broken']);
  assert.ok(!fs.existsSync(linkPath(root, '_batch')));
});

test('the frontmatter name wins over the folder name', () => {
  const root = tmpRoot();
  addSkill(root, 'folder-name', '1.0.0', { name: 'declared-name' });
  setActive(root, 'folder-name', '1.0.0');
  assert.strictEqual(frontmatterName(path.join(root, 'skf-skills', 'folder-name', '1.0.0', 'folder-name', 'SKILL.md')), 'declared-name');
  const result = run({ repoRoot: root });
  assert.deepStrictEqual(result.linked, ['declared-name']);
});

test('check mode reports problems and changes nothing', () => {
  const root = tmpRoot();
  addSkill(root, 'alpha', '1.0.0');
  setActive(root, 'alpha', '1.0.0');
  const before = run({ repoRoot: root, check: true });
  assert.deepStrictEqual(before.problems, ['alpha: not linked']);
  assert.ok(!fs.existsSync(path.join(root, '.claude')));
  run({ repoRoot: root });
  assert.deepStrictEqual(run({ repoRoot: root, check: true }).problems, []);
});

test('a checkout without the reference skills folder is a no-op', () => {
  const root = tmpRoot();
  const result = run({ repoRoot: root });
  assert.deepStrictEqual([...result.linked, ...result.skipped, ...result.ignored], []);
  assert.ok(!fs.existsSync(path.join(root, '.claude')));
});

for (const root of tmpRoots) {
  fs.rmSync(root, { recursive: true, force: true });
}

console.log(`\n  Passed: \u001B[32m${passed}\u001B[0m`);
console.log(`  Failed: \u001B[31m${failed}\u001B[0m`);

if (failed > 0) {
  process.exit(1);
}
console.log('\u001B[32mAll link-reference-skills tests passed!\u001B[0m');
