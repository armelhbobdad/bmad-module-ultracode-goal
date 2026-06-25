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

async function testPortabilityHonestyInstallOutput() {
  console.log(`${colors.yellow}Test Suite 6: Portability-Honesty Install Output${colors.reset}\n`);

  // Source of the canonical gap line + the installer source for static greps.
  // (This is a static-fact suite: the BEHAVIORAL "printed once at install on a
  // non-Claude-Code target" — driving install() and counting the gap line in
  // captured stdout — is covered by the cross-provider honesty suite in test-cli-integration.js.
  // Here we pin the constant's shape and the single emit SITE statically.)
  const installerPath = path.join(REPO_ROOT, 'tools', 'cli', 'lib', 'installer.js');
  const { PORTABILITY_GAP_LINE } = require(installerPath);
  const installerSrc = await fs.readFile(installerPath, 'utf8');

  const README_PATH = path.join(REPO_ROOT, 'README.md');
  const DOCS_PATH = path.join(REPO_ROOT, 'docs', 'how-it-works.md');

  // ---- one canonical gap line, exactly one emit site -------------------
  assert(
    typeof PORTABILITY_GAP_LINE === 'string' && /Claude.?Code.*only/i.test(PORTABILITY_GAP_LINE),
    'PORTABILITY_GAP_LINE is exported and names Claude Code as the only place enforcement is automatic',
    PORTABILITY_GAP_LINE,
  );
  // Count UNCOMMENTED emit sites: a `warn(PORTABILITY_GAP_LINE)` call that is
  // not on a `//`-commented line. This pins the live emit-site count to exactly
  // one. Twin: this count===1 fails if the emit is DUPLICATED (count 2) OR
  // SUPPRESSED — whether by deletion (count 0) or by commenting it out (count 0,
  // because a commented line is excluded) — proving the test pins the exact
  // count, not mere textual presence.
  const emitCount = installerSrc.split('\n').filter((l) => /warn\(PORTABILITY_GAP_LINE\)/.test(l) && !/^\s*\/\//.test(l)).length;
  assert(emitCount === 1, 'installer.js emits PORTABILITY_GAP_LINE from exactly one site', `emit sites = ${emitCount}`);

  // ---- honest copy, never over-claiming --------------------------------
  // Case-insensitive forbidden-claim denylist + the three required markers.
  const denylist = ['cross-provider enforcement', 'enforced everywhere', 'autonomous enforcement on any', 'auto-enforced on'];
  const hasAllMarkers = (text) => text.includes('Claude Code') && text.includes('/ucg-formalize') && /\b(manual|on-demand)\b/i.test(text);
  const denyHits = (text) => {
    const lc = text.toLowerCase();
    return denylist.filter((phrase) => lc.includes(phrase));
  };

  // Extract the README portability paragraph (the new "What still ships
  // everywhere" line) and the docs "Portability" section paragraph.
  const readmeSrc = await fs.readFile(README_PATH, 'utf8');
  const readmePara = (readmeSrc.split('\n').find((l) => l.includes('What still ships everywhere')) || '').trim();
  const docsSrc = await fs.readFile(DOCS_PATH, 'utf8');
  const docsMatch = docsSrc.match(/## Portability:[\s\S]*?(?=\n## |$)/);
  const docsPara = docsMatch ? docsMatch[0].trim() : '';

  const subjects = [
    ['PORTABILITY_GAP_LINE constant', PORTABILITY_GAP_LINE],
    ['README portability paragraph', readmePara],
    ['docs/how-it-works.md portability paragraph', docsPara],
  ];
  for (const [label, text] of subjects) {
    assert(text.length > 0, `${label} is present (non-empty)`, label);
    const hits = denyHits(text);
    // Twin: an over-claim like "autonomous enforcement works on any provider"
    // both trips the denylist AND drops the markers — either branch fails.
    assert(hits.length === 0, `${label} contains no forbidden cross-provider claim`, hits.join(' | '));
    assert(hasAllMarkers(text), `${label} carries all three required markers (Claude Code + /ucg-formalize + manual/on-demand)`, label);
  }

  // ---- portable half ships, never no-install ---------------------------
  // For each portable-half artifact that EXISTS in source, assert it is present
  // (skip-if-absent-in-source so the suite never orphans over a sibling-story
  // artifact). Asserting against the SOURCE tree: the installer copies the
  // skills/ tree wholesale via copySrcFiles, so a source artifact dropped from
  // the install would first be a source-tree regression.
  const SKILL_SRC = path.join(SKILLS_DIR, 'ultracode-goal');
  const portableHalf = [
    path.join(SKILL_SRC, 'skills', 'ucg-formalize', 'SKILL.md'),
    path.join(SKILL_SRC, 'scripts', 'formalize_check.py'),
    path.join(SKILL_SRC, 'scripts', 'merge_customization.py'),
  ];
  for (const artifactPath of portableHalf) {
    const rel = path.relative(REPO_ROOT, artifactPath).replaceAll(path.sep, '/');
    // skip-if-absent-in-source: only assert presence for artifacts that exist.
    if (await fs.pathExists(artifactPath)) {
      assert(true, `portable-half artifact present in source: ${rel}`);
    } else {
      console.log(`${colors.dim}  (skip-if-absent-in-source) ${rel} not yet authored${colors.reset}`);
    }
  }
  // At least one ucg-awareness/*.toml persistent_facts fragment (these ship in
  // source today — so this branch is always exercisable).
  const awarenessDir = path.join(SKILL_SRC, 'assets', 'ucg-awareness');
  let awarenessFragments = [];
  if (await fs.pathExists(awarenessDir)) {
    awarenessFragments = (await fs.readdir(awarenessDir)).filter((f) => f.endsWith('.toml'));
  }
  assert(
    awarenessFragments.length > 0,
    'at least one ucg-awareness/{skill}.toml persistent_facts fragment ships in source',
    `found ${awarenessFragments.length}`,
  );

  // Static check: the delimited Step 6b region contains no provider-gated
  // early-return/throw refusal. Scope the negative grep to the Step 6b block.
  const step6bMatch = installerSrc.match(/Step 6b:[\s\S]*?(?=\n {4}\/\/ Step 7:)/);
  assert(step6bMatch !== null, 'Step 6b region is delimited in installer.js', 'no Step 6b/Step 7 delimiters found');
  if (step6bMatch) {
    const step6b = step6bMatch[0];
    // Twin: an early-return that skips copying the fragments on non-Claude-Code
    // would introduce a provider-gated refusal token in this block.
    const refusalToken = /\b(unsupported|no-install)\b/i.test(step6b);
    // A provider-gated return/throw refusal: a line carrying BOTH a bare
    // return/throw control-flow token AND a 'claude'/'claude-code' provider name
    // (in either order — e.g. `if (!ides.includes('claude-code')) return;` or
    // `return; // claude-only`). The legitimate `ides.includes('claude-code')`
    // gating the single non-blocking WARN does not match — that line has no
    // return/throw. Scan line-by-line so the two tokens must co-occur in one
    // control-flow statement, not merely somewhere in the block.
    const providerGatedReturn = step6b.split('\n').some((l) => /\b(return|throw)\b/.test(l) && /\bclaude(-code)?\b/i.test(l));
    assert(!refusalToken, 'Step 6b block contains no "unsupported"/"no-install" refusal token', 'refusal token found in Step 6b');
    assert(
      !providerGatedReturn,
      'Step 6b block has no provider-gated early-return/throw refusal',
      'provider-name-guarded return/throw found in Step 6b',
    );
  }

  // ---- provider-invariant verdict + envelope (no fork here) ----
  // (a) installer.js carries ZERO envelope literal and zero verdict-mapping copy
  //     — this step emits the gap line, not a forked envelope. The envelope's
  //     identifying SHAPE is the co-occurrence of its structural keys
  //     status + decision_log + report (the envelope's five keys are status / skill /
  //     decision_log / report / deferred_work). The detector fires on that
  //     structural co-occurrence rather than requiring all five, so a FORKED
  //     envelope literal that DROPS deferred_work off Claude Code is still
  //     caught (the spec twin). Each key is matched as a quoted JSON object key
  //     so plain English prose ("a report", "status of") never trips it.
  const structuralEnvelopeKeys = ['status', 'decision_log', 'report'];
  const keyAsJsonLiteral = (k) => installerSrc.includes(`"${k}"`) || installerSrc.includes(`'${k}'`);
  const installerHasEnvelopeShape = structuralEnvelopeKeys.every(keyAsJsonLiteral);
  // Twin: inlining a forked envelope literal — even one dropping deferred_work
  // off Claude Code — lands status/decision_log/report as JSON keys in
  // installer.js, so installerHasEnvelopeShape becomes true and this fails.
  assert(
    !installerHasEnvelopeShape,
    'installer.js contains ZERO envelope literal / verdict-mapping copy (no forked envelope, even one dropping deferred_work)',
    'envelope-shaped key co-occurrence (status/decision_log/report) found in installer.js',
  );
  // Defence-in-depth: the canonical sentinel key never appears in installer.js.
  assert(
    !installerSrc.includes('deferred_work'),
    'installer.js carries no verdict/envelope key copy (deferred_work absent)',
    'deferred_work literal found in installer.js',
  );

  // (b) skip-if-absent zero-provider-conditional check over the formalize
  //     kernel + the ucg-formalize SKILL adapter: no 'claude'/'claude-code'
  //     branching around verdict/envelope emission. Both are clean today, so
  //     this PASSES; its twin (a planted provider-conditional dropping
  //     deferred_work off Claude Code) would fail.
  const providerInvariantSubjects = [
    ['formalize_check.py', path.join(SKILL_SRC, 'scripts', 'formalize_check.py')],
    ['ucg-formalize/SKILL.md', path.join(SKILL_SRC, 'skills', 'ucg-formalize', 'SKILL.md')],
  ];
  for (const [label, p] of providerInvariantSubjects) {
    if (!(await fs.pathExists(p))) {
      console.log(`${colors.dim}  (skip-if-absent) ${label} not yet authored — provider-conditional check skipped${colors.reset}`);
      continue;
    }
    const src = await fs.readFile(p, 'utf8');
    // Provider-name conditional: a 'claude'/'claude-code' token inside an
    // if/branch construct. The files have zero 'claude' tokens today, so any
    // occurrence is a fork signal.
    const hasProviderToken = /\bclaude(-code)?\b/i.test(src);
    assert(
      !hasProviderToken,
      `${label} has no provider-name ('claude'/'claude-code') conditional around verdict/envelope emission`,
      `provider token found in ${label}`,
    );
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
  await testPortabilityHonestyInstallOutput();

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
