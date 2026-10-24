/**
 * Context Index Validator
 *
 * CLAUDE.md is tracked, and its generated block is the context index of the
 * reference skills under skf-skills/: one row per exported skill, which every
 * Claude Code session in this checkout reads. The export workflow writes that
 * block between a BEGIN and an END marker comment, and the drop and rename
 * workflows rewrite it; nothing else should. This tool checks that the block
 * still matches the skills, so a snippet changed without a re-export, an
 * export committed without its CLAUDE.md change, or a hand edit inside the
 * block fails here instead of handing every session a stale index.
 *
 * It rebuilds the block the way the export's generator script assembles it
 * and compares the two line by line:
 * - The skills: every entry of skf-skills/.export-manifest.json whose
 *   active_version has an entry under `versions` that is not deprecated. A
 *   v1 manifest (`versions` a list) reads as the generator migrates it. The
 *   manifest's active_version picks the version, not the `active` link: a
 *   new version becomes active before it is exported, and the block keeps
 *   the exported one.
 * - Each one's snippet: skf-skills/<name>/<active_version>/<name>/
 *   context-snippet.md, else the one in the `active` link's package, else
 *   skf-skills/<name>/context-snippet.md (the flat layout), the order the
 *   generator tries them in.
 * - A row: the snippet without its blank edge lines, with a pipe before its
 *   first line (the `[<name> v<version>]` row header) and that line's `root:`
 *   set to .claude/skills/<name>/, the skill root the generator writes for
 *   CLAUDE.md. Its other lines already start with a pipe; a blank line inside
 *   it is written as it is.
 * - The block: the header line `[<WORD> Skills]|<n> skills|<m> stack`, where
 *   WORD is the markers' own word, two fixed preamble lines, then each row
 *   after a line holding a bare pipe, sorted by skill name. A package whose
 *   metadata.json skill_type is `stack` counts toward m, `single` or
 *   `individual` toward n; without one, a row with a `|stack:` line counts
 *   as a stack.
 *
 * The block opens at a line starting `<!-- <WORD>:BEGIN`, where WORD is an
 * upper-case word, and closes at the first `<!-- <WORD>:END -->` line after
 * it. When CLAUDE.md holds marker blocks with other words, the index is the
 * one whose BEGIN line is followed by a header line titled with its word.
 *
 * Findings, each with its file and line:
 * - CLAUDE.md is missing or holds no generated block, its block has no END
 *   line, or a second block with the same word follows it.
 * - An exported skill has no row, more than one, or a row that differs from
 *   its snippet (the first differing line is shown).
 * - A row names a skill that is not exported: its active version is
 *   deprecated, or the manifest does not list it at all (an export keeps
 *   such a row unless told to drop it).
 * - The rows are not sorted by name.
 * - The header's title or counts differ from what an export writes.
 * - The manifest cannot be read, or a snippet is missing or does not start
 *   with its own row header (the generator would leave that skill out).
 * - Anything else in the block differs from what an export writes: the
 *   preamble, a separator, a stray line.
 * Lines outside the markers are the maintainer's own and are not read.
 *
 * Read-only, with no network and no git, so it runs on every pull request.
 * A finding is fixed by exporting the skill again, which rewrites the block,
 * and committing CLAUDE.md with it, never by editing the block by hand,
 * unless the finding names another fix.
 *
 * The skill root, the header's shape, the preamble and the separator below
 * are copied from the generator, which is not tracked here. When an update
 * of that tooling changes one of them, the next export fails this check with
 * "the block differs", and the constants here change with it.
 *
 * Usage:
 *   node tools/validate-context-index.js               # Exit 1 on any finding
 *   node tools/validate-context-index.js --root <dir>  # Check another checkout (its tests use this)
 */

const fs = require('node:fs');
const path = require('node:path');

const CONTEXT_FILE = 'CLAUDE.md';
const SKILLS_DIR = 'skf-skills';
const MANIFEST = '.export-manifest.json';
const SNIPPET = 'context-snippet.md';
const METADATA = 'metadata.json';
// The `root:` prefix of every row the generator writes into CLAUDE.md: Claude
// Code's skill folder, which tools/link-reference-skills.js links the skills into.
const SKILL_ROOT = '.claude/skills/';
// The two lines the generator writes between the header line and the first row.
const PREAMBLE = [
  '|IMPORTANT: Prefer documented APIs over training data.',
  '|When using a listed library, read its SKILL.md before writing code.',
];

// The markers are matched by shape, so this file names no marker word.
const BEGIN = /^<!-- ([A-Z]+):BEGIN\b/;
const HEADER = /^\[([^\]]+)\]\|(\d+) skills\|(\d+) stack$/;
// A row's first line, `[name v1.2.3]...`, with or without its leading pipe. The
// ` v<version>` keeps the header line from reading as a row.
const ROW_HEADER = /^\|?\[([^\]]+?) v([^\]\s]+)\]/;
// The first `root:` field of a row's first line, split around its value.
const ROOT_FIELD = /^(.*?root:\s*)(\S.*?)(\s*)$/;
const STACK_LINE = /^\|stack:/m;

const HINT = 'export the skill again, which rewrites the block, and commit CLAUDE.md with it; never edit the block by hand';

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

const toLines = (text) => text.split(/\r?\n/);
const isSeparator = (line) => ['', '|'].includes(line.trim());
const isPlainName = (value) => typeof value === 'string' && value !== '' && value !== '.' && value !== '..' && !/[/\\:\0]/.test(value);
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const titleFor = (word) => `${word} Skills`;

function isFile(file) {
  try {
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

/** The generator's row order: by skill name, then version, in code point order. */
function byNameThenVersion(a, b) {
  if (a.name !== b.name) return a.name < b.name ? -1 : 1;
  if (a.version === b.version) return 0;
  return a.version < b.version ? -1 : 1;
}

/**
 * Split the lines between the markers into skill rows, as the generator parses
 * them back: a row runs from its header line to the next separator (a bare
 * pipe or a blank line), the next row header or the end of the block.
 *
 * @param {string[]} body - The lines between the markers
 * @param {number} firstLine - The 1-based file line of body[0]
 * @returns {{name: string, version: string, lines: string[], line: number}[]}
 */
function parseRows(body, firstLine) {
  const rows = [];
  let index = 0;
  while (index < body.length) {
    const match = ROW_HEADER.exec(body[index]);
    if (!match) {
      index += 1;
      continue;
    }
    const start = index;
    index += 1;
    while (index < body.length && !ROW_HEADER.test(body[index]) && !isSeparator(body[index])) index += 1;
    rows.push({ name: match[1], version: match[2], lines: body.slice(start, index), line: firstLine + start });
  }
  return rows;
}

/**
 * The row an export writes for a snippet, or the reason it would leave it out.
 *
 * @param {string} text - The snippet file's text
 * @param {string} name - The skill name the manifest gives
 * @returns {{lines: string[], version: string}|{problem: string}}
 */
function snippetRow(text, name) {
  const lines = toLines(text);
  while (lines.length > 0 && lines[0].trim() === '') lines.shift();
  while (lines.length > 0 && lines.at(-1).trim() === '') lines.pop();
  if (lines.length === 0) return { problem: 'is empty, so an export leaves the skill out of the index' };
  let first = lines[0].startsWith('|') ? lines[0].slice(1) : lines[0];
  const header = ROW_HEADER.exec(first);
  if (!first.startsWith('[') || !header || header[1] !== name) {
    return { problem: `does not start with the [${name} v<version>] row header, so an export leaves the skill out of the index` };
  }
  const root = ROOT_FIELD.exec(first);
  if (root) first = `${root[1]}${SKILL_ROOT}${name}/${root[3]}`;
  return { lines: [`|${first}`, ...lines.slice(1)], version: header[2] };
}

/**
 * Whether a package counts as a stack in the header: metadata.json's
 * skill_type when it gives one, else the row's shape.
 *
 * @param {string} packageDir - The package the snippet was read from
 * @param {string[]} rowLines - The row an export writes for it
 * @returns {boolean}
 */
function isStack(packageDir, rowLines) {
  let type = null;
  try {
    type = JSON.parse(fs.readFileSync(path.join(packageDir, METADATA), 'utf8')).skill_type;
  } catch {
    type = null;
  }
  if (type === 'single' || type === 'individual') return false;
  if (type === 'stack') return true;
  return STACK_LINE.test(rowLines.join('\n'));
}

/**
 * A manifest entry's record for one version, as the generator reads it, or
 * null. In a v1 manifest the generator turns a `versions` list into records,
 * the active one deprecated when the entry says `deprecated`.
 *
 * @param {*} entry - The manifest entry
 * @param {string} version - Its active_version
 * @param {boolean} v1 - Whether the manifest is a v1 one
 * @returns {{status?: string}|null}
 */
function versionRecord(entry, version, v1) {
  if (!isObject(entry)) return null;
  const { versions } = entry;
  if (v1 && Array.isArray(versions)) return versions.includes(version) ? { status: entry.deprecated ? 'deprecated' : 'active' } : null;
  const record = isObject(versions) && Object.hasOwn(versions, version) ? versions[version] : null;
  return isObject(record) ? record : null;
}

/**
 * The package an export reads a skill's snippet from, relative to the
 * checkout: the manifest version's, else the `active` link's, else the flat
 * layout's, the first that holds a context-snippet.md; null when none does.
 */
function findPackage(root, name, version) {
  const packages = [`${SKILLS_DIR}/${name}/${version}/${name}`, `${SKILLS_DIR}/${name}/active/${name}`, `${SKILLS_DIR}/${name}`];
  return packages.find((rel) => isFile(path.join(root, rel, SNIPPET))) ?? null;
}

/**
 * The exported skills and the rows an export writes for them, sorted by name.
 *
 * @param {string} root - Checkout root
 * @returns {{listed: Set<string>, exported: Set<string>, skills: object[], findings: object[]}|{error: object}}
 */
function exportedSkills(root) {
  const manifestRel = `${SKILLS_DIR}/${MANIFEST}`;
  let data;
  try {
    data = JSON.parse(fs.readFileSync(path.join(root, SKILLS_DIR, MANIFEST), 'utf8'));
  } catch (error) {
    const reason = error.code === 'ENOENT' ? 'not found' : `cannot be read (${error.message})`;
    return { error: { file: manifestRel, message: `${reason}: it lists the exported reference skills the index must match` } };
  }
  // The generator reads a manifest without `exports` as one with none.
  const exports = isObject(data) ? (Object.hasOwn(data, 'exports') ? data.exports : {}) : null;
  if (!isObject(exports)) {
    return { error: { file: manifestRel, message: '`exports` is not an object, so the exported reference skills cannot be read' } };
  }
  const v1 = data.schema_version !== '2';

  const listed = new Set(Object.keys(exports));
  const exported = new Set();
  const skills = [];
  const findings = [];
  for (const name of [...listed].sort()) {
    // Entries the generator cannot use (no active_version, no entry for it,
    // a name that is not one folder) and deprecated versions are left out.
    const entry = exports[name];
    const version = isObject(entry) ? entry.active_version : undefined;
    const record = versionRecord(entry, version, v1);
    if (!isPlainName(name) || !isPlainName(version) || !record) continue;
    if (record.status === 'deprecated') continue;
    exported.add(name);

    const packageRel = findPackage(root, name, version);
    if (!packageRel) {
      findings.push({
        file: `${SKILLS_DIR}/${name}/${version}/${name}/${SNIPPET}`,
        message: `not found: the manifest exports ${name} at ${version}, so this snippet is its row in the index`,
      });
      continue;
    }
    const snippetRel = `${packageRel}/${SNIPPET}`;
    let text;
    try {
      text = fs.readFileSync(path.join(root, snippetRel), 'utf8');
    } catch (error) {
      findings.push({ file: snippetRel, message: `cannot be read (${error.message}), so an export leaves the skill out of the index` });
      continue;
    }
    const row = snippetRow(text, name);
    if (row.problem) {
      findings.push({ file: snippetRel, message: row.problem });
      continue;
    }
    const stack = isStack(path.join(root, packageRel), row.lines);
    skills.push({ name, version: row.version, lines: row.lines, stack, snippet: snippetRel });
  }
  skills.sort(byNameThenVersion);
  return { listed, exported, skills, findings };
}

/**
 * Locate the generated block in CLAUDE.md.
 *
 * @param {string} root - Checkout root
 * @returns {{begin: number, word: string, body: string[], later: number[]}|{error: object}} begin is the
 *   1-based line of the BEGIN marker, later the lines of any further BEGIN marker with the same word
 */
function readBlock(root) {
  let text;
  try {
    text = fs.readFileSync(path.join(root, CONTEXT_FILE), 'utf8');
  } catch (error) {
    const reason = error.code === 'ENOENT' ? 'not found' : `cannot be read (${error.message})`;
    return {
      error: {
        file: CONTEXT_FILE,
        message: `${reason}: it is tracked, and its generated block is the context index of the reference skills`,
      },
    };
  }
  const lines = toLines(text);
  const begins = [];
  for (const [index, line] of lines.entries()) {
    const match = BEGIN.exec(line);
    if (match) begins.push({ index, word: match[1] });
  }
  // Another tool may keep a marker block of its own in CLAUDE.md. The index's
  // BEGIN line is followed by the header line its word titles.
  const titled = begins.find(({ index, word }) => HEADER.exec(lines[index + 1] ?? '')?.[1] === titleFor(word));
  const word = titled ? titled.word : begins.length === 1 ? begins[0].word : null;
  if (!word) {
    const message =
      begins.length === 0
        ? 'holds no generated block (a <!-- WORD:BEGIN line and a <!-- WORD:END --> line after it): export a reference skill to write it'
        : `holds no generated block: none of its ${begins.length} <!-- WORD:BEGIN lines is followed by a [WORD Skills]|<n> skills|<m> stack header line`;
    return { error: { file: CONTEXT_FILE, message, ownFix: begins.length === 0 } };
  }

  // An export rewrites the first block with this word, up to its first END line.
  const own = begins.filter((begin) => begin.word === word);
  const begin = own[0].index;
  const endMarker = `<!-- ${word}:END -->`;
  const end = lines.findIndex((line, index) => index > begin && line.trimEnd() === endMarker);
  if (end === -1) {
    return {
      error: {
        file: CONTEXT_FILE,
        line: begin + 1,
        message: `the generated block opened here has no ${endMarker} line after it: an export refuses to rewrite a block it cannot close, so add that line by hand below the block's last row, then export again`,
        ownFix: true,
      },
    };
  }
  const later = own.filter(({ index }) => index > end).map(({ index }) => index + 1);
  return { begin: begin + 1, word, body: lines.slice(begin + 1, end), later };
}

/**
 * The first line where two line lists differ, or null when they are equal.
 *
 * @param {string[]} actual - The lines found
 * @param {string[]} expected - The lines an export writes
 * @returns {{index: number, actual: string|undefined, expected: string|undefined}|null}
 */
function firstDifference(actual, expected) {
  for (let index = 0; index < Math.max(actual.length, expected.length); index += 1) {
    if (actual[index] !== expected[index]) return { index, actual: actual[index], expected: expected[index] };
  }
  return null;
}

/** "expected X, found Y" for a difference, naming a missing line as such. */
function describe(diff) {
  if (diff.expected === undefined) return `found "${diff.actual}", which an export does not write`;
  if (diff.actual === undefined) return `expected "${diff.expected}", found nothing`;
  return `expected "${diff.expected}", found "${diff.actual}"`;
}

/**
 * Compare the generated block of CLAUDE.md with the exported skills.
 *
 * @param {string} root - Checkout root
 * @returns {{findings: {file: string, line?: number, message: string, ownFix?: boolean}[], skills: object[]}}
 *   ownFix marks a finding whose message names a fix other than exporting again
 */
function checkIndex(root) {
  const expected = exportedSkills(root);
  if (expected.error) return { findings: [expected.error], skills: [] };
  const { listed, exported, skills } = expected;
  const findings = [...expected.findings];
  const block = readBlock(root);
  if (block.error) return { findings: [...findings, block.error], skills };

  const add = (line, message, ownFix = false) => findings.push({ file: CONTEXT_FILE, line, message, ownFix });
  const headerLine = block.begin + 1;
  const rows = parseRows(block.body, headerLine);

  for (const line of block.later) {
    add(
      line,
      `a second generated block opens here: an export rewrites only the first one, at line ${block.begin}, so delete this one by hand`,
      true,
    );
  }
  // A row the manifest does not list at all stays through an export, which
  // keeps it unless told to drop it, and counts in the header by its shape.
  const kept = [];
  for (const row of rows) {
    if (exported.has(row.name)) continue;
    if (listed.has(row.name)) {
      add(
        row.line,
        `[${row.name} v${row.version}] is not an exported skill: its active version in the manifest is deprecated or has no entry, so an export leaves its row out`,
      );
    } else {
      kept.push(row);
      add(
        row.line,
        `[${row.name} v${row.version}] is not in the export manifest, and an export keeps such a row unless told to drop it: export a reference skill again and choose Drop when it lists the rows the manifest lacks, or export this skill so the manifest lists it`,
        true,
      );
    }
  }
  for (const skill of skills) {
    const own = rows.filter((row) => row.name === skill.name);
    if (own.length === 0) {
      add(block.begin, `${skill.name} v${skill.version} is exported but has no row in the block (${skill.snippet})`);
    } else if (own.length > 1) {
      add(own[1].line, `${skill.name} has ${own.length} rows, at lines ${own.map((row) => row.line).join(', ')}; an export writes one`);
    } else {
      // From the row's first line, for the longer of the two: a blank line
      // inside a snippet ends the row as parseRows splits it, but an export
      // writes it and the snippet's lines after it.
      const start = own[0].line - headerLine;
      const found = block.body.slice(start, start + Math.max(own[0].lines.length, skill.lines.length));
      const diff = firstDifference(found, skill.lines);
      if (diff) add(own[0].line + diff.index, `the ${skill.name} row is stale against ${skill.snippet}: ${describe(diff)}`);
    }
  }
  for (const [index, row] of rows.entries()) {
    const previous = rows[index - 1];
    if (previous && byNameThenVersion(previous, row) > 0) {
      add(row.line, `the ${row.name} row comes after the ${previous.name} row, but an export sorts the rows by name`);
    }
  }

  const stacks = [...skills.map((skill) => skill.stack), ...kept.map((row) => STACK_LINE.test(row.lines.join('\n')))];
  const nStack = stacks.filter(Boolean).length;
  const nSingle = stacks.length - nStack;
  const title = titleFor(block.word);
  const header = HEADER.exec(block.body[0] ?? '');
  if (header) {
    if (header[1] !== title) add(headerLine, `the header's title is [${header[1]}], an export writes [${title}]`);
    if (Number(header[2]) !== nSingle || Number(header[3]) !== nStack) {
      add(
        headerLine,
        `the header counts ${header[2]} skills and ${header[3]} stack, the exported skills make ${nSingle} skills and ${nStack} stack`,
      );
    }
  } else {
    add(headerLine, `the block does not open with its header line, [${title}]|<n> skills|<m> stack`);
  }

  // Whatever the checks above do not explain: the preamble, a separator, a stray line.
  if (findings.length === 0) {
    const rebuilt = [`[${title}]|${nSingle} skills|${nStack} stack`, ...PREAMBLE, ...skills.flatMap((skill) => ['|', ...skill.lines])];
    const diff = firstDifference(block.body, rebuilt);
    if (diff) add(headerLine + diff.index, `the block differs from what an export writes: ${describe(diff)}`);
  }
  return { findings, skills };
}

function main(argv = process.argv.slice(2), env = process.env) {
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  const annotate = env.GITHUB_ACTIONS === 'true';
  const { findings, skills } = checkIndex(root);

  for (const finding of findings) {
    const where = finding.line ? `${finding.file}:${finding.line}` : finding.file;
    console.log(`${where}: ${finding.message}`);
    if (annotate) console.log(`::error file=${finding.file}${finding.line ? `,line=${finding.line}` : ''}::${finding.message}`);
  }
  if (findings.length === 0) {
    console.log(`The context index in ${CONTEXT_FILE} matches the ${skills.length} exported reference skills.`);
    return 0;
  }
  const hint = findings.some((finding) => finding.ownFix) ? `where a finding names no fix of its own, ${HINT}` : HINT;
  console.log(`\n${findings.length} finding(s): ${hint}.`);
  return 1;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { CONTEXT_FILE, parseRows, snippetRow, checkIndex, main };
