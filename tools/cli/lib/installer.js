/**
 * UCG Installer - Core orchestrator
 * Copies the ultracode-goal skill, installs it to IDEs, writes config + manifest.
 */

const path = require('node:path');
const fs = require('fs-extra');
const { spinner } = require('@clack/prompts');
const yaml = require('js-yaml');
const { installSkillsToIdes } = require('./ide-skills');
const { writeManifest } = require('./manifest');

// Dev-only artifacts never shipped into a user's project
const DEV_ARTIFACTS = new Set(['.analysis', '.decision-log.md', '__pycache__', '.pytest_cache', '.DS_Store', 'Thumbs.db']);

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

    // Step 6: Write installation manifest
    s.start('Writing manifest...');
    try {
      const packageJson = require('../../../package.json');
      await writeManifest(projectDir, config, {
        version: packageJson.version,
        ideDirectories,
      });
      s.stop('Installation manifest saved');
    } catch (error) {
      s.stop('Failed to write manifest');
      throw error;
    }

    return { success: true, ucgDir, projectDir };
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

    // Copy skill directories — each is a self-contained skill
    const srcEntries = await fs.readdir(this.srcDir, { withFileTypes: true });
    for (const entry of srcEntries) {
      if (entry.isDirectory()) {
        await fs.copy(path.join(this.srcDir, entry.name), path.join(ucgDir, entry.name), { filter: copyFilter });
      }
    }

    // Copy the module manifest
    const moduleYaml = path.join(this.srcDir, 'module.yaml');
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

module.exports = { Installer };
