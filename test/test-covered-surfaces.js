/**
 * Tests for tools/covered-surfaces.js
 *
 * `npm run test:changes-tool` runs this file. tools/changes.js takes the
 * minimum version bump and the removals a breaking fragment must name from
 * this diff, so these tests pin:
 * - each extractor on a small tree: the CLI subcommands and options (the
 *   options array of a command module, and the top-level -V/--version and
 *   -h/--help), the [workflow] keys of customize.toml up to the next table,
 *   CANONICAL_KEYS and RESULT_FILENAME of headless_envelope.py, the skill
 *   name and the phrases its description quotes, and gate_eval.py's flags,
 *   choices, GATE_VERDICT map, verdicts and printed result keys (the
 *   literal's first level and every result["<key>"] = assignment);
 * - the group of every change: a removal is hard, an addition additive, a
 *   headless key or result file added or removed is hard, a gate_status
 *   that maps to another verdict is hard, and a printed key added is for
 *   review;
 * - tool minimums: a base without tools/tool-requirements.yaml compares
 *   none, a raised or new minimum is hard, a lowered or removed one
 *   additive, and the same version written differently is no change;
 * - a git ref and the working tree read the same items;
 * - backtests against the real release tags, which this repository's
 *   history fixes: no pair of consecutive stable tags from v1.0.0 to v2.3.0
 *   has a hard item, v0.5.1..v1.0.0 has only the result file, and the
 *   additions of v2.0.0 and v2.2.0 are the gate flags and keys they shipped;
 * - the command line: --json, exit 2 on a ref that does not resolve, and a
 *   tree with no stable tag (exit 0 locally, 2 in CI).
 *
 * The backtests need the release tags. A CI run without them fails; a local
 * run skips them and says to run `git fetch --tags`.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const TOOL = path.join(ROOT, 'tools', 'covered-surfaces.js');
const surfaces = require(TOOL);

const IN_CI = process.env.GITHUB_ACTIONS === 'true' || process.env.CI === 'true';

let passed = 0;
let failed = 0;
let skipped = 0;
const tmpRoots = [];

function test(name, fn) {
  try {
    const result = fn();
    if (result === 'skip') {
      skipped += 1;
      console.log(`- ${name} (skipped)`);
      return;
    }
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

// --- Helpers ---

/** Environment for git and the tool: no CI markers and no inherited repository. */
function cleanEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of ['GITHUB_ACTIONS', 'CI', 'GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE']) delete env[key];
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

function git(root, args) {
  return execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(),
    encoding: 'utf8',
    stdio: 'pipe',
  });
}

function write(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(root, rel);
    if (body === null) {
      fs.rmSync(full, { force: true });
      continue;
    }
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
}

function commitAll(root, message) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message]);
}

/** A git repository holding `files` in one commit, tagged `tag` unless it is null. */
function makeRepo(files, tag = 'v1.0.0') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ucg-surfaces-'));
  tmpRoots.push(root);
  git(root, ['init', '-q', '-b', 'main']);
  write(root, files);
  commitAll(root, 'base');
  if (tag) git(root, ['tag', '-a', tag, '-m', tag]);
  return root;
}

/** A tree held in memory, in the shape refTree and workingTree return. */
function memoryTree(files) {
  return { label: 'memory', files: Object.keys(files).sort(), read: (file) => files[file] ?? null };
}

function list(found, kind) {
  return [...found.items.values()]
    .filter((item) => item.kind === kind)
    .map((item) => `${item.workflow} ${item.token}${item.detail ? `=${item.detail}` : ''}`)
    .sort();
}

/** "group kind change token" for each finding of a diff, sorted. */
function summary(report) {
  return surfaces.GROUPS.flatMap((group) =>
    report[group].map((finding) => `${group} ${finding.kind} ${finding.change} ${finding.token}`),
  ).sort();
}

function diff(baseFiles, headFiles) {
  return surfaces.diffSurfaces(surfaces.extractSurfaces(memoryTree(baseFiles)), surfaces.extractSurfaces(memoryTree(headFiles)));
}

function tokens(findings) {
  return findings.map((finding) => finding.token).sort();
}

function describeFindings(findings) {
  return findings.map((finding) => finding.text).join('\n');
}

function hasRefs(refs) {
  return refs.every((ref) => surfaces.resolveCommit(ROOT, ref));
}

/** Skip locally, fail in CI, when the history the backtests read is missing. */
function needRefs(refs) {
  if (hasRefs(refs)) return true;
  const message = `missing ${refs.filter((ref) => !surfaces.resolveCommit(ROOT, ref)).join(', ')}: run git fetch --tags`;
  if (IN_CI) throw new Error(message);
  console.log(`  ${message}`);
  return false;
}

function runTool(args, env = {}) {
  const result = spawnSync(process.execPath, [TOOL, ...args], { encoding: 'utf8', env: cleanEnv(env) });
  return { status: result.status, out: result.stdout + result.stderr };
}

const CLI_ENTRY = "const { program } = require('commander');\nprogram.version(packageJson.version).description('UltraCode Goal');\n";
const INSTALL_COMMAND = [
  'module.exports = {',
  "  command: 'install',",
  "  description: 'Install the module',",
  '  options: [',
  "    ['-d, --directory <dir>', 'Where to install'],",
  "    ['--yes', 'Take every default'],",
  '  ],',
  '  action: async () => {},',
  '};',
  '',
].join('\n');
const STATUS_COMMAND =
  "module.exports = {\n  command: 'status',\n  description: 'Show the install',\n  options: [],\n  action: async () => {},\n};\n";
const CUSTOMIZE = [
  'top_level = 1',
  '',
  '[workflow]',
  'activation_steps_prepend = []',
  'persistent_facts = ["file:{project-root}/**/project-context.md"]',
  '# a_comment = "not a key"',
  'max_turns_per_story = 25',
  'story_token_budget = 0',
  '',
  '[workflow.hooks]',
  'not_a_key = 1',
  '',
  '[other]',
  'also_not_a_key = 2',
  '',
].join('\n');
const HEADLESS = [
  '# The five always-present canonical keys; `reason` is the conditional sixth.',
  'CANONICAL_KEYS = ("status", "skill", "decision_log", "report", "deferred_work")',
  '',
  'RESULT_FILENAME = "run-result.json"',
  '',
].join('\n');
const SKILL = [
  '---',
  'name: ultracode-goal',
  "description: Runs a BMAD Epic. Use when the user requests to 'run an epic autonomously' or 'ultracode goal'.",
  '---',
  '',
  "# UltraCode Goal ('not a phrase')",
  '',
].join('\n');
const GATE = [
  'GATE_VERDICT = {',
  '    "PASS": "advance",',
  '    "WAIVED": "advance",',
  '    "FAIL": "reloop",',
  '}',
  '',
  '',
  'def evaluate(verdict, gate):',
  '    result = {',
  '        "verdict": verdict,',
  '        "gate_status": gate["gate_status"],',
  '        "p0_status": gate["p0_status"],',
  '        "nested": {',
  '            "inner": 1,',
  '        },',
  '    }',
  '    result["sweep_scope"] = None',
  '    return result',
  '',
  '',
  'def main():',
  '    parser.add_argument("--trace-output", required=True)',
  '    parser.add_argument(',
  '        "--profile",',
  '        required=True,',
  '        choices=["light", "production"],',
  '    )',
  '    parser.add_argument("--story", help="The story id.")',
  '    args = parser.parse_args()',
  '',
].join('\n');
const REQUIREMENTS = [
  'schema_version: 1',
  'tools:',
  '  claude_code:',
  '    name: Claude Code',
  '    minimum: "2.1.154"',
  '  node:',
  '    name: Node.js',
  '    minimum: "22"',
  '  python:',
  '    name: Python',
  '    minimum: "3.11"',
  '  git:',
  '    name: git',
  '    minimum: "2.15"',
  '  gh:',
  '    name: gh',
  '    minimum: null',
  '',
].join('\n');

const BASE_FILES = {
  'tools/cli/ucg-cli.js': CLI_ENTRY,
  'tools/cli/commands/install.js': INSTALL_COMMAND,
  'tools/cli/commands/status.js': STATUS_COMMAND,
  'skills/ultracode-goal/customize.toml': CUSTOMIZE,
  'skills/ultracode-goal/scripts/headless_envelope.py': HEADLESS,
  'skills/ultracode-goal/SKILL.md': SKILL,
  'skills/ultracode-goal/scripts/gate_eval.py': GATE,
};

// --- isSurfaceFile ---

test('isSurfaceFile: the files the extractors read, and nothing else', () => {
  for (const file of [
    'tools/cli/ucg-cli.js',
    'tools/cli/commands/install.js',
    'skills/ultracode-goal/customize.toml',
    'skills/ultracode-goal/scripts/headless_envelope.py',
    'skills/ultracode-goal/SKILL.md',
    'skills/ultracode-goal/scripts/gate_eval.py',
    'tools/tool-requirements.yaml',
  ]) {
    assert.strictEqual(surfaces.isSurfaceFile(file), true, file);
  }
  for (const file of [
    'tools/cli/lib/installer.js',
    'tools/cli/commands/nested/x.js',
    'skills/ultracode-goal/scripts/preflight_check.py',
    'skills/ucg-status/SKILL.md',
    'skills/ultracode-goal/references/gate.md',
    'docs/_internal/STABILITY.md',
  ]) {
    assert.strictEqual(surfaces.isSurfaceFile(file), false, file);
  }
});

// --- Extractors on small trees ---

test('extractSurfaces: CLI subcommands, their options array, and the top-level -V/--version and -h/--help', () => {
  const found = surfaces.extractSurfaces(memoryTree({ ...BASE_FILES, 'tools/cli/commands/helper.js': 'module.exports = {};\n' }));
  assert.deepStrictEqual(list(found, 'cli-subcommand'), ['cli install', 'cli status']);
  assert.deepStrictEqual(list(found, 'cli-option'), [
    'cli --help',
    'cli --version',
    'cli -V',
    'cli -h',
    'cli install --directory',
    'cli install --yes',
    'cli install -d',
  ]);
  // Without program.version() commander adds no -V/--version.
  const noVersion = surfaces.extractSurfaces(memoryTree({ 'tools/cli/ucg-cli.js': "const { program } = require('commander');\n" }));
  assert.deepStrictEqual(list(noVersion, 'cli-option'), ['cli --help', 'cli -h']);
  // No CLI entry point: no top-level options at all.
  assert.deepStrictEqual(list(surfaces.extractSurfaces(memoryTree({})), 'cli-option'), []);
});

const REGISTERING_ENTRY = [
  "const { program } = require('commander');",
  "const installCommand = require('./commands/install');",
  "const statusCommand = require('./commands/status');",
  'program.version(packageJson.version);',
  'for (const command of [installCommand, statusCommand]) {',
  '  program.command(command.command);',
  '}',
  '',
].join('\n');

test('extractSurfaces: a subcommand is a module the CLI registers, not every file in commands/', () => {
  const files = {
    ...BASE_FILES,
    'tools/cli/ucg-cli.js': REGISTERING_ENTRY,
    'tools/cli/commands/helper.js': STATUS_COMMAND.replace("command: 'status'", "command: 'helper'"),
  };
  assert.deepStrictEqual(list(surfaces.extractSurfaces(memoryTree(files)), 'cli-subcommand'), ['cli install', 'cli status']);
  // Dropping a module from the registered list removes its subcommand, while its file stays.
  const head = { ...files, 'tools/cli/ucg-cli.js': REGISTERING_ENTRY.replace('[installCommand, statusCommand]', '[installCommand]') };
  assert.deepStrictEqual(summary(diff(files, head)), ['hard cli-subcommand removed status']);
});

test('extractSurfaces: an array line that starts with [, an indented key and a multi-line string in [workflow]', () => {
  const TRIPLE = '"'.repeat(3);
  const customize = [
    '[workflow]',
    'protected_branches = [',
    '  ["main", "master"],',
    ']',
    '  indented_key = 1',
    `notes = ${TRIPLE}`,
    'looks_like = "a key"',
    TRIPLE,
    'last_key = 2',
    '',
    '[workflow.sub]',
    'sub_key = 3',
    '',
  ].join('\n');
  const found = surfaces.extractSurfaces(memoryTree({ 'skills/ultracode-goal/customize.toml': customize }));
  assert.deepStrictEqual(list(found, 'customize-key'), [
    'customize.toml indented_key',
    'customize.toml last_key',
    'customize.toml notes',
    'customize.toml protected_branches',
  ]);
});

test('extractSurfaces: an apostrophe inside a word is not a quoted phrase', () => {
  const skill = [
    '---',
    'name: ultracode-goal',
    "description: Runs the user's Epic. Use when the user requests to 'run an epic autonomously' or 'ultracode goal'.",
    '---',
    '',
  ].join('\n');
  const found = surfaces.extractSurfaces(memoryTree({ 'skills/ultracode-goal/SKILL.md': skill }));
  assert.deepStrictEqual(list(found, 'trigger-phrase'), ['skill run an epic autonomously', 'skill ultracode goal']);
});

test('extractSurfaces: annotated CANONICAL_KEYS and RESULT_FILENAME are read', () => {
  const headless = HEADLESS.replace('CANONICAL_KEYS = (', 'CANONICAL_KEYS: tuple[str, ...] = (').replace(
    'RESULT_FILENAME = ',
    'RESULT_FILENAME: str = ',
  );
  const base = surfaces.extractSurfaces(memoryTree(BASE_FILES));
  const head = surfaces.extractSurfaces(memoryTree({ ...BASE_FILES, 'skills/ultracode-goal/scripts/headless_envelope.py': headless }));
  assert.deepStrictEqual(list(head, 'headless-key'), list(base, 'headless-key'));
  assert.deepStrictEqual(list(head, 'result-file'), ['headless run-result.json']);
});

test('extractSurfaces: the [workflow] keys of customize.toml, up to the next table', () => {
  const found = surfaces.extractSurfaces(memoryTree(BASE_FILES));
  assert.deepStrictEqual(list(found, 'customize-key'), [
    'customize.toml activation_steps_prepend',
    'customize.toml max_turns_per_story',
    'customize.toml persistent_facts',
    'customize.toml story_token_budget',
  ]);
  const noTable = surfaces.extractSurfaces(memoryTree({ 'skills/ultracode-goal/customize.toml': 'max_turns_per_story = 25\n' }));
  assert.deepStrictEqual(list(noTable, 'customize-key'), []);
});

test('extractSurfaces: the five headless keys and the result file name', () => {
  const found = surfaces.extractSurfaces(memoryTree(BASE_FILES));
  assert.deepStrictEqual(list(found, 'headless-key'), [
    'headless decision_log',
    'headless deferred_work',
    'headless report',
    'headless skill',
    'headless status',
  ]);
  assert.deepStrictEqual(list(found, 'result-file'), ['headless run-result.json']);
});

test('extractSurfaces: the skill name and each phrase its description quotes, not the body', () => {
  const found = surfaces.extractSurfaces(memoryTree(BASE_FILES));
  assert.deepStrictEqual(list(found, 'skill-name'), ['skill ultracode-goal']);
  assert.deepStrictEqual(list(found, 'trigger-phrase'), ['skill run an epic autonomously', 'skill ultracode goal']);
  const noFrontmatter = surfaces.extractSurfaces(memoryTree({ 'skills/ultracode-goal/SKILL.md': "# Skill\n\n'run an epic'\n" }));
  assert.deepStrictEqual([...list(noFrontmatter, 'skill-name'), ...list(noFrontmatter, 'trigger-phrase')], []);
});

test('extractSurfaces: gate_eval.py flags, choices, statuses with their verdicts, verdicts and result keys', () => {
  const found = surfaces.extractSurfaces(memoryTree(BASE_FILES));
  assert.deepStrictEqual(list(found, 'gate-flag'), ['gate_eval.py --profile', 'gate_eval.py --story', 'gate_eval.py --trace-output']);
  assert.deepStrictEqual(list(found, 'gate-choice'), ['gate_eval.py --profile light', 'gate_eval.py --profile production']);
  assert.deepStrictEqual(list(found, 'gate-status'), [
    'gate_eval.py FAIL=reloop',
    'gate_eval.py PASS=advance',
    'gate_eval.py WAIVED=advance',
  ]);
  assert.deepStrictEqual(list(found, 'verdict'), ['gate_eval.py advance', 'gate_eval.py reloop']);
  // The literal's first level (a key with a digit included, a nested dict's
  // keys left out) and the assignment after it.
  assert.deepStrictEqual(list(found, 'gate-key'), [
    'gate_eval.py gate_status',
    'gate_eval.py nested',
    'gate_eval.py p0_status',
    'gate_eval.py sweep_scope',
    'gate_eval.py verdict',
  ]);
});

test('extractSurfaces: a result built with `return {` is read like `result = {`', () => {
  const returned = GATE.replace('    result = {', '    return {').replace('    result["sweep_scope"] = None\n    return result\n', '');
  const found = surfaces.extractSurfaces(memoryTree({ 'skills/ultracode-goal/scripts/gate_eval.py': returned }));
  assert.deepStrictEqual(list(found, 'gate-key'), [
    'gate_eval.py gate_status',
    'gate_eval.py nested',
    'gate_eval.py p0_status',
    'gate_eval.py verdict',
  ]);
});

test('extractSurfaces: tool minimums keyed by tool and named by its name; a null minimum is none', () => {
  const found = surfaces.extractSurfaces(memoryTree({ 'tools/tool-requirements.yaml': REQUIREMENTS }));
  assert.deepStrictEqual(list(found, 'tool-minimum'), [
    'requirements Claude Code=2.1.154',
    'requirements Node.js=22',
    'requirements Python=3.11',
    'requirements git=2.15',
  ]);
  assert.strictEqual(found.hasToolList, true);
  assert.strictEqual(surfaces.extractSurfaces(memoryTree({})).hasToolList, false);
  const broken = surfaces.extractSurfaces(memoryTree({ 'tools/tool-requirements.yaml': 'tools: [\n' }));
  assert.deepStrictEqual(list(broken, 'tool-minimum'), [], 'a list that is not YAML has no minimums');
});

// --- The group of each change ---

test('diffSurfaces: an unchanged tree has no finding', () => {
  assert.deepStrictEqual(summary(diff(BASE_FILES, BASE_FILES)), []);
});

test('diffSurfaces: a removed CLI subcommand or option is hard, an added one additive', () => {
  const head = {
    ...BASE_FILES,
    'tools/cli/commands/status.js': null,
    'tools/cli/commands/doctor.js': STATUS_COMMAND.replace("command: 'status'", "command: 'doctor'"),
    'tools/cli/commands/install.js': INSTALL_COMMAND.replace("    ['--yes', 'Take every default'],\n", "    ['--force', 'Overwrite'],\n"),
  };
  delete head['tools/cli/commands/status.js'];
  assert.deepStrictEqual(summary(diff(BASE_FILES, head)), [
    'additive cli-option added --force',
    'additive cli-subcommand added doctor',
    'hard cli-option removed --yes',
    'hard cli-subcommand removed status',
  ]);
});

test('diffSurfaces: a removed customize.toml key is hard, an added one additive', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/customize.toml': CUSTOMIZE.replace('story_token_budget = 0\n', 'heartbeat_interval = 60\n'),
  };
  assert.deepStrictEqual(summary(diff(BASE_FILES, head)), [
    'additive customize-key added heartbeat_interval',
    'hard customize-key removed story_token_budget',
  ]);
});

test('diffSurfaces: a headless key added or removed is hard, and so is a renamed result file', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/scripts/headless_envelope.py': HEADLESS.replace('"deferred_work")', '"deferred_work", "reason")')
      .replace('"report", ', '')
      .replace('run-result.json', 'result.json'),
  };
  const report = diff(BASE_FILES, head);
  assert.deepStrictEqual(summary(report), [
    'hard headless-key added reason',
    'hard headless-key removed report',
    'hard result-file added result.json',
    'hard result-file removed run-result.json',
  ]);
  assert.deepStrictEqual(report.additive, []);
});

test('diffSurfaces: a renamed skill or a dropped phrase is hard, a new phrase additive', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/SKILL.md': SKILL.replace('name: ultracode-goal', 'name: ucg').replace("'ultracode goal'", "'deliver the epic'"),
  };
  assert.deepStrictEqual(summary(diff(BASE_FILES, head)), [
    'additive skill-name added ucg',
    'additive trigger-phrase added deliver the epic',
    'hard skill-name removed ultracode-goal',
    'hard trigger-phrase removed ultracode goal',
  ]);
});

test('diffSurfaces: gate_eval.py flags and choices removed are hard, added additive', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/scripts/gate_eval.py': GATE.replace(
      '    parser.add_argument("--story", help="The story id.")',
      '    parser.add_argument("--baseline", help="A ref.")',
    ).replace('choices=["light", "production"]', 'choices=["light", "full"]'),
  };
  assert.deepStrictEqual(summary(diff(BASE_FILES, head)), [
    'additive gate-choice added --profile full',
    'additive gate-flag added --baseline',
    'hard gate-choice removed --profile production',
    'hard gate-flag removed --story',
  ]);
});

test('diffSurfaces: a gate_status that maps to another verdict is hard, a new status additive, a verdict gone hard', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/scripts/gate_eval.py': GATE.replace('"WAIVED": "advance"', '"WAIVED": "defer"').replace(
      '    "FAIL": "reloop",\n',
      '    "FAIL": "escalate",\n    "CONCERNS": "defer",\n',
    ),
  };
  const report = diff(BASE_FILES, head);
  assert.deepStrictEqual(summary(report), [
    'additive gate-status added CONCERNS',
    'additive verdict added defer',
    'additive verdict added escalate',
    'hard gate-status changed FAIL',
    'hard gate-status changed WAIVED',
    'hard verdict removed reloop',
  ]);
  assert.ok(
    report.hard.some((finding) => finding.text === 'gate_eval.py: gate_status value `WAIVED` now maps to `defer` (was `advance`)'),
    describeFindings(report.hard),
  );
});

test('diffSurfaces: a printed result key added is for review, one removed is hard', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/scripts/gate_eval.py': GATE.replace(
      '    result["sweep_scope"] = None\n',
      '    result["cycle_profile"] = None\n',
    ),
  };
  const report = diff(BASE_FILES, head);
  assert.deepStrictEqual(summary(report), ['hard gate-key removed sweep_scope', 'review gate-key added cycle_profile']);
  assert.strictEqual(report.review[0].text, 'gate_eval.py: gate_eval.py result key `cycle_profile` added');
});

test('diffSurfaces: findings are sorted by workflow, kind and token', () => {
  const head = {
    ...BASE_FILES,
    'skills/ultracode-goal/customize.toml': CUSTOMIZE.replace('story_token_budget = 0\n', ''),
    'tools/cli/commands/status.js': null,
  };
  delete head['tools/cli/commands/status.js'];
  assert.deepStrictEqual(
    diff(BASE_FILES, head).hard.map((finding) => finding.text),
    ['cli: CLI subcommand `status` removed', 'customize.toml: customize.toml key `story_token_budget` removed'],
  );
});

// --- Tool minimums ---

test('tool minimums: a base without the list compares none, even when the head sets them', () => {
  const report = diff(BASE_FILES, { ...BASE_FILES, 'tools/tool-requirements.yaml': REQUIREMENTS });
  assert.deepStrictEqual(summary(report), []);
});

test('tool minimums: raised or new is hard, lowered or removed additive, the same version written differently no change', () => {
  const base = { ...BASE_FILES, 'tools/tool-requirements.yaml': REQUIREMENTS };
  const head = {
    ...BASE_FILES,
    'tools/tool-requirements.yaml': REQUIREMENTS.replace('minimum: "2.1.154"', 'minimum: "2.1.200"')
      .replace('minimum: "22"', 'minimum: "20"')
      .replace('minimum: "3.11"', 'minimum: null')
      .replace('minimum: "2.15"', 'minimum: "2.15.0"')
      .replace('    name: gh\n    minimum: null\n', '    name: gh\n    minimum: "2.0"\n'),
  };
  const report = diff(base, head);
  assert.deepStrictEqual(summary(report), [
    'additive tool-minimum lowered Node.js',
    'additive tool-minimum removed Python',
    'hard tool-minimum added gh',
    'hard tool-minimum raised Claude Code',
  ]);
  const texts = [...report.hard, ...report.additive].map((finding) => finding.text).sort();
  assert.deepStrictEqual(texts, [
    'requirements: tool minimum `Claude Code` raised from 2.1.154 to 2.1.200',
    'requirements: tool minimum `Node.js` lowered from 22 to 20',
    'requirements: tool minimum `Python` removed (was 3.11)',
    'requirements: tool minimum `gh` added (2.0)',
  ]);
});

test('tool minimums: renaming a tool moves no minimum', () => {
  const base = { ...BASE_FILES, 'tools/tool-requirements.yaml': REQUIREMENTS };
  const head = { ...BASE_FILES, 'tools/tool-requirements.yaml': REQUIREMENTS.replace('name: Node.js', 'name: Node') };
  assert.deepStrictEqual(summary(diff(base, head)), []);
});

test('tool minimums: the list removed after a release is not a removal of every minimum', () => {
  // A head without the list reads as no minimums: each one is removed, additive.
  const report = diff({ 'tools/tool-requirements.yaml': REQUIREMENTS }, {});
  assert.deepStrictEqual(tokens(report.additive), ['Claude Code', 'Node.js', 'Python', 'git']);
  assert.deepStrictEqual(report.hard, []);
});

// --- Reading a tree ---

test('refTree and workingTree read the same items from the same files', () => {
  const root = makeRepo({ ...BASE_FILES, 'tools/tool-requirements.yaml': REQUIREMENTS, 'docs/other.md': '# Not read\n' });
  const fromRef = surfaces.extractSurfaces(surfaces.refTree(root, 'HEAD'));
  const fromDisk = surfaces.extractSurfaces(surfaces.workingTree(root));
  assert.deepStrictEqual([...fromRef.items.keys()].sort(), [...fromDisk.items.keys()].sort());
  assert.ok(fromRef.items.size > 30, `${fromRef.items.size} items`);
  assert.deepStrictEqual(surfaces.refTree(root, 'HEAD').files, surfaces.workingTree(root).files);
  assert.strictEqual(surfaces.openTree(root, null).label, 'working tree');
  assert.throws(() => surfaces.refTree(root, 'nope'), /ref nope not found/);
});

test('refTree reads a file with Windows line endings like the working tree', () => {
  const root = makeRepo({ 'skills/ultracode-goal/customize.toml': CUSTOMIZE.replaceAll('\n', '\r\n') });
  const found = surfaces.extractSurfaces(surfaces.refTree(root, 'HEAD'));
  assert.deepStrictEqual(list(found, 'customize-key'), list(surfaces.extractSurfaces(memoryTree(BASE_FILES)), 'customize-key'));
});

test('this checkout: HEAD and the working tree read the same items from every surface file left unchanged', () => {
  const dirty = new Set(
    git(ROOT, ['status', '--porcelain', '--untracked-files=all'])
      .split('\n')
      .filter(Boolean)
      .map((line) => line.slice(3)),
  );
  const keep = (found) =>
    [...found.items.values()]
      .filter((item) => !dirty.has(item.where))
      .map((item) => item.key)
      .sort();
  const fromHead = surfaces.extractSurfaces(surfaces.refTree(ROOT, 'HEAD'));
  const fromDisk = surfaces.extractSurfaces(surfaces.workingTree(ROOT));
  assert.deepStrictEqual(keep(fromDisk), keep(fromHead));
  // Every surface the contract names is read on this checkout.
  for (const kind of [
    'cli-subcommand',
    'cli-option',
    'customize-key',
    'headless-key',
    'result-file',
    'skill-name',
    'trigger-phrase',
    'gate-flag',
    'gate-choice',
    'gate-status',
    'verdict',
    'gate-key',
  ]) {
    assert.ok(list(fromDisk, kind).length > 0, `no ${kind} read on this checkout`);
  }
  assert.deepStrictEqual(list(fromDisk, 'headless-key'), [
    'headless decision_log',
    'headless deferred_work',
    'headless report',
    'headless skill',
    'headless status',
  ]);
  assert.deepStrictEqual(list(fromDisk, 'gate-status'), [
    'gate_eval.py CONCERNS=defer',
    'gate_eval.py FAIL=reloop',
    'gate_eval.py NOT_EVALUATED=escalate',
    'gate_eval.py PASS=advance',
    'gate_eval.py WAIVED=advance',
  ]);
  assert.deepStrictEqual(list(fromDisk, 'cli-subcommand'), ['cli install', 'cli status', 'cli uninstall', 'cli update']);
});

// --- Backtests against the real history ---

const CONSECUTIVE = [
  ['v1.0.0', 'v1.0.1'],
  ['v1.0.1', 'v2.0.0'],
  ['v2.0.0', 'v2.1.0'],
  ['v2.1.0', 'v2.2.0'],
  ['v2.2.0', 'v2.3.0'],
];

test('backtest: no pair of consecutive stable tags from v1.0.0 to v2.3.0 has a hard item', () => {
  if (!needRefs(['v1.0.0', 'v1.0.1', 'v2.0.0', 'v2.1.0', 'v2.2.0', 'v2.3.0'])) return 'skip';
  const withHard = [];
  for (const [base, head] of CONSECUTIVE) {
    const report = surfaces.compareRefs(ROOT, base, head);
    if (report.hard.length > 0) withHard.push(`${base}..${head}: ${describeFindings(report.hard)}`);
  }
  assert.deepStrictEqual(withHard, []);
});

test('backtest v0.5.1..v1.0.0: the result file run-result.json is the only hard item', () => {
  if (!needRefs(['v0.5.1', 'v1.0.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v0.5.1', 'v1.0.0');
  assert.deepStrictEqual(
    report.hard.map((finding) => `${finding.kind} ${finding.token}`),
    ['result-file run-result.json'],
  );
});

test('backtest v1.0.1..v2.0.0: --epic-level added, and its epic_level key for review', () => {
  if (!needRefs(['v1.0.1', 'v2.0.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v1.0.1', 'v2.0.0');
  assert.deepStrictEqual(
    report.additive.map((finding) => finding.text),
    ['gate_eval.py: gate_eval.py flag `--epic-level` added'],
  );
  assert.deepStrictEqual(
    report.review.map((finding) => finding.text),
    ['gate_eval.py: gate_eval.py result key `epic_level` added'],
  );
});

test('backtest v2.0.0..v2.1.0: the roll-up flags --rollup and --sprint-status added', () => {
  if (!needRefs(['v2.0.0', 'v2.1.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v2.0.0', 'v2.1.0');
  assert.deepStrictEqual(tokens(report.additive), ['--rollup', '--sprint-status']);
  assert.deepStrictEqual(report.review, []);
});

test('backtest v2.1.0..v2.2.0: --tests-ran and --cycle-profile with its two choices added, and their keys for review', () => {
  if (!needRefs(['v2.1.0', 'v2.2.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v2.1.0', 'v2.2.0');
  assert.deepStrictEqual(
    report.additive.map((finding) => finding.text),
    [
      'gate_eval.py: gate_eval.py flag `--cycle-profile` added',
      'gate_eval.py: gate_eval.py flag `--tests-ran` added',
      'gate_eval.py: gate_eval.py choice `--cycle-profile delta` added',
      'gate_eval.py: gate_eval.py choice `--cycle-profile full` added',
    ],
  );
  assert.deepStrictEqual(tokens(report.review), ['cycle_profile', 'sweep_scope']);
});

test('backtest v2.2.0..v2.3.0: no covered surface moved', () => {
  if (!needRefs(['v2.2.0', 'v2.3.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v2.2.0', 'v2.3.0');
  assert.deepStrictEqual(summary(report), []);
});

// A smoke test only: later changes may rightly change what HEAD reports, and
// the exact results are pinned by the backtests above.
test('smoke: the last stable tag compares with HEAD and with the working tree', () => {
  const tag = surfaces.lastStableTag(ROOT);
  if (!tag) {
    if (IN_CI) throw new Error('no stable release tag: run git fetch --tags');
    console.log('  no stable release tag: run git fetch --tags');
    return 'skip';
  }
  for (const head of ['HEAD', null]) {
    const report = surfaces.compareRefs(ROOT, tag, head);
    for (const group of surfaces.GROUPS) assert.ok(Array.isArray(report[group]), group);
  }
});

// --- The command line ---

test('cli: the report, --json, and --base/--head against another checkout', () => {
  const root = makeRepo(BASE_FILES);
  write(root, { 'skills/ultracode-goal/customize.toml': CUSTOMIZE.replace('story_token_budget = 0\n', 'heartbeat_interval = 60\n') });
  commitAll(root, 'swap a key');
  const text = runTool(['--root', root]);
  assert.strictEqual(text.status, 0, text.out);
  assert.match(text.out, /^Covered surfaces: v1\.0\.0 -> working tree\n/);
  assert.match(
    text.out,
    /hard \(minimum major; a breaking fragment must name each one\): 1\n {2}- customize\.toml: customize\.toml key `story_token_budget` removed/,
  );
  assert.match(text.out, /additive \(minimum minor\): 1\n {2}- customize\.toml: customize\.toml key `heartbeat_interval` added/);
  assert.match(text.out, /review \(never fails; judge whether each one needs a note\): 0/);
  const json = runTool(['--root', root, '--base', 'v1.0.0', '--head', 'HEAD', '--json']);
  assert.strictEqual(json.status, 0, json.out);
  const parsed = JSON.parse(json.out);
  assert.deepStrictEqual(Object.keys(parsed), ['base', 'head', 'hard', 'additive', 'review']);
  assert.strictEqual(parsed.base, 'v1.0.0');
  assert.strictEqual(parsed.head, 'HEAD');
  assert.deepStrictEqual(tokens(parsed.hard), ['story_token_budget']);
  assert.deepStrictEqual(tokens(parsed.additive), ['heartbeat_interval']);
});

test('cli: a ref that does not resolve exits 2', () => {
  const root = makeRepo(BASE_FILES);
  for (const args of [
    ['--base', 'v9.9.9'],
    ['--base', 'v1.0.0', '--head', 'nope'],
  ]) {
    const run = runTool(['--root', root, ...args]);
    assert.strictEqual(run.status, 2, run.out);
    assert.match(run.out, /error: ref (v9\.9\.9|nope) not found\./);
  }
});

test('cli: no stable tag exits 0 locally and 2 in CI; a prerelease tag is not a base', () => {
  const root = makeRepo(BASE_FILES, 'v1.0.0-rc.0');
  const local = runTool(['--root', root]);
  assert.strictEqual(local.status, 0, local.out);
  assert.match(local.out, /No stable release tag found, so there is nothing to compare against/);
  for (const env of [{ CI: 'true' }, { GITHUB_ACTIONS: 'true' }]) {
    const ci = runTool(['--root', root], env);
    assert.strictEqual(ci.status, 2, ci.out);
    assert.match(ci.out, /error: no stable release tag found\. Fetch tags/);
  }
  assert.strictEqual(surfaces.lastStableTag(root), null);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed${skipped > 0 ? `, ${skipped} skipped` : ''}`);
if (failed > 0) process.exit(1);
