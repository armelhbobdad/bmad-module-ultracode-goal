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
    assert(ucgRowCount === 2, 'reinstall keeps exactly one row set (_meta + capability)', `found ${ucgRowCount}`);

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
