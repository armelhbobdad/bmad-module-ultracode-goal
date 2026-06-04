/**
 * UCG Status Command
 * Shows installation state, version, configured IDEs, and skill integrity.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { readManifest } = require('../lib/manifest');
const { getAvailablePlatforms } = require('../lib/ide-skills');

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
      const packageJson = require('../../../package.json');
      const status = await getStatus(projectDir);
      displayStatus(status, packageJson.version);
    } catch (error) {
      console.error(chalk.red('\nFailed to read status:'), error.message);
      process.exit(1);
    }
  },
};
