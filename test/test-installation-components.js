/**
 * Installation Component Tests
 *
 * Static verification of the shippable module pieces:
 * - module.yaml structure
 * - SKILL.md frontmatter and routing
 * - Stage reference files
 * - Deterministic scripts (uv-script shebang)
 * - customize.toml shape
 *
 * Usage: node test/test-installation-components.js
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const REPO_ROOT = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(REPO_ROOT, 'skills');
const SKILL_DIR = path.join(SKILLS_DIR, 'ultracode-goal');

// ANSI colors
const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  yellow: '[33m',
  cyan: '[36m',
  dim: '[2m',
};

let passed = 0;
let failed = 0;

function assert(condition, testName, errorMessage = '') {
  if (condition) {
    console.log(`${colors.green}✓${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}✗${colors.reset} ${testName}`);
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

const STAGE_REFERENCES = ['ingest-and-scope.md', 'preflight.md', 'define-done.md', 'execute.md', 'gate.md', 'finalize.md'];

const SCRIPTS = [
  'gate_eval.py',
  'preflight_check.py',
  'merge_config.py',
  'merge_help_csv.py',
  path.join('hooks', 'guard_pretooluse.py'),
  path.join('hooks', 'budget_stop.py'),
];

async function testModuleYaml() {
  console.log(`${colors.yellow}Test Suite 1: module.yaml Structure${colors.reset}\n`);

  // BMad standalone-module layout: module.yaml lives inside the skill's assets/
  const moduleYamlPath = path.join(SKILL_DIR, 'assets', 'module.yaml');
  assert(await fs.pathExists(moduleYamlPath), 'skills/ultracode-goal/assets/module.yaml exists');
  assert(!(await fs.pathExists(path.join(SKILLS_DIR, 'module.yaml'))), 'no stale module.yaml at skills/ root');

  try {
    const moduleYaml = yaml.load(await fs.readFile(moduleYamlPath, 'utf8'));
    assert(moduleYaml.code === 'ultracode-goal', 'module.yaml has code: ultracode-goal');
    assert(typeof moduleYaml.name === 'string' && moduleYaml.name.length > 0, 'module.yaml has a name');
    assert(typeof moduleYaml.description === 'string' && moduleYaml.description.length > 20, 'module.yaml has a real description');
    assert(typeof moduleYaml.default_selected === 'boolean', 'module.yaml has boolean default_selected');
    assert(
      moduleYaml.health_check_repo && typeof moduleYaml.health_check_repo.default === 'string',
      'module.yaml declares health_check_repo default',
    );
    assert(
      /^[\w-]+\/[\w-]+$/.test(moduleYaml.health_check_repo?.default || ''),
      'health_check_repo default is an owner/repo slug',
      moduleYaml.health_check_repo?.default,
    );
  } catch (error) {
    assert(false, 'module.yaml parses as YAML', error.message);
  }

  console.log('');
}

async function testSkillStructure() {
  console.log(`${colors.yellow}Test Suite 2: Skill Structure${colors.reset}\n`);

  const skillMdPath = path.join(SKILL_DIR, 'SKILL.md');
  assert(await fs.pathExists(skillMdPath), 'SKILL.md exists');

  const content = await fs.readFile(skillMdPath, 'utf8');

  // Frontmatter
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
  assert(frontmatterMatch !== null, 'SKILL.md has frontmatter');
  if (frontmatterMatch) {
    const frontmatter = yaml.load(frontmatterMatch[1]);
    assert(frontmatter.name === 'ultracode-goal', 'frontmatter name matches directory basename');
    assert(typeof frontmatter.description === 'string' && frontmatter.description.length >= 10, 'frontmatter has a description');
    assert(/use when/i.test(frontmatter.description), 'description carries a "Use when" trigger clause');
  }

  // Body routing
  assert(content.includes('## Stages'), 'SKILL.md has a Stages routing table');
  assert(content.includes('## Non-negotiables'), 'SKILL.md states its non-negotiables');

  // Stage references
  for (const ref of STAGE_REFERENCES) {
    const refPath = path.join(SKILL_DIR, 'references', ref);
    assert(await fs.pathExists(refPath), `references/${ref} exists`);
    assert(content.includes(`references/${ref}`), `SKILL.md routes to references/${ref}`);
  }

  // customize.toml
  const customizePath = path.join(SKILL_DIR, 'customize.toml');
  assert(await fs.pathExists(customizePath), 'customize.toml exists');
  const customize = await fs.readFile(customizePath, 'utf8');
  assert(customize.includes('[workflow]'), 'customize.toml has the [workflow] table');

  console.log('');
}

async function testScripts() {
  console.log(`${colors.yellow}Test Suite 3: Deterministic Scripts${colors.reset}\n`);

  for (const script of SCRIPTS) {
    const scriptPath = path.join(SKILL_DIR, 'scripts', script);
    const exists = await fs.pathExists(scriptPath);
    assert(exists, `scripts/${script.replaceAll(path.sep, '/')} exists`);

    if (exists) {
      const content = await fs.readFile(scriptPath, 'utf8');
      assert(
        content.startsWith('#!/usr/bin/env -S uv run --script'),
        `scripts/${script.replaceAll(path.sep, '/')} has the uv-script shebang`,
      );
      assert(content.includes('# /// script'), `scripts/${script.replaceAll(path.sep, '/')} carries PEP 723 metadata`);
    }
  }

  // Pytest suites exist in the repo (they are dev-only and filtered from installs)
  const testsDir = path.join(SKILL_DIR, 'scripts', 'tests');
  assert(await fs.pathExists(testsDir), 'scripts/tests/ pytest suites present in the repo');

  console.log('');
}

async function testStandaloneModuleAssets() {
  console.log(`${colors.yellow}Test Suite 4: Standalone Module Assets${colors.reset}\n`);

  const moduleYaml = yaml.load(await fs.readFile(path.join(SKILL_DIR, 'assets', 'module.yaml'), 'utf8'));

  // module-setup.md — self-registration flow for non-npx installs
  const setupPath = path.join(SKILL_DIR, 'assets', 'module-setup.md');
  assert(await fs.pathExists(setupPath), 'assets/module-setup.md exists');
  if (await fs.pathExists(setupPath)) {
    const setupContent = await fs.readFile(setupPath, 'utf8');
    assert(!setupContent.trimStart().startsWith('---'), 'module-setup.md has no frontmatter (WF-01/WF-02)');
    assert(
      setupContent.includes('merge_config.py') && setupContent.includes('merge_help_csv.py'),
      'module-setup.md runs both merge scripts',
    );
  }

  // module-help.csv — the capability rows registered into the help catalog
  const helpCsvPath = path.join(SKILL_DIR, 'assets', 'module-help.csv');
  assert(await fs.pathExists(helpCsvPath), 'assets/module-help.csv exists');
  if (await fs.pathExists(helpCsvPath)) {
    const csvText = await fs.readFile(helpCsvPath, 'utf8');
    const lines = csvText.trim().split('\n');
    assert(
      lines[0] === 'module,skill,display-name,menu-code,description,action,args,phase,after,before,required,output-location,outputs',
      'module-help.csv carries the 13-column standalone-module header',
      lines[0],
    );
    const dataLines = lines.slice(1);
    assert(dataLines.length > 0, 'module-help.csv registers at least one capability');
    assert(
      dataLines.every((l) => l.startsWith(`${moduleYaml.name},`)),
      "every row's module column matches module.yaml name (anti-zombie key, single-sourced)",
    );
    assert(!dataLines.some((l) => l.includes(',_meta,')), 'no authored _meta row (the installer assembles it from module.yaml docs_llms)');
    assert(
      dataLines.some((l) => l.includes(',ultracode-goal,')),
      'the ultracode-goal capability row is registered',
    );
    assert(
      typeof moduleYaml.docs_llms === 'string' && /^https:\/\//.test(moduleYaml.docs_llms),
      'module.yaml declares docs_llms for the assembled _meta row',
    );

    // Single-sourcing (F3): the catalog description derives from module.yaml header + subheader
    assert(csvText.includes(moduleYaml.header), 'capability description carries module.yaml header verbatim');
    assert(csvText.toLowerCase().includes(moduleYaml.subheader.toLowerCase()), 'capability description carries module.yaml subheader');

    // Menu codes unique within the module
    const menuCodes = dataLines.map((l) => l.split(',')[3]).filter((code) => code && code.length > 0);
    assert(new Set(menuCodes).size === menuCodes.length, 'menu codes are unique within the module');
  }

  console.log('');
}

async function testMarketplaceManifest() {
  console.log(`${colors.yellow}Test Suite 5: Plugin Marketplace Manifest${colors.reset}\n`);

  const marketplacePath = path.join(REPO_ROOT, '.claude-plugin', 'marketplace.json');
  assert(await fs.pathExists(marketplacePath), '.claude-plugin/marketplace.json exists');

  try {
    const marketplace = JSON.parse(await fs.readFile(marketplacePath, 'utf8'));
    assert(marketplace.name === 'bmad-module-ultracode-goal', 'marketplace name matches the package');
    assert(Array.isArray(marketplace.plugins) && marketplace.plugins.length > 0, 'marketplace declares plugins');

    const plugin = marketplace.plugins[0];
    assert(/^\d+\.\d+\.\d+/.test(plugin.version || ''), 'plugin version is semver');
    assert(
      Array.isArray(plugin.skills) && plugin.skills.includes('./skills/ultracode-goal'),
      'plugin skills reference ./skills/ultracode-goal',
    );

    // Version coupling: marketplace.json must match package.json until release automation syncs them
    const packageJson = JSON.parse(await fs.readFile(path.join(REPO_ROOT, 'package.json'), 'utf8'));
    assert(
      plugin.version === packageJson.version,
      'marketplace plugin version matches package.json version',
      `marketplace=${plugin.version} package=${packageJson.version}`,
    );
  } catch (error) {
    assert(false, 'marketplace.json parses as JSON', error.message);
  }

  console.log('');
}

// ============================================================
// Runner
// ============================================================

async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('UCG Installation Component Tests');
  console.log(`========================================${colors.reset}\n`);

  await testModuleYaml();
  await testSkillStructure();
  await testScripts();
  await testStandaloneModuleAssets();
  await testMarketplaceManifest();

  console.log(`${colors.cyan}========================================`);
  console.log('Test Results:');
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`========================================${colors.reset}\n`);

  if (failed === 0) {
    console.log(`${colors.green}All installation component tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}Some installation component tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
