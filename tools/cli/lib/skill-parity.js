/**
 * Skill Parity - content comparison between shipped source and an installed copy.
 *
 * Why this exists: `ucg status` decided "Skill Integrity" with four
 * `fs.pathExists` calls and a filename count. A truncated, hand-edited, or
 * several-releases-behind `gate_eval.py` was indistinguishable from a
 * byte-perfect one on every surface in the repo.
 *
 * That is not hypothetical. A run opened with the loaded skill copy one merge
 * behind source: its `formalize_check.py` was missing a readiness guard entirely,
 * so it returned `ready` for an eight-story Epic with zero story files on disk,
 * which is the exact verdict preflight's hard gate reads. `gate_trail.py` was
 * absent outright. `ucg status` reported `installed` with every integrity row
 * `present` throughout, because presence is all it ever checked.
 *
 * The reference tree is the CLI's OWN bundled `skills/`, resolved the same way
 * the Installer resolves it. In a user's project that is the published package's
 * copy, so drift means tamper or a half-finished update. In this repo it IS
 * tracked source, so drift means the install is behind the working tree, which is
 * the stale-mirror condition that motivated the check. An install-time checksum
 * manifest would catch neither: it only proves the tree is unchanged since
 * install, and says nothing about whether install was ever current.
 *
 * Comparison is over raw bytes (sha256). Safe because the installer writes
 * nothing inside the copied skill directory after the copy - every post-copy
 * write lands at the install root (config.yaml, VERSION, manifest).
 */

const path = require('node:path');
const crypto = require('node:crypto');
const fs = require('fs-extra');

const { shippedCopyFilter } = require('./installer');
const { ARTIFACT_FILTER } = require('./ide-skills');

/**
 * Files whose absence from source is a real problem (deletion drift), as opposed
 * to incidental runtime residue. A reference or script deleted from source but
 * still sitting in an installed copy stays loadable by the conductor, and
 * `status` prints a raw reference COUNT, so a stale extra silently inflates it
 * and reads green. Anything else extra is reported but not failed, so a stray
 * runtime write cannot brick the signal.
 */
function isContentPath(relPath) {
  const normalized = relPath.split(path.sep).join('/');
  if (normalized.startsWith('references/') && normalized.endsWith('.md')) return true;
  if (normalized.startsWith('scripts/') && normalized.endsWith('.py')) return true;
  return false;
}

/**
 * The predicate for walking a tree destined for a given copy.
 *
 * The two copies are NOT filtered identically, and assuming they are produces
 * false `missing` entries. The module copy is source filtered by the installer's
 * own rule. The IDE copy is made FROM the module copy and filtered again by a
 * separate OS-artifact set, so it excludes strictly more.
 *
 * @param {'module'|'ide'} kind
 */
function walkFilter(kind) {
  return (fullPath) => {
    if (!shippedCopyFilter(fullPath)) return false;
    if (kind === 'ide' && ARTIFACT_FILTER.has(path.basename(fullPath))) return false;
    return true;
  };
}

/**
 * Walk a tree into {relative path -> sha256}, recording any path it could not read.
 *
 * Every I/O failure is RECORDED, never silently absorbed. An earlier version
 * caught readdir and returned the partial map, which made "unreadable subtree"
 * indistinguishable from "empty subtree" and produced both failure modes at once:
 * drift inside an unreadable SOURCE subtree read as ok (the files became
 * non-failing `extra`), while an unreadable source ROOT made a byte-perfect
 * install look out of sync. readFile was not guarded at all, so a single
 * permission-damaged file aborted the whole status command.
 *
 * Callers must treat a non-empty `errors` as UNVERIFIABLE — not as pass, and not
 * as fail. Those are three different answers and collapsing any two of them is
 * how this check would lie.
 */
async function collect(dir, filter, base = dir, out = new Map(), errors = []) {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch (error) {
    errors.push({ path: dir, code: error.code || 'EUNKNOWN' });
    return out;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (!filter(full)) continue;
    if (entry.isDirectory()) {
      await collect(full, filter, base, out, errors);
    } else if (entry.isFile()) {
      try {
        const buf = await fs.readFile(full);
        out.set(path.relative(base, full).split(path.sep).join('/'), crypto.createHash('sha256').update(buf).digest('hex'));
      } catch (error) {
        errors.push({ path: full, code: error.code || 'EUNKNOWN' });
      }
    }
  }
  return out;
}

/**
 * Compare an installed skill copy against the shipped source tree.
 *
 * @param {string} sourceDir   - the CLI's bundled skills/<name>
 * @param {string} installedDir - the copy to check
 * @param {'module'|'ide'} kind - which filter the copy was made under
 * @returns {Promise<{present: boolean, ok: boolean|null, missing: string[], drifted: string[], extra: string[], extraContent: string[]}>}
 */
async function compareTrees(sourceDir, installedDir, kind = 'module') {
  if (!(await fs.pathExists(installedDir))) {
    // Absent is "not installed", never red. `ok: null` so a caller cannot read
    // a missing copy as a passing one.
    return { present: false, ok: null, missing: [], drifted: [], extra: [], extraContent: [], unreadable: [] };
  }

  const filter = walkFilter(kind);
  const unreadable = [];
  const source = await collect(sourceDir, filter, sourceDir, new Map(), unreadable);
  const installed = await collect(installedDir, filter, installedDir, new Map(), unreadable);

  const missing = [];
  const drifted = [];
  for (const [rel, digest] of source) {
    const other = installed.get(rel);
    if (other === undefined) missing.push(rel);
    else if (other !== digest) drifted.push(rel);
  }

  const extra = [];
  for (const rel of installed.keys()) {
    if (!source.has(rel)) extra.push(rel);
  }
  const extraContent = extra.filter(isContentPath);

  missing.sort();
  drifted.sort();
  extra.sort();
  extraContent.sort();

  return {
    present: true,
    // THREE outcomes, not two. `null` means the walk was incomplete, so no
    // verdict is honest: a clean-looking result could be hiding drift inside the
    // part that could not be read, and a dirty-looking one could be an artefact
    // of the same gap. Never collapse this into true (a false green, which is
    // the exact failure this whole check exists to remove) or into false (which
    // would cry wolf on a byte-perfect install).
    ok: unreadable.length > 0 ? null : missing.length === 0 && drifted.length === 0 && extraContent.length === 0,
    missing,
    drifted,
    extra,
    extraContent,
    unreadable,
  };
}

module.exports = { compareTrees, isContentPath, walkFilter };
