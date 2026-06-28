/**
 * IDE Skill Installer — Verbatim skill directory installation
 *
 * Follows the BMAD standard: skill directories (containing SKILL.md +
 * supporting files) are copied directly to each IDE's skills/ directory.
 * IDEs read SKILL.md natively.
 *
 * UCG is Claude-Code-only; platform-codes.yaml carries the single Claude Code
 * target (config-driven, no IDE-specific code).
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const PLATFORM_CODES_PATH = path.join(__dirname, 'platform-codes.yaml');

// UCG-owned skill directories inside IDE skills/ targets
const UCG_SKILLS = new Set(['ultracode-goal']);

// OS/editor artifacts to filter during copy
const ARTIFACT_FILTER = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '._.DS_Store']);

/**
 * Load platform configuration from platform-codes.yaml.
 * Returns { platforms: { 'claude-code': { name, preferred, installer: { target_dir, legacy_targets } }, ... } }
 */
function loadPlatforms() {
  const content = fs.readFileSync(PLATFORM_CODES_PATH, 'utf8');
  return yaml.load(content);
}

/**
 * Get available platforms for UI display.
 * Returns array of { value, label, preferred, skillInvocationPrefix }.
 * skillInvocationPrefix is null when the IDE only auto-invokes skills.
 */
function getAvailablePlatforms() {
  const config = loadPlatforms();
  return Object.entries(config.platforms)
    .filter(([, p]) => !p.suspended)
    .map(([code, p]) => ({
      value: code,
      label: p.name,
      preferred: p.preferred || false,
      skillInvocationPrefix: p.skill_invocation_prefix ?? null,
    }))
    .sort((a, b) => {
      // Preferred first, then alphabetical
      if (a.preferred !== b.preferred) return b.preferred ? 1 : -1;
      return a.label.localeCompare(b.label);
    });
}

/**
 * Install skill directories to all selected IDEs.
 *
 * @param {string} projectDir - Project root directory
 * @param {string} ucgDir - Path to installed UCG module (e.g., {projectDir}/_bmad/ucg)
 * @param {string[]} ideCodes - Array of IDE codes (always ['claude-code'])
 * @returns {{ installed: number, ides: string[], directories: string[] }}
 */
async function installSkillsToIdes(projectDir, ucgDir, ideCodes) {
  if (!ideCodes || ideCodes.length === 0) return { installed: 0, ides: [], directories: [] };

  const config = loadPlatforms();
  let totalInstalled = 0;
  const processedIdes = [];
  const allDirectories = [];

  // Copy filter: skip OS artifacts
  const copyFilter = (src) => !ARTIFACT_FILTER.has(path.basename(src));

  for (const ideCode of ideCodes) {
    const platform = config.platforms[ideCode];
    if (!platform || !platform.installer?.target_dir) continue;

    const targetDir = path.join(projectDir, platform.installer.target_dir);

    // Clean legacy targets first (old command files from previous UCG installs)
    await cleanLegacyTargets(projectDir, platform);

    // Clean existing UCG skills from this IDE (for update/reinstall)
    await cleanUcgSkills(targetDir);

    // Ensure target directory exists
    await fs.ensureDir(targetDir);

    // Copy UCG-owned skill directories from the installed module
    if (await fs.pathExists(ucgDir)) {
      const entries = await fs.readdir(ucgDir, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        if (UCG_SKILLS.has(entry.name)) {
          const src = path.join(ucgDir, entry.name);
          const dest = path.join(targetDir, entry.name);
          await fs.copy(src, dest, { filter: copyFilter });
          totalInstalled++;
        }
      }
    }

    allDirectories.push(platform.installer.target_dir);
    processedIdes.push(ideCode);
  }

  return { installed: totalInstalled, ides: processedIdes, directories: allDirectories };
}

/**
 * Remove legacy command files from old IDE target directories.
 * Handles migration from command-file approach to skill-directory approach.
 */
async function cleanLegacyTargets(projectDir, platform) {
  const legacyTargets = platform.installer?.legacy_targets || [];

  for (const legacyDir of legacyTargets) {
    const fullPath = path.join(projectDir, legacyDir);
    if (!(await fs.pathExists(fullPath))) continue;

    try {
      const files = await fs.readdir(fullPath);
      for (const file of files) {
        // Remove UCG-specific command files from legacy directories
        if (file.startsWith('bmad-ultracode-goal-') || file.startsWith('bmad-ucg-')) {
          await fs.remove(path.join(fullPath, file));
        }
      }

      // Remove empty directories
      const remaining = await fs.readdir(fullPath);
      if (remaining.length === 0) {
        await fs.remove(fullPath);
        // Also try to remove empty parent
        const parentDir = path.dirname(fullPath);
        try {
          const parentRemaining = await fs.readdir(parentDir);
          if (parentRemaining.length === 0) await fs.remove(parentDir);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* non-critical, continue */
    }
  }
}

/**
 * Remove existing UCG skill directories from an IDE target.
 * Called before reinstalling to ensure clean state.
 */
async function cleanUcgSkills(targetDir) {
  if (!(await fs.pathExists(targetDir))) return;

  try {
    const entries = await fs.readdir(targetDir);
    for (const entry of entries) {
      // Only remove UCG-owned directories
      if (UCG_SKILLS.has(entry)) {
        await fs.remove(path.join(targetDir, entry));
      }
    }
  } catch {
    /* non-critical */
  }
}

/**
 * Remove all UCG skills from all known IDE directories.
 * Used during uninstall.
 */
async function removeAllUcgSkills(projectDir) {
  const config = loadPlatforms();
  const removed = [];

  for (const [, platform] of Object.entries(config.platforms)) {
    if (!platform.installer?.target_dir) continue;
    const targetDir = path.join(projectDir, platform.installer.target_dir);
    if (await fs.pathExists(targetDir)) {
      await cleanUcgSkills(targetDir);
      // Also clean legacy targets
      await cleanLegacyTargets(projectDir, platform);
      removed.push(platform.installer.target_dir);
    }
  }

  return removed;
}

module.exports = { installSkillsToIdes, getAvailablePlatforms, removeAllUcgSkills, loadPlatforms };
