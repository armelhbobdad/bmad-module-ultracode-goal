/**
 * CLI Integration Tests - Install/Update/Uninstall Flows
 *
 * End-to-end tests using temp directories to verify:
 * - Fresh install creates all expected files
 * - Update preserves config.yaml and replaces UCG files
 * - Uninstall removes all tracked files
 * - IDE skill installation for each target
 * - Manifest accuracy
 *
 * Usage: node test/test-cli-integration.js
 */

const path = require('node:path');
const os = require('node:os');
const fs = require('fs-extra');
const yaml = require('js-yaml');

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

/**
 * Create a temp directory for a test case.
 */
async function makeTempDir(label) {
  const dir = path.join(os.tmpdir(), `ucg-test-${label}-${Date.now()}`);
  await fs.ensureDir(dir);
  return dir;
}

/**
 * Suppress spinners, console.log, and stderr writes during install to keep test output clean.
 */
function suppressConsole() {
  const origLog = console.log;
  const origStdoutWrite = process.stdout.write;
  const origStderrWrite = process.stderr.write;
  console.log = () => {};
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  return () => {
    console.log = origLog;
    process.stdout.write = origStdoutWrite;
    process.stderr.write = origStderrWrite;
  };
}

const STAGE_REFERENCES = ['ingest-and-scope.md', 'preflight.md', 'define-done.md', 'execute.md', 'gate.md', 'finalize.md'];

// ============================================================
// Test Suites
// ============================================================

async function testFreshInstall() {
  console.log(`${colors.yellow}Test Suite 1: Fresh Install${colors.reset}\n`);

  const projectDir = await makeTempDir('fresh');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'test-project',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    const result = await installer.install(config);
    restore();

    assert(result.success === true, 'install returns success');

    // Verify UCG directory structure
    const ucgDir = path.join(projectDir, '_bmad/ucg');
    assert(await fs.pathExists(ucgDir), 'UCG directory created');

    const skillDir = path.join(ucgDir, 'ultracode-goal');
    assert(await fs.pathExists(path.join(skillDir, 'SKILL.md')), 'ultracode-goal/SKILL.md copied');
    assert(await fs.pathExists(path.join(skillDir, 'customize.toml')), 'customize.toml copied');

    // Verify all six stage references
    for (const ref of STAGE_REFERENCES) {
      assert(await fs.pathExists(path.join(skillDir, 'references', ref)), `references/${ref} copied`);
    }

    // Verify deterministic scripts and hooks
    assert(await fs.pathExists(path.join(skillDir, 'scripts', 'gate_eval.py')), 'scripts/gate_eval.py copied');
    assert(await fs.pathExists(path.join(skillDir, 'scripts', 'preflight_check.py')), 'scripts/preflight_check.py copied');
    assert(await fs.pathExists(path.join(skillDir, 'scripts', 'hooks', 'guard_pretooluse.py')), 'hooks/guard_pretooluse.py copied');
    assert(await fs.pathExists(path.join(skillDir, 'scripts', 'hooks', 'budget_stop.py')), 'hooks/budget_stop.py copied');

    // Verify dev artifacts are filtered out of the installed copy
    assert(!(await fs.pathExists(path.join(skillDir, 'scripts', 'tests'))), 'pytest suites not shipped');
    assert(!(await fs.pathExists(path.join(skillDir, '.analysis'))), '.analysis not shipped');
    assert(!(await fs.pathExists(path.join(skillDir, '.decision-log.md'))), '.decision-log.md not shipped');
    assert(!(await fs.pathExists(path.join(skillDir, 'scripts', '__pycache__'))), '__pycache__ not shipped');
    assert(!(await fs.pathExists(path.join(ucgDir, 'reports'))), 'skills/reports/ (builder reports) not shipped');

    // Verify module.yaml and VERSION
    assert(await fs.pathExists(path.join(ucgDir, 'module.yaml')), 'module.yaml copied');
    assert(await fs.pathExists(path.join(skillDir, 'assets', 'module.yaml')), 'standalone module.yaml travels inside the skill assets/');

    // Verify help-catalog registration (bmad-help routing)
    const catalogPath = path.join(projectDir, '_bmad/_config/bmad-help.csv');
    assert(await fs.pathExists(catalogPath), 'bmad-help.csv created');
    const catalogText = await fs.readFile(catalogPath, 'utf8');
    assert(catalogText.includes('UltraCode Goal,ultracode-goal,'), 'catalog has the ultracode-goal capability row');
    assert(catalogText.includes('UltraCode Goal,_meta,'), 'catalog has the module _meta row');
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad/module-help.csv'))), 'module-help.csv not created when absent');
    const versionPath = path.join(ucgDir, 'VERSION');
    assert(await fs.pathExists(versionPath), 'VERSION file written');
    const versionContent = (await fs.readFile(versionPath, 'utf8')).trim();
    assert(/^\d+\.\d+\.\d+/.test(versionContent), 'VERSION contains a semver string');

    // Verify config.yaml
    const configPath = path.join(ucgDir, 'config.yaml');
    assert(await fs.pathExists(configPath), 'config.yaml created');
    const configContent = yaml.load(await fs.readFile(configPath, 'utf8'));
    assert(configContent.project_name === 'test-project', 'config.yaml has correct project_name');
    assert(configContent.output_folder === '_bmad-output', 'config.yaml has output_folder');
    assert(configContent.ucg_folder === '_bmad/ucg', 'config.yaml has ucg_folder');
    assert(Array.isArray(configContent.ides) && configContent.ides.includes('claude-code'), 'config.yaml has IDEs');

    // Verify the skill installed to the IDE directory (.claude/skills/)
    const claudeSkillsDir = path.join(projectDir, '.claude', 'skills');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'ultracode-goal', 'SKILL.md')), 'skill installed to .claude/skills/');
    assert(
      await fs.pathExists(path.join(claudeSkillsDir, 'ultracode-goal', 'scripts', 'gate_eval.py')),
      'skill scripts installed to .claude/skills/',
    );

    // Verify learning material
    assert(await fs.pathExists(path.join(projectDir, '_ucg-learn')), '_ucg-learn/ directory created');

    // Verify manifest
    const manifestPath = path.join(projectDir, '_bmad/_config/ucg-manifest.yaml');
    assert(await fs.pathExists(manifestPath), 'manifest created');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.module === 'ucg', 'manifest has module: ucg');
    assert(manifest.action === 'fresh', 'manifest has action: fresh');
    assert(Array.isArray(manifest.files.ucg) && manifest.files.ucg.length > 0, 'manifest tracks UCG files');
    assert(Array.isArray(manifest.files.ide_skills) && manifest.files.ide_skills.length > 0, 'manifest tracks IDE skill files');
  } catch (error) {
    assert(false, 'fresh install completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUpdatePreservesConfig() {
  console.log(`${colors.yellow}Test Suite 2: Update Preserves Config${colors.reset}\n`);

  const projectDir = await makeTempDir('update');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Step 1: Fresh install
    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'original-name',
      ides: ['cursor'],
      install_learning: false,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify initial config
    const ucgDir = path.join(projectDir, '_bmad/ucg');
    const configPath = path.join(ucgDir, 'config.yaml');
    const origConfig = await fs.readFile(configPath, 'utf8');
    assert(origConfig.includes('original-name'), 'initial config has original project name');

    // Step 2: Update
    const updateConfig = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      _action: 'update',
    };

    restore = suppressConsole();
    const result = await installer.install(updateConfig);
    restore();

    assert(result.success === true, 'update returns success');

    // Config should be preserved
    const updatedConfig = await fs.readFile(configPath, 'utf8');
    assert(updatedConfig.includes('original-name'), 'config.yaml preserved after update');

    // UCG files should still exist
    assert(await fs.pathExists(path.join(ucgDir, 'ultracode-goal', 'SKILL.md')), 'skill exists after update');
    assert(await fs.pathExists(path.join(ucgDir, 'module.yaml')), 'module.yaml exists after update');

    // IDE selection should carry over from the saved config (cursor was selected on fresh install)
    const claudeSkillsAfterUpdate = await fs.pathExists(path.join(projectDir, '.cursor', 'skills', 'ultracode-goal', 'SKILL.md'));
    assert(claudeSkillsAfterUpdate, 'IDE skill reinstalled from saved config after update');

    // Manifest should reflect update action
    const manifestPath = path.join(projectDir, '_bmad/_config/ucg-manifest.yaml');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.action === 'update', 'manifest action is update');
  } catch (error) {
    assert(false, 'update flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testHelpCatalogRegistration() {
  console.log(`${colors.yellow}Test Suite 2b: Help Catalog Registration${colors.reset}\n`);

  const projectDir = await makeTempDir('help-catalog');

  // The assembled catalog header as the BMAD installer writes it
  const catalogHeader =
    'module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs';
  const foreignRow =
    'BMad Builder,bmad-module-builder,Validate Module,VM,"Check that a module\'s structure is complete.",validate-module,,anytime,,,false,bmad_builder_reports,validation report';

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { removeHelpEntries } = require('../tools/cli/lib/help-catalog');
    const installer = new Installer();

    // Seed a pre-existing BMad project: assembled catalog + module-help.csv
    const catalogPath = path.join(projectDir, '_bmad/_config/bmad-help.csv');
    await fs.ensureDir(path.dirname(catalogPath));
    await fs.writeFile(catalogPath, `${catalogHeader}\n${foreignRow}\n`, 'utf8');
    const moduleHelpPath = path.join(projectDir, '_bmad/module-help.csv');
    await fs.writeFile(moduleHelpPath, `${catalogHeader}\n${foreignRow}\n`, 'utf8');

    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'help-catalog-test',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    let catalogText = await fs.readFile(catalogPath, 'utf8');
    assert(catalogText.startsWith(catalogHeader), 'existing catalog header (preceded-by/followed-by) preserved');
    assert(catalogText.includes('BMad Builder,'), 'foreign module rows preserved');
    assert(catalogText.includes('UltraCode Goal,ultracode-goal,'), 'UCG capability row appended');

    const moduleHelpText = await fs.readFile(moduleHelpPath, 'utf8');
    assert(moduleHelpText.includes('UltraCode Goal,'), 'pre-existing module-help.csv also updated');
    assert(moduleHelpText.includes('BMad Builder,'), 'module-help.csv foreign rows preserved');

    // Re-install: anti-zombie keeps exactly one row set (no duplicates)
    restore = suppressConsole();
    await installer.install({ ...config, _action: 'update' });
    restore();

    catalogText = await fs.readFile(catalogPath, 'utf8');
    const ucgRowCount = catalogText.split('\n').filter((l) => l.startsWith('UltraCode Goal,')).length;
    // _meta + 2 capability rows (ultracode-goal + ucg-formalize); anti-zombie keeps the set stable across reinstall (not 6).
    assert(ucgRowCount === 3, 'reinstall is anti-zombie: _meta + 2 capability rows, no duplication', `found ${ucgRowCount}`);

    // Uninstall path: UCG rows removed, foreign rows survive
    const touched = await removeHelpEntries(projectDir, ['UltraCode Goal']);
    assert(touched.length === 2, 'uninstall touches both catalog targets', touched.join(', '));
    catalogText = await fs.readFile(catalogPath, 'utf8');
    assert(!catalogText.includes('UltraCode Goal,'), 'UCG rows removed from catalog on uninstall');
    assert(catalogText.includes('BMad Builder,'), 'foreign rows survive uninstall');

    // A catalog this module created alone (only UCG rows) is deleted outright
    const soloDir = await makeTempDir('help-catalog-solo');
    try {
      restore = suppressConsole();
      await installer.install({ ...config, projectDir: soloDir });
      restore();
      const soloCatalog = path.join(soloDir, '_bmad/_config/bmad-help.csv');
      assert(await fs.pathExists(soloCatalog), 'solo install creates the catalog');
      // A stray trailing blank line (hand-edited catalog) must not defeat deletion
      await fs.appendFile(soloCatalog, '\n', 'utf8');
      await removeHelpEntries(soloDir, ['UltraCode Goal']);
      assert(!(await fs.pathExists(soloCatalog)), 'header-only catalog deleted on uninstall (despite blank line)');
    } finally {
      await fs.remove(soloDir);
    }
  } catch (error) {
    assert(false, 'help catalog registration completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUninstallCleansUp() {
  console.log(`${colors.yellow}Test Suite 3: Uninstall Cleanup${colors.reset}\n`);

  const projectDir = await makeTempDir('uninstall');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../tools/cli/lib/manifest');
    const installer = new Installer();

    // Install first
    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'uninstall-test',
      ides: ['claude-code', 'cursor'],
      install_learning: true,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify files exist before uninstall
    assert(await fs.pathExists(path.join(projectDir, '_bmad/ucg')), 'UCG dir exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '_ucg-learn')), '_ucg-learn exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.claude/skills')), '.claude/skills exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.cursor/skills')), '.cursor/skills exists before uninstall');

    // Read manifest
    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest exists before uninstall');

    // Simulate uninstall: remove all tracked files (mirrors uninstall.js logic without interactive prompt)
    restore = suppressConsole();

    // Remove this module's help-catalog rows (mirrors uninstall.js)
    const { removeHelpEntries } = require('../tools/cli/lib/help-catalog');
    await removeHelpEntries(projectDir, manifest.help_catalog?.module_codes || []);

    // Remove IDE skill directories (directory-level cleanup, not file-by-file)
    for (const dir of manifest.directories || []) {
      const dirPath = path.join(projectDir, dir);
      if (await fs.pathExists(dirPath)) await fs.remove(dirPath);
      // Clean empty parent (e.g., .claude/ after removing .claude/skills)
      const parentDir = path.dirname(dirPath);
      if (await fs.pathExists(parentDir)) {
        const entries = await fs.readdir(parentDir);
        if (entries.length === 0) await fs.remove(parentDir);
      }
    }

    // Remove learning
    const learnDir = path.join(projectDir, '_ucg-learn');
    if (await fs.pathExists(learnDir)) await fs.remove(learnDir);

    // Remove UCG module
    const ucgDir = path.join(projectDir, manifest.ucg_folder);
    if (await fs.pathExists(ucgDir)) await fs.remove(ucgDir);

    // Remove manifest
    const manifestPath = path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE);
    if (await fs.pathExists(manifestPath)) await fs.remove(manifestPath);
    const configDir = path.join(projectDir, MANIFEST_DIR);
    if (await fs.pathExists(configDir)) {
      const entries = await fs.readdir(configDir);
      if (entries.length === 0) await fs.remove(configDir);
    }
    const bmadDir = path.join(projectDir, '_bmad');
    if (await fs.pathExists(bmadDir)) {
      const entries = await fs.readdir(bmadDir);
      if (entries.length === 0) await fs.remove(bmadDir);
    }

    restore();

    // Verify everything is cleaned up
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad/ucg'))), 'UCG dir removed');
    assert(!(await fs.pathExists(path.join(projectDir, '_ucg-learn'))), '_ucg-learn removed');
    assert(!(await fs.pathExists(path.join(projectDir, '.claude/skills'))), '.claude/skills removed');
    assert(!(await fs.pathExists(path.join(projectDir, '.cursor/skills'))), '.cursor/skills removed');
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad'))), '_bmad/ cleaned up (empty)');
  } catch (error) {
    assert(false, 'uninstall flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testIdeSkillInstallation() {
  console.log(`${colors.yellow}Test Suite 4: IDE Skill Installation${colors.reset}\n`);

  const projectDir = await makeTempDir('ide-skills');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Test with a subset of IDEs (claude-code and cursor represent the pattern)
    const testIdes = ['claude-code', 'cursor'];

    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'ide-test',
      ides: testIdes,
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify each IDE got the skill directory (not command files)
    const ideSkillDirs = {
      'claude-code': '.claude/skills',
      cursor: '.cursor/skills',
    };

    for (const [ide, targetDir] of Object.entries(ideSkillDirs)) {
      const fullDir = path.join(projectDir, targetDir);
      const exists = await fs.pathExists(fullDir);
      assert(exists, `${ide}: ${targetDir}/ created`);

      if (exists) {
        const entries = await fs.readdir(fullDir);
        assert(entries.includes('ultracode-goal'), `${ide}: has the ultracode-goal skill directory`);

        const skillMd = path.join(fullDir, 'ultracode-goal', 'SKILL.md');
        assert(await fs.pathExists(skillMd), `${ide}: SKILL.md present`);

        // Verify the full skill travels: references + scripts + hooks
        for (const ref of STAGE_REFERENCES) {
          const refPath = path.join(fullDir, 'ultracode-goal', 'references', ref);
          if (!(await fs.pathExists(refPath))) {
            assert(false, `${ide}: references/${ref} present`);
          }
        }
        assert(true, `${ide}: all ${STAGE_REFERENCES.length} stage references present`);
        assert(await fs.pathExists(path.join(fullDir, 'ultracode-goal', 'scripts', 'hooks')), `${ide}: hooks travel with the skill`);
      }
    }

    // Verify SKILL.md content routing is intact
    const skillContent = await fs.readFile(path.join(projectDir, '.claude/skills/ultracode-goal/SKILL.md'), 'utf8');
    assert(skillContent.includes('## Stages'), 'SKILL.md has Stages routing table');
    assert(skillContent.includes('name: ultracode-goal'), 'SKILL.md frontmatter intact');
  } catch (error) {
    assert(false, 'IDE skill installation completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testManifestAccuracy() {
  console.log(`${colors.yellow}Test Suite 5: Manifest Accuracy${colors.reset}\n`);

  const projectDir = await makeTempDir('manifest');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { readManifest } = require('../tools/cli/lib/manifest');
    const installer = new Installer();

    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'manifest-test',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest readable');

    // Verify every file in manifest actually exists on disk
    let allExist = true;
    let missingFiles = [];
    const allFiles = [...manifest.files.ucg, ...manifest.files.ide_skills, ...manifest.files.learning];

    for (const file of allFiles) {
      if (!(await fs.pathExists(path.join(projectDir, file)))) {
        allExist = false;
        missingFiles.push(file);
      }
    }
    assert(allExist, `all ${allFiles.length} manifest files exist on disk`, missingFiles.join(', '));

    // Verify manifest metadata
    assert(manifest.ucg_folder === '_bmad/ucg', 'manifest has correct ucg_folder');
    assert(typeof manifest.version === 'string' && manifest.version.length > 0, 'manifest has version');
    assert(typeof manifest.installed_at === 'string', 'manifest has installed_at timestamp');

    // Verify directories list
    assert(Array.isArray(manifest.directories), 'manifest has directories array');
    assert(manifest.directories.includes('_bmad/ucg'), 'directories includes UCG folder');
    assert(manifest.directories.includes('_ucg-learn'), 'directories includes learning material');

    // Verify help-catalog registration record
    assert(manifest.help_catalog !== null && typeof manifest.help_catalog === 'object', 'manifest records help_catalog');
    assert(
      Array.isArray(manifest.help_catalog.module_codes) && manifest.help_catalog.module_codes.includes('UltraCode Goal'),
      'help_catalog records the module code',
    );
    assert(
      Array.isArray(manifest.help_catalog.targets) && manifest.help_catalog.targets.length > 0,
      'help_catalog records the touched targets',
    );
  } catch (error) {
    assert(false, 'manifest accuracy test completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testFreshInstallWithoutLearning() {
  console.log(`${colors.yellow}Test Suite 6: Install Without Learning Material${colors.reset}\n`);

  const projectDir = await makeTempDir('no-learn');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      ucgFolder: '_bmad/ucg',
      project_name: 'no-learn-test',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    assert(!(await fs.pathExists(path.join(projectDir, '_ucg-learn'))), 'no _ucg-learn when learning disabled');

    // Manifest should have empty learning files list
    const { readManifest } = require('../tools/cli/lib/manifest');
    const manifest = await readManifest(projectDir);
    assert(manifest.files.learning.length === 0, 'manifest has no learning files');
    assert(manifest.files.ide_skills.length === 0, 'manifest has no IDE skill files (no IDEs selected)');
  } catch (error) {
    assert(false, 'install without learning completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testGitignoreEntries() {
  console.log(`${colors.yellow}Test Suite 7: .gitignore Entries${colors.reset}\n`);

  const ENTRY = '.claude/settings.local.json';

  const baseConfig = {
    project_name: 'gi-test',
    ucgFolder: '_bmad/ucg',
    ides: [],
    install_learning: false,
    _action: 'fresh',
  };

  // Case A: No .gitignore — creates one
  const dirA = await makeTempDir('gitignore-new');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    const restore = suppressConsole();
    await installer.install({ ...baseConfig, projectDir: dirA });
    restore();

    const giPath = path.join(dirA, '.gitignore');
    assert(await fs.pathExists(giPath), 'creates .gitignore when none exists');
    const content = await fs.readFile(giPath, 'utf8');
    assert(content.includes(ENTRY), `.gitignore contains ${ENTRY}`);
  } catch (error) {
    assert(false, 'gitignore creation test', error.message);
  } finally {
    await fs.remove(dirA);
  }

  // Case B: Existing .gitignore without entry — appends
  const dirB = await makeTempDir('gitignore-append');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirB, '.gitignore'), 'node_modules/\n.env\n', 'utf8');
    const restore = suppressConsole();
    await installer.install({ ...baseConfig, projectDir: dirB });
    restore();

    const content = await fs.readFile(path.join(dirB, '.gitignore'), 'utf8');
    assert(content.includes('node_modules/'), 'preserves existing entries');
    assert(content.includes(ENTRY), `appends ${ENTRY} entry`);
    const occurrences = content.split(ENTRY).length - 1;
    assert(occurrences === 1, 'entry appears exactly once');
  } catch (error) {
    assert(false, 'gitignore append test', error.message);
  } finally {
    await fs.remove(dirB);
  }

  // Case C: .gitignore already has entry — no duplicate
  const dirC = await makeTempDir('gitignore-dup');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirC, '.gitignore'), `node_modules/\n${ENTRY}\n`, 'utf8');
    const restore = suppressConsole();
    await installer.install({ ...baseConfig, projectDir: dirC });
    restore();

    const content = await fs.readFile(path.join(dirC, '.gitignore'), 'utf8');
    const occurrences = content.split(ENTRY).length - 1;
    assert(occurrences === 1, 'does not duplicate existing entry');
  } catch (error) {
    assert(false, 'gitignore no-duplicate test', error.message);
  } finally {
    await fs.remove(dirC);
  }

  // Case D: .gitignore without trailing newline — appends cleanly
  const dirD = await makeTempDir('gitignore-nonl');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirD, '.gitignore'), 'node_modules/', 'utf8');
    const restore = suppressConsole();
    await installer.install({ ...baseConfig, projectDir: dirD });
    restore();

    const content = await fs.readFile(path.join(dirD, '.gitignore'), 'utf8');
    assert(!content.includes(`node_modules/${ENTRY}`), 'entry on its own line (not appended to previous)');
    assert(content.includes(ENTRY), 'entry present after no-newline file');
  } catch (error) {
    assert(false, 'gitignore no-trailing-newline test', error.message);
  } finally {
    await fs.remove(dirD);
  }

  console.log('');
}

// ============================================================
// Test Suite 8: Step 6b — UCG-awareness shaping
// ============================================================

const REPO_ROOT = path.resolve(__dirname, '..');
// Vendored under skills/.../tests/fixtures/engine/ so the suite stays hermetic
// in CI (the real _bmad/ tree is gitignored and absent on a clean checkout).
const REAL_ENGINE = path.join(REPO_ROOT, 'skills', 'ultracode-goal', 'scripts', 'tests', 'fixtures', 'engine', 'resolve_customization.py');

// The enumerated forbidden cross-provider-auto-enforcement-claim set, defined
// as a literal constant. The
// machine half asserts the honesty line matches the POSITIVE shape exactly once
// AND matches ZERO of these alternations — printing any forbidden literal flips
// .test() to true and fails the suite (non-vacuous).
const STEP6B_FORBIDDEN_ENFORCEMENT =
  /(auto.?enforc|automatic(ally)? enforc|preflight (is )?enforced|enforced (on|across) (cursor|all providers|every provider)|cross-?provider auto|enforce.{0,20}(cursor|all providers|every provider))/i;
const CLAUDE_CODE_ONLY = /Claude.?Code.*only/i;

/**
 * Copy the real deep_merge engine into a temp project so merge_customization.py
 * resolves it exactly as it will at install time (mirrors REAL_ENGINE in
 * skills/.../tests/test_merge_customization.py).
 */
async function seedEngine(projectDir) {
  const dest = path.join(projectDir, '_bmad', 'scripts', 'resolve_customization.py');
  await fs.ensureDir(path.dirname(dest));
  await fs.copy(REAL_ENGINE, dest);
}

/** Seed present BMAD skills by creating .claude/skills/{skill}/ dirs. */
async function seedSkills(projectDir, skills) {
  for (const skill of skills) {
    await fs.ensureDir(path.join(projectDir, '.claude', 'skills', skill));
  }
}

/**
 * Spy on clack's log.warn AND note/outro so emitted warning + note strings are
 * captured into one joined string BEFORE suppressConsole() reassigns stdout
 * (suppressConsole swallows stdout, so reading stdout won't work). Returns
 * {joined(), restore()}.
 */
function spyClackSinks() {
  const clack = require('@clack/prompts');
  const captured = [];
  const origWarn = clack.log.warn;
  const origInfo = clack.log.info;
  const origNote = clack.note;
  const origOutro = clack.outro;
  clack.log.warn = (msg) => captured.push(String(msg));
  clack.log.info = (msg) => captured.push(String(msg));
  clack.note = (body, title) => captured.push(String(body) + '\n' + String(title));
  clack.outro = (msg) => captured.push(String(msg));
  return {
    captured,
    joined: () => captured.join('\n'),
    restore: () => {
      clack.log.warn = origWarn;
      clack.log.info = origInfo;
      clack.note = origNote;
      clack.outro = origOutro;
    },
  };
}

const PLANNING_SKILLS = ['bmad-prd', 'bmad-architecture', 'bmad-create-epics-and-stories', 'bmad-create-story'];

async function testStep6bUcgAwareness() {
  console.log(`${colors.yellow}Test Suite 8: Step 6b — UCG-awareness shaping${colors.reset}\n`);

  const { Installer, PORTABILITY_GAP_LINE } = require('../tools/cli/lib/installer');
  const { promptInstall } = require('../tools/cli/lib/ui');

  // --- ui.js promptInstall surfaces exactly one new opt-in -------------
  // (a) the confirm wiring: grep-style assertions on the source.
  {
    const uiSrc = await fs.readFile(path.join(REPO_ROOT, 'tools/cli/lib/ui.js'), 'utf8');
    const enableCount = (uiSrc.match(/enable_ucg_awareness/g) || []).length;
    assert(enableCount >= 1, 'ui.js references enable_ucg_awareness', `count=${enableCount}`);
    // the new confirm carries initialValue: false (off-by-default twin)
    assert(/initialValue:\s*false/.test(uiSrc), 'a confirm with initialValue: false exists (off-by-default)');
    // it is threaded onto the returned config object
    assert(/return\s*{[\s\S]*enable_ucg_awareness[\s\S]*}/.test(uiSrc), 'enable_ucg_awareness threaded onto returned config');
  }

  // (b) opt-out is a true no-op: install({enable_ucg_awareness:false}) writes
  //     no _bmad/custom/*.toml even with engine + skills present. Anti-vacuous
  //     twin: deleting the gate (always-write) would create the file here.
  {
    const projectDir = await makeTempDir('s6b-optout');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, PLANNING_SKILLS);
      const installer = new Installer();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'optout',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: false,
        _action: 'fresh',
      });
      restore();
      assert(result.success === true, 'opt-out install returns success');
      const customDir = path.join(projectDir, '_bmad', 'custom');
      const wrote = (await fs.pathExists(customDir)) ? await fs.readdir(customDir) : [];
      const tomls = wrote.filter((f) => f.endsWith('.toml'));
      assert(tomls.length === 0, 'Twin: opt-out writes NO _bmad/custom/*.toml', `found ${tomls.join(', ')}`);
    } catch (error) {
      assert(false, 'opt-out no-op completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // (c) promptInstall returns the boolean from the confirm mock, and the
  //     update path leaves it falsy. ui.js DESTRUCTURES @clack/prompts at load;
  //     clack's exports are non-configurable bindings (reassignment is a silent
  //     no-op), so we replace the CACHED clack module exports with a writable
  //     copy BEFORE re-requiring ui.js, and run in a fresh temp cwd so the
  //     existing-install select() branch is skipped.
  {
    const clackPath = require.resolve('@clack/prompts');
    const uiPath = require.resolve('../tools/cli/lib/ui');
    const realClack = require('@clack/prompts');
    const origCwd = process.cwd();
    const promptDir = await makeTempDir('s6b-promptinstall');
    const restore = suppressConsole();

    let confirmAnswers = [];
    let confirmIdx = 0;
    // A writable stand-in for the clack module: copy every real export, then
    // override the interactive ones. ui.js's `require('@clack/prompts')` will
    // receive this object once we swap it into require.cache.
    const stubClack = {
      ...realClack,
      text: async () => 'p',
      multiselect: async () => ['claude-code'],
      select: async () => 'fresh',
      confirm: async () => confirmAnswers[confirmIdx++],
      intro: () => {},
      outro: () => {},
      note: () => {},
      log: { ...realClack.log, info: () => {}, warn: () => {} },
    };
    const realClackCacheExports = require.cache[clackPath].exports;

    try {
      require.cache[clackPath].exports = stubClack;
      process.chdir(promptDir);
      delete require.cache[uiPath];
      const ui = require(uiPath); // re-require so the destructure binds stubs
      const u = new ui.UI();
      u.displayBanner = () => {};

      // [install_learning=true, enable_ucg_awareness=true]
      confirmAnswers = [true, true];
      confirmIdx = 0;
      const cfgTrue = await u.promptInstall();
      assert(cfgTrue.enable_ucg_awareness === true, 'confirm()=true -> config.enable_ucg_awareness === true');

      // [install_learning=true, enable_ucg_awareness=false]
      confirmAnswers = [true, false];
      confirmIdx = 0;
      const cfgFalse = await u.promptInstall();
      assert(cfgFalse.enable_ucg_awareness === false, 'confirm()=false -> config.enable_ucg_awareness === false');
    } catch (error) {
      assert(false, 'promptInstall confirm wiring completes without error', error.message + '\n' + error.stack);
    } finally {
      process.chdir(origCwd);
      require.cache[clackPath].exports = realClackCacheExports;
      restore();
      delete require.cache[uiPath]; // restore the unstubbed ui module for later suites
      await fs.remove(promptDir);
    }
  }

  // --- present-only enumeration -> stamped overlays --------------------
  // Anti-vacuous twin: a fifth non-planning skill (bmad-dev-story) present is
  // NOT enrolled (only the four planning targets), and an absent planning skill
  // (bmad-create-story) is skipped.
  {
    const projectDir = await makeTempDir('s6b-present-only');
    try {
      await seedEngine(projectDir);
      // present: bmad-prd, bmad-architecture (+ a non-planning bmad-dev-story);
      // absent: bmad-create-story, bmad-create-epics-and-stories.
      await seedSkills(projectDir, ['bmad-prd', 'bmad-architecture', 'bmad-dev-story']);
      const installer = new Installer();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'present-only',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      assert(result.success === true, 'install returns success');

      const customDir = path.join(projectDir, '_bmad', 'custom');
      const prdPath = path.join(customDir, 'bmad-prd.toml');
      const archPath = path.join(customDir, 'bmad-architecture.toml');
      assert(await fs.pathExists(prdPath), 'bmad-prd.toml written (present skill)');
      assert(await fs.pathExists(archPath), 'bmad-architecture.toml written (present skill)');

      const prdText = await fs.readFile(prdPath, 'utf8');
      assert(prdText.includes('block = "ucg-awareness"'), 'bmad-prd.toml carries [ucg] block = "ucg-awareness"');
      assert(/\[ucg:bmad-prd-\d+\]/.test(prdText), 'bmad-prd.toml carries a persistent_facts entry');
      const archText = await fs.readFile(archPath, 'utf8');
      assert(archText.includes('block = "ucg-awareness"'), 'bmad-architecture.toml carries block = "ucg-awareness"');
      assert(/persistent_facts/.test(archText), 'bmad-architecture.toml carries persistent_facts');

      assert(!(await fs.pathExists(path.join(customDir, 'bmad-create-story.toml'))), 'absent bmad-create-story skipped (no overlay)');
      assert(
        !(await fs.pathExists(path.join(customDir, 'bmad-dev-story.toml'))),
        'Twin: non-planning bmad-dev-story NOT enrolled (only the four planning targets)',
      );
    } catch (error) {
      assert(false, 'present-only enumeration completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- degrade-not-throw (one fragment throws, another succeeds) -------
  // Stub runStep6bMerge so bmad-prd throws and bmad-architecture succeeds.
  // Anti-vacuous twin is documented below: without the try-catch the throw
  // propagates and install() rejects + no manifest.
  {
    const projectDir = await makeTempDir('s6b-degrade');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, ['bmad-prd', 'bmad-architecture']);
      const installer = new Installer();

      // Capture warnings via the clack log.warn spy.
      const spy = spyClackSinks();
      const origRunner = installer.runStep6bMerge.bind(installer);
      installer.runStep6bMerge = (targetPath, fragmentPath) => {
        if (targetPath.includes('bmad-prd')) {
          throw new Error('simulated bmad-prd merge failure');
        }
        return origRunner(targetPath, fragmentPath); // bmad-architecture really merges
      };

      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'degrade',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      spy.restore();

      assert(result.success === true, 'install resolves success:true despite a per-fragment failure');
      const manifestPath = path.join(projectDir, '_bmad/_config/ucg-manifest.yaml');
      assert(await fs.pathExists(manifestPath), 'manifest (Step 7) still written after degrade');
      assert(
        await fs.pathExists(path.join(projectDir, '_bmad', 'custom', 'bmad-architecture.toml')),
        'the other fragment (bmad-architecture) still merged',
      );
      const prdWarnings = spy.captured.filter((m) => /bmad-prd/.test(m) && /fail/i.test(m));
      assert(prdWarnings.length === 1, 'exactly one warning recorded for bmad-prd', `found ${prdWarnings.length}`);
    } catch (error) {
      assert(false, 'degrade-not-throw completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- absent resolve_customization.py -> verify-only no-op ---------
  // No engine seeded; assert no _bmad/custom/*.toml, exactly one warning,
  // success true, AND the standalone path intact (formalize_check.py + skill).
  {
    const projectDir = await makeTempDir('s6b-absent-resolve');
    try {
      await seedSkills(projectDir, PLANNING_SKILLS); // skills present, but NO engine
      const installer = new Installer();
      const spy = spyClackSinks();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'absent-resolve',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      spy.restore();

      assert(result.success === true, 'install returns success with absent engine');
      const customDir = path.join(projectDir, '_bmad', 'custom');
      const wrote = (await fs.pathExists(customDir)) ? await fs.readdir(customDir) : [];
      const tomls = wrote.filter((f) => f.endsWith('.toml'));
      assert(tomls.length === 0, 'NO _bmad/custom/*.toml written (no dark write)', `found ${tomls.join(', ')}`);
      const engineWarns = spy.captured.filter((m) => /resolve_customization\.py|customization engine/i.test(m));
      assert(engineWarns.length === 1, 'exactly one absent-engine warning', `found ${engineWarns.length}`);

      // Anti-vacuous twin: standalone verify-only path intact.
      const ucgSkill = path.join(projectDir, '_bmad/ucg/ultracode-goal');
      assert(
        await fs.pathExists(path.join(ucgSkill, 'scripts', 'formalize_check.py')),
        'Twin: formalize_check.py present (verify-only still works)',
      );
      assert(
        await fs.pathExists(path.join(ucgSkill, 'skills', 'ucg-formalize', 'SKILL.md')),
        'Twin: /ucg-formalize skill present in installed tree',
      );
    } catch (error) {
      assert(false, 'absent-resolve completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- schema-mismatch -> one drift-warning, run still succeeds -----
  {
    const projectDir = await makeTempDir('s6b-schema-mismatch');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, ['bmad-prd', 'bmad-architecture']);
      const installer = new Installer();
      const spy = spyClackSinks();
      const origRunner = installer.runStep6bMerge.bind(installer);
      installer.runStep6bMerge = (targetPath, fragmentPath) => {
        if (targetPath.includes('bmad-prd')) {
          return { status: 'skipped', skipped: 'schema-mismatch', conflicts: [], rows_added: 0, rows_removed: 0 };
        }
        return origRunner(targetPath, fragmentPath);
      };

      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'schema-mismatch',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      spy.restore();

      assert(result.success === true, 'install returns success on schema-mismatch');
      const driftWarns = spy.captured.filter((m) => /bmad-prd/.test(m) && /drift|schema|persistent_facts/i.test(m));
      assert(driftWarns.length === 1, 'exactly one drift-warning for bmad-prd', `found ${driftWarns.length}`);
      assert(
        !(await fs.pathExists(path.join(projectDir, '_bmad', 'custom', 'bmad-prd.toml'))),
        'schema-mismatch wrote nothing for bmad-prd',
      );
      assert(
        await fs.pathExists(path.join(projectDir, '_bmad', 'custom', 'bmad-architecture.toml')),
        'the other fragment still merged after the mismatch',
      );
    } catch (error) {
      assert(false, 'schema-mismatch completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- idempotent reinstall (byte-identical) + update non-wipe ---------
  {
    const crypto = require('node:crypto');
    const projectDir = await makeTempDir('s6b-idempotent');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, ['bmad-prd', 'bmad-architecture']);
      const installer = new Installer();
      const config = {
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'idempotent',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      };
      const prdPath = path.join(projectDir, '_bmad', 'custom', 'bmad-prd.toml');
      const sha = async () =>
        crypto
          .createHash('sha256')
          .update(await fs.readFile(prdPath))
          .digest('hex');

      let restore = suppressConsole();
      await installer.install({ ...config });
      restore();
      const hash1 = await sha();

      restore = suppressConsole();
      await installer.install({ ...config });
      restore();
      const hash2 = await sha();
      assert(hash1 === hash2, 'reinstall leaves bmad-prd.toml byte-identical');

      // single [ucg] block (no append-duplication zombie)
      const text2 = await fs.readFile(prdPath, 'utf8');
      const ucgBlocks = (text2.match(/^\[ucg\]\s*$/gm) || []).length;
      assert(ucgBlocks === 1, 'exactly one [ucg] block after reinstall (no zombie)', `found ${ucgBlocks}`);

      // Anti-vacuous twin: mutating the overlay content changes the hash.
      await fs.appendFile(prdPath, '\n# tampered\n', 'utf8');
      const hashMut = await sha();
      assert(hashMut !== hash1, 'Twin: mutated content yields a DIFFERENT hash (comparison reads real bytes)');

      // update-action install does not delete _bmad/custom/ user state.
      restore = suppressConsole();
      await installer.install({ projectDir, ucgFolder: '_bmad/ucg', _action: 'update' });
      restore();
      assert(await fs.pathExists(prdPath), 'update-action install preserves _bmad/custom/bmad-prd.toml');
    } catch (error) {
      assert(false, 'idempotent reinstall completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- cross-provider honesty (operator-benchmark machine half) --------
  {
    const projectDir = await makeTempDir('s6b-honesty');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, PLANNING_SKILLS);
      const installer = new Installer();

      // Spy BEFORE suppressConsole reassigns stdout — capture notes + warnings.
      const spy = spyClackSinks();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'honesty',
        ides: ['cursor'], // excludes claude-code -> portability note fires
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      spy.restore();

      const joined = spy.joined();
      const claudeCodeOnlyLines = joined.split('\n').filter((l) => CLAUDE_CODE_ONLY.test(l)).length;
      assert(claudeCodeOnlyLines === 1, 'exactly one /Claude.?Code.*only/i line emitted', `found ${claudeCodeOnlyLines}`);
      assert(
        STEP6B_FORBIDDEN_ENFORCEMENT.test(joined) === false,
        'ZERO forbidden cross-provider auto-enforcement phrases',
        `matched: ${JSON.stringify(joined.match(STEP6B_FORBIDDEN_ENFORCEMENT))}`,
      );
      // the exported constant is the line printed (and itself clean)
      assert(CLAUDE_CODE_ONLY.test(PORTABILITY_GAP_LINE), 'PORTABILITY_GAP_LINE matches the positive shape');
      assert(STEP6B_FORBIDDEN_ENFORCEMENT.test(PORTABILITY_GAP_LINE) === false, 'PORTABILITY_GAP_LINE matches none of the forbidden set');

      // the four overlays still wrote for present skills (never no-install)
      const customDir = path.join(projectDir, '_bmad', 'custom');
      for (const skill of PLANNING_SKILLS) {
        assert(await fs.pathExists(path.join(customDir, `${skill}.toml`)), `${skill}.toml still wrote on a non-Claude-Code provider`);
      }
      assert(result.success === true, 'install returns success on a non-Claude-Code provider');

      // Anti-vacuous twin: a forbidden literal flips the negative guard true.
      const tamperedJoined = joined + '\npreflight enforced on cursor across all providers';
      assert(
        STEP6B_FORBIDDEN_ENFORCEMENT.test(tamperedJoined) === true,
        'Twin: a forbidden literal flips STEP6B_FORBIDDEN_ENFORCEMENT.test to true',
      );
      // positive count fails on empty output (non-vacuous)
      assert(''.split('\n').filter((l) => CLAUDE_CODE_ONLY.test(l)).length === 0, 'Twin: count===1 fails on empty output');
    } catch (error) {
      assert(false, 'cross-provider honesty completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  console.log('');
}

// ============================================================
// Test Suite 8b: Step 6b decline no-op
// ============================================================
//
// The decline path writes nothing: enable_ucg_awareness=false skips Step 6b
// entirely, so merge_customization.py is never spawned and the _bmad/custom/
// file inventory + bytes equal the pre-install set exactly. The positive
// control (=true) proves the no-op is caused by the decline GATE, not an inert
// step. And /ucg-formalize (formalize_check.py) stays invocable after decline
// (verify-without-shape).

/** Snapshot {filename -> sha256(bytes)} of _bmad/custom/*.toml (empty if dir absent). */
async function snapshotCustomToml(projectDir) {
  const crypto = require('node:crypto');
  const customDir = path.join(projectDir, '_bmad', 'custom');
  if (!(await fs.pathExists(customDir))) return {};
  const out = {};
  for (const name of await fs.readdir(customDir)) {
    if (!name.endsWith('.toml')) continue;
    const bytes = await fs.readFile(path.join(customDir, name));
    out[name] = crypto.createHash('sha256').update(bytes).digest('hex');
  }
  return out;
}

/** grep-style count of literal `[ucg]` stamp headers under _bmad/custom/. */
async function countUcgStamps(projectDir) {
  const customDir = path.join(projectDir, '_bmad', 'custom');
  if (!(await fs.pathExists(customDir))) return 0;
  let count = 0;
  for (const name of await fs.readdir(customDir)) {
    if (!name.endsWith('.toml')) continue;
    const text = await fs.readFile(path.join(customDir, name), 'utf8');
    count += (text.match(/^\[ucg\]\s*$/gm) || []).length;
  }
  return count;
}

async function testStep6bDeclineNoOp() {
  console.log(`${colors.yellow}Test Suite 8b: Step 6b decline no-op${colors.reset}\n`);

  const { Installer } = require('../tools/cli/lib/installer');
  const { spawnSync } = require('node:child_process');

  // --- enable_ucg_awareness=false writes NOTHING under _bmad/custom/ ----
  {
    const projectDir = await makeTempDir('s8b-decline');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, PLANNING_SKILLS);

      // Pre-install custom-toml inventory (engine + skills present, no UCG yet).
      const before = await snapshotCustomToml(projectDir);

      const installer = new Installer();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'decline-noop',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: false,
        _action: 'fresh',
      });
      restore();
      assert(result.success === true, 'declined install returns success');

      // Inventory + bytes equal the pre-install set exactly (no UCG file/byte).
      const after = await snapshotCustomToml(projectDir);
      assert(
        JSON.stringify(before) === JSON.stringify(after),
        '_bmad/custom/*.toml inventory + bytes unchanged by a declined install',
        `before=${JSON.stringify(before)} after=${JSON.stringify(after)}`,
      );
      // Zero [ucg] stamps anywhere under _bmad/custom/ (grep -rc '\[ucg\]' == 0).
      assert((await countUcgStamps(projectDir)) === 0, 'zero [ucg] stamps under _bmad/custom/ after decline');

      // /ucg-formalize (formalize_check.py) is still invocable after a
      // decline — the standalone gate path is unaffected (verify-without-shape).
      const formalize = path.join(projectDir, '_bmad', 'ucg', 'ultracode-goal', 'scripts', 'formalize_check.py');
      assert(await fs.pathExists(formalize), 'formalize_check.py installed (standalone gate present after decline)');
      const proc = spawnSync('uv', ['run', '--script', formalize, '--help'], { encoding: 'utf8' });
      assert(
        proc.status === 0 && /usage:\s*formalize_check\.py/i.test(proc.stdout),
        'formalize_check.py runs (--help) after decline',
        `status=${proc.status} stderr=${(proc.stderr || '').slice(0, 200)}`,
      );
    } catch (error) {
      assert(false, 'decline no-op completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- positive-control twin: the SAME harness with =true DOES create at
  //     least one _bmad/custom/{skill}.toml carrying an [ucg] stamp — proving
  //     the no-op above is caused by the decline gate, not an inert Step 6b. ---
  {
    const projectDir = await makeTempDir('s8b-accept');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, PLANNING_SKILLS);

      const installer = new Installer();
      const restore = suppressConsole();
      const result = await installer.install({
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'accept-control',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
        _action: 'fresh',
      });
      restore();
      assert(result.success === true, 'Twin: accepted install returns success');

      const after = await snapshotCustomToml(projectDir);
      const wroteToml = Object.keys(after);
      assert(
        wroteToml.length > 0,
        'Twin: accept (=true) DOES create at least one _bmad/custom/{skill}.toml',
        `wrote=${wroteToml.join(', ')}`,
      );
      assert(
        (await countUcgStamps(projectDir)) >= 1,
        'Twin: at least one [ucg] stamp under _bmad/custom/ when accepted (gate, not inert step)',
      );
    } catch (error) {
      assert(false, 'positive-control completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  console.log('');
}

// ============================================================
// Test Suite 8c: Anti-zombie reinstall integration test
// ============================================================
//
// Drives the REAL installer reinstall PATH end-to-end — installer.install()
// with _action='update', which runs `fs.remove(ucgDir)` (installer.js:50, skill
// tree only) then copySrcFiles then the gated Step-6b UCG-awareness merge —
// N>=3 times against a temp project, and asserts the injected persistent_facts
// content stays byte-stable in the un-wiped _bmad/custom/ overlay. DISTINCT
// from Suite 8's single byte-identical reinstall and from the
// merge_customization.py UNIT idempotency test: this proves the
// fs.remove-then-recopy flow does not zombie-duplicate, refresh a stale
// [ucg].version, or clobber human content across N installer runs.
//
// Framework note: there is no Vitest in this repo (the story spec's
// "Vitest/Node" file is corrected); this is a plain node Suite wired into the
// existing `npm run test:cli`, using the same assert()/suppressConsole()/temp-
// project/seedEngine/seedSkills helpers as Suite 8.

const REINSTALL_FRAGMENTS_DIR = path.join(REPO_ROOT, 'skills', 'ultracode-goal', 'assets', 'ucg-awareness');
// The per-directive id marker carried by every UCG-stamped persistent_facts
// string, e.g. "[ucg:bmad-prd-01]" — same shape as merge_customization.py's
// UCG_MARKER. Count/strip/match assertions key off THIS marker + the [ucg]
// stamp, never off a per-item version (which the overlay format does not define).
const UCG_ITEM_MARKER = /\[ucg:[a-z0-9-]+-\d+\]/;

/**
 * Parse a TOML file via python3's stdlib tomllib and return the JS object.
 * Fail-CLOSED (fail-loud, mirrors gate_eval.py:201-203 posture): a
 * non-zero exit, an unreadable/garbled file, or unparseable JSON THROWS — never
 * silently returns {} — so an absent/garbled overlay can never make a byte-
 * stability assertion trivially true.
 */
function parseTomlViaPython(tomlPath) {
  const { spawnSync } = require('node:child_process');
  const code = [
    'import tomllib, json, sys',
    'p = sys.argv[1]',
    'with open(p, "rb") as fh:',
    '    data = tomllib.load(fh)',
    'sys.stdout.write(json.dumps(data))',
  ].join('\n');
  const proc = spawnSync('python3', ['-c', code, tomlPath], { encoding: 'utf8' });
  if (proc.status !== 0) {
    throw new Error(`parseTomlViaPython failed (status=${proc.status}) for ${tomlPath}: ${(proc.stderr || '').trim()}`);
  }
  try {
    return JSON.parse(proc.stdout);
  } catch (error) {
    throw new Error(`parseTomlViaPython got unparseable JSON for ${tomlPath}: ${error.message}`);
  }
}

/**
 * Serialize a JS object to TOML text via tomli-w (the same writer
 * merge_customization.py uses), so fixtures round-trip byte-cleanly through
 * tomllib. Runs `uv run --with tomli-w` (uv is the merge tool's own runner).
 * Throws on any non-zero exit (fail-loud fixture setup, not a silent skip).
 */
function serializeTomlViaPython(obj) {
  const { spawnSync } = require('node:child_process');
  const code = ['import json, sys, tomli_w', 'data = json.load(sys.stdin)', 'sys.stdout.write(tomli_w.dumps(data))'].join('\n');
  const proc = spawnSync('uv', ['run', '--with', 'tomli-w', 'python3', '-c', code], {
    encoding: 'utf8',
    input: JSON.stringify(obj),
  });
  if (proc.status !== 0) {
    throw new Error(`serializeTomlViaPython failed (status=${proc.status}): ${(proc.stderr || '').trim()}`);
  }
  return proc.stdout;
}

/** workflow.persistent_facts as an array (fail-closed: throws if not an array). */
function persistentFacts(parsed) {
  const facts = parsed?.workflow?.persistent_facts;
  if (!Array.isArray(facts)) {
    throw new TypeError(`expected workflow.persistent_facts array, got ${JSON.stringify(facts)}`);
  }
  return facts;
}

/** The UCG-stamped subset: persistent_facts strings carrying a [ucg:<id>] marker. */
function stampedItems(facts) {
  return facts.filter((f) => typeof f === 'string' && UCG_ITEM_MARKER.test(f));
}

/** The non-UCG (human-owned) subset: facts with NO [ucg:<id>] marker. */
function nonStampedItems(facts) {
  return facts.filter((f) => typeof f !== 'string' || !UCG_ITEM_MARKER.test(f));
}

/** Count UCG-stamped persistent_facts items. */
function countStampedItems(facts) {
  return stampedItems(facts).length;
}

/** Read the shipped fragment's items + block-level [ucg].version (source of truth). */
function readFragment(skill) {
  const parsed = parseTomlViaPython(path.join(REINSTALL_FRAGMENTS_DIR, `${skill}.toml`));
  const items = Array.isArray(parsed.persistent_facts) ? parsed.persistent_facts : [];
  const version = parsed.ucg?.version;
  return { items, version, count: items.length };
}

/** sha256 of a file's raw bytes. */
async function sha256File(filePath) {
  const crypto = require('node:crypto');
  return crypto
    .createHash('sha256')
    .update(await fs.readFile(filePath))
    .digest('hex');
}

function jsonEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Twins are guarded negative paths: skip-by-default, opt in via env flag so
// each assertion is proven to FLAG a hollow implementation (the predicate is
// discriminating, not vacuously satisfied by a no-op installer). They mutate an
// in-memory copy of the REAL post-install parse to model a hollow merge, then
// assert the assertion's predicate catches the mutant.
const TWINS_ENABLED = process.env.UCG_REINSTALL_TWINS === '1';

async function twin(name, fn) {
  if (!TWINS_ENABLED) {
    console.log(`${colors.dim}  ↳ twin skipped (set UCG_REINSTALL_TWINS=1): ${name}${colors.reset}`);
    return;
  }
  await fn();
}

async function testReinstallAntiZombie() {
  console.log(`${colors.yellow}Test Suite 8c: Anti-zombie reinstall${colors.reset}\n`);

  const { Installer } = require('../tools/cli/lib/installer');
  const SKILL = 'bmad-prd'; // a targeted planning fragment with a real overlay
  const N = 3; // N>=3 consecutive installer-driven reinstalls
  const fragment = readFragment(SKILL);

  // Guard: the fragment itself must ship a non-empty stamped set, else every
  // count/deep-equal assertion below would be vacuously satisfiable.
  assert(fragment.count >= 1, 'PRE: shipped fragment ships >=1 stamped item', `count=${fragment.count}`);
  assert(typeof fragment.version === 'string' && fragment.version.length > 0, 'PRE: fragment carries a block-level [ucg].version');

  // --- byte-stable SHA-256 across N installer reinstalls --------------
  {
    const projectDir = await makeTempDir('s8c-bytestable');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, [SKILL]); // at least one present planning workflow
      const installer = new Installer();
      const customToml = path.join(projectDir, '_bmad', 'custom', `${SKILL}.toml`);
      const baseConfig = {
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'reinstall-bytestable',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
      };

      // Run 1 (fresh) seeds the overlay; runs 2..N drive the update reinstall
      // path (fs.remove(ucgDir) at installer.js:50, then Step-6b merge).
      const hashes = [];
      for (let run = 1; run <= N; run++) {
        const restore = suppressConsole();
        const result = await installer.install({ ...baseConfig, _action: run === 1 ? 'fresh' : 'update' });
        restore();
        assert(result.success === true, `installer run ${run} returns success`);
        assert(await fs.pathExists(customToml), `_bmad/custom/${SKILL}.toml present after run ${run} (overlay never wiped)`);
        hashes.push(await sha256File(customToml));
      }

      // The merge target is the un-wiped overlay: byte-identical run 2..N.
      assert(hashes[1] === hashes[2], `sha256(${SKILL}.toml) byte-identical run 2 === run ${N}`, `run2=${hashes[1]} runN=${hashes[2]}`);
      assert(
        hashes.slice(1).every((h) => h === hashes[1]),
        'every reinstall run 2..N is byte-identical (anti-zombie convergence)',
        `hashes=${JSON.stringify(hashes)}`,
      );

      // Anti-vacuous: prove the installer actually WROTE a non-empty overlay
      // (not a no-op installer that never touches persistent_facts at all).
      const facts = persistentFacts(parseTomlViaPython(customToml));
      assert(countStampedItems(facts) >= 1, 'overlay carries >=1 stamped item (installer is not a no-op writer)');

      // Twin: a hand-injected duplicate stamped item before a run, OR an
      // append-without-strip merge, makes hashes diverge / item count grow.
      // Modeled in-memory: an append-without-strip hollow merge would yield a
      // distinct byte image (more items) -> a DIFFERENT hash; the byte-stability equality
      // assertion would then fail. Proven by detecting the mutant.
      await twin('append-without-strip diverges hashes', () => {
        const crypto = require('node:crypto');
        const realBytes = JSON.stringify(facts);
        const hollowBytes = JSON.stringify([...facts, ...stampedItems(facts)]); // append, no strip
        const realHash = crypto.createHash('sha256').update(realBytes).digest('hex');
        const hollowHash = crypto.createHash('sha256').update(hollowBytes).digest('hex');
        assert(realHash !== hollowHash, 'Twin: append-without-strip yields a DIFFERENT image -> byte-stability equality would fail');
        assert(
          countStampedItems([...facts, ...stampedItems(facts)]) > fragment.count,
          'Twin: append-without-strip grows the stamped count past the fragment count',
        );
      });
    } catch (error) {
      assert(false, 'byte-stable reinstall completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- stamped item count == fragment count (1x, never Nx/2x) ---------
  {
    const projectDir = await makeTempDir('s8c-count');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, [SKILL]);
      const installer = new Installer();
      const customToml = path.join(projectDir, '_bmad', 'custom', `${SKILL}.toml`);
      const baseConfig = {
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'reinstall-count',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
      };

      for (let run = 1; run <= N; run++) {
        const restore = suppressConsole();
        await installer.install({ ...baseConfig, _action: run === 1 ? 'fresh' : 'update' });
        restore();
        const parsed = parseTomlViaPython(customToml);
        const facts = persistentFacts(parsed);
        const count = countStampedItems(facts);
        assert(
          count === fragment.count,
          `no append-duplication across N installs: stamped count === fragment count after run ${run}`,
          `count=${count} fragment=${fragment.count}`,
        );
        // Owned by the [ucg] block: managed=true, block='ucg-awareness'.
        assert(parsed.ucg?.managed === true && parsed.ucg?.block === 'ucg-awareness', `[ucg] block owns the stamped set after run ${run}`);
      }

      // Twin: pre-seed TWO identical stamped items (a prior zombie) BEFORE a
      // run; the strip-then-reappend collapses them to exactly 1x. An append-
      // only hollow merge would stay >=2 and fail. We prove BOTH halves:
      //   (a) the real installer collapses a pre-seeded zombie to 1x;
      //   (b) an append-only mutant of the same input stays >2 (predicate catches it).
      await twin('pre-seeded zombie collapses to 1x; append-only mutant stays >=2', async () => {
        const zombieDir = await makeTempDir('s8c-count-zombie');
        try {
          await seedEngine(zombieDir);
          await seedSkills(zombieDir, [SKILL]);
          const zInstaller = new Installer();
          const zToml = path.join(zombieDir, '_bmad', 'custom', `${SKILL}.toml`);
          // Fresh install to seed the overlay.
          let r = suppressConsole();
          await zInstaller.install({ ...baseConfig, projectDir: zombieDir, _action: 'fresh' });
          r();
          // Hand-inject a DUPLICATE of the first stamped item (simulate a zombie).
          const seeded = parseTomlViaPython(zToml);
          const dupItem = stampedItems(persistentFacts(seeded))[0];
          seeded.workflow.persistent_facts.push(dupItem);
          await fs.writeFile(zToml, serializeTomlViaPython(seeded), 'utf8');
          const preCount = countStampedItems(persistentFacts(parseTomlViaPython(zToml)));
          assert(preCount > fragment.count, 'Twin: pre-seeded overlay has a zombie duplicate (> fragment count)', `preCount=${preCount}`);
          // The append-only HOLLOW predicate would leave it >fragment; assert that.
          const hollowAppendOnly = [...persistentFacts(parseTomlViaPython(zToml)), ...fragment.items];
          assert(
            countStampedItems(hollowAppendOnly) > fragment.count,
            'Twin: an append-only (no-strip) merge keeps the zombie -> count stays >1x (predicate catches it)',
          );
          // The REAL installer reinstall collapses it back to exactly 1x.
          r = suppressConsole();
          await zInstaller.install({ ...baseConfig, projectDir: zombieDir, _action: 'update' });
          r();
          const postCount = countStampedItems(persistentFacts(parseTomlViaPython(zToml)));
          assert(
            postCount === fragment.count,
            'Twin: real installer collapses the pre-seeded zombie back to exactly 1x',
            `postCount=${postCount}`,
          );
        } finally {
          await fs.remove(zombieDir);
        }
      });
    } catch (error) {
      assert(false, 'stamped-count completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- stale block-level [ucg].version is refreshed in place ----------
  {
    const projectDir = await makeTempDir('s8c-stale');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, [SKILL]);
      const installer = new Installer();
      const customToml = path.join(projectDir, '_bmad', 'custom', `${SKILL}.toml`);
      const baseConfig = {
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'reinstall-stale',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
      };

      // Seed the overlay with a UCG block whose block-level [ucg].version is
      // STALE plus matching stamped items AND a prior-build stamped item whose
      // marker (bmad-prd-99) the current fragment no longer ships — so an
      // over-narrow strip would zombie it.
      const STALE = '0.0.0-stale';
      const staleItem = 'Stale prior-build UCG fact no longer shipped. [ucg:bmad-prd-99]';
      const seedDoc = {
        workflow: {
          persistent_facts: [...fragment.items.slice(0, 1), staleItem],
        },
        ucg: {
          managed: true,
          version: STALE,
          block: 'ucg-awareness',
          installed_at: '2020-01-01T00:00:00Z',
        },
      };
      await fs.ensureDir(path.dirname(customToml));
      await fs.writeFile(customToml, serializeTomlViaPython(seedDoc), 'utf8');

      // Drive the update reinstall path.
      const restore = suppressConsole();
      const result = await installer.install({ ...baseConfig, _action: 'update' });
      restore();
      assert(result.success === true, 'installer reinstall over a stale block returns success');

      const parsed = parseTomlViaPython(customToml);
      const facts = persistentFacts(parsed);
      const rawText = await fs.readFile(customToml, 'utf8');

      // (a) [ucg].version refreshed to current; the stale scalar is gone.
      assert(
        parsed.ucg?.version === fragment.version,
        'stale version block is refreshed not duplicated (a): [ucg].version === current fragment version',
        `got=${parsed.ucg?.version} want=${fragment.version}`,
      );
      assert(!rawText.includes(STALE), `(a): the literal '${STALE}' scalar is absent from the resolved overlay`);

      // (b) the stamped-item subset (by marker) deep-equals the fragment items.
      assert(
        jsonEqual(stampedItems(facts), fragment.items),
        '(b): stamped-item subset deep-equals the current fragment items',
        `got=${JSON.stringify(stampedItems(facts))}`,
      );
      assert(
        !stampedItems(facts).some((s) => s.includes('[ucg:bmad-prd-99]')),
        '(b): the stale cross-build marked item (bmad-prd-99) was stripped (no zombie)',
      );

      // (c) total stamped count === fragment count (no stale+current pile-up).
      assert(
        countStampedItems(facts) === fragment.count,
        '(c): total stamped count === fragment count (1x, no pile-up)',
        `count=${countStampedItems(facts)} fragment=${fragment.count}`,
      );

      // Twin A: version-stamp NOT refreshed (write new items, leave [ucg].version
      // stale) -> assertion (a) fails. Twin B: over-narrow same-marker-only strip
      // leaves cross-build items -> count = 2x, assertion (c) fails.
      await twin('un-refreshed version stamp / over-narrow strip are caught', () => {
        // Twin A: hollow merge refreshes items but zombies the version scalar.
        const hollowA = { ...parsed, ucg: { ...parsed.ucg, version: STALE } };
        assert(hollowA.ucg.version !== fragment.version, 'Twin A: un-refreshed [ucg].version (still stale) -> assertion (a) would fail');

        // Twin B: over-narrow strip keeps the prior-build marked item alongside
        // the fresh ones -> stamped count = fragment + 1 (>1x).
        const hollowB = [...fragment.items, staleItem];
        assert(
          countStampedItems(hollowB) > fragment.count,
          'Twin B: over-narrow same-marker-only strip zombies cross-build item -> count >1x, assertion (c) would fail',
        );
      });
    } catch (error) {
      assert(false, 'stale-version refresh completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  // --- human / non-UCG content byte-stable across N reinstalls --------
  {
    const projectDir = await makeTempDir('s8c-human');
    try {
      await seedEngine(projectDir);
      await seedSkills(projectDir, [SKILL]);
      const installer = new Installer();
      const customToml = path.join(projectDir, '_bmad', 'custom', `${SKILL}.toml`);
      const baseConfig = {
        projectDir,
        ucgFolder: '_bmad/ucg',
        project_name: 'reinstall-human',
        ides: ['claude-code'],
        install_learning: false,
        enable_ucg_awareness: true,
      };

      // Seed a human non-UCG persistent_facts item (no marker) + a human scalar
      // BEFORE the first reinstall, alongside one stamped item so a real merge
      // touches the array.
      const HUMAN_ITEM = 'Human-authored guardrail with no UCG marker; must survive byte-identical.';
      const HUMAN_SCALAR = 'do-not-touch-me';
      const seedDoc = {
        workflow: {
          persistent_facts: [HUMAN_ITEM, ...fragment.items.slice(0, 1)],
        },
        human_scalar: HUMAN_SCALAR,
        ucg: {
          managed: true,
          version: fragment.version,
          block: 'ucg-awareness',
          installed_at: '2026-06-25T00:00:00Z',
        },
      };
      await fs.ensureDir(path.dirname(customToml));
      await fs.writeFile(customToml, serializeTomlViaPython(seedDoc), 'utf8');

      for (let run = 1; run <= N; run++) {
        const restore = suppressConsole();
        await installer.install({ ...baseConfig, _action: 'update' });
        restore();
        const parsed = parseTomlViaPython(customToml);
        const facts = persistentFacts(parsed);
        // The human non-stamped subset is byte/value-stable (deep-equal).
        assert(
          jsonEqual(nonStampedItems(facts), [HUMAN_ITEM]),
          `human content byte-stable across N installs: non-stamped item preserved after run ${run}`,
          `got=${JSON.stringify(nonStampedItems(facts))}`,
        );
        assert(parsed.human_scalar === HUMAN_SCALAR, `human scalar preserved after run ${run}`, `got=${parsed.human_scalar}`);
      }

      // Twin: a drop-and-rewrite-all merge (rewrites the whole array) drops or
      // reorders the human item -> deep-equal breaks. Modeled: a hollow merge
      // that writes ONLY the fragment items (dropping human content) fails the
      // deep-equal predicate.
      await twin('drop-and-rewrite-all clobbers human content', () => {
        const facts = persistentFacts(parseTomlViaPython(customToml));
        const hollowRewriteAll = [...fragment.items]; // drops the human item entirely
        assert(
          !jsonEqual(nonStampedItems(hollowRewriteAll), [HUMAN_ITEM]),
          'Twin: drop-and-rewrite-all loses the human item -> deep-equal would fail (predicate catches it)',
        );
        // sanity: the real merge kept it (the predicate is satisfiable, not always-false)
        assert(jsonEqual(nonStampedItems(facts), [HUMAN_ITEM]), 'Twin: control — the real merge DID preserve the human item');
      });
    } catch (error) {
      assert(false, 'human-content preservation completes without error', error.message + '\n' + error.stack);
    } finally {
      await fs.remove(projectDir);
    }
  }

  console.log('');
}

// ============================================================
// Runner
// ============================================================

/**
 * Banner geometry: the installer box must render with a single, consistent
 * right edge, the horizontal rules must match the box's outer width, and the
 * box must fit the terminal at every width (regression: the tagline row used
 * to overflow the frame because over-long content padded to zero silently).
 */
async function testBannerGeometry() {
  console.log(`\n${colors.cyan}Banner geometry...${colors.reset}`);
  // eslint-disable-next-line no-control-regex -- stripping ANSI escape codes for width checks
  const strip = (s) => s.replaceAll(/\u001B\[\d+(?:;\d+)*m/g, '');
  const uiPath = require.resolve('../tools/cli/lib/ui.js');

  for (const cols of [80, 100, 60, 40]) {
    delete require.cache[uiPath];
    const originalColumns = process.stdout.columns;
    const originalLog = console.log;
    const originalWrite = process.stdout.write;
    const lines = [];
    process.stdout.columns = cols;
    console.log = (...args) => lines.push(args.join(' '));
    process.stdout.write = () => true; // swallow the clack intro frame
    try {
      const { UI } = require(uiPath);
      new UI().displayBanner();
    } finally {
      console.log = originalLog;
      process.stdout.write = originalWrite;
      process.stdout.columns = originalColumns;
    }

    const plain = lines.map(strip);
    const boxLines = plain.filter((l) => /[╔╟╚║╝]/.test(l));
    const edges = new Set(boxLines.map((l) => l.trimEnd().length));
    const edge = [...edges][0];
    const rules = plain.filter((l) => /━/.test(l));

    assert(edges.size === 1, `banner box has one consistent right edge at ${cols} cols`, `edges: ${[...edges].join(', ')}`);
    assert(edge <= cols, `banner box fits a ${cols}-col terminal`, `edge ${edge} > ${cols}`);
    assert(
      rules.every((l) => l.trimEnd().length === edge),
      `horizontal rules match the box width at ${cols} cols`,
    );
  }
}

async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('UCG CLI Integration Tests');
  console.log(`========================================${colors.reset}\n`);

  await testFreshInstall();
  await testUpdatePreservesConfig();
  await testHelpCatalogRegistration();
  await testUninstallCleansUp();
  await testIdeSkillInstallation();
  await testManifestAccuracy();
  await testFreshInstallWithoutLearning();
  await testGitignoreEntries();
  await testStep6bUcgAwareness();
  await testStep6bDeclineNoOp();
  await testReinstallAntiZombie();
  await testBannerGeometry();

  console.log(`${colors.cyan}========================================`);
  console.log('Test Results:');
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`========================================${colors.reset}\n`);

  if (failed === 0) {
    console.log(`${colors.green}All CLI integration tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}Some CLI integration tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
