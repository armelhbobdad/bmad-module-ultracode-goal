/**
 * UCG Status Command
 * Shows installation state, version, configured IDEs, and skill integrity.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { readManifest } = require('../lib/manifest');
const { getAvailablePlatforms, loadPlatforms } = require('../lib/ide-skills');
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
  const srcSkillDir = path.join(path.resolve(__dirname, '..', '..', '..'), 'skills', SKILL_NAME);
  const unverifiable = (dir, error) => ({
    present: true,
    ok: null,
    missing: [],
    drifted: [],
    extra: [],
    extraContent: [],
    unreadable: [{ path: dir, code: error.code || 'EUNKNOWN' }],
  });
  const skillParity = { module: null, ides: [] };
  // Parity is a diagnostic row, never a reason for `status` to die. Losing the
  // version, manifest and presence rows because one file is permission-damaged
  // trades a whole report for one unreadable byte.
  try {
    skillParity.module = await compareTrees(srcSkillDir, skillDir, 'module');
  } catch (error) {
    skillParity.module = unverifiable(UCG_FOLDER + '/' + SKILL_NAME, error);
  }

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
  for (const [code, platform] of Object.entries(platforms)) {
    const targetDir = platform?.installer?.target_dir;
    if (!targetDir) continue;
    const entry = { ide: code, dir: path.join(targetDir, SKILL_NAME) };
    // Per platform, NOT around the loop. A catch spanning the whole loop drops
    // the failing platform AND every platform after it, and a copy that renders
    // no row at all is a false green on the one surface built to expose staleness.
    try {
      Object.assign(entry, await compareTrees(srcSkillDir, path.join(projectDir, targetDir, SKILL_NAME), 'ide'));
    } catch (error) {
      Object.assign(entry, unverifiable(entry.dir, error));
    }
    skillParity.ides.push(entry);
  }

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
    skillParity,
    versionMatch,
  };
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
  console.log(`    Skill:        ${status.skillInstalled ? chalk.green('installed') : chalk.yellow('not installed')}`);
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
  const parity = status.skillParity;
  if (parity) {
    const copies = [
      { label: 'module copy', dir: UCG_FOLDER + '/' + SKILL_NAME, ...parity.module },
      ...parity.ides.map((entry) => ({ label: entry.ide, ...entry })),
    ];
    for (const copy of copies) {
      const name = `${copy.label}:`.padEnd(14);
      if (!copy.present) {
        console.log(`    ${name}${chalk.dim('not installed')} ${chalk.dim(copy.dir)}`);
        continue;
      }
      if (copy.ok === true) {
        console.log(`    ${name}${chalk.green('matches source')}`);
        continue;
      }
      if (copy.ok === null) {
        // Neither pass nor fail: part of a tree could not be read, so any verdict
        // would be invented. Say so rather than picking the comfortable one.
        const first = (copy.unreadable || [])[0];
        const detail = first
          ? `${copy.unreadable.length} path(s) unreadable, first: ${first.path} (${first.code})`
          : 'tree could not be fully read';
        console.log(`    ${name}${chalk.yellow('unverifiable')} ${chalk.dim(`(${detail})`)}`);
        continue;
      }
      const parts = [];
      if (copy.missing.length > 0) parts.push(`${copy.missing.length} missing`);
      if (copy.drifted.length > 0) parts.push(`${copy.drifted.length} changed`);
      if (copy.extraContent.length > 0) parts.push(`${copy.extraContent.length} stale`);
      // Deliberately NOT phrased as tampering. When the versions match, the
      // ordinary cause is a source tree that moved ahead of the install, which
      // is the normal state in the repo that develops this module.
      const cause =
        status.versionMatch === false && status.installedVersion
          ? `installed v${status.installedVersion}, this CLI is v${version}`
          : "differs from this CLI's bundled source";
      console.log(`    ${name}${chalk.yellow('out of sync')} ${chalk.dim(`(${parts.join(', ')}; ${cause})`)}`);
    }
    const anyStale = copies.some((c) => c.present && c.ok === false);
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
