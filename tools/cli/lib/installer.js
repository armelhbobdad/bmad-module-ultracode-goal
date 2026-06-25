/**
 * UCG Installer - Core orchestrator
 * Copies the ultracode-goal skill, installs it to IDEs, writes config + manifest.
 */

const path = require('node:path');
const { spawnSync } = require('node:child_process');
const fs = require('fs-extra');
const { spinner, log } = require('@clack/prompts');
const yaml = require('js-yaml');
const { installSkillsToIdes } = require('./ide-skills');
const { registerHelpEntries } = require('./help-catalog');
const { writeManifest } = require('./manifest');

// Dev-only artifacts never shipped into a user's project
const DEV_ARTIFACTS = new Set(['.analysis', '.decision-log.md', '__pycache__', '.pytest_cache', '.DS_Store', 'Thumbs.db']);

// The four Epic-1 planning fragments Step 6b enrolls (FR-8). Each maps to a
// real BMAD skill whose presence is probed before merging, and to a fragment
// under skills/ultracode-goal/assets/ucg-awareness/{skill}.toml (story 1.4).
// The TEA (Epic 2) and dev/review-cycle (Epic 3, AD-4 deferred) fragments are
// deliberately NOT enrolled here.
const STEP6B_PLANNING_FRAGMENTS = ['bmad-prd', 'bmad-architecture', 'bmad-create-epics-and-stories', 'bmad-create-story'];

// Single canonical cross-provider portability gap line (AC6 / AD-8 / NFR-6).
// Exported so the integration test asserts against this exact string. Story
// 1.11 will canonicalize it further (docs + operator rubric) — keep it a clean,
// honest sentence that matches /Claude.?Code.*only/i and contains NONE of the
// forbidden cross-provider auto-enforcement phrases. The note is non-blocking:
// the portable fragments + the standalone /ucg-formalize gate install on every
// provider; only the preflight HOOK auto-runs on Claude Code, and elsewhere
// /ucg-formalize is a manual on-demand verdict.
const PORTABILITY_GAP_LINE =
  'Automatic preflight gating at run start is a Claude Code-only capability; on other providers /ucg-formalize stays available as a manual, on-demand verdict you invoke yourself, while the portable shaping fragments and the standalone gate still install everywhere.';

class Installer {
  constructor() {
    // Resolve directories relative to this file (tools/cli/lib/ -> up 3 levels)
    const repoRoot = path.resolve(__dirname, '..', '..', '..');
    this.srcDir = path.join(repoRoot, 'skills');
    this.docsDir = path.join(repoRoot, 'docs');
  }

  async install(config) {
    const { projectDir, ucgFolder } = config;
    const ucgDir = path.join(projectDir, ucgFolder);
    const action = config._action || 'fresh';
    const s = spinner();

    // Handle update vs fresh for existing installation
    if (action === 'update' && (await fs.pathExists(ucgDir))) {
      const configPath = path.join(ucgDir, 'config.yaml');
      if (!config._savedConfigYaml && (await fs.pathExists(configPath))) {
        config._savedConfigYaml = await fs.readFile(configPath, 'utf8');
      }

      // On update, extract settings from saved config
      if (config._savedConfigYaml) {
        try {
          const savedData = yaml.load(config._savedConfigYaml);
          if (!config.ides && savedData.ides) config.ides = savedData.ides;
          if (config.install_learning == null && savedData.install_learning != null) config.install_learning = savedData.install_learning;
        } catch {
          /* ignore parse errors, defaults will apply */
        }
      }

      s.start('Updating UCG files...');
      await fs.remove(ucgDir);
      s.stop('Old files cleared');
    } else if (action === 'fresh' && (await fs.pathExists(ucgDir))) {
      s.start('Removing existing UCG installation...');
      await fs.remove(ucgDir);
      s.stop('Old installation removed');
    }

    // Ensure parent directory exists (for _bmad/ucg/)
    await fs.ensureDir(path.dirname(ucgDir));

    // Step 1: Copy source files
    s.start('Copying UCG files...');
    try {
      await this.copySrcFiles(ucgDir);
      s.stop('UCG files copied');
    } catch (error) {
      s.stop('Failed to copy UCG files');
      throw error;
    }

    // Step 2: Update .gitignore (the skill merges hooks into .claude/settings.local.json
    // at preflight — that file must never be committed)
    await this.updateGitignore(projectDir);

    // Step 3: Write config.yaml
    s.start('Writing configuration...');
    try {
      await this.writeConfig(ucgDir, config);
      s.stop('Configuration saved');
    } catch (error) {
      s.stop('Failed to write configuration');
      throw error;
    }

    // Step 4: Copy learning material (optional)
    if (config.install_learning !== false) {
      s.start('Copying learning & reference material...');
      try {
        await this.copyLearningMaterial(projectDir);
        s.stop('Learning material added to _ucg-learn/');
      } catch (error) {
        s.stop('Failed to copy learning material');
        throw error;
      }
    }

    // Step 5: Install the skill to selected IDEs
    let ideDirectories = [];
    const selectedIdes = config.ides || [];
    if (selectedIdes.length > 0) {
      s.start('Installing the skill to IDEs...');
      try {
        const ideResult = await installSkillsToIdes(projectDir, ucgDir, selectedIdes);
        ideDirectories = ideResult.directories || [];
        if (ideResult.installed > 0) {
          s.stop(`Skill installed for ${ideResult.ides.join(', ')}`);
        } else {
          s.stop('No IDE skill installation needed');
        }
      } catch (error) {
        s.stop('Failed to install the skill to IDEs');
        throw error;
      }
    }

    // Step 6: Register capabilities into the BMad help catalog so bmad-help
    // can route to the module (anti-zombie upsert — idempotent on update)
    let helpCatalog = null;
    s.start('Registering with the BMad help catalog...');
    try {
      const skillAssets = path.join(this.srcDir, 'ultracode-goal', 'assets');
      helpCatalog = await registerHelpEntries(projectDir, path.join(skillAssets, 'module-help.csv'), path.join(skillAssets, 'module.yaml'));
      s.stop(`Help catalog updated (${helpCatalog.targets.join(', ')})`);
    } catch (error) {
      s.stop('Failed to register with the BMad help catalog');
      throw error;
    }

    // Step 6b: Wire UCG-awareness shaping into the present BMAD planning
    // workflows (opt-in, FR-1). UNLIKE every other step, this one DEGRADES
    // rather than throws (AD-3/FR-12): any per-fragment failure, an absent
    // resolve engine, or a schema-mismatch warns and continues — install()
    // still returns success and Step 7 still writes the manifest.
    if (config.enable_ucg_awareness === true) {
      s.start('Wiring UCG-awareness into planning workflows...');
      const warnings = [];
      const warn = (msg) => {
        warnings.push(msg);
        log.warn(msg);
      };
      try {
        // Cross-provider honesty (AC6 / AD-8 / NFR-6): emit the single
        // portability gap line when the target IDE set excludes Claude Code.
        // Never a refusal, never a duplicate — exactly one print.
        const ides = Array.isArray(config.ides) ? config.ides : [];
        if (!ides.includes('claude-code')) {
          warn(PORTABILITY_GAP_LINE);
        }

        // FR-12 case-2: the merge engine deep_merge is imported by
        // merge_customization.py from {projectDir}/_bmad/scripts/resolve_customization.py.
        // If it is absent/older, no-op Step 6b entirely (verify-only degrade):
        // write nothing, warn once. The standalone /ucg-formalize gate +
        // formalize_check.py remain installed (INV-3).
        const enginePath = path.join(projectDir, '_bmad', 'scripts', 'resolve_customization.py');
        if (await fs.pathExists(enginePath)) {
          const fragmentsDir = path.join(this.srcDir, 'ultracode-goal', 'assets', 'ucg-awareness');
          let merged = 0;
          let skippedAbsent = 0;
          for (const skill of STEP6B_PLANNING_FRAGMENTS) {
            // Present-skill probe: the true signal is the BMAD skills tree, NOT
            // whether _bmad/custom/{skill}.toml already exists (architecture
            // Corrections line 146). Probe the resolved skills root.
            if (!(await this.isSkillPresent(projectDir, skill))) {
              skippedAbsent++;
              continue;
            }
            const fragmentPath = path.join(fragmentsDir, `${skill}.toml`);
            if (!(await fs.pathExists(fragmentPath))) {
              // A Phase-3-deferred fragment was never authored — skip silently
              // (FR-1 skip-absent also covers never-authored fragments).
              continue;
            }
            const targetPath = path.join(projectDir, '_bmad', 'custom', `${skill}.toml`);
            try {
              const outcome = this.runStep6bMerge(targetPath, fragmentPath);
              if (outcome.skipped === 'schema-mismatch') {
                warn(
                  `UCG-awareness shaping for ${skill}: target customization does not expose the ` +
                    `workflow.persistent_facts channel — drift detected, skipped (no write).`,
                );
              } else if (outcome.status === 'conflict') {
                merged++;
                warn(`UCG-awareness shaping for ${skill}: hand-edited rows left in place (${outcome.conflicts.join(', ')}).`);
              } else {
                merged++;
              }
            } catch (mergeError) {
              // Per-fragment failure DEGRADES — warn and continue, never abort.
              warn(`UCG-awareness shaping for ${skill} failed: ${mergeError.message}`);
            }
          }
          s.stop(`UCG-awareness shaping complete (${merged} merged, ${skippedAbsent} skipped — absent)`);
        } else {
          warn(
            'UCG-awareness shaping skipped: BMAD customization engine (_bmad/scripts/resolve_customization.py) ' +
              'not found — degrading to verify-only. The standalone /ucg-formalize gate is still installed.',
          );
          s.stop('UCG-awareness shaping skipped (verify-only)');
        }
      } catch (error) {
        // Belt-and-braces: Step 6b NEVER rethrows (degrade-not-throw, AD-3).
        s.stop('UCG-awareness shaping degraded');
        warn(`UCG-awareness shaping degraded: ${error.message}`);
      }
    }

    // Step 7: Write installation manifest
    s.start('Writing manifest...');
    try {
      const packageJson = require('../../../package.json');
      await writeManifest(projectDir, config, {
        version: packageJson.version,
        ideDirectories,
        helpCatalog,
      });
      s.stop('Installation manifest saved');
    } catch (error) {
      s.stop('Failed to write manifest');
      throw error;
    }

    return { success: true, ucgDir, projectDir };
  }

  /**
   * Probe whether a real BMAD skill is present in the project's skills tree.
   * The architecture Corrections row (line 146) warns: present-in-project !=
   * overlay-exists; the true signal is the BMAD skills tree. So we look for the
   * actual skill directory under any installed IDE skills root, never at
   * _bmad/custom/{skill}.toml.
   *
   * @param {string} projectDir - Project root
   * @param {string} skill - BMAD skill directory name (e.g. bmad-prd)
   * @returns {Promise<boolean>}
   */
  async isSkillPresent(projectDir, skill) {
    const roots = [
      path.join(projectDir, '.claude', 'skills'),
      path.join(projectDir, '.cursor', 'skills'),
      path.join(projectDir, '.opencode', 'skills'),
      path.join(projectDir, 'bmad', 'skills'),
      path.join(projectDir, '_bmad', 'skills'),
    ];
    for (const root of roots) {
      if (await fs.pathExists(path.join(root, skill))) return true;
    }
    return false;
  }

  /**
   * Spawn merge_customization.py for one present fragment and parse its JSON
   * result. Mirrors the FR-8 invocation:
   *   merge_customization.py --target _bmad/custom/{skill}.toml --fragment {fragment}
   * Run via `uv run --script` so its PEP-723 block auto-provisions tomli-w.
   *
   * Exit-code lanes (the merge family, NOT gate_eval): 0 = success/skip/
   * conflict, 1 = validation, 2 = missing engine. A non-zero exit or an
   * unparseable payload throws — the Step-6b try-catch degrades it to a warning.
   *
   * @param {string} targetPath - Absolute path to _bmad/custom/{skill}.toml
   * @param {string} fragmentPath - Absolute path to the fragment TOML
   * @returns {{status:string, skipped:(string|null), conflicts:string[], rows_added:number, rows_removed:number}}
   */
  runStep6bMerge(targetPath, fragmentPath) {
    const script = path.join(this.srcDir, 'ultracode-goal', 'scripts', 'merge_customization.py');
    const result = spawnSync('uv', ['run', '--script', script, '--target', targetPath, '--fragment', fragmentPath], {
      encoding: 'utf8',
    });

    if (result.error) {
      throw new Error(`failed to spawn merge tool: ${result.error.message}`);
    }
    // Exit 2 = missing engine dependency; 1 = validation error. Both are
    // failures the caller degrades. Exit 0 = success/skip/conflict (JSON on
    // stdout).
    if (result.status === 2) {
      throw new Error('merge engine (resolve_customization.py) missing');
    }
    if (result.status === 1) {
      throw new Error(`merge validation error: ${(result.stderr || '').trim()}`);
    }
    if (result.status !== 0) {
      throw new Error(`merge tool exited ${result.status}: ${(result.stderr || '').trim()}`);
    }

    let payload;
    try {
      payload = JSON.parse(result.stdout);
    } catch {
      throw new Error(`unparseable merge output: ${(result.stdout || '').trim().slice(0, 200)}`);
    }
    return {
      status: payload.status,
      skipped: payload.skipped ?? null,
      conflicts: Array.isArray(payload.conflicts) ? payload.conflicts : [],
      rows_added: payload.rows_added ?? 0,
      rows_removed: payload.rows_removed ?? 0,
    };
  }

  /**
   * Copy skills/ content into the target UCG directory.
   * The single ultracode-goal skill directory is copied alongside module.yaml,
   * filtering out dev/test artifacts that have no place in a user's project.
   */
  async copySrcFiles(ucgDir) {
    const copyFilter = (src) => {
      const base = path.basename(src);
      if (DEV_ARTIFACTS.has(base)) return false;
      // Skip pytest suites — dev-only, not needed at runtime
      if (base === 'tests' && path.basename(path.dirname(src)) === 'scripts') return false;
      return true;
    };

    // Copy skill directories — each is a self-contained skill.
    // skills/reports/ is the BMad Builder's report output folder (a sibling
    // of the skills, not skill content) — never ship it.
    const srcEntries = await fs.readdir(this.srcDir, { withFileTypes: true });
    for (const entry of srcEntries) {
      if (entry.isDirectory() && entry.name !== 'reports') {
        await fs.copy(path.join(this.srcDir, entry.name), path.join(ucgDir, entry.name), { filter: copyFilter });
      }
    }

    // Copy the module manifest. Source of truth lives inside the skill
    // (skills/ultracode-goal/assets/module.yaml — the BMad standalone-module
    // layout); a root-level copy is kept in the installed tree so existing
    // consumers of {ucgFolder}/module.yaml keep working.
    const moduleYaml = path.join(this.srcDir, 'ultracode-goal', 'assets', 'module.yaml');
    if (await fs.pathExists(moduleYaml)) {
      await fs.copy(moduleYaml, path.join(ucgDir, 'module.yaml'));
    }

    // Write VERSION file for UCG version resolution in installed projects
    const packageJson = require('../../../package.json');
    await fs.writeFile(path.join(ucgDir, 'VERSION'), packageJson.version, 'utf8');
  }

  async writeConfig(ucgDir, config) {
    // On update, restore the user's existing config
    if (config._savedConfigYaml) {
      await fs.writeFile(path.join(ucgDir, 'config.yaml'), config._savedConfigYaml, 'utf8');
      return;
    }

    // Get user name from git or system
    const getUserName = () => {
      try {
        const { execSync } = require('node:child_process');
        return execSync('git config user.name', { encoding: 'utf8' }).trim() || 'Developer';
      } catch {
        return 'Developer';
      }
    };

    const configData = {
      user_name: getUserName(),
      project_name: config.project_name || 'Untitled Project',
      communication_language: 'en',
      document_output_language: 'en',
      output_folder: config.output_folder || '_bmad-output',
      ucg_folder: config.ucgFolder,
      ides: config.ides || [],
      install_learning: config.install_learning !== false,
    };

    const yamlStr = yaml.dump(configData, { lineWidth: -1 });
    await fs.writeFile(path.join(ucgDir, 'config.yaml'), `# UCG Configuration - Generated by installer\n${yamlStr}`, 'utf8');
  }

  async updateGitignore(projectDir) {
    const gitignorePath = path.join(projectDir, '.gitignore');
    const entry = '.claude/settings.local.json';

    try {
      if (await fs.pathExists(gitignorePath)) {
        const content = await fs.readFile(gitignorePath, 'utf8');
        // Check if entry already present (exact line match)
        const lines = content.split('\n');
        if (lines.some((line) => line.trim() === entry)) return;
        // Append with preceding newline if file doesn't end with one
        const prefix = content.endsWith('\n') ? '' : '\n';
        await fs.appendFile(gitignorePath, `${prefix}${entry}\n`, 'utf8');
      } else {
        await fs.writeFile(gitignorePath, `${entry}\n`, 'utf8');
      }
    } catch {
      // Non-critical — don't fail the install over .gitignore
    }
  }

  async copyLearningMaterial(projectDir) {
    const learnDir = path.join(projectDir, '_ucg-learn');
    if (await fs.pathExists(this.docsDir)) {
      await fs.copy(this.docsDir, learnDir);
    }
  }
}

module.exports = { Installer, PORTABILITY_GAP_LINE, STEP6B_PLANNING_FRAGMENTS };
