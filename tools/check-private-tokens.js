/**
 * Private Token Check
 *
 * A local guard against pushing details of a private project into this public
 * repository. The maintainer keeps the strings that must never appear here
 * (a project's name, its keys, paths and ids) in a token list that git ignores,
 * so the list itself never reaches a commit. Without a list the check passes
 * silently: CI and other contributors never notice it.
 *
 * The list is the first that exists of:
 * - the file given with --list <file>;
 * - .private-tokens at the root of the working tree;
 * - .private-tokens at the root of the main worktree, so a push from a linked
 *   worktree is checked against the same list.
 * One token per line. Blank lines and lines starting with # are skipped.
 *
 * Matching ignores case. On each side where a token ends in a letter or a
 * digit, the text next to the match must not be a letter or a digit, so the
 * token "abc" matches "ABC-1" and "x_abc" but not "abcd", and the token "ab-"
 * matches "ab-12".
 *
 * What it checks (--pre-push, run by .husky/pre-push): the refs git hands a
 * pre-push hook on stdin. Each pushed ref's local and remote name, the message
 * of a pushed annotated tag, and, for every commit the push sends that no
 * remote-tracking ref already holds, the commit message, every line the commit
 * adds and the path of every file it adds or renames. Commits already on a
 * remote are never checked again: their history cannot change.
 *
 * Not checked, because it never passes through git push: text written on
 * GitHub itself (issue and pull request titles, bodies and comments, release
 * notes) and the merge commit GitHub writes from a pull request's branch name
 * and title.
 * --tree checks every tracked file in the working tree, and its path, instead:
 * a sweep of the current state.
 * --text checks the text on standard input, with the same matcher and the
 * same finding lines as --tree (the source is named "stdin"): pipe text through
 * it before posting it on GitHub, and post only on exit 0.
 *
 * Exit codes: 0 when nothing matched or there is no list, 1 when a token
 * matched, 2 when the check cannot run. --text exits 2 when there is no list
 * as well: a check that gates posting must not pass on a missing list.
 *
 * Usage:
 *   node tools/check-private-tokens.js --pre-push < refs   # what the hook runs
 *   node tools/check-private-tokens.js --tree              # sweep the working tree
 *   node tools/check-private-tokens.js --text < body.md    # check text before posting it
 *   node tools/check-private-tokens.js --list <file> ...   # use another list
 *   node tools/check-private-tokens.js --root <dir> ...    # check another checkout (its tests use this)
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const LIST_NAME = '.private-tokens';
const ZERO_SHA = /^0+$/;
const ALNUM = /[\dA-Za-z]/;
const HINT = 'Remove each one (git commit --amend, or a rebase for an older commit) and push again.';
const TEXT_HINT = 'Reword each one and check the text again before posting it.';

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

/**
 * Parse a token list: one token per line, blank lines and # comments skipped.
 *
 * @param {string} text - The list file's content
 * @returns {string[]} The tokens, trimmed and deduplicated
 */
function parseTokens(text) {
  const tokens = new Set();
  for (const raw of text.split(/\r?\n/)) {
    const token = raw.trim();
    if (token && !token.startsWith('#')) tokens.add(token);
  }
  return [...tokens];
}

function escapeRegExp(text) {
  return text.replaceAll(/[$()*+.?[\\\]^{|}]/g, String.raw`\$&`);
}

/**
 * Build one case-insensitive matcher for all tokens, longest first, with a
 * letter-or-digit boundary on each side where the token ends in one.
 *
 * @param {string[]} tokens
 * @returns {RegExp|null} A global matcher, or null for an empty list
 */
function buildMatcher(tokens) {
  if (tokens.length === 0) return null;
  const parts = [...tokens]
    .sort((a, b) => b.length - a.length)
    .map((token) => {
      const before = ALNUM.test(token[0]) ? String.raw`(?<![\dA-Za-z])` : '';
      const after = ALNUM.test(token.at(-1)) ? String.raw`(?![\dA-Za-z])` : '';
      return `${before}${escapeRegExp(token)}${after}`;
    });
  return new RegExp(parts.join('|'), 'gi');
}

/**
 * The distinct tokens a text holds, as they are written in the list.
 *
 * @param {string} text
 * @param {RegExp|null} matcher - From buildMatcher
 * @param {string[]} tokens - The list the matcher was built from
 * @returns {string[]}
 */
function findTokens(text, matcher, tokens) {
  if (!matcher || !text) return [];
  const found = new Set();
  for (const match of text.matchAll(matcher)) {
    const hit = match[0].toLowerCase();
    found.add(tokens.find((token) => token.toLowerCase() === hit) ?? match[0]);
  }
  return [...found];
}

function makeGit(root) {
  return (args, input) =>
    execFileSync('git', ['-c', 'core.quotePath=false', ...args], {
      cwd: root,
      encoding: 'utf8',
      input,
      maxBuffer: 256 * 1024 * 1024,
      stdio: [input === undefined ? 'ignore' : 'pipe', 'pipe', 'pipe'],
    });
}

/**
 * The token list's path, or null when there is none.
 *
 * @param {string} root - The checkout being checked
 * @param {Function} git - From makeGit(root)
 * @param {string|null} explicit - The --list value
 */
function findList(root, git, explicit) {
  if (explicit) return path.resolve(explicit);
  const candidates = [];
  try {
    candidates.push(path.join(git(['rev-parse', '--show-toplevel']).trim(), LIST_NAME));
    const common = git(['rev-parse', '--path-format=absolute', '--git-common-dir']).trim();
    candidates.push(path.join(path.dirname(common), LIST_NAME));
  } catch {
    candidates.push(path.join(root, LIST_NAME));
  }
  return candidates.find((file) => fs.existsSync(file)) ?? null;
}

/**
 * Parse `git log -p` output, one record per commit, into the lines each
 * commit adds and the paths it adds or renames.
 *
 * @param {string} log - Output of git log --format=%x1e%H -p -U0 with a/ and b/ prefixes
 * @returns {{commit: string, file: string, line: number|null, text: string}[]}
 */
function parseAddedLines(log) {
  const added = [];
  for (const record of log.split('\u001E')) {
    const [header, ...rest] = record.split('\n');
    const commit = header.trim();
    if (!commit) continue;
    let file = null;
    let lineNo = 0;
    // A `+++ ` line names the file only before a file's first hunk: inside a
    // hunk it is an added line whose text starts with "++ ".
    let inHunk = false;
    for (const raw of rest) {
      const line = raw.replace(/\r$/, '');
      if (line.startsWith('diff --git ')) {
        inHunk = false;
        file = null;
        continue;
      }
      if (!inHunk && line.startsWith('rename to ')) {
        added.push({ commit, file: line.slice(10), line: null, text: line.slice(10) });
        continue;
      }
      if (!inHunk && line.startsWith('+++ ')) {
        file = line.startsWith('+++ b/') ? line.slice(6) : null;
        if (file) added.push({ commit, file, line: null, text: file });
        continue;
      }
      if (line.startsWith('@@')) {
        inHunk = true;
        const match = /\+(\d+)/.exec(line);
        lineNo = match ? Number(match[1]) : 0;
        continue;
      }
      if (inHunk && line.startsWith('+') && file) {
        added.push({ commit, file, line: lineNo, text: line.slice(1) });
        lineNo += 1;
      }
    }
  }
  return added;
}

/**
 * The refs a pre-push hook reads on stdin, without deletions.
 *
 * @param {string} input - Lines of "<local ref> <local sha> <remote ref> <remote sha>"
 */
function parsePushedRefs(input) {
  const refs = [];
  for (const line of input.split('\n')) {
    const [localRef, localSha, remoteRef, remoteSha] = line.trim().split(/\s+/);
    if (!localSha || ZERO_SHA.test(localSha)) continue;
    refs.push({ localRef, localSha, remoteRef, remoteSha: remoteSha && !ZERO_SHA.test(remoteSha) ? remoteSha : null });
  }
  return refs;
}

/** The revision arguments for the commits a ref's push sends that no remote already holds. */
function newCommitRange(git, ref) {
  const range = [ref.localSha, '--not', '--remotes'];
  if (ref.remoteSha) {
    try {
      git(['cat-file', '-e', `${ref.remoteSha}^{commit}`]);
      range.push(ref.remoteSha);
    } catch {
      // The remote tip is not here: the remote-tracking refs bound the range.
    }
  }
  return range;
}

function checkPush(git, refs, matcher, tokens) {
  const findings = [];
  const seen = new Set();
  let commits = 0;
  for (const ref of refs) {
    // The ref names become public too: a branch name stays on its pull request for good.
    for (const name of new Set([ref.localRef, ref.remoteRef].filter(Boolean))) {
      for (const token of findTokens(name, matcher, tokens)) findings.push(`ref name ${name}: ${token}`);
    }
    // An annotated tag carries a message of its own, outside every commit.
    if (git(['cat-file', '-t', ref.localSha]).trim() === 'tag') {
      const tag = git(['cat-file', 'tag', ref.localSha]);
      const message = tag.slice(tag.indexOf('\n\n') + 2);
      for (const [index, text] of message.split('\n').entries()) {
        for (const token of findTokens(text, matcher, tokens)) {
          findings.push(`tag ${ref.remoteRef ?? ref.localRef}, message line ${index + 1}: ${token}`);
        }
      }
    }
    const range = newCommitRange(git, ref);
    const messages = git(['log', '--format=%x1e%H%x1f%B', ...range]);
    for (const record of messages.split('\u001E')) {
      const [sha, body = ''] = record.split('\u001F');
      const commit = sha.trim();
      if (!commit || seen.has(commit)) continue;
      seen.add(commit);
      commits += 1;
      for (const [index, text] of body.split('\n').entries()) {
        for (const token of findTokens(text, matcher, tokens)) {
          findings.push(`commit ${commit.slice(0, 8)}, message line ${index + 1}: ${token}`);
        }
      }
    }
    const log = git([
      'log',
      '--no-merges',
      '--format=%x1e%H',
      '-p',
      '-U0',
      '--no-color',
      '--no-ext-diff',
      '--src-prefix=a/',
      '--dst-prefix=b/',
      ...range,
    ]);
    for (const entry of parseAddedLines(log)) {
      for (const token of findTokens(entry.text, matcher, tokens)) {
        const where = entry.line === null ? `${entry.file} (file path)` : `${entry.file}:${entry.line}`;
        findings.push(`${where}, commit ${entry.commit.slice(0, 8)}: ${token}`);
      }
    }
  }
  return { findings: [...new Set(findings)], commits };
}

function checkTree(root, git, matcher, tokens) {
  const findings = [];
  const files = git(['ls-files', '-z']).split('\0').filter(Boolean);
  for (const file of files) {
    for (const token of findTokens(file, matcher, tokens)) findings.push(`${file} (file path): ${token}`);
    let buffer;
    try {
      buffer = fs.readFileSync(path.join(root, file));
    } catch {
      continue; // deleted in the working tree, or a submodule
    }
    if (buffer.includes(0)) continue; // binary
    for (const [index, text] of buffer.toString('utf8').split(/\r?\n/).entries()) {
      for (const token of findTokens(text, matcher, tokens)) findings.push(`${file}:${index + 1}: ${token}`);
    }
  }
  return { findings, files: files.length };
}

/**
 * Check a text, line by line, with the finding lines of --tree.
 *
 * @param {string} text
 * @param {RegExp|null} matcher - From buildMatcher
 * @param {string[]} tokens - The list the matcher was built from
 * @param {string} [source] - The name the finding lines give the text
 * @returns {{findings: string[], lines: number}}
 */
function checkText(text, matcher, tokens, source = 'stdin') {
  const findings = [];
  const lines = text === '' ? [] : text.replace(/\r?\n$/, '').split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    for (const token of findTokens(line, matcher, tokens)) findings.push(`${source}:${index + 1}: ${token}`);
  }
  return { findings, lines: lines.length };
}

const MODES = { '--pre-push': 'pre-push', '--tree': 'tree', '--text': 'text' };

function main(argv = process.argv.slice(2), stdin = () => fs.readFileSync(0, 'utf8')) {
  const root = path.resolve(argValue(argv, '--root') || process.cwd());
  const modes = Object.keys(MODES).filter((flag) => argv.includes(flag));
  if (modes.length !== 1) {
    console.error('usage: check-private-tokens.js --pre-push | --tree | --text [--list <file>] [--root <dir>]');
    return 2;
  }
  const mode = MODES[modes[0]];
  const git = makeGit(root);
  const explicit = argValue(argv, '--list');
  const listFile = findList(root, git, explicit);
  if (!listFile || !fs.existsSync(listFile)) {
    if (!explicit && mode !== 'text') return 0;
    console.error(
      explicit ? `error: token list ${explicit} not found.` : `error: no ${LIST_NAME} list found, so the text was not checked.`,
    );
    return 2;
  }
  const tokens = parseTokens(fs.readFileSync(listFile, 'utf8'));
  const matcher = buildMatcher(tokens);

  let result;
  let scope;
  try {
    if (mode === 'tree') {
      result = checkTree(root, git, matcher, tokens);
      scope = `${result.files} tracked file(s)`;
    } else if (mode === 'text') {
      result = checkText(stdin(), matcher, tokens);
      scope = `${result.lines} line(s) of standard input`;
    } else {
      result = checkPush(git, parsePushedRefs(stdin()), matcher, tokens);
      scope = `${result.commits} new commit(s)`;
    }
  } catch (error) {
    console.error(`error: private token check could not run: ${error.message.split('\n')[0]}`);
    return 2;
  }

  const listName = path.basename(listFile);
  if (result.findings.length === 0) {
    console.log(`Private token check: no token from ${listName} in ${scope}.`);
    return 0;
  }
  console.log(`Private token check: ${result.findings.length} finding(s) from ${listName} in ${scope}:`);
  for (const finding of result.findings) console.log(`  ${finding}`);
  if (mode === 'pre-push') console.log(HINT);
  if (mode === 'text') console.log(TEXT_HINT);
  return 1;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { parseTokens, buildMatcher, findTokens, parseAddedLines, parsePushedRefs, checkText, main };
