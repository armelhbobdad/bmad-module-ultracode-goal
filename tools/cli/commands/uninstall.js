/**
 * UCG Uninstall Command
 * Clean removal of UCG files, IDE skill directories, and learning material.
 * Uses the manifest to know exactly what to remove.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const { confirm, isCancel, spinner, log, outro } = require('@clack/prompts');
const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../lib/manifest');
const { removeAllUcgSkills } = require('../lib/ide-skills');

/**
 * Count files that still exist on disk from manifest lists.
 */
async function countExistingFiles(projectDir, manifest) {
  const allFiles = [...(manifest.files.ucg || []), ...(manifest.files.ide_skills || []), ...(manifest.files.learning || [])];

  let existing = 0;
  for (const file of allFiles) {
    if (await fs.pathExists(path.join(projectDir, file))) {
      existing++;
    }
  }
  return { total: allFiles.length, existing };
}

/**
 * Display what will be removed, grouped by category.
 */
async function displayRemovalPlan(projectDir, manifest) {
  const categories = [
    { key: 'ucg', label: 'UCG module files', dir: manifest.ucg_folder },
    { key: 'ide_skills', label: 'IDE skill directories' },
    { key: 'learning', label: 'Learning material', dir: '_ucg-learn' },
  ];

  const lines = [];
  for (const cat of categories) {
    const files = manifest.files[cat.key] || [];
    if (files.length === 0) continue;

    // Count how many still exist
    let existCount = 0;
    for (const f of files) {
      if (await fs.pathExists(path.join(projectDir, f))) existCount++;
    }

    if (existCount === 0) continue;

    if (cat.dir) {
      lines.push(`${chalk.red('×')} ${cat.label} ${chalk.dim(`(${cat.dir}/ — ${existCount} files)`)}`);
    } else {
      lines.push(`${chalk.red('×')} ${cat.label} ${chalk.dim(`(${existCount} files)`)}`);
    }
  }

  // Manifest itself
  lines.push(`${chalk.red('×')} Installation manifest ${chalk.dim(`(${MANIFEST_DIR}/${MANIFEST_FILE})`)}`);

  log.warn(`The following will be removed:\n${lines.join('\n')}`);
  log.info(
    'Note: hooks merged into .claude/settings.local.json are not removed —\ndelete the ultracode-goal entries there manually if you added them.',
  );
}

/**
 * Remove a directory if it exists and is empty.
 */
async function removeEmptyDir(dirPath) {
  if (!(await fs.pathExists(dirPath))) return;
  try {
    const entries = await fs.readdir(dirPath);
    if (entries.length === 0) {
      await fs.remove(dirPath);
    }
  } catch {
    // ignore
  }
}

module.exports = {
  command: 'uninstall',
  description: 'Remove the UCG installation from the current project',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const manifest = await readManifest(projectDir);

      if (!manifest) {
        // Check if UCG exists without manifest
        const ucgExists = await fs.pathExists(path.join(projectDir, '_bmad/ucg'));
        if (ucgExists) {
          log.warn(
            'No manifest found. Reinstall first to generate one,\nthen run uninstall again for clean removal.\nRun: npx bmad-module-ultracode-goal install',
          );
        } else {
          log.warn('UltraCode Goal is not installed in this directory.');
        }
        process.exit(0);
        return;
      }

      const { existing } = await countExistingFiles(projectDir, manifest);
      if (existing === 0) {
        log.warn('No UCG files found to remove.');
        // Clean up stale manifest
        await fs.remove(path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE));
        process.exit(0);
        return;
      }

      await displayRemovalPlan(projectDir, manifest);

      const shouldProceed = await confirm({
        message: 'Proceed with uninstall?',
        initialValue: false,
      });

      if (isCancel(shouldProceed) || !shouldProceed) {
        log.warn('Uninstall cancelled.');
        process.exit(0);
        return;
      }

      const s = spinner();

      // Remove IDE skill directories from all known platforms (skills + legacy command files)
      s.start('Removing IDE skill directories...');
      const removedIdeDirs = await removeAllUcgSkills(projectDir);
      if (removedIdeDirs.length > 0) {
        s.stop(`Cleaned the skill from ${removedIdeDirs.length} IDE target(s)`);
      } else {
        s.stop('No IDE skill directories found');
      }

      // Remove learning material directory
      const learnFiles = manifest.files.learning || [];
      if (learnFiles.length > 0) {
        s.start('Removing learning material...');
        const learnDir = path.join(projectDir, '_ucg-learn');
        if (await fs.pathExists(learnDir)) {
          await fs.remove(learnDir);
        }
        s.stop('Learning material removed');
      }

      // Remove UCG module directory
      s.start('Removing UCG module...');
      const ucgDir = path.join(projectDir, manifest.ucg_folder);
      if (await fs.pathExists(ucgDir)) {
        await fs.remove(ucgDir);
      }
      s.stop('UCG module removed');

      // Remove manifest
      const manifestPath = path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE);
      if (await fs.pathExists(manifestPath)) {
        await fs.remove(manifestPath);
      }
      // Clean empty _bmad/_config/ and _bmad/ if we were the only occupant
      await removeEmptyDir(path.join(projectDir, MANIFEST_DIR));
      await removeEmptyDir(path.join(projectDir, '_bmad'));

      outro('UltraCode Goal uninstalled successfully.');

      process.exit(0);
    } catch (error) {
      console.error(chalk.red('\nUninstall failed:'), error.message);
      process.exit(1);
    }
  },
};
