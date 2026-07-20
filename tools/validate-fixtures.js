/**
 * Fixture Tracking Validator
 *
 * Fails when a test fixture is matched by a .gitignore rule.
 *
 * Why this exists: `git add` on an ignored path is a SILENT no-op. The file stays
 * on disk, so the suite reads it and passes locally, while the commit never
 * carries it and CI checks out a tree where it does not exist. That is a green
 * local run and a red CI run with no diff between them to explain it.
 *
 * It has happened here. Three fixtures under a run-folder matched a repo-wide
 * recursive-glob rule on `.decision-log.md` and were dropped from the commit
 * without a word; the suite was green locally off files on disk, and CI failed on
 * both platforms with an empty runs index. The root fix was a negated .gitignore rule
 * exempting the fixture tree, but nothing machine-checked it, so the next fixture
 * that mimics a local-only artifact (a dotfile, a marker, a run sentinel) would
 * repeat it silently.
 *
 * This check is deliberately about IGNORE STATUS, not tracked status. An ignored
 * fixture is always a bug: either the fixture is misnamed, or .gitignore needs a
 * negation. A merely-untracked fixture is just a file the author has not committed
 * yet, which is normal mid-edit and not this tool's business.
 *
 * Usage:
 *   node tools/validate-fixtures.js            # Warn (exit 0)
 *   node tools/validate-fixtures.js --strict   # Fail on ignored fixtures (exit 1)
 */

const path = require('node:path');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

const STRICT = process.argv.includes('--strict');
const VERBOSE = process.argv.includes('--verbose');

const REPO_ROOT = path.resolve(__dirname, '..');

// Fixture roots to police. Add a directory here and its whole subtree is covered.
const FIXTURE_ROOTS = ['skills/ultracode-goal/scripts/tests/fixtures'];

// Generated artifacts that live INSIDE the fixture tree but are not fixtures.
// These are correctly ignored, and flagging them would make the check cry wolf on
// every machine that has run the suite. Mirrors the installer's own dev-artifact
// exclusions. Directory names are matched as whole path segments, so a fixture
// legitimately named e.g. `pycache-repro.md` is unaffected.
const GENERATED_DIRS = new Set(['__pycache__', '.pytest_cache', '.ruff_cache', 'node_modules']);
const GENERATED_FILES = /\.(pyc|pyo)$|^\.DS_Store$|^desktop\.ini$/;

function collectFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (GENERATED_DIRS.has(entry.name)) continue;
      out.push(...collectFiles(full));
    } else if (!GENERATED_FILES.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Return the subset of `paths` that git considers ignored.
 *
 * `git check-ignore` exits 1 when NOTHING matches, which is the success case here
 * and must not be read as a failure. Paths are fed on stdin so a large fixture
 * tree cannot blow the argv limit.
 */
function ignoredPaths(paths) {
  if (paths.length === 0) return [];
  try {
    const out = execFileSync('git', ['check-ignore', '--stdin'], {
      cwd: REPO_ROOT,
      input: paths.join('\n'),
      encoding: 'utf8',
    });
    return out.split('\n').filter(Boolean);
  } catch (error) {
    // Exit 1 with empty output = no path matched an ignore rule. Anything else
    // (git missing, not a repo) is a real failure and must not read as a pass.
    if (error.status === 1 && !error.stdout) return [];
    throw new Error(`git check-ignore failed: ${error.message}`);
  }
}

function main() {
  console.log('');
  console.log(`Validating fixture tracking in: ${REPO_ROOT}`);
  console.log(`Mode: ${STRICT ? 'STRICT (exit 1 on issues)' : 'WARN (exit 0)'}`);
  console.log('');

  const files = [];
  for (const root of FIXTURE_ROOTS) {
    const abs = path.join(REPO_ROOT, root);
    if (!fs.existsSync(abs)) {
      console.log(`   Fixture root missing, skipped: ${root}`);
      continue;
    }
    files.push(...collectFiles(abs).map((f) => path.relative(REPO_ROOT, f)));
  }

  const ignored = ignoredPaths(files);

  if (VERBOSE) {
    for (const file of files) console.log(`   checked  ${file}`);
  }

  console.log(''.padEnd(60, '─'));
  console.log('');
  console.log('Summary:');
  console.log(`   Fixture roots:   ${FIXTURE_ROOTS.length}`);
  console.log(`   Files scanned:   ${files.length}`);
  console.log(`   Ignored files:   ${ignored.length}`);
  console.log('');

  if (ignored.length > 0) {
    console.log('   Fixtures matched by a .gitignore rule:');
    console.log('');
    for (const file of ignored) {
      let rule = '(rule unknown)';
      try {
        rule = execFileSync('git', ['check-ignore', '-v', file], {
          cwd: REPO_ROOT,
          encoding: 'utf8',
        })
          .split('\t')[0]
          .trim();
      } catch {
        /* keep the placeholder */
      }
      console.log(`     ${file}`);
      console.log(`       ignored by  ${rule}`);
    }
    console.log('');
    console.log('   Staging an ignored path is a silent no-op, so this fixture would');
    console.log('   be dropped from the commit while the local suite still reads it');
    console.log('   off disk. Add a negation to .gitignore (see the fixture-tree');
    console.log('   exemptions already there), or rename the fixture.');
    console.log('');
  } else {
    console.log('   All fixtures are trackable!');
    console.log('');
  }

  if (process.env.GITHUB_STEP_SUMMARY) {
    let summary = '## Fixture Tracking Validation\n\n';
    if (ignored.length > 0) {
      summary += '| Ignored fixture |\n|------|\n';
      for (const file of ignored) summary += `| ${file} |\n`;
      summary += '\n';
    }
    summary += `**${files.length} fixtures scanned, ${ignored.length} matched by a .gitignore rule**\n`;
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
  }

  process.exit(ignored.length > 0 && STRICT ? 1 : 0);
}

main();
