/**
 * UCG Installer UI - Banner, prompts, and success message.
 * Uses @clack/prompts for terminal UI.
 *
 * Brand palette:
 *   indigo  #6366F1  — primary
 *   light   #818CF8  — accent, highlights
 *   dark    #4F46E5  — frame, deep emphasis
 *   spark   #A5B4FC  — icons
 */

const { intro, outro, text, multiselect, confirm, note, isCancel, cancel, log, select } = require('@clack/prompts');
const chalk = require('chalk');
const figlet = require('figlet');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { readManifest } = require('./manifest');
const { compareVersions } = require('./version-check');
const { getAvailablePlatforms, getDetectionMarkers } = require('./ide-skills');

const UCG_FOLDER = '_bmad/ucg';

// Brand colors
const brand = {
  indigo: chalk.hex('#6366F1'),
  light: chalk.hex('#818CF8'),
  dark: chalk.hex('#4F46E5'),
  spark: chalk.hex('#A5B4FC'),
};

class UI {
  displayBanner() {
    const packageJson = require('../../../package.json');
    const version = packageJson.version;

    let logoLines;
    try {
      logoLines = figlet.textSync('UCG', { font: 'ANSI Shadow' }).trimEnd().split('\n');
      // Remove trailing empty lines from figlet output
      while (logoLines.length > 0 && !logoLines.at(-1).trim()) logoLines.pop();
    } catch {
      logoLines = ['  U C G'];
    }

    const indent = '  ';
    // eslint-disable-next-line no-control-regex -- stripping ANSI escape codes for visual width calculation
    const visibleWidth = (s) => s.replaceAll(/\u001B\[\d+(?:;\d+)*m/g, '').length;

    // Plain text for every box row, measured before styling, so the frame is
    // sized to its content and can never be broken by an over-long line.
    const titleText = 'UltraCode Goal  ◎  Autonomous Epic Conductor';
    const taglineText = 'Run a BMAD Epic autonomously to a machine-checked Definition-of-Done.';
    const versionText = `v${version}  ·  MIT License  ·  Open Source`;

    // Inner box width: hug the widest row, capped to the terminal (and to 76
    // so the full frame stays within an 80-column window).
    const cols = process.stdout.columns || 80;
    const logoWidth = Math.max(...logoLines.map((l) => l.trimEnd().length));
    const wMin = logoWidth + indent.length + 2; // the logo cannot wrap
    const wMax = Math.max(wMin, Math.min(76, cols - 4));
    const longest = Math.max(logoWidth, titleText.length, taglineText.length, versionText.length);
    const w = Math.min(longest + indent.length + 2, wMax);
    const usable = w - 2 - indent.length;

    // Word-wrap plain text to the usable row width (kicks in on narrow terminals).
    const wrap = (text, width) => {
      const lines = [];
      let line = '';
      for (const word of text.split(' ')) {
        if (line && line.length + 1 + word.length > width) {
          lines.push(line);
          line = word;
        } else {
          line = line ? line + ' ' + word : word;
        }
      }
      if (line) lines.push(line);
      return lines;
    };

    const frame = brand.dark;
    const top = frame('  ╔' + '═'.repeat(w) + '╗');
    const mid = frame('  ╟' + '─'.repeat(w) + '╢');
    const bottom = frame('  ╚' + '═'.repeat(w) + '╝');
    const rule = frame('  ' + '━'.repeat(w + 2)); // matches the box's outer width
    const row = (content) => {
      const pad = Math.max(0, w - visibleWidth(content) - 2);
      return frame('  ║ ') + content + ' '.repeat(pad) + frame(' ║');
    };
    const empty = row('');

    console.log();
    console.log(top);
    console.log(empty);
    for (const line of logoLines) {
      console.log(row(indent + brand.indigo.bold(line.replace(/\s+$/, ''))));
    }
    console.log(empty);
    console.log(mid);
    if (titleText.length <= usable) {
      console.log(
        row(indent + chalk.white.bold('UltraCode Goal') + '  ' + brand.spark('◎') + '  ' + chalk.dim('Autonomous Epic Conductor')),
      );
    } else {
      console.log(row(indent + chalk.white.bold('UltraCode Goal') + '  ' + brand.spark('◎')));
      console.log(row(indent + chalk.dim('Autonomous Epic Conductor')));
    }
    for (const line of wrap(taglineText, usable)) {
      console.log(row(indent + chalk.dim(line)));
    }
    for (const line of wrap(versionText, usable)) {
      console.log(row(indent + chalk.dim(line)));
    }
    console.log(bottom);
    console.log();
    console.log(rule);
    console.log();
    const resource = (label, url) => '  ' + chalk.dim(label.padEnd(10)) + brand.indigo(url);
    console.log(resource('Docs', 'https://armelhbobdad.github.io/bmad-module-ultracode-goal/'));
    console.log(resource('GitHub', 'https://github.com/armelhbobdad/bmad-module-ultracode-goal'));
    console.log(resource('Support', 'https://buymeacoffee.com/armelhbobdad'));
    console.log();
    console.log(rule);
    console.log();

    intro(brand.indigo('UltraCode Goal Installer'));
  }

  async detectInstallation(projectDir) {
    const hasBmadUcg = await fs.pathExists(path.join(projectDir, UCG_FOLDER));
    const hasBmadDir = await fs.pathExists(path.join(projectDir, '_bmad'));

    if (hasBmadUcg) {
      return { type: 'existing', folder: UCG_FOLDER };
    }
    if (hasBmadDir) {
      return { type: 'bmad-ready', folder: UCG_FOLDER };
    }
    return { type: 'fresh', folder: UCG_FOLDER };
  }

  async promptInstall() {
    this.displayBanner();

    const projectDir = process.cwd();
    const defaultProjectName = path.basename(projectDir);
    const detection = await this.detectInstallation(projectDir);
    const ucgFolder = detection.folder;

    log.info(`Target: ${brand.light(projectDir)}`);

    let action = 'fresh';

    if (detection.type === 'existing') {
      const existingManifest = await readManifest(projectDir);
      const installedVersion = existingManifest?.version || null;
      const incomingVersion = require('../../../package.json').version;

      let versionLabel;
      let updateOptionLabel;
      if (!installedVersion) {
        versionLabel = `version unknown → v${incomingVersion}`;
        updateOptionLabel = `Update — Install v${incomingVersion}, keep config.yaml`;
      } else if (installedVersion === incomingVersion) {
        versionLabel = `v${installedVersion} — already at this version`;
        updateOptionLabel = `Update — Reinstall v${incomingVersion}, keep config.yaml`;
      } else if (compareVersions(installedVersion, incomingVersion)) {
        versionLabel = `v${installedVersion} → v${incomingVersion} available`;
        updateOptionLabel = `Update — Upgrade from v${installedVersion} to v${incomingVersion}, keep config.yaml`;
      } else {
        versionLabel = `v${installedVersion} → v${incomingVersion}, DOWNGRADE`;
        updateOptionLabel = `Update — Downgrade to v${incomingVersion}, keep config.yaml`;
      }

      log.warn(`Found existing installation at ${chalk.white(UCG_FOLDER + '/')} (${versionLabel})`);

      const choice = await select({
        message: 'What would you like to do?',
        options: [
          { label: updateOptionLabel, value: 'update' },
          { label: 'Fresh install — Remove everything and start over', value: 'fresh' },
          { label: 'Cancel', value: 'cancel' },
        ],
      });

      if (isCancel(choice) || choice === 'cancel') {
        cancel('Installation cancelled.');
        return { cancelled: true };
      }
      action = choice;
    } else {
      log.info(`The skill will be installed in ${chalk.white(ucgFolder + '/')}`);
    }

    if (action === 'update') {
      log.info('Existing config.yaml will be preserved.');
      return {
        projectDir,
        ucgFolder,
        _detection: detection,
        _action: action,
        cancelled: false,
      };
    }

    // Load saved config to pre-populate defaults on fresh reinstall
    const savedConfig = await this.loadSavedConfig(projectDir, ucgFolder);
    if (savedConfig) {
      log.info('Previous configuration detected — defaults pre-populated.');
    }

    // Build IDE options from platform-codes.yaml
    const platforms = getAvailablePlatforms();
    const ideOptions = platforms.map((p) => ({
      label: p.preferred ? `${p.label} (Recommended)` : p.label,
      value: p.value,
    }));

    // Pre-check IDEs: saved config takes priority, then auto-detect from directories
    const savedIdes = savedConfig?.ides || [];
    let initialIdes = [];
    if (savedIdes.length > 0) {
      initialIdes = savedIdes;
    } else {
      const detectedIdes = await this.detectIdes(projectDir);
      if (detectedIdes.length > 0) {
        initialIdes = detectedIdes;
        log.info(`Auto-detected IDEs: ${brand.light(detectedIdes.join(', '))}`);
      }
    }

    // Mark initially selected IDEs
    for (const opt of ideOptions) {
      opt.initialSelected = initialIdes.includes(opt.value);
    }

    // Project name
    const project_name = await text({
      message: 'Project name:',
      initialValue: savedConfig?.project_name || defaultProjectName,
    });
    if (isCancel(project_name)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // IDE selection
    const ides = await multiselect({
      message: 'Which tools/IDEs are you using?',
      options: ideOptions,
      initialValues: initialIdes,
      required: true,
    });
    if (isCancel(ides)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // Learning material
    const install_learning = await confirm({
      message: 'Install learning & reference material?',
      initialValue: true,
    });
    if (isCancel(install_learning)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    return {
      projectDir,
      project_name,
      ides,
      install_learning,
      ucgFolder,
      _detection: detection,
      _action: action,
      cancelled: false,
    };
  }

  async detectIdes(projectDir) {
    const markers = getDetectionMarkers();
    const detected = [];
    for (const [ide, paths] of Object.entries(markers)) {
      for (const p of paths) {
        if (await fs.pathExists(path.join(projectDir, p))) {
          detected.push(ide);
          break;
        }
      }
    }
    return detected;
  }

  async loadSavedConfig(projectDir, ucgFolder) {
    const configPath = path.join(projectDir, ucgFolder, 'config.yaml');
    try {
      if (await fs.pathExists(configPath)) {
        const content = await fs.readFile(configPath, 'utf8');
        return yaml.load(content) || null;
      }
    } catch {
      // ignore parse errors
    }
    return null;
  }

  displaySuccess(ucgFolder, ides = [], action = 'fresh') {
    // Build per-platform lookup tables from platform-codes.yaml
    const ideNames = {};
    const idePrefixes = {};
    for (const p of getAvailablePlatforms()) {
      ideNames[p.value] = p.label;
      idePrefixes[p.value] = p.skillInvocationPrefix; // null = auto-invoke only
    }

    const selectedIdes = Array.isArray(ides) && ides.length > 0 ? ides : [];

    let ideDisplay;
    if (selectedIdes.length === 0) {
      ideDisplay = 'your IDE';
    } else if (selectedIdes.length === 1) {
      ideDisplay = ideNames[selectedIdes[0]] || 'your IDE';
    } else {
      ideDisplay = selectedIdes.map((ide) => ideNames[ide] || ide).join(' or ');
    }

    // Build per-IDE invocation hints. Skills with a prefix get a literal
    // command; auto-invoke IDEs get a chat-based instruction.
    const invocations = selectedIdes.map((ide) => {
      const name = ideNames[ide] || ide;
      const prefix = idePrefixes[ide];
      if (prefix) {
        return { ide: name, command: `${prefix}ultracode-goal`, auto: false };
      }
      return { ide: name, command: null, auto: true };
    });

    // Compose the activate line shown in steps and outro.
    let activateLine;
    if (invocations.length === 0) {
      // Update flow with no IDE list — show both common forms
      activateLine = `${brand.light('/ultracode-goal')} ${chalk.dim('(Claude Code)')}  ${chalk.dim('·')}  ${brand.light('$ultracode-goal')} ${chalk.dim('(Codex)')}`;
    } else if (invocations.length === 1) {
      const inv = invocations[0];
      activateLine = inv.auto ? chalk.dim(`${inv.ide} auto-loads ultracode-goal`) : brand.light(inv.command);
    } else {
      // Mixed: show one segment per IDE
      activateLine = invocations
        .map((inv) =>
          inv.auto
            ? `${chalk.dim('auto')} ${chalk.dim('(' + inv.ide + ')')}`
            : `${brand.light(inv.command)} ${chalk.dim('(' + inv.ide + ')')}`,
        )
        .join('  ');
    }

    let noteTitle;
    let noteBody;

    if (action === 'update') {
      noteTitle = brand.indigo.bold('Update complete!');
      noteBody = [
        `${chalk.white.bold('What Changed')}`,
        'UCG files have been refreshed.',
        'Your config.yaml is preserved.',
        '',
        `${chalk.white.bold('Next Steps')}`,
        `1. Reload the skill in ${ideDisplay}:  ${activateLine}`,
        `2. Resume or relaunch your Epic — the decision log recovers run state`,
      ].join('\n');
    } else {
      noteTitle = brand.indigo.bold('Installation complete!');
      noteBody = [
        `${chalk.white.bold('Get Started')}`,
        `1. Open this folder in ${ideDisplay}`,
        `2. Activate the conductor:  ${activateLine}`,
        `3. Name the Epic — UCG preflights it to a hard, remediated green light`,
        `4. The run advances only when the deterministic gate reads PASS`,
        '',
        `${chalk.white.bold('Note')}`,
        `UCG merges PreToolUse/Stop hooks into ${chalk.white('.claude/settings.local.json')}`,
        `(machine-local, gitignored) at preflight — see SECURITY.md in the repo.`,
      ].join('\n');
    }

    note(noteBody, noteTitle);

    outro(
      `${brand.spark('◎')}  Skill: ${chalk.white('ultracode-goal')} ${chalk.dim('(Autonomous Epic Conductor)')}\n${brand.dark('⚡')} Docs: ${brand.indigo('https://armelhbobdad.github.io/bmad-module-ultracode-goal/')}\n${brand.light('▶')}  Launch an Epic:  ${activateLine}`,
    );
  }
}

module.exports = { UI };
