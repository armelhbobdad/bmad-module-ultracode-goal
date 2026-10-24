/**
 * UCG Status Command
 * Shows installation state, version, configured IDEs, and skill integrity.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { readManifest } = require('../lib/manifest');
const { getAvailablePlatforms, loadPlatforms, UCG_SKILLS } = require('../lib/ide-skills');
const { compareTrees } = require('../lib/skill-parity');

const packageJson = require('../../../package.json');

const UCG_FOLDER = '_bmad/ucg';
const SKILL_NAME = 'ultracode-goal';

function getIdeNames() {
  const names = { other: 'Other' };
  for (const p of getAvailablePlatforms()) {
    names[p.value] = p.label;
  }
  return names;
}

async function readYaml(filePath) {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    return yaml.load(content) || {};
  } catch {
    return null;
  }
}

async function getStatus(projectDir) {
  const ucgDir = path.join(projectDir, UCG_FOLDER);
  const skillDir = path.join(ucgDir, SKILL_NAME);

  const installed = await fs.pathExists(ucgDir);
  if (!installed) {
    return { installed: false };
  }

  // Read config
  const config = await readYaml(path.join(ucgDir, 'config.yaml'));

  // Read installed version
  let installedVersion = null;
  try {
    installedVersion = (await fs.readFile(path.join(ucgDir, 'VERSION'), 'utf8')).trim();
  } catch {
    /* keep null */
  }

  // Skill integrity: SKILL.md, stage references, deterministic scripts, hooks
  const skillInstalled = await fs.pathExists(path.join(skillDir, 'SKILL.md'));

  let referenceCount = 0;
  const referencesDir = path.join(skillDir, 'references');
  if (await fs.pathExists(referencesDir)) {
    const entries = await fs.readdir(referencesDir);
    referenceCount = entries.filter((entry) => entry.endsWith('.md')).length;
  }

  const gateScript = await fs.pathExists(path.join(skillDir, 'scripts', 'gate_eval.py'));
  const preflightScript = await fs.pathExists(path.join(skillDir, 'scripts', 'preflight_check.py'));
  const hooksPresent = await fs.pathExists(path.join(skillDir, 'scripts', 'hooks'));

  // Learning material
  const learnInstalled = await fs.pathExists(path.join(projectDir, '_ucg-learn'));

  // Read manifest
  const manifest = await readManifest(projectDir);

  // Content parity against the CLI's own bundled source. Presence checks above
  // cannot see a truncated, hand-edited, or releases-behind file; this can.
  //
  // Every skill the installer copies, not only `ultracode-goal`: preflight
  // refuses to launch without `ucg-create-story` or `ucg-dev-story`, so a
  // status that checked one skill read green on a project whose every run
  // stops at preflight.
  const srcSkillsDir = path.join(path.resolve(__dirname, '..', '..', '..'), 'skills');
  const unverifiable = (dir, error) => ({
    present: true,
    ok: null,
    missing: [],
    drifted: [],
    extra: [],
    extraContent: [],
    unreadable: [{ path: dir, code: error.code || 'EUNKNOWN' }],
  });
  // Parity is a diagnostic row, never a reason for `status` to die. Losing the
  // version, manifest and presence rows because one file is permission-damaged
  // trades a whole report for one unreadable byte.
  const inspectCopy = async (name, installedDir, label, kind) => {
    const entry = { dir: label, installed: await fs.pathExists(path.join(installedDir, 'SKILL.md')) };
    try {
      Object.assign(entry, await compareTrees(path.join(srcSkillsDir, name), installedDir, kind));
    } catch (error) {
      Object.assign(entry, unverifiable(label, error));
    }
    return entry;
  };

  // Every configured platform, NOT config.ides. On update the installer sets
  // `ides` in memory but writeConfig restores the saved config.yaml verbatim, so
  // the on-disk list can be empty (older installs never persisted it) on a
  // project that provably HAS an IDE copy. Reading it here would skip exactly
  // the stale copy this check exists to catch.
  let platforms = {};
  try {
    platforms = loadPlatforms().platforms || {};
  } catch {
    /* platform config unreadable: report the module copy alone */
  }
  const targets = Object.entries(platforms)
    .map(([code, platform]) => ({ code, targetDir: platform?.installer?.target_dir }))
    .filter((target) => target.targetDir);

  const skills = [];
  for (const name of UCG_SKILLS) {
    const skill = { name, module: await inspectCopy(name, path.join(ucgDir, name), UCG_FOLDER + '/' + name, 'module'), ides: [] };
    // Per platform, NOT around the loop. A catch spanning the whole loop drops
    // the failing platform AND every platform after it, and a copy that renders
    // no row at all is a false green on the one surface built to expose staleness.
    for (const { code, targetDir } of targets) {
      const entry = await inspectCopy(name, path.join(projectDir, targetDir, name), path.join(targetDir, name), 'ide');
      skill.ides.push({ ide: code, ...entry });
    }
    skills.push(skill);
  }
  // The `ultracode-goal` rows, in the shape older readers of getStatus know.
  const main = skills.find((skill) => skill.name === SKILL_NAME);
  const skillParity = { module: main.module, ides: main.ides };

  const versionMatch = installedVersion !== null && installedVersion === packageJson.version;

  return {
    installed: true,
    config,
    installedVersion,
    skillInstalled,
    referenceCount,
    gateScript,
    preflightScript,
    hooksPresent,
    learnInstalled,
    manifest,
    skills,
    skillParity,
    versionMatch,
  };
}

/** The Installation row: is every UCG skill's module copy there, with its SKILL.md? */
function skillsRow(status) {
  const skills = status.skills || [];
  if (skills.length === 0) return status.skillInstalled ? chalk.green('installed') : chalk.yellow('not installed');
  const absent = skills.filter((skill) => !skill.module.installed).map((skill) => skill.name);
  if (absent.length === 0) return `${chalk.green('installed')} ${chalk.dim(`(${skills.length} skills)`)}`;
  if (absent.length === skills.length) return chalk.yellow('not installed');
  return `${chalk.yellow(`${skills.length - absent.length} of ${skills.length} installed`)} ${chalk.dim(`(missing: ${absent.join(', ')})`)}`;
}

/** What is wrong with one skill's copy, for the row beneath its copy's verdict. */
function describeProblem(entry) {
  if (!entry.present) return chalk.yellow('not installed');
  if (!entry.installed) return `${chalk.yellow('not installed')} ${chalk.dim('(no SKILL.md)')}`;
  if (entry.ok === null) {
    const first = (entry.unreadable || [])[0];
    const detail = first
      ? `${entry.unreadable.length} path(s) unreadable, first: ${first.path} (${first.code})`
      : 'tree could not be fully read';
    return `${chalk.yellow('unverifiable')} ${chalk.dim(`(${detail})`)}`;
  }
  const parts = [];
  if (entry.missing.length > 0) parts.push(`${entry.missing.length} missing`);
  if (entry.drifted.length > 0) parts.push(`${entry.drifted.length} changed`);
  if (entry.extraContent.length > 0) parts.push(`${entry.extraContent.length} stale`);
  return chalk.yellow(parts.join(', '));
}

function displayStatus(status, version) {
  console.log('');
  console.log(chalk.hex('#6366F1').bold('  UltraCode Goal — Status'));
  console.log(chalk.dim(`  v${version}`));
  console.log('');

  if (!status.installed) {
    console.log(chalk.yellow('  Not installed.'));
    console.log(chalk.dim('  Run: npx bmad-module-ultracode-goal install'));
    console.log('');
    return;
  }

  const config = status.config || {};

  // Installation
  const manifest = status.manifest;
  console.log(chalk.white.bold('  Installation'));
  console.log(`    Project:      ${chalk.hex('#818CF8')(config.project_name || '(unknown)')}`);
  console.log(`    UCG folder:   ${chalk.dim(UCG_FOLDER + '/')}`);
  console.log(`    Version:      ${status.installedVersion ? chalk.white(status.installedVersion) : chalk.yellow('(unknown)')}`);
  console.log(`    Skills:       ${skillsRow(status)}`);
  if (manifest) {
    console.log(
      `    Installed:    ${chalk.dim(manifest.installed_at ? new Date(manifest.installed_at).toLocaleDateString() : '(unknown)')}`,
    );
    console.log(`    Manifest:     ${chalk.green('present')}`);
  } else {
    console.log(`    Manifest:     ${chalk.yellow('missing')} ${chalk.dim('(reinstall to generate)')}`);
  }
  console.log('');

  // Skill integrity
  console.log(chalk.white.bold('  Skill Integrity'));
  console.log(`    Stages:       ${chalk.white(status.referenceCount)} ${chalk.dim('reference files')}`);
  console.log(`    gate_eval:    ${status.gateScript ? chalk.green('present') : chalk.red('missing')}`);
  console.log(`    preflight:    ${status.preflightScript ? chalk.green('present') : chalk.red('missing')}`);
  console.log(`    hooks:        ${status.hooksPresent ? chalk.green('present') : chalk.red('missing')}`);

  // Content parity. Presence above says a file exists; this says it is the file
  // this CLI ships. A stale copy passes every presence row and fails here.
  // One row per copy, covering every UCG skill in it; a copy with a problem
  // lists each skill that has one beneath its row.
  const skills = status.skills || [];
  if (skills.length > 0) {
    const copies = [
      { label: 'module copy', dir: UCG_FOLDER, entries: skills.map((skill) => ({ name: skill.name, ...skill.module })) },
      ...skills[0].ides.map(({ ide, dir }) => ({
        label: ide,
        dir: path.dirname(dir),
        entries: skills.map((skill) => ({ name: skill.name, ...skill.ides.find((entry) => entry.ide === ide) })),
      })),
    ];
    // Deliberately NOT phrased as tampering. When the versions match, the
    // ordinary cause is a source tree that moved ahead of the install, which
    // is the normal state in the repo that develops this module.
    const cause =
      status.versionMatch === false && status.installedVersion
        ? `installed v${status.installedVersion}, this CLI is v${version}`
        : "differs from this CLI's bundled source";
    let anyStale = false;
    for (const copy of copies) {
      const name = `${copy.label}:`.padEnd(14);
      if (!copy.entries.some((entry) => entry.present)) {
        console.log(`    ${name}${chalk.dim('not installed')} ${chalk.dim(copy.dir)}`);
        continue;
      }
      const problems = copy.entries.filter((entry) => !entry.installed || entry.ok !== true);
      if (problems.length === 0) {
        console.log(`    ${name}${chalk.green('matches source')} ${chalk.dim(`(${copy.entries.length} skills)`)}`);
        continue;
      }
      // A skill missing from a copy that holds the others is out of sync: it is
      // the skill a run looks for and does not find.
      const stale = problems.some((entry) => !entry.installed || entry.ok === false);
      anyStale = anyStale || stale;
      // Neither pass nor fail when only unreadable paths stand in the way: any
      // verdict would be invented. Say so rather than picking the comfortable one.
      const verdict = stale ? `${chalk.yellow('out of sync')} ${chalk.dim(`(${cause})`)}` : chalk.yellow('unverifiable');
      console.log(`    ${name}${verdict}`);
      for (const entry of problems) {
        console.log(`${' '.repeat(18)}${entry.name}: ${describeProblem(entry)}`);
      }
    }
    if (anyStale) {
      console.log('');
      console.log(chalk.dim('    A copy that differs from source is the copy your runs actually load.'));
      console.log(chalk.dim(`    Refresh with: ${chalk.reset(chalk.dim.bold('npx bmad-module-ultracode-goal update'))}`));
    }
  }
  console.log('');

  // IDEs
  const ides = config.ides || [];
  const ideNames = getIdeNames();
  console.log(chalk.white.bold('  IDEs'));
  if (ides.length > 0) {
    for (const ide of ides) {
      console.log(`    ${chalk.green('●')} ${ideNames[ide] || ide}`);
    }
  } else {
    console.log(chalk.dim('    None configured'));
  }
  console.log('');

  // Learning material
  console.log(chalk.white.bold('  Learning Material'));
  console.log(`    _ucg-learn/:  ${status.learnInstalled ? chalk.green('installed') : chalk.dim('not installed')}`);
  console.log('');
}

module.exports = {
  command: 'status',
  description: 'Show UCG installation state, version, and configuration',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const status = await getStatus(projectDir);
      displayStatus(status, packageJson.version);
    } catch (error) {
      console.error(chalk.red('\nFailed to read status:'), error.message);
      process.exit(1);
    }
  },
  // Exported for the integration suite: parity is asserted against a real
  // install, not against the rendered string.
  getStatus,
  displayStatus,
};
