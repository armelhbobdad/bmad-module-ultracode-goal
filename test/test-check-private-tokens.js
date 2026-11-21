/**
 * Tests for tools/check-private-tokens.js
 *
 * .husky/pre-push runs this tool with --pre-push before the quality run. These
 * tests pin its silent pass without a token list, the token matching rules,
 * what a push is checked for (commit messages, added lines, added and renamed
 * paths, only the commits no remote holds yet), the main-worktree fallback
 * for a linked worktree, the --tree sweep, and the --text check of text
 * on stdin, which exits 2 without a list.
 *
 * The pure helpers are called directly; the exit-code tests drive the tool
 * against throwaway repositories, each cloned from a throwaway bare remote,
 * through its --root flag. Every token here is invented.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'check-private-tokens.js');
const { parseTokens, buildMatcher, findTokens, parseAddedLines, parsePushedRefs, checkText } = require(TOOL);

const ZERO = '0'.repeat(40);
const CLEAN_BASE = { 'README.md': 'A clean readme.\n' };
const LIST = '# invented tokens\n\nAcme Widgets\nawx\nzz-9-1\nq7-\n';

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
function cleanEnv() {
  const env = { ...process.env };
  for (const key of ['GITHUB_ACTIONS', 'CI', 'GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE', 'GIT_COMMON_DIR']) {
    delete env[key];
  }
  return {
    ...env,
    GIT_AUTHOR_NAME: 'Test',
    GIT_AUTHOR_EMAIL: 'test@example.com',
    GIT_COMMITTER_NAME: 'Test',
    GIT_COMMITTER_EMAIL: 'test@example.com',
    GIT_CONFIG_NOSYSTEM: '1',
  };
}

function git(root, args) {
  return execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(),
    encoding: 'utf8',
    stdio: 'pipe',
  });
}

function write(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(root, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
}

function commitAll(root, message) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message]);
  return git(root, ['rev-parse', 'HEAD']).trim();
}

function tmpDir(prefix) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  tmpRoots.push(dir);
  return dir;
}

/**
 * A clone of a bare remote whose main holds `base`, with a feature branch
 * checked out and, unless `list` is null, a token list git ignores.
 */
function makeClone(base = CLEAN_BASE, list = LIST) {
  const remote = tmpDir('cpt-remote-');
  git(remote, ['init', '-q', '--bare', '-b', 'main']);
  const root = tmpDir('cpt-clone-');
  git(root, ['clone', '-q', remote, '.']);
  write(root, base);
  commitAll(root, 'base');
  git(root, ['push', '-q', 'origin', 'main']);
  git(root, ['switch', '-q', '-c', 'feature']);
  fs.appendFileSync(path.join(root, '.git', 'info', 'exclude'), '.private-tokens\n');
  if (list !== null) write(root, { '.private-tokens': list });
  return root;
}

/** Run the tool as the hook would for a push of the current branch. */
function prePush(root, extra = [], refs = null) {
  const head = git(root, ['rev-parse', 'HEAD']).trim();
  const input = refs ?? `refs/heads/feature ${head} refs/heads/feature ${ZERO}\n`;
  const result = spawnSync(process.execPath, [TOOL, '--root', root, '--pre-push', ...extra], {
    encoding: 'utf8',
    env: cleanEnv(),
    input,
  });
  return { status: result.status, out: result.stdout + result.stderr };
}

function tree(root, extra = []) {
  const result = spawnSync(process.execPath, [TOOL, '--root', root, '--tree', ...extra], { encoding: 'utf8', env: cleanEnv() });
  return { status: result.status, out: result.stdout + result.stderr };
}

/** Run the tool on a text given on stdin, as before posting it on GitHub. */
function text(root, input, extra = []) {
  const result = spawnSync(process.execPath, [TOOL, '--root', root, '--text', ...extra], {
    encoding: 'utf8',
    env: cleanEnv(),
    input,
  });
  return { status: result.status, out: result.stdout + result.stderr };
}

// --- Pure helpers ---

test('parseTokens: skips blank lines and comments, trims and deduplicates', () => {
  assert.deepStrictEqual(parseTokens('# c\n\n  awx  \nawx\r\nAcme Widgets\n#x\n'), ['awx', 'Acme Widgets']);
  assert.deepStrictEqual(parseTokens(''), []);
});

test('findTokens: ignores case and returns the token as listed', () => {
  const tokens = parseTokens(LIST);
  const matcher = buildMatcher(tokens);
  assert.deepStrictEqual(findTokens('The ACME widgets team', matcher, tokens), ['Acme Widgets']);
  assert.deepStrictEqual(findTokens('ran AWX twice', matcher, tokens), ['awx']);
});

test('findTokens: a letter or digit next to a token that ends in one blocks the match', () => {
  const tokens = parseTokens(LIST);
  const matcher = buildMatcher(tokens);
  assert.deepStrictEqual(findTokens('awx-1 x_awx (awx) awx.', matcher, tokens), ['awx']);
  assert.deepStrictEqual(findTokens('awxs sawx awx1 1awx', matcher, tokens), []);
  assert.deepStrictEqual(findTokens('story zz-9-1-login', matcher, tokens), ['zz-9-1']);
  assert.deepStrictEqual(findTokens('zz-9-10 xzz-9-1 zz-9-1a', matcher, tokens), []);
});

test('findTokens: a token ending in punctuation matches whatever follows it', () => {
  const tokens = parseTokens(LIST);
  const matcher = buildMatcher(tokens);
  assert.deepStrictEqual(findTokens('key q7-12-3', matcher, tokens), ['q7-']);
  assert.deepStrictEqual(findTokens('aq7-12', matcher, tokens), []);
});

test('findTokens: regex characters in a token are literal, and an empty list finds nothing', () => {
  const tokens = ['a.b', 'c+'];
  const matcher = buildMatcher(tokens);
  assert.deepStrictEqual(findTokens('axb c', matcher, tokens), []);
  assert.deepStrictEqual(findTokens('a.b and c+d', matcher, tokens), ['a.b', 'c+']);
  assert.strictEqual(buildMatcher([]), null);
  assert.deepStrictEqual(findTokens('anything', null, []), []);
});

test('parseAddedLines: added lines, added paths and renames, not hunk lines that look like headers', () => {
  const log = [
    '\u001Eabc123',
    '',
    'diff --git a/x.md b/x.md',
    '--- a/x.md',
    '+++ b/x.md',
    '@@ -1,0 +2,2 @@',
    '+first',
    '+++ inside a hunk',
    'diff --git a/old.md b/new.md',
    'similarity index 100%',
    'rename from old.md',
    'rename to new.md',
  ].join('\n');
  assert.deepStrictEqual(parseAddedLines(log), [
    { commit: 'abc123', file: 'x.md', line: null, text: 'x.md' },
    { commit: 'abc123', file: 'x.md', line: 2, text: 'first' },
    { commit: 'abc123', file: 'x.md', line: 3, text: '++ inside a hunk' },
    { commit: 'abc123', file: 'new.md', line: null, text: 'new.md' },
  ]);
});

test('parsePushedRefs: skips deletions and reads a new branch as having no remote tip', () => {
  const sha = 'a'.repeat(40);
  assert.deepStrictEqual(parsePushedRefs(`refs/heads/x ${sha} refs/heads/x ${ZERO}\n(delete) ${ZERO} refs/heads/y ${sha}\n\n`), [
    { localRef: 'refs/heads/x', localSha: sha, remoteRef: 'refs/heads/x', remoteSha: null },
  ]);
});

// --- The hook ---

test('without a token list the check passes silently', () => {
  const root = makeClone(undefined, null);
  write(root, { 'notes.md': 'Acme Widgets awx\n' });
  commitAll(root, 'docs: awx notes');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 0, out);
  assert.strictEqual(out, '');
});

test('a clean push passes and says what it checked', () => {
  const root = makeClone();
  write(root, { 'notes.md': 'Nothing private here.\n' });
  commitAll(root, 'docs: add notes');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 0, out);
  assert.match(out, /no token from \.private-tokens in 1 new commit/);
});

test('a token in a commit message fails the push', () => {
  const root = makeClone();
  write(root, { 'notes.md': 'Nothing private here.\n' });
  const sha = commitAll(root, 'fix: handle a case\n\nSeen on the ACME WIDGETS run.');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, new RegExp(`commit ${sha.slice(0, 8)}, message line 3: Acme Widgets`));
});

test('a token on an added line fails the push with its file and line', () => {
  const root = makeClone();
  write(root, { 'skills/demo/test.py': 'a = 1\nkey = "zz-9-1-login"\n' });
  commitAll(root, 'test: add a case');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skills\/demo\/test\.py:2, commit \w{8}: zz-9-1/);
});

test('a token in an added or renamed path fails the push', () => {
  const root = makeClone({ 'memory/plain-note.md': 'body\n' });
  write(root, { 'memory/awx-note.md': 'body two\n' });
  git(root, ['mv', 'memory/plain-note.md', 'memory/q7-note.md']);
  commitAll(root, 'chore: notes');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /memory\/awx-note\.md \(file path\), commit \w{8}: awx/);
  assert.match(out, /memory\/q7-note\.md \(file path\), commit \w{8}: q7-/);
});

test('removing a token passes: only added lines count', () => {
  const root = makeClone({ 'docs/page.md': 'Example key zz-9-1.\n' });
  write(root, { 'docs/page.md': 'Example key ab-1-2.\n' });
  commitAll(root, 'docs: use an invented key');
  const { status, out } = prePush(root);
  assert.strictEqual(status, 0, out);
});

test('commits a remote already holds are not checked again', () => {
  const root = makeClone();
  write(root, { 'old.md': 'awx\n' });
  commitAll(root, 'docs: awx was pushed long ago');
  git(root, ['push', '-q', 'origin', 'feature']);
  write(root, { 'new.md': 'clean\n' });
  commitAll(root, 'docs: clean follow-up');
  const head = git(root, ['rev-parse', 'HEAD']).trim();
  const remoteTip = git(root, ['rev-parse', 'origin/feature']).trim();
  const { status, out } = prePush(root, [], `refs/heads/feature ${head} refs/heads/feature ${remoteTip}\n`);
  assert.strictEqual(status, 0, out);
  assert.match(out, /in 1 new commit/);
});

test('a merge commit message is checked, its diff is not checked twice', () => {
  const root = makeClone();
  git(root, ['switch', '-q', '-c', 'side']);
  write(root, { 'side.md': 'clean\n' });
  commitAll(root, 'docs: side');
  git(root, ['switch', '-q', 'feature']);
  write(root, { 'main.md': 'clean\n' });
  commitAll(root, 'docs: feature');
  git(root, ['merge', '-q', '--no-ff', 'side', '-m', 'Merge side for awx']);
  const { status, out } = prePush(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /message line 1: awx/);
});

test('a token in the pushed branch name fails the push, even with clean commits', () => {
  const root = makeClone();
  git(root, ['switch', '-q', '-c', 'fix/awx-run']);
  write(root, { 'notes.md': 'clean\n' });
  const head = commitAll(root, 'docs: clean');
  const { status, out } = prePush(root, [], `refs/heads/fix/awx-run ${head} refs/heads/fix/awx-run ${ZERO}\n`);
  assert.strictEqual(status, 1, out);
  assert.match(out, /ref name refs\/heads\/fix\/awx-run: awx/);
});

test('a token in a pushed annotated tag message fails the push', () => {
  const root = makeClone();
  git(root, ['switch', '-q', 'main']);
  git(root, ['tag', '-a', 'v1.0.0', '-m', 'Release\n\nFirst cut for Acme Widgets.']);
  const tagSha = git(root, ['rev-parse', 'v1.0.0']).trim();
  const { status, out } = prePush(root, [], `refs/tags/v1.0.0 ${tagSha} refs/tags/v1.0.0 ${ZERO}\n`);
  assert.strictEqual(status, 1, out);
  assert.match(out, /tag refs\/tags\/v1\.0\.0, message line 3: Acme Widgets/);
});

test('a branch deletion passes', () => {
  const root = makeClone();
  const { status, out } = prePush(root, [], `(delete) ${ZERO} refs/heads/feature ${'b'.repeat(40)}\n`);
  assert.strictEqual(status, 0, out);
});

test('a push from a linked worktree uses the list at the main worktree root', () => {
  const root = makeClone();
  const linked = path.join(tmpDir('cpt-wt-'), 'wt');
  git(root, ['worktree', 'add', '-q', '-b', 'wt-branch', linked]);
  write(linked, { 'wt.md': 'awx\n' });
  commitAll(linked, 'docs: from a worktree');
  const head = git(linked, ['rev-parse', 'HEAD']).trim();
  const { status, out } = prePush(linked, [], `refs/heads/wt-branch ${head} refs/heads/wt-branch ${ZERO}\n`);
  assert.strictEqual(status, 1, out);
  assert.match(out, /wt\.md:1, commit \w{8}: awx/);
});

test('--list names another list, and a named list that is missing is an error', () => {
  const root = makeClone(undefined, null);
  write(root, { 'notes.md': 'plain\n' });
  commitAll(root, 'docs: mention qqq');
  const other = path.join(tmpDir('cpt-list-'), 'tokens.txt');
  fs.writeFileSync(other, 'qqq\n');
  const named = prePush(root, ['--list', other]);
  assert.strictEqual(named.status, 1, named.out);
  assert.match(named.out, /message line 1: qqq/);
  const missing = prePush(root, ['--list', path.join(path.dirname(other), 'nope.txt')]);
  assert.strictEqual(missing.status, 2, missing.out);
});

// --- The sweep ---

test('--tree finds tokens in tracked files and paths, not in untracked files', () => {
  const root = makeClone({ 'README.md': 'clean\n', 'docs/awx.md': 'line one\nmeets Acme Widgets\n' });
  write(root, { 'untracked.md': 'awx\n' });
  const { status, out } = tree(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /docs\/awx\.md \(file path\): awx/);
  assert.match(out, /docs\/awx\.md:2: Acme Widgets/);
  assert.doesNotMatch(out, /untracked/);
  const clean = tree(makeClone());
  assert.strictEqual(clean.status, 0, clean.out);
  assert.match(clean.out, /tracked file/);
});

// --- The text check ---

test('checkText: finding lines name stdin and the line, like --tree; a final newline adds no line', () => {
  const tokens = parseTokens(LIST);
  const matcher = buildMatcher(tokens);
  assert.deepStrictEqual(checkText('clean\r\nran AWX on zz-9-1\nAcme widgets\n', matcher, tokens), {
    findings: ['stdin:2: awx', 'stdin:2: zz-9-1', 'stdin:3: Acme Widgets'],
    lines: 3,
  });
  assert.deepStrictEqual(checkText('', matcher, tokens), { findings: [], lines: 0 });
  assert.deepStrictEqual(checkText('one\n', matcher, tokens), { findings: [], lines: 1 });
});

test('--text passes clean text on stdin and says what it checked', () => {
  const root = makeClone();
  const { status, out } = text(root, 'Title\n\nA body with an invented key ex-51-2.\n');
  assert.strictEqual(status, 0, out);
  assert.match(out, /no token from \.private-tokens in 3 line\(s\) of standard input/);
});

test('--text fails on a token with the --tree finding lines and exits 1', () => {
  const root = makeClone({ 'docs/page.md': 'line one\nmeets Acme Widgets\n' });
  const { status, out } = text(root, 'line one\nmeets Acme Widgets\nkey q7-12\n');
  assert.strictEqual(status, 1, out);
  assert.match(out, /^ {2}stdin:2: Acme Widgets$/m);
  assert.match(out, /^ {2}stdin:3: q7-$/m);
  assert.match(out, /Reword each one/);
  // The same text in a tracked file gives the same finding line, with the file in place of stdin.
  const swept = tree(root);
  assert.match(swept.out, /^ {2}docs\/page\.md:2: Acme Widgets$/m);
});

test('--text exits 2 when no token list is found, where the other modes pass silently', () => {
  const root = makeClone(undefined, null);
  const { status, out } = text(root, 'Acme Widgets\n');
  assert.strictEqual(status, 2, out);
  assert.match(out, /no \.private-tokens list found/);
  const missing = text(root, 'plain\n', ['--list', path.join(root, 'nope.txt')]);
  assert.strictEqual(missing.status, 2, missing.out);
  assert.match(missing.out, /token list .*nope\.txt not found/);
});

test('--text from a linked worktree uses the list at the main worktree root', () => {
  const root = makeClone();
  const linked = path.join(tmpDir('cpt-wt-'), 'wt');
  git(root, ['worktree', 'add', '-q', '-b', 'wt-text', linked]);
  const { status, out } = text(linked, 'ran awx\n');
  assert.strictEqual(status, 1, out);
  assert.match(out, /stdin:1: awx/);
});

test('without a mode the tool prints its usage and exits 2', () => {
  const result = spawnSync(process.execPath, [TOOL], { encoding: 'utf8', env: cleanEnv() });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr, /usage/);
});

test('more than one mode is a usage error, so --text never falls back to another mode', () => {
  const root = makeClone();
  const result = spawnSync(process.execPath, [TOOL, '--root', root, '--tree', '--text'], {
    encoding: 'utf8',
    env: cleanEnv(),
    input: 'awx\n',
  });
  assert.strictEqual(result.status, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /usage/);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
