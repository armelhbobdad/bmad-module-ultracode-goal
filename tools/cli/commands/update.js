/**
 * UCG Quick Update Command
 * Replaces UCG files and reinstalls the skill without re-prompting.
 * Preserves config.yaml.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { Installer } = require('../lib/installer');
const { UI } = require('../lib/ui');

const UCG_FOLDER = '_bmad/ucg';

module.exports = {
  command: 'update',
  description: 'Update UCG files and reinstall the skill (preserves config)',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const ucgDir = path.join(projectDir, UCG_FOLDER);

      if (!(await fs.pathExists(ucgDir))) {
        console.log(chalk.yellow('\n  UltraCode Goal is not installed in this directory.'));
        console.log(chalk.dim('  Run: npx bmad-module-ultracode-goal install\n'));
        process.exit(0);
        return;
      }

      console.log('');
      console.log(chalk.hex('#6366F1').bold('  UltraCode Goal — Quick Update'));
      console.log(chalk.dim('  Replacing UCG files, preserving config.\n'));

      const installer = new Installer();
      const result = await installer.install({
        projectDir,
        ucgFolder: UCG_FOLDER,
        _action: 'update',
      });

      if (result && result.success) {
        // Read config to get IDEs for post-update notes
        let ides = [];
        try {
          const configContent = await fs.readFile(path.join(ucgDir, 'config.yaml'), 'utf8');
          const config = yaml.load(configContent);
          ides = config?.ides || [];
        } catch {
          /* use empty */
        }
        const ui = new UI();
        ui.displaySuccess(UCG_FOLDER, ides, 'update');
        process.exit(0);
      } else {
        console.error(chalk.red('\nUpdate failed.'));
        process.exit(1);
      }
    } catch (error) {
      console.error(chalk.red('\nUpdate failed:'), error.message);
      process.exit(1);
    }
  },
};
