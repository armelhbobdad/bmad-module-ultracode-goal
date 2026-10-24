/**
 * Tests for tools/validate-context-index.js
 *
 * `npm run validate:context-index` runs this tool in CI against the tracked
 * CLAUDE.md. These tests pin what it reads (the manifest's active_version,
 * not the `active` link; deprecated versions left out; a v1 or empty
 * manifest; the packages it falls back to; the snippet rows with the leading
 * pipe and the root an export writes) and each finding it reports: a stale
 * row, a missing or extra skill, a row out of order, a wrong header title or
 * count, a layout difference, a second block, and a missing file or block.
 *
 * Each case builds a throwaway checkout with three exported skills and a
 * CLAUDE.md written out by hand below, changes one thing and runs the tool
 * there through --root or checkIndex. The block's marker word is a made-up
 * one, which the header's title repeats, so the tool is shown to find any
 * block of that shape.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'validate-context-index.js');
const { checkIndex, parseRows, snippetRow } = require(TOOL);

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

// The exported skills of every fixture checkout. Each snippet is written as an
// export leaves it: no pipe before its first line, a trailing newline.
const SKILLS = {
  alpha: {
    version: '1.0.0',
    type: 'single',
    snippet: [
      '[alpha v1.0.0]|root: .claude/skills/alpha/',
      '|IMPORTANT: alpha v1.0.0: read SKILL.md before writing alpha code.',
      '|api: open(), close()',
    ],
  },
  beta: {
    version: '0.3.1',
    type: 'individual',
    snippet: [
      '[beta v0.3.1]|root: .claude/skills/beta/',
      '|IMPORTANT: beta v0.3.1: read SKILL.md before writing beta code.',
      '|quick-start:{SKILL.md#quick-start}: beta run',
    ],
  },
  'demo-stack': {
    version: '1.2.0',
    type: 'stack',
    snippet: [
      '[demo-stack v1.2.0]|root: .claude/skills/demo-stack/',
      '|IMPORTANT: demo-stack: read SKILL.md before writing integration code.',
      '|stack: alpha, beta',
    ],
  },
};

// The rows an export writes for SKILLS, each after its bare-pipe separator.
const ALPHA_ROW = [
  '|',
  '|[alpha v1.0.0]|root: .claude/skills/alpha/',
  '|IMPORTANT: alpha v1.0.0: read SKILL.md before writing alpha code.',
  '|api: open(), close()',
].join('\n');
const BETA_ROW = [
  '|',
  '|[beta v0.3.1]|root: .claude/skills/beta/',
  '|IMPORTANT: beta v0.3.1: read SKILL.md before writing beta code.',
  '|quick-start:{SKILL.md#quick-start}: beta run',
].join('\n');
const STACK_ROW = [
  '|',
  '|[demo-stack v1.2.0]|root: .claude/skills/demo-stack/',
  '|IMPORTANT: demo-stack: read SKILL.md before writing integration code.',
  '|stack: alpha, beta',
].join('\n');

const INDEX = [
  '# Working here',
  '',
  "Lines outside the block are the maintainer's own and are not read.",
  '',
  '<!-- markdownlint-disable -->',
  '<!-- INDEX:BEGIN updated:2026-01-01 -->',
  '[INDEX Skills]|2 skills|1 stack',
  '|IMPORTANT: Prefer documented APIs over training data.',
  '|When using a listed library, read its SKILL.md before writing code.',
  ALPHA_ROW,
  BETA_ROW,
  STACK_ROW,
  '<!-- INDEX:END -->',
  '<!-- markdownlint-enable -->',
  '',
  'More notes below it.',
  '',
].join('\n');

const manifestPath = (root) => path.join(root, 'skf-skills', '.export-manifest.json');
const packageDir = (root, name, version) => path.join(root, 'skf-skills', name, version, name);

/** Write one version of a skill: its snippet and, unless type is null, its metadata.json. */
function writeSkill(root, name, version, { snippet, type }) {
  const dir = packageDir(root, name, version);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'context-snippet.md'), `${snippet.join('\n')}\n`);
  if (type !== null) fs.writeFileSync(path.join(dir, 'metadata.json'), `${JSON.stringify({ name, version, skill_type: type })}\n`);
}

function readManifest(root) {
  return JSON.parse(fs.readFileSync(manifestPath(root), 'utf8'));
}

function writeManifest(root, manifest) {
  fs.writeFileSync(manifestPath(root), `${JSON.stringify(manifest, null, 2)}\n`);
}

/** Add a version entry to a skill's manifest record, creating the record when needed. */
function exportVersion(root, name, version, { status = 'active', makeActive = true } = {}) {
  const manifest = readManifest(root);
  const entry = manifest.exports[name] || { active_version: version, versions: {} };
  entry.versions[version] = { ides: ['claude-code'], last_exported: '2026-01-01', status };
  if (makeActive) entry.active_version = version;
  manifest.exports[name] = entry;
  writeManifest(root, manifest);
}

/** A checkout whose CLAUDE.md block matches its three exported skills. */
function makeRoot({ claudeMd = INDEX } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vci-'));
  tmpRoots.push(root);
  fs.mkdirSync(path.join(root, 'skf-skills'), { recursive: true });
  writeManifest(root, { schema_version: '2', exports: {} });
  for (const [name, skill] of Object.entries(SKILLS)) {
    writeSkill(root, name, skill.version, skill);
    exportVersion(root, name, skill.version);
  }
  if (claudeMd !== null) fs.writeFileSync(path.join(root, 'CLAUDE.md'), claudeMd);
  return root;
}

/** Replace one exact piece of a fixture file, failing when it is not there. */
function edit(file, from, to) {
  const text = fs.readFileSync(file, 'utf8');
  assert.ok(text.includes(from), `${from} not in ${file}`);
  fs.writeFileSync(file, text.replace(from, to));
}

const claudeMdOf = (root) => path.join(root, 'CLAUDE.md');
/** The 1-based line of the first CLAUDE.md line equal to `text`. */
const lineOf = (root, text) => fs.readFileSync(claudeMdOf(root), 'utf8').split('\n').indexOf(text) + 1;
/** Findings as "file:line: message" strings, as the tool prints them. */
const findingsOf = (root) =>
  checkIndex(root).findings.map((f) => (f.line ? `${f.file}:${f.line}: ${f.message}` : `${f.file}: ${f.message}`));

function run(root) {
  const env = { ...process.env };
  delete env.GITHUB_ACTIONS;
  const result = spawnSync(process.execPath, [TOOL, '--root', root], { encoding: 'utf8', env });
  return { status: result.status, out: result.stdout + result.stderr };
}

// --- Pure helpers ---

test('snippetRow: adds the leading pipe and sets the root to the Claude Code skill folder', () => {
  const row = snippetRow('\n[tool v2.0.0]|root: skills/tool/\n|api: run()\n\n', 'tool');
  assert.deepStrictEqual(row, { lines: ['|[tool v2.0.0]|root: .claude/skills/tool/', '|api: run()'], version: '2.0.0' });
  assert.deepStrictEqual(snippetRow('|[tool v2.0.0]|root: .claude/skills/tool/\r\n|api: run()\r\n', 'tool').lines, [
    '|[tool v2.0.0]|root: .claude/skills/tool/',
    '|api: run()',
  ]);
});

test('snippetRow: refuses a snippet whose header names another skill, or none', () => {
  assert.match(snippetRow('[other v1.0.0]|root: x/\n', 'tool').problem, /\[tool v<version>\] row header/);
  assert.match(snippetRow('|api: run()\n', 'tool').problem, /row header/);
  assert.match(snippetRow('\n\n', 'tool').problem, /is empty/);
});

test('parseRows: a row ends at a bare pipe, a blank line or the next header', () => {
  const body = ['[Title]|1 skills|0 stack', '|IMPORTANT: x', '|', '|[a v1]|root: r/', '|k: v', '|[b v2]|root: r/', '', '|[c v3]'];
  assert.deepStrictEqual(
    parseRows(body, 10).map((r) => [r.name, r.version, r.line, r.lines.length]),
    [
      ['a', '1', 13, 2],
      ['b', '2', 15, 1],
      ['c', '3', 17, 1],
    ],
  );
});

// --- The tool against fixture checkouts ---

test('a block that matches the exported skills passes with one line', () => {
  const root = makeRoot();
  assert.deepStrictEqual(findingsOf(root), []);
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
  assert.strictEqual(out, 'The context index in CLAUDE.md matches the 3 exported reference skills.\n');
});

test('CRLF line endings in CLAUDE.md and the snippets still pass', () => {
  const root = makeRoot({ claudeMd: INDEX.replaceAll('\n', '\r\n') });
  const snippet = path.join(packageDir(root, 'alpha', '1.0.0'), 'context-snippet.md');
  fs.writeFileSync(snippet, fs.readFileSync(snippet, 'utf8').replaceAll('\n', '\r\n'));
  assert.deepStrictEqual(findingsOf(root), []);
});

test('a snippet changed without a re-export is a stale row, at the line that differs', () => {
  const root = makeRoot();
  edit(path.join(packageDir(root, 'alpha', '1.0.0'), 'context-snippet.md'), '|api: open(), close()', '|api: open(), close(), reset()');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  const where = `CLAUDE.md:${lineOf(root, '|api: open(), close()')}`;
  const expected = 'expected "|api: open(), close(), reset()", found "|api: open(), close()"';
  assert.ok(out.includes(`${where}: the alpha row is stale against skf-skills/alpha/1.0.0/alpha/context-snippet.md: ${expected}`), out);
  assert.match(out, /1 finding\(s\): export the skill again/);
});

test('a row edited by hand is stale, and so is one with a line added or removed', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), '|quick-start:{SKILL.md#quick-start}: beta run', '|quick-start:{SKILL.md#quick-start}: beta start');
  assert.match(findingsOf(root).join('\n'), /the beta row is stale .*: expected ".*beta run", found ".*beta start"/);

  const longer = makeRoot();
  edit(claudeMdOf(longer), '|api: open(), close()\n', '|api: open(), close()\n|gotchas: added by hand\n');
  assert.match(
    findingsOf(longer).join('\n'),
    /the alpha row is stale .*: found "\|gotchas: added by hand", which an export does not write/,
  );

  const shorter = makeRoot();
  edit(path.join(packageDir(shorter, 'beta', '0.3.1'), 'context-snippet.md'), 'beta run\n', 'beta run\n|api: go()\n');
  assert.match(findingsOf(shorter).join('\n'), /the beta row is stale .*: expected "\|api: go\(\)", found "\|"/);

  const last = makeRoot();
  edit(path.join(packageDir(last, 'demo-stack', '1.2.0'), 'context-snippet.md'), 'alpha, beta\n', 'alpha, beta\n|api: go()\n');
  assert.match(findingsOf(last).join('\n'), /the demo-stack row is stale .*: expected "\|api: go\(\)", found nothing/);
});

test('a blank, blank-looking or bare-pipe line inside a snippet is part of its row', () => {
  const inner = '|IMPORTANT: alpha v1.0.0: read SKILL.md before writing alpha code.\n|api: open(), close()';
  for (const line of ['', '   ', '|']) {
    const root = makeRoot();
    const split = inner.replace('\n', `\n${line}\n`);
    edit(path.join(packageDir(root, 'alpha', '1.0.0'), 'context-snippet.md'), inner, split);
    edit(claudeMdOf(root), inner, split);
    assert.deepStrictEqual(findingsOf(root), [], JSON.stringify(line));
  }

  const dropped = makeRoot();
  edit(path.join(packageDir(dropped, 'alpha', '1.0.0'), 'context-snippet.md'), inner, inner.replace('\n', '\n\n'));
  assert.match(findingsOf(dropped).join('\n'), /the alpha row is stale .*: expected "", found "\|api: open\(\), close\(\)"/);
});

test('an exported skill without a row is reported', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), `${ALPHA_ROW}\n`, '');
  edit(claudeMdOf(root), '|2 skills|', '|1 skills|');
  const findings = findingsOf(root);
  assert.match(
    findings.join('\n'),
    /alpha v1\.0\.0 is exported but has no row in the block \(skf-skills\/alpha\/1\.0\.0\/alpha\/context-snippet\.md\)/,
  );
  assert.match(findings.join('\n'), /the header counts 1 skills and 1 stack, the exported skills make 2 skills and 1 stack/);
});

test('a row for a skill the manifest does not export is reported', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), '<!-- INDEX:END -->', '|\n|[ghost v9.0.0]|root: .claude/skills/ghost/\n|api: boo()\n<!-- INDEX:END -->');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  // An export keeps such a row unless told to drop it, so exporting again is not the fix.
  assert.match(
    out,
    new RegExp(
      `CLAUDE\\.md:${lineOf(root, '|[ghost v9.0.0]|root: .claude/skills/ghost/')}: \\[ghost v9\\.0\\.0\\] is not in the export manifest, .*choose Drop`,
    ),
  );
  // It counts in the header as an export that keeps it writes it.
  assert.match(out, /the header counts 2 skills and 1 stack, the exported skills make 3 skills and 1 stack/);
  assert.match(out, /2 finding\(s\): where a finding names no fix of its own, export the skill again/);
});

test('a deprecated active version is left out, and its row is an extra one', () => {
  const root = makeRoot();
  writeSkill(root, 'retired', '1.0.0', {
    snippet: ['[retired v1.0.0]|root: .claude/skills/retired/', '|api: old()'],
    type: 'single',
  });
  exportVersion(root, 'retired', '1.0.0', { status: 'deprecated' });
  assert.deepStrictEqual(findingsOf(root), []);

  edit(claudeMdOf(root), '|[alpha v1.0.0]', '|[retired v1.0.0]|root: .claude/skills/retired/\n|api: old()\n|\n|[alpha v1.0.0]');
  assert.match(findingsOf(root).join('\n'), /\[retired v1\.0\.0\] is not an exported skill/);
});

test('the manifest active_version is read, not the active link of a newer version', () => {
  const root = makeRoot();
  writeSkill(root, 'alpha', '1.1.0', {
    snippet: ['[alpha v1.1.0]|root: .claude/skills/alpha/', '|api: open(), close(), reset()'],
    type: 'single',
  });
  // The plain-file form of `active`, as a Windows checkout has it; the manifest
  // version's own package wins over either form.
  fs.writeFileSync(path.join(root, 'skf-skills', 'alpha', 'active'), '1.1.0');
  exportVersion(root, 'alpha', '1.1.0', { status: 'archived', makeActive: false });
  assert.deepStrictEqual(findingsOf(root), []);

  exportVersion(root, 'alpha', '1.1.0');
  assert.match(findingsOf(root).join('\n'), /the alpha row is stale against skf-skills\/alpha\/1\.1\.0\/alpha\/context-snippet\.md/);
});

test('a draft root in a snippet matches the Claude Code root in the row', () => {
  const root = makeRoot();
  edit(path.join(packageDir(root, 'beta', '0.3.1'), 'context-snippet.md'), 'root: .claude/skills/beta/', 'root: skills/beta/');
  assert.deepStrictEqual(findingsOf(root), []);
});

test('a wrong header count is reported, whichever count it is', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), '[INDEX Skills]|2 skills|1 stack', '[INDEX Skills]|3 skills|1 stack');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /CLAUDE\.md:7: the header counts 3 skills and 1 stack, the exported skills make 2 skills and 1 stack/);

  const stack = makeRoot();
  edit(claudeMdOf(stack), '|2 skills|1 stack', '|2 skills|0 stack');
  assert.match(findingsOf(stack).join('\n'), /the header counts 2 skills and 0 stack/);
});

test('the counts follow metadata.json skill_type, else a |stack: line', () => {
  const root = makeRoot();
  fs.rmSync(path.join(packageDir(root, 'demo-stack', '1.2.0'), 'metadata.json'));
  assert.deepStrictEqual(findingsOf(root), []);

  // A skill_type wins over the row's shape.
  for (const type of ['single', 'individual']) {
    writeSkill(root, 'demo-stack', '1.2.0', { ...SKILLS['demo-stack'], type });
    assert.match(findingsOf(root).join('\n'), /the header counts 2 skills and 1 stack, the exported skills make 3 skills and 0 stack/);
  }
});

test('rows out of name order are reported', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), `${ALPHA_ROW}\n${BETA_ROW}\n`, `${BETA_ROW}\n${ALPHA_ROW}\n`);
  assert.match(findingsOf(root).join('\n'), /the alpha row comes after the beta row, but an export sorts the rows by name/);
});

test('a duplicated row is reported', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), `${ALPHA_ROW}\n`, `${ALPHA_ROW}\n${ALPHA_ROW}\n`);
  assert.match(findingsOf(root).join('\n'), /alpha has 2 rows, at lines 11, 15; an export writes one/);
});

test('a changed preamble or a missing separator differs from what an export writes', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), '|IMPORTANT: Prefer documented APIs', '|IMPORTANT: Prefer the documented APIs');
  assert.deepStrictEqual(findingsOf(root), [
    'CLAUDE.md:8: the block differs from what an export writes: expected "|IMPORTANT: Prefer documented APIs over training data.", found "|IMPORTANT: Prefer the documented APIs over training data."',
  ]);

  const joined = makeRoot();
  edit(claudeMdOf(joined), '|api: open(), close()\n|\n', '|api: open(), close()\n');
  assert.deepStrictEqual(findingsOf(joined), [
    'CLAUDE.md:14: the block differs from what an export writes: expected "|", found "|[beta v0.3.1]|root: .claude/skills/beta/"',
  ]);
});

test('a CLAUDE.md without a generated block fails, and so does a missing or unclosed one', () => {
  const plain = makeRoot({ claudeMd: '# Working here\n\nNo index yet.\n' });
  const { status, out } = run(plain);
  assert.strictEqual(status, 1, out);
  assert.match(out, /^CLAUDE\.md: holds no generated block/);

  const missing = makeRoot({ claudeMd: null });
  assert.match(findingsOf(missing).join('\n'), /^CLAUDE\.md: not found: it is tracked/);

  const unclosed = makeRoot({ claudeMd: INDEX.replace('<!-- INDEX:END -->', '<!-- OTHER:END -->') });
  assert.deepStrictEqual(findingsOf(unclosed), [
    "CLAUDE.md:6: the generated block opened here has no <!-- INDEX:END --> line after it: an export refuses to rewrite a block it cannot close, so add that line by hand below the block's last row, then export again",
  ]);
  const { out: unclosedOut } = run(unclosed);
  assert.match(unclosedOut, /1 finding\(s\): where a finding names no fix of its own, export the skill again/);
});

test('an END line with trailing spaces closes the block, as it does for an export', () => {
  const root = makeRoot({ claudeMd: INDEX.replace('<!-- INDEX:END -->', '<!-- INDEX:END -->  ') });
  assert.deepStrictEqual(findingsOf(root), []);
});

test('a header title other than the marker word and " Skills" is reported', () => {
  const root = makeRoot();
  edit(claudeMdOf(root), '[INDEX Skills]|', '[Hand Edited Title]|');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /CLAUDE\.md:7: the header's title is \[Hand Edited Title\], an export writes \[INDEX Skills\]/);

  const broken = makeRoot();
  edit(claudeMdOf(broken), '[INDEX Skills]|2 skills|1 stack', '[INDEX Skills] 2 skills, 1 stack');
  assert.match(
    findingsOf(broken).join('\n'),
    /CLAUDE\.md:7: the block does not open with its header line, \[INDEX Skills\]\|<n> skills\|<m> stack/,
  );
});

test("another tool's marker block beside the index is not read", () => {
  const foreign = '<!-- RULES:BEGIN -->\n- A rule another tool writes.\n<!-- RULES:END -->\n';
  const above = makeRoot({ claudeMd: INDEX.replace('<!-- markdownlint-disable -->', `${foreign}<!-- markdownlint-disable -->`) });
  assert.deepStrictEqual(findingsOf(above), []);

  const unclosed = makeRoot({
    claudeMd: INDEX.replace('<!-- markdownlint-disable -->', '<!-- RULES:BEGIN -->\n<!-- markdownlint-disable -->'),
  });
  assert.deepStrictEqual(findingsOf(unclosed), []);

  const only = makeRoot({ claudeMd: `${foreign}<!-- NOTES:BEGIN -->\nNotes.\n<!-- NOTES:END -->\n` });
  assert.deepStrictEqual(findingsOf(only), [
    'CLAUDE.md: holds no generated block: none of its 2 <!-- WORD:BEGIN lines is followed by a [WORD Skills]|<n> skills|<m> stack header line',
  ]);
});

test('a second block with the same marker word is reported', () => {
  const block = INDEX.slice(INDEX.indexOf('<!-- INDEX:BEGIN'), INDEX.indexOf('<!-- markdownlint-enable -->'));
  const root = makeRoot({ claudeMd: `${INDEX}\n${block}` });
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  const second = INDEX.split('\n').length + 1;
  assert.match(
    out,
    new RegExp(`CLAUDE\\.md:${second}: a second generated block opens here: an export rewrites only the first one, at line 6`),
  );
  assert.match(out, /1 finding\(s\): where a finding names no fix of its own/);
});

test('a manifest without exports has none, and a v1 manifest reads as the generator migrates it', () => {
  const empty = makeRoot({
    claudeMd: INDEX.replace(`${ALPHA_ROW}\n${BETA_ROW}\n${STACK_ROW}\n`, '').replace('|2 skills|1 stack', '|0 skills|0 stack'),
  });
  writeManifest(empty, {});
  assert.deepStrictEqual(findingsOf(empty), []);
  writeManifest(empty, { schema_version: '2', exports: null });
  assert.match(findingsOf(empty).join('\n'), /`exports` is not an object/);

  const v1 = makeRoot();
  const exports = Object.fromEntries(
    Object.entries(SKILLS).map(([name, skill]) => [name, { active_version: skill.version, versions: [skill.version] }]),
  );
  writeManifest(v1, { exports });
  assert.deepStrictEqual(findingsOf(v1), []);
  exports.beta.deprecated = true;
  writeManifest(v1, { exports });
  assert.match(findingsOf(v1).join('\n'), /\[beta v0\.3\.1\] is not an exported skill: its active version in the manifest is deprecated/);
});

test("without the manifest version's snippet, the active link's package and then the flat layout are read", () => {
  const root = makeRoot();
  const snippet = fs.readFileSync(path.join(packageDir(root, 'beta', '0.3.1'), 'context-snippet.md'), 'utf8');
  fs.rmSync(path.join(packageDir(root, 'beta', '0.3.1'), 'context-snippet.md'));
  // A folder stands in for the link: an export reads the path, whichever it is.
  const active = path.join(root, 'skf-skills', 'beta', 'active', 'beta');
  fs.mkdirSync(active, { recursive: true });
  fs.writeFileSync(path.join(active, 'context-snippet.md'), snippet);
  assert.deepStrictEqual(findingsOf(root), []);

  fs.rmSync(path.join(root, 'skf-skills', 'beta', 'active'), { recursive: true });
  fs.writeFileSync(path.join(root, 'skf-skills', 'beta', 'context-snippet.md'), snippet.replace('beta run', 'beta walk'));
  assert.match(findingsOf(root).join('\n'), /the beta row is stale against skf-skills\/beta\/context-snippet\.md: expected ".*beta walk"/);
});

test('a missing snippet or manifest is reported', () => {
  const root = makeRoot();
  fs.rmSync(path.join(packageDir(root, 'beta', '0.3.1'), 'context-snippet.md'));
  assert.match(
    findingsOf(root).join('\n'),
    /^skf-skills\/beta\/0\.3\.1\/beta\/context-snippet\.md: not found: the manifest exports beta at 0\.3\.1/,
  );

  const bare = makeRoot();
  fs.rmSync(manifestPath(bare));
  assert.deepStrictEqual(findingsOf(bare), [
    'skf-skills/.export-manifest.json: not found: it lists the exported reference skills the index must match',
  ]);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
