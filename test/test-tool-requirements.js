/**
 * Tests for tools/tool-requirements.js
 *
 * `npm run validate:tool-requirements` runs this tool with --check in CI.
 * These tests pin each kind of mismatch it reports (the generated table, the
 * prose minimums and the README badge, engines.node, .nvmrc, the workflows'
 * node-version and python-version, written out or in a matrix, the Claude
 * Code minimums preflight_check.py launches above, the README "Tested with"
 * rows, the list's own schema), --write, and the PEP 723 requires-python
 * headers under skills/.
 *
 * Each case copies the files the tool reads into a throwaway folder, changes
 * one thing and runs the tool there through --root. Expected line numbers are
 * looked up in the copy, so an unrelated docs edit does not break a test.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const REPO = path.join(__dirname, '..');
const TOOL = path.join(REPO, 'tools', 'tool-requirements.js');
const {
  compareVersions,
  lowerBound,
  readRequiresPython,
  loadRequirements,
  renderTable,
  checkAll,
  REQUIREMENTS,
  PREREQUISITES_DOC,
  START,
} = require(TOOL);

const PREFLIGHT = 'skills/ultracode-goal/scripts/preflight_check.py';
const FIXTURE_FILES = [
  REQUIREMENTS,
  PREREQUISITES_DOC,
  'README.md',
  'CONTRIBUTING.md',
  'package.json',
  '.nvmrc',
  '.github/workflows/quality.yaml',
  '.github/workflows/release.yaml',
  '.github/workflows/install-smoke.yaml',
  PREFLIGHT,
];

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

/** A copy of the files the tool reads. */
function makeRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'toolreq-'));
  tmpRoots.push(root);
  for (const file of FIXTURE_FILES) {
    const target = path.join(root, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(REPO, file), target);
  }
  return root;
}

function read(root, file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

function write(root, file, body) {
  const target = path.join(root, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, body);
}

/** Replace the first occurrence of `from`, which must exist. */
function edit(root, file, from, to) {
  const body = read(root, file);
  assert.ok(body.includes(from), `${file} holds no ${JSON.stringify(from)}`);
  write(root, file, body.replace(from, to));
}

/** The 1-based line of the first line of `file` holding `text`. */
function lineOf(root, file, text) {
  const index = read(root, file)
    .split('\n')
    .findIndex((line) => line.includes(text));
  assert.notStrictEqual(index, -1, `${file} holds no ${JSON.stringify(text)}`);
  return index + 1;
}

function run(root, flags = ['--check'], env = {}) {
  const childEnv = { ...process.env, ...env };
  if (!('GITHUB_ACTIONS' in env)) delete childEnv.GITHUB_ACTIONS;
  const result = spawnSync(process.execPath, [TOOL, '--root', root, ...flags], { encoding: 'utf8', env: childEnv });
  return { status: result.status, out: result.stdout + result.stderr };
}

/** Run --check and expect exit 1 with a finding at file:line. */
function expectFinding(root, file, line, pattern) {
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  const finding = out.split('\n').find((text) => text.startsWith(`${file}:${line}: `));
  assert.ok(finding, `no finding at ${file}:${line} in:\n${out}`);
  if (pattern) assert.match(finding, pattern);
}

// --- Pure helpers ---

test('compareVersions reads missing parts as 0', () => {
  assert.strictEqual(compareVersions('22', '22.0.0'), 0);
  assert.strictEqual(compareVersions('3.10', '3.11'), -1);
  assert.strictEqual(compareVersions('2.1.59', '2.1.154'), -1);
  assert.strictEqual(compareVersions('2.1.301', '2.1.154'), 1);
});

test('lowerBound takes the >= clause of a requires-python specifier', () => {
  assert.strictEqual(lowerBound('>=3.10'), '3.10');
  assert.strictEqual(lowerBound('>=3.11,<4'), '3.11');
  assert.strictEqual(lowerBound('<4, >= 3.9'), '3.9');
  assert.strictEqual(lowerBound('==3.12'), null);
});

test('readRequiresPython reads the # /// script block, not a docstring that quotes one', () => {
  const header = readRequiresPython(['# /// script', '# requires-python = ">=3.11"', '# dependencies = []', '# ///', '"""x"""']);
  assert.deepStrictEqual(header, { spec: '>=3.11', line: 2 });
  assert.strictEqual(readRequiresPython(['"""', 'requires-python = ">=3.10"', '"""']), null);
});

test('renderTable: one row per tool with its minimum and tested versions, then the fixed row', () => {
  const tools = loadRequirements(REPO).data.tools;
  const table = renderTable(tools);
  assert.match(table[0], /^\| Tool +\| Used for +\| Minimum +\| Tested on +\| Install +\|$/);
  assert.match(table[1], /^\| -+ \| -+ \| -+ \| -+ \| -+ \|$/);
  assert.strictEqual(table.length, 2 + Object.keys(tools).length + 1);
  // A product name reads as it is, a command name in backticks.
  const claude = table.find((row) => row.startsWith('| Claude Code '));
  assert.match(claude, /\| 2\.1\.154 +\| 2\.1\.301 +\|/);
  // No minimum reads `none`, and no tested version `not recorded`.
  assert.match(
    table.find((row) => row.startsWith('| `gh` (GitHub CLI)')),
    /\| none +\| not recorded +\|/,
  );
  for (const name of ['Node.js ', 'Python ', '`uv` (Python package runner)', '`git` ', 'BMAD Method ', 'TEA (Test Architect)']) {
    assert.ok(
      table.some((row) => row.startsWith(`| ${name}`)),
      `no ${name} row`,
    );
  }
  assert.match(table.at(-1), /^\| A BMAD project with an Epic/);
  assert.ok(new Set(table.map((row) => row.length)).size === 1, 'rows are not padded to the same width');
});

// --- The repository and a clean copy ---

test('the repository agrees with its tool list', () => {
  const { status, out } = run(REPO);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Tool versions agree with tools\/tool-requirements\.yaml/);
});

test('a copy of the repository passes', () => {
  const { status, out } = run(makeRoot());
  assert.strictEqual(status, 0, out);
});

// --- Prose minimums ---

test('the README install line: a Node.js minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'README.md', '[Node.js](https://nodejs.org/) >= 22', '[Node.js](https://nodejs.org/) >= 20');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', 'nodejs.org/) >= 20'), /says 20, but the Node\.js minimum .* is 22/);
});

test('the README Python badge', () => {
  const root = makeRoot();
  edit(root, 'README.md', 'python-%3E%3D3.11', 'python-%3E%3D3.10');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', 'python-%3E%3D3.10'), /Python badge says >=3\.10/);
});

test('CONTRIBUTING.md: a Python minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'CONTRIBUTING.md', '[Python](https://www.python.org/) >= 3.11', '[Python](https://www.python.org/) >= 3.10');
  expectFinding(root, 'CONTRIBUTING.md', lineOf(root, 'CONTRIBUTING.md', 'python.org/) >= 3.10'), /Python minimum .* is 3\.11/);
});

test('CONTRIBUTING.md: a Node.js minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'CONTRIBUTING.md', '[Node.js](https://nodejs.org/) >= 22', '[Node.js](https://nodejs.org/) >= 21');
  expectFinding(root, 'CONTRIBUTING.md', lineOf(root, 'CONTRIBUTING.md', 'nodejs.org/) >= 21'));
});

test('any docs page: "Node ≥ 20", and a Claude Code minimum written in prose', () => {
  const root = makeRoot();
  write(root, 'docs/extra.md', '# Extra\n\nYou need Node ≥ 20.\n\nAnd Claude Code >= 2.1.139.\n');
  expectFinding(root, 'docs/extra.md', 3, /"Node ≥ 20" says 20/);
  expectFinding(root, 'docs/extra.md', 5, /"Claude Code >= 2\.1\.139" says 2\.1\.139, but the Claude Code minimum .* is 2\.1\.154/);
});

test('a minimum written as "3.11+" is read too', () => {
  const root = makeRoot();
  write(root, 'docs/extra.md', '# Extra\n\nRuns on Python 3.10+.\n');
  expectFinding(root, 'docs/extra.md', 3, /"Python 3\.10\+" says 3\.10, but the Python minimum .* is 3\.11/);
});

test('the README install line states the Claude Code minimum', () => {
  const root = makeRoot();
  edit(
    root,
    'README.md',
    '[Claude Code](https://claude.com/product/claude-code) >= 2.1.154',
    '[Claude Code](https://claude.com/product/claude-code)',
  );
  expectFinding(root, 'README.md', 1, /no copy of the Claude Code minimum: the install line must say "Claude Code >= 2\.1\.154"/);
});

test('an install line that no longer states the minimum in a form the check reads', () => {
  const root = makeRoot();
  edit(root, 'README.md', '[Python](https://www.python.org/) >= 3.11', '[Python](https://www.python.org/) 3.11 or newer');
  expectFinding(root, 'README.md', 1, /no copy of the Python minimum: the install line must say "Python >= 3\.11"/);
});

// --- Copies outside the docs ---

test('package.json engines.node', () => {
  const root = makeRoot();
  edit(root, 'package.json', '"node": ">=22.0.0"', '"node": ">=20.0.0"');
  expectFinding(root, 'package.json', lineOf(root, 'package.json', '"node": ">=20.0.0"'), /engines\.node is ">=20\.0\.0"/);
});

test('.nvmrc', () => {
  const root = makeRoot();
  write(root, '.nvmrc', '23\n');
  expectFinding(root, '.nvmrc', 1, /not a Node\.js tested version .* \(22, 24\)/);
});

test('the install smoke test runs the Node.js minimum', () => {
  const root = makeRoot();
  const file = '.github/workflows/install-smoke.yaml';
  edit(root, file, 'node-version: "22"', 'node-version: "20"');
  expectFinding(root, file, lineOf(root, file, 'node-version: "20"'), /runs the Node\.js minimum .* \(22\)/);
});

test('the install smoke test sets no node-version', () => {
  const root = makeRoot();
  const file = '.github/workflows/install-smoke.yaml';
  edit(root, file, '          node-version: "22"\n', '');
  expectFinding(root, file, 1, /no node-version: the install smoke test runs the Node\.js minimum \(22\)/);
});

test('another workflow: a node-version that is not a tested version', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v6
        with:
          node-version: "20"
`,
  );
  expectFinding(root, file, lineOf(root, file, 'node-version: "20"'), /node-version 20 is not a Node\.js tested version .* \(22, 24\)/);
});

test('a CI python-version that is not a tested version', () => {
  const root = makeRoot();
  const file = '.github/workflows/quality.yaml';
  edit(root, file, 'python-version: "3.12"', 'python-version: "3.13"');
  expectFinding(
    root,
    file,
    lineOf(root, file, 'python-version: "3.13"'),
    /python-version 3\.13 is not a Python tested version .* \(3\.11, 3\.12\)/,
  );
});

test('the release workflow python-version', () => {
  const root = makeRoot();
  const file = '.github/workflows/release.yaml';
  edit(root, file, 'python-version: "3.12"', 'python-version: "3.10"');
  expectFinding(root, file, lineOf(root, file, 'python-version: "3.10"'));
});

test('no workflow runs the Python minimum', () => {
  const root = makeRoot();
  const file = '.github/workflows/quality.yaml';
  edit(root, file, 'python-version: "3.11"', 'python-version: "3.12"');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /no workflow runs Python 3\.11, the minimum/);
});

test('a matrix and a list are read item by item, each at its line and once; another expression is skipped', () => {
  const root = makeRoot();
  // The matrix below is left as the only run of the Python minimum.
  edit(root, '.github/workflows/quality.yaml', 'python-version: "3.11"', 'python-version: "3.12"');
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  test:
    strategy:
      matrix:
        python: ["3.11", "3.10"]
        node: ["24"]
        include:
          - node: "20"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v6
        with:
          python-version: \${{ matrix.python }}
      - uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: \${{ matrix.python }}
      - uses: actions/setup-node@v6
        with:
          node-version: \${{ matrix.node }}
      - uses: actions/setup-python@v6
        with:
          python-version: ["3.12", "3.13"]
      - uses: actions/setup-python@v6
        with:
          python-version: \${{ inputs.python }}
`,
  );
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.deepStrictEqual(
    out.split('\n').filter((line) => /^\S+:\d+: /.test(line)),
    [
      `${file}:${lineOf(root, file, '- node: "20"')}: node-version 20 is not a Node.js tested version in ${REQUIREMENTS} (22, 24)`,
      `${file}:${lineOf(root, file, 'python: ["3.11", "3.10"]')}: python-version 3.10 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
      `${file}:${lineOf(root, file, '["3.12", "3.13"]')}: python-version 3.13 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
    ],
  );
});

test('a multi-line value, an alias and the with: of a reusable workflow call are read too', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      PYTHON: &python "3.8"
    steps:
      - uses: actions/setup-python@v6
        with:
          python-version: |
            3.12
            3.9
      - uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: *python
  call:
    uses: ./.github/workflows/reusable.yaml
    with:
      node-version: "21"
`,
  );
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.deepStrictEqual(
    out.split('\n').filter((line) => /^\S+:\d+: /.test(line)),
    [
      `${file}:${lineOf(root, file, 'node-version: "21"')}: node-version 21 is not a Node.js tested version in ${REQUIREMENTS} (22, 24)`,
      `${file}:${lineOf(root, file, 'python-version: |')}: python-version 3.9 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
      `${file}:${lineOf(root, file, '&python "3.8"')}: python-version 3.8 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
    ],
  );
});

test('a workflow that is not YAML: its versions cannot be read', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(root, file, 'jobs:\n  build: [\n');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /^\.github\/workflows\/extra\.yaml:\d+: not valid YAML: .+ \(its node-version and python-version are not checked\)$/m);
});

// --- The Claude Code minimums preflight launches above ---

test('preflight: the highest MIN_ tuple is the Claude Code minimum', () => {
  const root = makeRoot();
  edit(root, PREFLIGHT, 'MIN_WORKFLOWS = (2, 1, 154)', 'MIN_WORKFLOWS = (2, 1, 200)');
  expectFinding(
    root,
    PREFLIGHT,
    lineOf(root, PREFLIGHT, 'MIN_WORKFLOWS = (2, 1, 200)'),
    /preflight refuses to launch below 2\.1\.200 \(MIN_WORKFLOWS\), but the Claude Code minimum .* is 2\.1\.154/,
  );
});

test('preflight: a lower tuple that is not the highest does not move the minimum', () => {
  const root = makeRoot();
  edit(root, PREFLIGHT, 'MIN_GOAL = (2, 1, 139)', 'MIN_GOAL = (2, 1, 140)');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('preflight: a missing one of the three minimums', () => {
  const root = makeRoot();
  edit(root, PREFLIGHT, 'MIN_AUTOMEMORY = (2, 1, 59)\n', '');
  expectFinding(root, PREFLIGHT, 1, /no MIN_AUTOMEMORY = \(major, minor, patch\) line: the Claude Code minimum has no complete copy/);
  const body = read(root, PREFLIGHT).replaceAll(/^MIN_[A-Z_]+ = .*$/gm, '');
  write(root, PREFLIGHT, body);
  expectFinding(root, PREFLIGHT, 1, /no MIN_GOAL, MIN_WORKFLOWS, MIN_AUTOMEMORY = /);
});

test('preflight: an annotated tuple is read, and another MIN_ tuple is not a Claude Code minimum', () => {
  const root = makeRoot();
  edit(root, PREFLIGHT, 'MIN_WORKFLOWS = (2, 1, 154)', 'MIN_WORKFLOWS: tuple[int, int, int] = (2, 1, 154)\nMIN_PYTHON = (3, 11, 0)');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

// --- The README "Tested with" table ---

test('a "Tested with" version that is not a tested version', () => {
  const root = makeRoot();
  edit(root, 'README.md', '| TEA (Test Architect) | 1.27.2 |', '| TEA (Test Architect) | 1.28.0 |');
  expectFinding(
    root,
    'README.md',
    lineOf(root, 'README.md', '| TEA (Test Architect) | 1.28.0 |'),
    /the "Tested with" row for TEA gives 1\.28\.0, which is not a TEA tested version .* \(1\.27\.2\)/,
  );
});

test('a "Tested with" version in backticks or with a leading v is read as the version', () => {
  const root = makeRoot();
  edit(root, 'README.md', '| TEA (Test Architect) | 1.27.2 |', '| TEA (Test Architect) | `v1.27.2` |');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('a second "Tested with" row for the same component', () => {
  const root = makeRoot();
  const row = read(root, 'README.md')
    .split('\n')
    .find((line) => line.startsWith('| BMAD Method |'));
  edit(root, 'README.md', `${row}\n`, `${row}\n${row.replace('6.12.0', '6.13.0')}\n`);
  expectFinding(root, 'README.md', lineOf(root, 'README.md', '| BMAD Method | 6.13.0'), /a second "BMAD Method" row: keep one/);
});

test('a tool whose "Tested with" row is gone', () => {
  const root = makeRoot();
  const row = read(root, 'README.md')
    .split('\n')
    .find((line) => line.startsWith('| BMAD Method |'));
  edit(root, 'README.md', `${row}\n`, '');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', '**Tested with:**'), /no "BMAD Method" row/);
});

test('no "Tested with" paragraph at all', () => {
  const root = makeRoot();
  edit(root, 'README.md', '**Tested with:**', '**Tried with:**');
  expectFinding(root, 'README.md', 1, /no "\*\*Tested with:\*\*" paragraph and table/);
});

// --- The generated table and --write ---

test('a hand edit to the table is reported, and --write puts it back', () => {
  const root = makeRoot();
  edit(root, PREREQUISITES_DOC, '| 2.1.154 |', '| 2.1.100 |');
  expectFinding(root, PREREQUISITES_DOC, lineOf(root, PREREQUISITES_DOC, START), /run node tools\/tool-requirements\.js --write/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 0, wrote.out);
  assert.match(wrote.out, /Wrote the prerequisites table/);
  assert.strictEqual(read(root, PREREQUISITES_DOC), read(REPO, PREREQUISITES_DOC));
  const again = run(root, ['--write']);
  assert.strictEqual(again.status, 0, again.out);
  assert.match(again.out, /is up to date/);
});

test('a new minimum: --write regenerates the table, and every stale copy is still reported', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "3.11"\n    tested: ["3.11", "3.12"]', 'minimum: "3.12"\n    tested: ["3.12"]');
  const checked = run(root);
  assert.strictEqual(checked.status, 1, checked.out);
  assert.match(checked.out, /docs\/getting-started\.md:\d+: the prerequisites table differs/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 1, wrote.out);
  assert.doesNotMatch(wrote.out, /the prerequisites table differs/);
  assert.match(read(root, PREREQUISITES_DOC), /\| Python +\| .+ \| 3\.12 +\| 3\.12 +\|/);
  for (const [file, text] of [
    ['README.md', 'python-%3E%3D3.11'],
    ['README.md', 'python.org/) >= 3.11'],
    ['CONTRIBUTING.md', 'python.org/) >= 3.11'],
    ['.github/workflows/quality.yaml', 'python-version: "3.11"'],
    [PREFLIGHT, 'requires-python = ">=3.11"'],
  ]) {
    assert.match(wrote.out, new RegExp(`${file.replaceAll('.', String.raw`\.`)}:${lineOf(root, file, text)}: `), `${file} not reported`);
  }
});

test('missing markers: --check and --write both report them', () => {
  const root = makeRoot();
  edit(root, PREREQUISITES_DOC, `${START}\n`, '');
  expectFinding(root, PREREQUISITES_DOC, 1, /no <!-- tool-requirements:start -->/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 1, wrote.out);
  assert.match(wrote.out, /add the two markers/);
});

// --- The list itself ---

test('schema: an unknown key, named at its line', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, '    install_url: https://cli.github.com\n', '    install_url: https://cli.github.com\n    minimun: "2.0"\n');
  expectFinding(root, REQUIREMENTS, lineOf(root, REQUIREMENTS, 'minimun:'), /tools\.gh: unknown key "minimun"/);
});

test('schema: a version written as a number', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "3.11"', 'minimum: 3.11');
  expectFinding(root, REQUIREMENTS, lineOf(root, REQUIREMENTS, 'minimum: 3.11'), /tools\.python\.minimum must be null or a quoted version/);
});

test('schema: a kind that does not exist', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'kind: optional', 'kind: required');
  expectFinding(root, REQUIREMENTS, lineOf(root, REQUIREMENTS, 'kind: required'), /tools\.gh\.kind must be one of runtime, gate, optional/);
});

test('schema: a minimum above every tested version', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "2.1.154"', 'minimum: "2.1.400"');
  expectFinding(
    root,
    REQUIREMENTS,
    lineOf(root, REQUIREMENTS, 'minimum: "2.1.400"'),
    /minimum 2\.1\.400 is above every tested version \(2\.1\.301\)/,
  );
});

test('schema: Node, Python and Claude Code need a minimum, since the copy checks compare with it', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "22"', 'minimum: null');
  edit(root, REQUIREMENTS, 'minimum: "3.11"', 'minimum: null');
  edit(root, REQUIREMENTS, 'minimum: "2.1.154"', 'minimum: null');
  const lines = read(root, REQUIREMENTS).split('\n');
  const minimumLine = (key) => lines.findIndex((line, index) => index > lines.indexOf(`  ${key}:`) && line.startsWith('    minimum:')) + 1;
  expectFinding(root, REQUIREMENTS, minimumLine('node'), /tools\.node\.minimum must be a version: the copy checks need it/);
  expectFinding(root, REQUIREMENTS, minimumLine('python'), /tools\.python\.minimum must be a version: the copy checks need it/);
  expectFinding(root, REQUIREMENTS, minimumLine('claude_code'), /tools\.claude_code\.minimum must be a version: the copy checks need it/);
  assert.doesNotMatch(run(root).out, /null/);
});

test('schema: a tool the checks need', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, '  node:\n', '  nodejs:\n');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /tools\.node is missing: the copy checks need it/);
});

test('a list that is not YAML, a missing list and no mode exit 2', () => {
  const root = makeRoot();
  write(root, REQUIREMENTS, 'tools: [\n');
  const broken = run(root);
  assert.strictEqual(broken.status, 2, broken.out);
  assert.match(broken.out, /not valid YAML/);
  fs.rmSync(path.join(root, REQUIREMENTS));
  const missing = run(root);
  assert.strictEqual(missing.status, 2, missing.out);
  assert.match(missing.out, /tool-requirements\.yaml not found/);
  const usage = run(makeRoot(), []);
  assert.strictEqual(usage.status, 2, usage.out);
});

test('in GitHub Actions each finding is also an error annotation', () => {
  const root = makeRoot();
  write(root, '.nvmrc', '23\n');
  const { status, out } = run(root, ['--check'], { GITHUB_ACTIONS: 'true' });
  assert.strictEqual(status, 1, out);
  assert.match(out, /^::error file=\.nvmrc,line=1::/m);
});

// --- requires-python headers ---

test('a requires-python header below the Python minimum, at its file and line; a docstring that quotes one is not read', () => {
  const root = makeRoot();
  const header = (spec) => `# /// script\n# requires-python = "${spec}"\n# dependencies = []\n# ///\n`;
  write(root, 'skills/ultracode-goal/scripts/old.py', `${header('>=3.9')}"""Quotes requires-python = ">=3.8" in its docstring."""\n`);
  write(root, 'skills/ucg-status/scripts/shebang.py', `#!/usr/bin/env -S uv run --script\n${header('>=3.10')}import tomllib\n`);
  write(root, 'skills/ultracode-goal/scripts/new.py', `${header('>=3.11,<4')}print("ok")\n`);
  write(root, 'skills/ultracode-goal/scripts/newer.py', `${header('>=3.12')}print("ok")\n`);
  write(root, 'skills/ultracode-goal/scripts/plain.py', 'print("no header")\n');
  expectFinding(
    root,
    'skills/ultracode-goal/scripts/old.py',
    2,
    /requires-python = ">=3\.9" is below the Python minimum .*: declare ">=3\.11"/,
  );
  expectFinding(root, 'skills/ucg-status/scripts/shebang.py', 3, /requires-python = ">=3\.10"/);
  // One script's higher floor raises the minimum of the whole run.
  expectFinding(
    root,
    'skills/ultracode-goal/scripts/newer.py',
    2,
    /requires-python = ">=3\.12" is above the Python minimum .* \(3\.11\): raise the minimum there/,
  );
  assert.deepStrictEqual(
    checkAll(root, loadRequirements(root)).map((finding) => `${finding.file}:${finding.line}`),
    ['skills/ucg-status/scripts/shebang.py:3', 'skills/ultracode-goal/scripts/newer.py:2', 'skills/ultracode-goal/scripts/old.py:2'],
  );
});

test('every requires-python header under skills/ declares exactly the Python minimum', () => {
  const minimum = loadRequirements(REPO).data.tools.python.minimum;
  const below = checkAll(REPO, loadRequirements(REPO)).filter((finding) => /requires-python/.test(finding.message));
  assert.deepStrictEqual(below, [], `headers below ">=${minimum}"`);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
