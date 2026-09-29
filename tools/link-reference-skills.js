/**
 * Reference Skill Linker
 *
 * Links every generated reference skill under skf-skills/ into .claude/skills/,
 * so a Claude Code session in this checkout can load it.
 *
 * Why this exists: Claude Code loads project skills only from
 * .claude/skills/<name>/SKILL.md, and .claude/ is gitignored here. The reference
 * skills are tracked under skf-skills/<group>/<version>/<group>/ instead, where no
 * session discovers them on its own. A link per skill closes that gap without
 * committing anything under .claude/, and because each link goes through the
 * group's `active` pointer, it never goes stale when a new version is made active.
 *
 * Ownership: the linker creates, updates and removes only entries that are links
 * into skf-skills/. A real directory or a link to anywhere else that happens to
 * share a skill's name (the BMAD installer's copies, a copy made by
 * `npx skills add`) is left alone and reported as skipped. It refuses to run when
 * .claude or .claude/skills is itself a link, because its relative links would
 * then resolve from somewhere else, possibly another checkout.
 *
 * Windows: unless core.symlinks is enabled, git checks a tracked symlink out as a
 * plain file holding its target, so `active` then contains the version as text,
 * and the linker links that version's folder directly. Directory symlinks can also
 * need Developer Mode or admin rights, so the linker falls back to a junction,
 * which needs neither but must hold an absolute path. Re-run it after `active`
 * changes on such a checkout.
 *
 * Usage:
 *   node tools/link-reference-skills.js           # link and print a summary
 *   node tools/link-reference-skills.js --quiet   # npm postprepare: silent unless something
 *                                                 # was skipped, and never fails the install
 *   node tools/link-reference-skills.js --check   # change nothing; exit 1 if a link is missing,
 *                                                 # stale or blocked
 */

const fs = require('node:fs');
const path = require('node:path');

const SOURCE_DIR = 'skf-skills';
const TARGET_DIR = path.join('.claude', 'skills');

// Windows paths compare without regard to case: `c:\repo` and `C:\repo` are the same folder.
const comparable = (p) => (process.platform === 'win32' ? p.toLowerCase() : p);

/**
 * Read a SKILL.md frontmatter `name`, or null when there is none.
 *
 * @param {string} skillMd - Absolute path to SKILL.md
 * @returns {string|null} The declared name
 */
function frontmatterName(skillMd) {
  const text = fs.readFileSync(skillMd, 'utf8');
  const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!block) return null;
  const line = /^name:\s*['"]?([^'"\r\n]+?)['"]?\s*$/m.exec(block[1]);
  return line ? line[1].trim() : null;
}

/**
 * Resolve the version a group's `active` entry names.
 *
 * @param {string} activePath - Absolute path to <group>/active
 * @returns {{version: string, viaLink: boolean}|null} The version, and whether `active` is a real link
 */
function readActive(activePath) {
  let stat;
  try {
    stat = fs.lstatSync(activePath);
  } catch {
    return null;
  }
  if (stat.isSymbolicLink()) {
    return { version: path.basename(fs.readlinkSync(activePath)), viaLink: true };
  }
  if (stat.isFile()) {
    // A symlink checked out as a plain file (git on Windows without core.symlinks).
    const version = fs.readFileSync(activePath, 'utf8').trim();
    return version && !/[\\/]/.test(version) ? { version, viaLink: false } : null;
  }
  return null;
}

/**
 * List the reference skills to link, one per group with a usable `active` entry.
 *
 * @param {string} repoRoot - Checkout root
 * @returns {{skills: object[], ignored: string[]}} Skills to link, and groups that could not be resolved
 */
function discoverSkills(repoRoot) {
  const sourceRoot = path.join(repoRoot, SOURCE_DIR);
  const skills = [];
  const ignored = [];
  if (!fs.existsSync(sourceRoot)) return { skills, ignored };

  // Sorted, so that when two groups declare the same name the same one wins every run.
  const entries = fs.readdirSync(sourceRoot, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    // _batch/ and dot entries hold run records and markers, not skills.
    if (!entry.isDirectory() || entry.name.startsWith('_') || entry.name.startsWith('.')) continue;
    const group = entry.name;
    const active = readActive(path.join(sourceRoot, group, 'active'));
    const versionDir = active && path.join(sourceRoot, group, active.version, group);
    const skillMd = versionDir && path.join(versionDir, 'SKILL.md');
    if (!skillMd || !fs.existsSync(skillMd)) {
      ignored.push(group);
      continue;
    }
    skills.push({
      group,
      version: active.version,
      name: frontmatterName(skillMd) || group,
      versionDir,
      // Relative, through `active`, so the link follows the active version on its own.
      linkTarget: active.viaLink ? path.join('..', '..', SOURCE_DIR, group, 'active', group) : null,
    });
  }
  return { skills, ignored };
}

/**
 * Whether a link resolves to somewhere inside this checkout's skf-skills/.
 *
 * @param {string} linkPath - Absolute path of the link
 * @param {string} repoRoot - Checkout root
 * @returns {boolean} True when the linker owns this entry
 */
function isOwnedLink(linkPath, repoRoot) {
  const raw = fs.readlinkSync(linkPath).replace(/^\\\\\?\\/, '');
  const resolved = path.resolve(path.dirname(linkPath), raw);
  const sourceRoot = path.join(repoRoot, SOURCE_DIR) + path.sep;
  return comparable(resolved + path.sep).startsWith(comparable(sourceRoot));
}

/**
 * Refuse a .claude or .claude/skills that is itself a link (or junction): links
 * written into it would resolve from its real location, not from this checkout.
 *
 * @param {string} repoRoot - Checkout root
 */
function assertLocalTarget(repoRoot) {
  for (const rel of ['.claude', TARGET_DIR]) {
    let stat = null;
    try {
      stat = fs.lstatSync(path.join(repoRoot, rel));
    } catch {
      stat = null;
    }
    if (stat && stat.isSymbolicLink()) {
      throw new Error(`${rel} is a link, so links written into it would not resolve inside this checkout. Make it a real folder.`);
    }
  }
}

/**
 * The directory a link finally resolves to, or null when it dangles.
 *
 * @param {string} linkPath - Absolute path of the link
 * @returns {string|null} Real path of the target
 */
function realTarget(linkPath) {
  try {
    return fs.realpathSync(linkPath);
  } catch {
    return null;
  }
}

/**
 * Remove a link without following it. Junctions on Windows refuse unlink, so
 * fall back to rmdir, which removes the junction and never its target.
 *
 * @param {string} linkPath - Absolute path of the link
 */
function removeLink(linkPath) {
  try {
    fs.unlinkSync(linkPath);
  } catch (error) {
    if (!['EPERM', 'EISDIR'].includes(error.code)) throw error;
    fs.rmdirSync(linkPath);
  }
}

/**
 * Create a directory link, falling back to a junction where symlinks are not allowed.
 *
 * @param {object} skill - Entry from discoverSkills
 * @param {string} dest - Absolute path of the link to create
 */
function createLink(skill, dest) {
  // Relative either way, so the link survives moving the checkout.
  const target = skill.linkTarget || path.relative(path.dirname(dest), skill.versionDir);
  try {
    fs.symlinkSync(target, dest, 'dir');
    return;
  } catch (error) {
    if (!['EPERM', 'EACCES', 'ENOTSUP', 'ENOSYS'].includes(error.code)) throw error;
  }
  // Junctions need an absolute target and cannot go through `active`, so they
  // point at the resolved version folder.
  fs.symlinkSync(skill.versionDir, dest, 'junction');
}

/**
 * Bring .claude/skills/ in line with the active reference skills.
 *
 * @param {{repoRoot: string, check?: boolean}} options - Checkout root; `check` reports without changing anything
 * @returns {{linked: string[], updated: string[], unchanged: string[], removed: string[], skipped: object[], ignored: string[], problems: string[]}} What happened, per skill name
 */
function run({ repoRoot, check = false }) {
  const result = { linked: [], updated: [], unchanged: [], removed: [], skipped: [], ignored: [], problems: [] };
  const { skills, ignored } = discoverSkills(repoRoot);
  result.ignored = ignored;
  assertLocalTarget(repoRoot);

  const targetRoot = path.join(repoRoot, TARGET_DIR);
  if (!check && skills.length > 0) fs.mkdirSync(targetRoot, { recursive: true });
  const claimedBy = new Map();

  for (const skill of skills) {
    const where = path.join(TARGET_DIR, skill.name);
    const first = claimedBy.get(skill.name);
    if (first) {
      result.skipped.push({
        name: skill.name,
        reason: `${SOURCE_DIR}/${first} already declares that name, so ${SOURCE_DIR}/${skill.group} is left out`,
      });
      if (check) result.problems.push(`${skill.name}: ${result.skipped.at(-1).reason}`);
      continue;
    }
    claimedBy.set(skill.name, skill.group);
    const dest = path.join(targetRoot, skill.name);
    let stat = null;
    try {
      stat = fs.lstatSync(dest);
    } catch {
      stat = null;
    }

    if (!stat) {
      if (check) result.problems.push(`${skill.name}: not linked`);
      else {
        createLink(skill, dest);
        result.linked.push(skill.name);
      }
      continue;
    }
    if (!stat.isSymbolicLink() || !isOwnedLink(dest, repoRoot)) {
      const kind = stat.isSymbolicLink() ? 'a link to somewhere else' : 'a real directory';
      result.skipped.push({ name: skill.name, reason: `${where} is ${kind}; remove it and run \`npm run skills:link\`` });
      if (check) result.problems.push(`${skill.name}: blocked, ${where} is ${kind}`);
      continue;
    }
    const current = realTarget(dest);
    if (current && comparable(current) === comparable(fs.realpathSync(skill.versionDir))) {
      result.unchanged.push(skill.name);
      continue;
    }
    if (check) result.problems.push(`${skill.name}: points at an inactive version`);
    else {
      removeLink(dest);
      createLink(skill, dest);
      result.updated.push(skill.name);
    }
  }

  // Drop our own links to skills that no longer exist, including the last one.
  if (fs.existsSync(targetRoot)) {
    for (const entry of fs.readdirSync(targetRoot)) {
      if (claimedBy.has(entry)) continue;
      const dest = path.join(targetRoot, entry);
      if (!fs.lstatSync(dest).isSymbolicLink() || !isOwnedLink(dest, repoRoot)) continue;
      if (check) result.problems.push(`${entry}: stale link`);
      else {
        removeLink(dest);
        result.removed.push(entry);
      }
    }
  }
  return result;
}

/**
 * One-line summary of a run.
 *
 * @param {object} result - Return value of run()
 * @returns {string} Human-readable summary
 */
function summarize(result) {
  const parts = [
    `${result.linked.length} linked`,
    `${result.updated.length} updated`,
    `${result.unchanged.length} unchanged`,
    `${result.removed.length} removed`,
  ];
  return `Reference skills in ${TARGET_DIR}: ${parts.join(', ')}.`;
}

function main() {
  const quiet = process.argv.includes('--quiet');
  const check = process.argv.includes('--check');
  const repoRoot = path.resolve(__dirname, '..');
  try {
    const result = run({ repoRoot, check });
    for (const { name, reason } of result.skipped) console.warn(`Reference skill ${name} not linked: ${reason}.`);
    if (check) {
      for (const problem of result.problems) console.log(`  ${problem}`);
      console.log(
        result.problems.length === 0 ? 'All reference skills are linked.' : `${result.problems.length} reference skill link problem(s).`,
      );
      process.exit(result.problems.length === 0 ? 0 : 1);
    }
    if (!quiet) {
      console.log(summarize(result));
      for (const group of result.ignored) console.log(`  skipped ${SOURCE_DIR}/${group}: no active version with a SKILL.md`);
    }
  } catch (error) {
    // From npm's postprepare hook a failure here must never break `npm install`.
    console.warn(`Reference skills were not linked: ${error.message}`);
    process.exit(quiet ? 0 : 1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { discoverSkills, readActive, frontmatterName, run, summarize };
