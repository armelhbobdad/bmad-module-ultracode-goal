/**
 * Covered-Surface Diff
 *
 * Compares the public contract surfaces of two trees, by default the last
 * stable release tag and the working tree, and sorts every difference into
 * one of three groups. tools/changes.js uses the result to set the minimum
 * version bump of a release and to refuse a release whose change fragments
 * do not name a removal.
 *
 * What it reads: the surfaces docs/_internal/STABILITY.md enumerates as the
 * public contract, plus the tool minimums.
 * - CLI subcommands: the `command:` of each module in tools/cli/commands/
 *   that tools/cli/ucg-cli.js registers.
 * - CLI options: each subcommand's `options:` flags, and the top-level
 *   -V/--version (when tools/cli/ucg-cli.js sets program.version) and
 *   -h/--help (commander adds them to every program).
 * - customize.toml keys: the keys of the [workflow] table of
 *   skills/ultracode-goal/customize.toml.
 * - The headless emit shape: CANONICAL_KEYS and RESULT_FILENAME in
 *   skills/ultracode-goal/scripts/headless_envelope.py.
 * - The skill name and its invocation phrases: the `name:` of
 *   skills/ultracode-goal/SKILL.md and each phrase its `description:`
 *   quotes in single quotes.
 * - gate_eval.py: each --flag of its argument parser, each value a flag's
 *   choices= list allows, each gate_status of GATE_VERDICT with the
 *   verdict it maps to, each verdict, and each key of the printed result
 *   object (the `result = {...}` literal and every `result["<key>"] =`).
 * - Tool minimums: the `minimum` of each tool in tools/tool-requirements.yaml,
 *   keyed by the tool and named by its `name` (a tool with a null minimum
 *   has none).
 *
 * Groups:
 * - hard: a removed subcommand, option, customize key, skill name,
 *   invocation phrase, gate flag, choice, gate_status, verdict or printed
 *   key; a headless key or the result file name added or removed (the emit
 *   shape is exactly five keys); a gate_status that maps to another
 *   verdict; a tool minimum raised or given to a tool that had none. The
 *   release needs a major bump, and a breaking change fragment must name
 *   the item.
 * - additive: one of those surfaces added (except the headless shape and
 *   printed keys), or a tool minimum lowered or removed. The release needs
 *   at least a minor bump.
 * - review: a printed key added to gate_eval.py's result. STABILITY.md
 *   counts a key every invocation prints as a shape change, and one that
 *   appears only with a new flag as additive; the text cannot tell the two
 *   apart, so a person judges it. Listed, never a failure.
 *
 * A tree whose tools/tool-requirements.yaml is missing has no tool
 * minimums, and the list's first appearance moves none: the versions it
 * records were already stated in the docs, so a base without the list
 * leaves the minimums out of the comparison.
 *
 * Usage:
 *   node tools/covered-surfaces.js                       # last stable tag vs the working tree
 *   node tools/covered-surfaces.js --base v2.2.0 --head HEAD
 *   node tools/covered-surfaces.js --json                # findings as JSON
 *   node tools/covered-surfaces.js --root <dir>          # another checkout (the tests use this)
 *
 * The last stable tag is `git describe --tags --abbrev=0 --match 'v[0-9]*'
 * --exclude '*-*'`, as in release.yaml's "Get new version and previous tag"
 * step; keep the two in step. Exit codes: 0 when the report is printed
 * (findings never fail this tool); 2 when a ref does not resolve, or when no
 * stable tag is found in CI. A local run with no stable tag says so and
 * exits 0.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const YAML = require('yaml');
const { REQUIREMENTS: TOOL_REQUIREMENTS, compareVersions } = require('./tool-requirements.js');

const CLI_ENTRY = 'tools/cli/ucg-cli.js';
const CLI_COMMAND = /^tools\/cli\/commands\/[^/]+\.js$/;
const CUSTOMIZE = 'skills/ultracode-goal/customize.toml';
const HEADLESS = 'skills/ultracode-goal/scripts/headless_envelope.py';
const SKILL = 'skills/ultracode-goal/SKILL.md';
const GATE_EVAL = 'skills/ultracode-goal/scripts/gate_eval.py';
const SURFACE_FILES = new Set([CLI_ENTRY, CUSTOMIZE, HEADLESS, SKILL, GATE_EVAL, TOOL_REQUIREMENTS]);
// The folders and files refTree lists, as git pathspecs.
const SURFACE_PATHSPECS = ['tools/cli', CUSTOMIZE, HEADLESS, SKILL, GATE_EVAL, TOOL_REQUIREMENTS];

/**
 * How each kind of item is grouped when it is removed, added or changed.
 * A missing entry means that change is not reported.
 */
const KINDS = {
  'cli-subcommand': { label: 'CLI subcommand', removed: 'hard', added: 'additive' },
  'cli-option': { label: 'CLI option', removed: 'hard', added: 'additive' },
  'customize-key': { label: 'customize.toml key', removed: 'hard', added: 'additive' },
  // The emit shape is exactly five keys: adding one breaks it as much as removing one.
  'headless-key': { label: 'headless emit key', removed: 'hard', added: 'hard' },
  'result-file': { label: 'headless result file', removed: 'hard', added: 'hard' },
  'skill-name': { label: 'skill name', removed: 'hard', added: 'additive' },
  'trigger-phrase': { label: 'invocation phrase', removed: 'hard', added: 'additive' },
  'gate-flag': { label: 'gate_eval.py flag', removed: 'hard', added: 'additive' },
  'gate-choice': { label: 'gate_eval.py choice', removed: 'hard', added: 'additive' },
  'gate-status': { label: 'gate_status value', removed: 'hard', added: 'additive', changed: 'hard' },
  verdict: { label: 'verdict value', removed: 'hard', added: 'additive' },
  'gate-key': { label: 'gate_eval.py result key', removed: 'hard', added: 'review' },
  // A new minimum, or a raised one, turns away users the release before accepted.
  'tool-minimum': { label: 'tool minimum', added: 'hard', raised: 'hard', removed: 'additive', lowered: 'additive' },
};
const GROUPS = ['hard', 'additive', 'review'];
const KIND_ORDER = Object.keys(KINDS);

// --- Reading a tree ---

function makeGit(root) {
  return (args, options = {}) =>
    execFileSync('git', ['-c', 'core.quotePath=false', ...args], {
      cwd: root,
      encoding: 'utf8',
      maxBuffer: 256 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
      ...options,
    });
}

/** The commit a ref names, or null when it does not resolve. */
function resolveCommit(root, ref) {
  try {
    return makeGit(root)(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]).trim() || null;
  } catch {
    return null;
  }
}

/**
 * The newest version tag (v<digit>...) with no prerelease suffix reachable
 * from `from` (HEAD by default), or null. A tag that is not a version, such
 * as `stable`, is never taken as the base.
 */
function lastStableTag(root, from = 'HEAD') {
  try {
    return makeGit(root)(['describe', '--tags', '--abbrev=0', '--match', 'v[0-9]*', '--exclude', '*-*', from]).trim() || null;
  } catch {
    return null;
  }
}

/** True for the files the extractors read. */
function isSurfaceFile(file) {
  return SURFACE_FILES.has(file) || CLI_COMMAND.test(file);
}

function normalizeNewlines(text) {
  return text === null || text === undefined ? null : text.replaceAll('\r\n', '\n');
}

/** Split `git cat-file --batch` output into the contents of each requested object. */
function parseCatFileBatch(buffer) {
  const contents = [];
  let pos = 0;
  while (pos < buffer.length) {
    const eol = buffer.indexOf(0x0a, pos);
    if (eol === -1) break;
    const header = buffer.toString('utf8', pos, eol).split(' ');
    if (header[1] === 'missing') {
      contents.push(null);
      pos = eol + 1;
      continue;
    }
    const size = Number(header[2]);
    contents.push(buffer.toString('utf8', eol + 1, eol + 1 + size));
    pos = eol + 1 + size + 1;
  }
  return contents;
}

/** A tree read from a git ref: every surface file is read in one git call. */
function refTree(root, ref) {
  const commit = resolveCommit(root, ref);
  if (!commit) throw new Error(`ref ${ref} not found`);
  const git = makeGit(root);
  const blobs = new Map();
  for (const entry of git(['ls-tree', '-r', '-z', '--full-tree', commit, '--', ...SURFACE_PATHSPECS]).split('\0')) {
    const tab = entry.indexOf('\t');
    if (tab === -1) continue;
    const [, type, sha] = entry.slice(0, tab).split(' ');
    if (type === 'blob') blobs.set(entry.slice(tab + 1), sha);
  }
  const wanted = [...blobs.keys()].filter((file) => isSurfaceFile(file));
  const contents = new Map();
  if (wanted.length > 0) {
    const output = execFileSync('git', ['cat-file', '--batch'], {
      cwd: root,
      input: wanted.map((file) => blobs.get(file)).join('\n') + '\n',
      maxBuffer: 512 * 1024 * 1024,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    for (const [index, text] of parseCatFileBatch(output).entries()) contents.set(wanted[index], normalizeNewlines(text));
  }
  return { label: ref, files: wanted.sort(), read: (file) => contents.get(file) ?? null };
}

/** The working tree of a checkout, read from disk. */
function workingTree(root) {
  const files = [];
  for (const file of SURFACE_FILES) {
    if (fs.existsSync(path.join(root, file))) files.push(file);
  }
  let commands = [];
  try {
    commands = fs.readdirSync(path.join(root, 'tools', 'cli', 'commands'), { withFileTypes: true });
  } catch {
    // no CLI in this tree
  }
  for (const entry of commands) {
    if (entry.isFile() && entry.name.endsWith('.js')) files.push(`tools/cli/commands/${entry.name}`);
  }
  files.sort();
  const read = (file) => {
    try {
      return normalizeNewlines(fs.readFileSync(path.join(root, file), 'utf8'));
    } catch {
      return null;
    }
  };
  return { label: 'working tree', files, read };
}

/** A tree for a ref, or the working tree when the ref is null. */
function openTree(root, ref) {
  return ref ? refTree(root, ref) : workingTree(root);
}

// --- Extractors ---

/** The flags of a commander option spec: "-o, --output <dir>" gives -o and --output. */
function optionFlags(spec) {
  return spec
    .split(/[\s,|]+/)
    .filter((part) => /^--?[A-Za-z][\w-]*$/.test(part))
    .map((part) => part.trim());
}

/** The text inside the brackets that `opener` (a regex ending in `[`) opens, or '' when it is absent or unclosed. */
function bracketed(text, opener) {
  const open = opener.exec(text);
  if (!open) return '';
  let depth = 1;
  const start = open.index + open[0].length;
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === '[') depth += 1;
    else if (text[index] === ']') {
      depth -= 1;
      if (depth === 0) return text.slice(start, index);
    }
  }
  return '';
}

/**
 * The command modules ucg-cli.js registers: each `const <name> =
 * require('./commands/<file>')` whose <name> is in the array its
 * `for (const command of [...])` loop walks. A module in tools/cli/commands/
 * that the CLI does not register is no subcommand, and one it stops
 * registering is removed. When the entry file is missing or holds no such
 * loop, every module in the folder counts, so nothing is lost silently.
 */
function registeredCommands(tree, entry) {
  const files = tree.files.filter((name) => CLI_COMMAND.test(name));
  const loop = entry === null ? null : /for\s*\(\s*const\s+\w+\s+of\s+\[([^\]]*)\]\s*\)/.exec(entry);
  if (!loop) return files;
  const modules = new Map();
  for (const match of entry.matchAll(/\bconst\s+(\w+)\s*=\s*require\(\s*['"]\.\/commands\/([^'"]+?)(?:\.js)?['"]\s*\)/g)) {
    modules.set(match[1], `tools/cli/commands/${match[2]}.js`);
  }
  const names = loop[1]
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
  return names.map((name) => modules.get(name)).filter((file) => file && files.includes(file));
}

function cliItems(tree, add) {
  const entry = tree.read(CLI_ENTRY);
  if (entry !== null) {
    // commander adds -h/--help to every program, and -V/--version with
    // program.version().
    const topLevel = ['-h', '--help'];
    if (/\bprogram\s*\.\s*version\s*\(/.test(entry)) topLevel.push('-V', '--version');
    for (const flag of topLevel) add({ kind: 'cli-option', workflow: 'cli', token: flag, where: CLI_ENTRY });
  }
  for (const file of registeredCommands(tree, entry)) {
    const text = tree.read(file) || '';
    const command = /\bcommand\s*:\s*['"`]([a-z][\w-]*)/.exec(text);
    if (!command) continue;
    const name = command[1];
    add({ kind: 'cli-subcommand', workflow: 'cli', token: name, where: file });
    const options = bracketed(text, /\boptions\s*:\s*\[/);
    for (const spec of options.matchAll(/\[\s*['"`](-[^'"`]+)['"`]/g)) {
      for (const flag of optionFlags(spec[1])) {
        add({ kind: 'cli-option', workflow: `cli ${name}`, token: flag, where: file });
      }
    }
  }
}

/** The keys of the [workflow] table, up to the next table header. */
function customizeItems(tree, add) {
  const lines = (tree.read(CUSTOMIZE) || '').split('\n');
  const start = lines.findIndex((line) => line.trim() === '[workflow]');
  if (start === -1) return;
  // A table header ([name], [a.b] or [[name]]) alone on its line ends the
  // table; a line of an array value that starts with [ does not.
  const header = /^\s*\[\[?[A-Za-z_][\w.-]*\]\]?\s*(?:#.*)?$/;
  let inString = false;
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    // A key = value line inside a multi-line string is text, not a key.
    const quotes = (line.match(/"{3}|'{3}/g) || []).length;
    if (inString) {
      if (quotes % 2 === 1) inString = false;
      continue;
    }
    if (header.test(line)) break;
    const key = /^\s*([A-Za-z_][\w-]*)\s*=/.exec(line);
    if (key) add({ kind: 'customize-key', workflow: 'customize.toml', token: key[1], where: CUSTOMIZE });
    if (quotes % 2 === 1) inString = true;
  }
}

function headlessItems(tree, add) {
  const text = tree.read(HEADLESS) || '';
  const keys = /^CANONICAL_KEYS\s*(?::[^=\n]*)?=\s*\(([^)]*)\)/m.exec(text);
  for (const key of keys ? keys[1].matchAll(/["']([^"']+)["']/g) : []) {
    add({ kind: 'headless-key', workflow: 'headless', token: key[1], where: HEADLESS });
  }
  const file = /^RESULT_FILENAME\s*(?::[^=\n]*)?=\s*["']([^"']+)["']/m.exec(text);
  if (file) add({ kind: 'result-file', workflow: 'headless', token: file[1], where: HEADLESS });
}

/** The frontmatter of a Markdown file as a map of its top-level keys, or null. */
function frontmatter(text) {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text || '');
  if (!match) return null;
  try {
    return YAML.parse(match[1]) || null;
  } catch {
    return null;
  }
}

function skillItems(tree, add) {
  const data = frontmatter(tree.read(SKILL));
  if (!data) return;
  if (typeof data.name === 'string') add({ kind: 'skill-name', workflow: 'skill', token: data.name, where: SKILL });
  // A phrase is quoted in single quotes; an apostrophe inside a word (user's) is not a quote.
  for (const phrase of String(data.description || '').matchAll(/(?<![\w'])'([^']+)'(?![\w'])/g)) {
    add({ kind: 'trigger-phrase', workflow: 'skill', token: phrase[1], where: SKILL });
  }
}

/** The text of each parser.add_argument(...) call, up to the next one. */
function argumentCalls(text) {
  const starts = [...text.matchAll(/\.add_argument\(/g)].map((match) => match.index);
  return starts.map((start, index) => {
    if (index + 1 < starts.length) return text.slice(start, starts[index + 1]);
    // The last call ends at the first blank line after it, or at the end of the file.
    const blank = text.indexOf('\n\n', start);
    return text.slice(start, blank === -1 ? text.length : blank + 1);
  });
}

/** The body of the `NAME = {` literal that opens a line, up to its closing brace at that indent. */
function dictLiteral(text, name) {
  const open = new RegExp(String.raw`^( *)${name}\s*=\s*\{\n`, 'm').exec(text);
  if (!open) return null;
  const close = text.indexOf(`\n${open[1]}}`, open.index);
  return close === -1 ? null : text.slice(open.index + open[0].length, close);
}

/**
 * The keys of the printed result: the dict literal that holds
 * `"verdict": verdict` (written `result = {` or `return {` over the
 * releases), at its first level only.
 */
function resultKeys(text) {
  const at = text.search(/["']verdict["']\s*:\s*verdict\b/);
  if (at === -1) return [];
  const lineStart = text.lastIndexOf('{\n', at);
  if (lineStart === -1) return [];
  const indent = /^( *)/.exec(text.slice(text.lastIndexOf('\n', lineStart) + 1))[1];
  const close = text.indexOf(`\n${indent}}`, at);
  const body = text.slice(lineStart + 2, close === -1 ? text.length : close);
  const keys = [...body.matchAll(new RegExp(String.raw`^${indent} {4}["']([a-z][a-z0-9_]*)["']\s*:`, 'gm'))].map((match) => match[1]);
  // A key added after the literal: result["sweep_scope"] = ...
  for (const match of text.matchAll(/\bresult\[["']([a-z][a-z0-9_]*)["']\]\s*=/g)) keys.push(match[1]);
  return keys;
}

function gateItems(tree, add) {
  const text = tree.read(GATE_EVAL) || '';
  for (const call of argumentCalls(text)) {
    const flag = /^\.add_argument\(\s*["'](--[a-z][\w-]*)["']/.exec(call);
    if (!flag) continue;
    add({ kind: 'gate-flag', workflow: 'gate_eval.py', token: flag[1], where: GATE_EVAL });
    const choices = /\bchoices\s*=\s*\[([^\]]*)\]/.exec(call);
    for (const value of choices ? choices[1].matchAll(/["']([^"']+)["']/g) : []) {
      add({ kind: 'gate-choice', workflow: 'gate_eval.py', token: `${flag[1]} ${value[1]}`, where: GATE_EVAL });
    }
  }
  const verdicts = dictLiteral(text, 'GATE_VERDICT') || '';
  const seen = new Set();
  for (const pair of verdicts.matchAll(/["']([A-Z_]+)["']\s*:\s*["']([a-z_]+)["']/g)) {
    add({ kind: 'gate-status', workflow: 'gate_eval.py', token: pair[1], where: GATE_EVAL, detail: pair[2] });
    if (!seen.has(pair[2])) {
      seen.add(pair[2]);
      add({ kind: 'verdict', workflow: 'gate_eval.py', token: pair[2], where: GATE_EVAL });
    }
  }
  for (const key of resultKeys(text)) {
    add({ kind: 'gate-key', workflow: 'gate_eval.py', token: key, where: GATE_EVAL });
  }
}

/**
 * The minimum of each tool in the tool list, keyed by the tool: a fragment
 * names it by its `name`. A tree whose list is missing or not YAML has none.
 */
function toolMinimumItems(tree, add) {
  let tools;
  try {
    tools = YAML.parse(tree.read(TOOL_REQUIREMENTS) || '')?.tools;
  } catch {
    return;
  }
  if (!tools || typeof tools !== 'object' || Array.isArray(tools)) return;
  for (const [key, tool] of Object.entries(tools)) {
    const minimum = tool && typeof tool.minimum === 'string' ? tool.minimum.trim() : '';
    if (!/^\d+(?:\.\d+)*$/.test(minimum)) continue;
    add({
      kind: 'tool-minimum',
      workflow: 'requirements',
      token: String(tool.name || key),
      where: TOOL_REQUIREMENTS,
      detail: minimum,
      id: key,
    });
  }
}

/**
 * Every covered item of one tree.
 *
 * @returns {{items: Map<string, object>, hasToolList: boolean}}
 */
function extractSurfaces(tree) {
  const items = new Map();
  const add = (item) => {
    // A tool minimum is keyed by the tool's key in the list, so renaming its
    // display name (the token a fragment names) moves no minimum.
    const key =
      item.kind === 'tool-minimum' ? [item.kind, item.id].join('|') : [item.kind, item.workflow, item.token, item.id || ''].join('|');
    if (!items.has(key)) items.set(key, { key, where: '', detail: '', ...item });
  };
  cliItems(tree, add);
  customizeItems(tree, add);
  headlessItems(tree, add);
  skillItems(tree, add);
  gateItems(tree, add);
  toolMinimumItems(tree, add);
  return { items, hasToolList: tree.read(TOOL_REQUIREMENTS) !== null };
}

// --- Diff ---

function describe(item, change, before) {
  const kind = KINDS[item.kind];
  const text = `${item.workflow}: ${kind.label} \`${item.token}\` ${change}`;
  if (item.kind === 'gate-status' && change === 'changed') {
    return `${item.workflow}: ${kind.label} \`${item.token}\` now maps to \`${item.detail}\` (was \`${before}\`)`;
  }
  if (item.kind === 'tool-minimum') {
    if (change === 'added') return `${text} (${item.detail})`;
    if (change === 'removed') return `${text} (was ${item.detail})`;
    return `${item.workflow}: ${kind.label} \`${item.token}\` ${change} from ${before} to ${item.detail}`;
  }
  return text;
}

/**
 * Compare two extractions.
 *
 * @returns {{hard: object[], additive: object[], review: object[]}} findings per group
 */
function diffSurfaces(base, head) {
  const findings = [];
  const push = (item, change, before) => {
    const group = KINDS[item.kind][change];
    if (!group) return;
    findings.push({
      group,
      kind: item.kind,
      change,
      workflow: item.workflow,
      token: item.token,
      where: item.where,
      text: describe(item, change, before),
    });
  };
  // The list's first appearance moves no minimum: see the header.
  const comparesMinimums = base.hasToolList;
  for (const [key, item] of base.items) {
    const now = head.items.get(key);
    if (!now) push(item, 'removed');
    else if (item.kind === 'tool-minimum') {
      // "2.15" and "2.15.0" are the same minimum: only a move up or down counts.
      const direction = compareVersions(now.detail, item.detail);
      if (direction !== 0) push(now, direction > 0 ? 'raised' : 'lowered', item.detail);
    } else if (item.detail !== now.detail) push(now, 'changed', item.detail);
  }
  for (const [key, item] of head.items) {
    if (base.items.has(key)) continue;
    if (item.kind === 'tool-minimum' && !comparesMinimums) continue;
    push(item, 'added');
  }
  findings.sort(
    (a, b) =>
      a.workflow.localeCompare(b.workflow, 'en') ||
      KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) ||
      a.token.localeCompare(b.token, 'en', { numeric: true }) ||
      a.text.localeCompare(b.text, 'en'),
  );
  const result = {};
  for (const group of GROUPS) result[group] = findings.filter((finding) => finding.group === group);
  return result;
}

/**
 * Diff the covered surfaces of two refs in `root`. A null `headRef` reads
 * the working tree.
 */
function compareRefs(root, baseRef, headRef = null) {
  const base = extractSurfaces(refTree(root, baseRef));
  const head = extractSurfaces(openTree(root, headRef));
  return { baseRef, headRef, headLabel: headRef || 'working tree', ...diffSurfaces(base, head), head };
}

// --- CLI ---

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

const GROUP_TITLES = {
  hard: 'hard (minimum major; a breaking fragment must name each one)',
  additive: 'additive (minimum minor)',
  review: 'review (never fails; judge whether each one needs a note)',
};

function formatReport(report) {
  const lines = [`Covered surfaces: ${report.baseRef} -> ${report.headLabel}`];
  for (const group of GROUPS) {
    lines.push('', `${GROUP_TITLES[group]}: ${report[group].length}`);
    for (const finding of report[group]) lines.push(`  - ${finding.text}`);
  }
  return lines.join('\n');
}

function main(argv = process.argv.slice(2), env = process.env) {
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  const inCi = env.GITHUB_ACTIONS === 'true' || env.CI === 'true';
  const baseRef = argValue(argv, '--base') || lastStableTag(root);
  const headRef = argValue(argv, '--head');
  if (!baseRef) {
    if (inCi) {
      console.error('error: no stable release tag found. Fetch tags (actions/checkout with fetch-depth: 0) or pass --base <ref>.');
      return 2;
    }
    console.log('No stable release tag found, so there is nothing to compare against (fetch tags or pass --base <ref>).');
    return 0;
  }
  for (const ref of [baseRef, headRef].filter(Boolean)) {
    if (!resolveCommit(root, ref)) {
      console.error(`error: ref ${ref} not found.`);
      return 2;
    }
  }
  const report = compareRefs(root, baseRef, headRef);
  if (argv.includes('--json')) {
    const { hard, additive, review } = report;
    console.log(JSON.stringify({ base: baseRef, head: report.headLabel, hard, additive, review }, null, 2));
  } else {
    console.log(formatReport(report));
  }
  return 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  GROUPS,
  KINDS,
  compareRefs,
  diffSurfaces,
  extractSurfaces,
  formatReport,
  isSurfaceFile,
  lastStableTag,
  main,
  openTree,
  parseCatFileBatch,
  refTree,
  resolveCommit,
  workingTree,
};
