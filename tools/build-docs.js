/**
 * UltraCode Goal (UCG) Documentation Build Pipeline
 *
 * Generates LLM-friendly text bundles (llms.txt, llms-full.txt) from docs/*.md
 * and builds the documentation website.
 *
 * Build outputs:
 *   build/artifacts/  - llms.txt, llms-full.txt
 *   build/site/       - Final website output (deployable)
 */

const { execSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// =============================================================================
// Configuration
// =============================================================================

const PROJECT_ROOT = path.dirname(__dirname);
const BUILD_DIR = path.join(PROJECT_ROOT, 'build');

const SITE_URL = process.env.SITE_URL || 'https://armelhbobdad.github.io/bmad-module-ultracode-goal';
const REPO_URL = 'https://github.com/armelhbobdad/bmad-module-ultracode-goal';

// llms-full.txt is consumed by AI agents as context. Most LLMs have ~200k token limits.
// 600k chars ≈ 150k tokens (safe margin).
const LLM_MAX_CHARS = 600_000;
const LLM_WARN_CHARS = 500_000;

const LLM_EXCLUDE_PATTERNS = ['changelog'];

// =============================================================================
// Main Entry Point
// =============================================================================

async function main() {
  console.log();
  printBanner('UCG Documentation Build Pipeline');
  console.log();
  console.log(`Project root: ${PROJECT_ROOT}`);
  console.log(`Build directory: ${BUILD_DIR}`);
  console.log();

  cleanBuildDirectory();

  const docsDir = path.join(PROJECT_ROOT, 'docs');
  const artifactsDir = generateArtifacts(docsDir);
  const siteDir = buildSite(artifactsDir);

  printBuildSummary(docsDir, artifactsDir, siteDir);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

// =============================================================================
// Pipeline Stages
// =============================================================================

function generateArtifacts(docsDir) {
  printHeader('Generating LLM text bundles');

  const outputDir = path.join(BUILD_DIR, 'artifacts');
  fs.mkdirSync(outputDir, { recursive: true });

  generateLlmsTxt(outputDir);
  generateLlmsFullTxt(docsDir, outputDir);

  console.log();
  console.log(`  \u001B[32m✓\u001B[0m Artifact generation complete`);

  return outputDir;
}

function buildSite(artifactsDir) {
  printHeader('Building documentation website');

  const siteDir = path.join(BUILD_DIR, 'site');

  runSiteBuild();
  copyArtifactsToSite(artifactsDir, siteDir);

  console.log();
  console.log(`  \u001B[32m✓\u001B[0m Website build complete`);

  return siteDir;
}

// =============================================================================
// LLM File Generation
// =============================================================================

function generateLlmsTxt(outputDir) {
  console.log('  → Generating llms.txt...');

  const content = [
    '# UltraCode Goal (UCG) Documentation',
    '',
    '> Run a BMAD Epic autonomously to a machine-checked, TEA-gated Definition-of-Done.',
    '',
    `Documentation: ${SITE_URL}`,
    `Repository: ${REPO_URL}`,
    `Full docs: ${SITE_URL}/llms-full.txt`,
    '',
    '## Why',
    '',
    `- **[Why UltraCode Goal](${SITE_URL}/why-ultracode-goal/)** - The problem, the three enforcement layers, and when not to use it`,
    '',
    '## Try',
    '',
    `- **[Getting Started](${SITE_URL}/getting-started/)** - Prerequisites, install, the first-run walkthrough, and the flags table`,
    `- **[How It Works](${SITE_URL}/how-it-works/)** - The six stages narrated, the routing conditions, and the headless emit shape`,
    `- **[Parallel Mode](${SITE_URL}/parallel-mode/)** - The experimental worktree fan-out and its known limits`,
    '',
    '## Reference',
    '',
    `- **[Architecture](${SITE_URL}/architecture/)** - The conductor model, the three enforcement layers, the file layout, and customization resolution`,
    `- **[Gate Model](${SITE_URL}/gate-model/)** - How gate evaluation maps TEA's gate status to a verdict, the thresholds, and the fail-closed contract`,
    `- **[Health Check](${SITE_URL}/health-check/)** - The terminal self-improvement reflection, the privacy model, and how to disable it`,
    `- **[Troubleshooting](${SITE_URL}/troubleshooting/)** - Real failure modes and their remediations`,
    '',
    '---',
    '',
    '## Quick Links',
    '',
    `- [Full Documentation (llms-full.txt)](${SITE_URL}/llms-full.txt) - Complete docs for AI context`,
    '',
  ].join('\n');

  const outputPath = path.join(outputDir, 'llms.txt');
  fs.writeFileSync(outputPath, content, 'utf-8');
  console.log(`    Generated llms.txt (${content.length.toLocaleString()} chars)`);
}

function generateLlmsFullTxt(docsDir, outputDir) {
  console.log('  → Generating llms-full.txt...');

  const date = new Date().toISOString().split('T')[0];
  const files = getAllMarkdownFiles(docsDir);

  const output = [
    '# UltraCode Goal (UCG) Documentation (Full)',
    '',
    '> Complete documentation for AI consumption',
    `> Generated: ${date}`,
    `> Repository: ${REPO_URL}`,
    '',
  ];

  let fileCount = 0;
  let skippedCount = 0;

  for (const mdPath of files) {
    if (shouldExcludeFromLlm(mdPath)) {
      skippedCount++;
      continue;
    }

    const fullPath = path.join(docsDir, mdPath);
    try {
      const content = readMarkdownContent(fullPath);
      output.push(`<document path="${mdPath}">`, content, '</document>', '');
      fileCount++;
    } catch (error) {
      console.error(`    Warning: Could not read ${mdPath}: ${error.message}`);
    }
  }

  const result = output.join('\n');
  validateLlmSize(result);

  const outputPath = path.join(outputDir, 'llms-full.txt');
  fs.writeFileSync(outputPath, result, 'utf-8');

  const tokenEstimate = Math.floor(result.length / 4).toLocaleString();
  console.log(
    `    Processed ${fileCount} files (skipped ${skippedCount}), ${result.length.toLocaleString()} chars (~${tokenEstimate} tokens)`,
  );
}

function getAllMarkdownFiles(dir, baseDir = dir) {
  const files = [];

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      files.push(...getAllMarkdownFiles(fullPath, baseDir));
    } else if (entry.name.endsWith('.md')) {
      const relativePath = path.relative(baseDir, fullPath);
      files.push(relativePath);
    }
  }

  return files;
}

function shouldExcludeFromLlm(filePath) {
  const pathParts = filePath.split(path.sep);
  if (pathParts.some((part) => part.startsWith('_'))) return true;

  return LLM_EXCLUDE_PATTERNS.some((pattern) => filePath.includes(pattern));
}

function readMarkdownContent(filePath) {
  let content = fs.readFileSync(filePath, 'utf-8');

  if (content.startsWith('---')) {
    const end = content.indexOf('---', 3);
    if (end !== -1) {
      content = content.slice(end + 3).trim();
    }
  }

  return content;
}

function validateLlmSize(content) {
  const charCount = content.length;

  if (charCount > LLM_MAX_CHARS) {
    console.error(`    ERROR: Exceeds ${LLM_MAX_CHARS.toLocaleString()} char limit`);
    process.exit(1);
  } else if (charCount > LLM_WARN_CHARS) {
    console.warn(`    \u001B[33mWARNING: Approaching ${LLM_WARN_CHARS.toLocaleString()} char limit\u001B[0m`);
  }
}

// =============================================================================
// Website Build
// =============================================================================

function runSiteBuild() {
  console.log('  → Running website build...');
  execSync('npm --prefix website run build', {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
    env: {
      ...process.env,
    },
  });
}

function copyArtifactsToSite(artifactsDir, siteDir) {
  console.log('  → Copying artifacts to site...');

  fs.copyFileSync(path.join(artifactsDir, 'llms.txt'), path.join(siteDir, 'llms.txt'));
  fs.copyFileSync(path.join(artifactsDir, 'llms-full.txt'), path.join(siteDir, 'llms-full.txt'));
}

// =============================================================================
// Build Summary
// =============================================================================

function printBuildSummary(docsDir, artifactsDir, siteDir) {
  console.log();
  printBanner('Build Complete!');
  console.log();
  console.log('Build artifacts:');
  console.log(`  Source docs:     ${docsDir}`);
  console.log(`  Generated files: ${artifactsDir}`);
  console.log(`  Final site:      ${siteDir}`);
  console.log();
  console.log(`Deployable output: ${siteDir}/`);
  console.log();

  listDirectoryContents(siteDir);
}

function listDirectoryContents(dir) {
  const entries = fs.readdirSync(dir).slice(0, 15);

  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    const stat = fs.statSync(fullPath);

    if (stat.isFile()) {
      const sizeStr = formatFileSize(stat.size);
      console.log(`  ${entry.padEnd(40)} ${sizeStr.padStart(8)}`);
    } else {
      console.log(`  ${entry}/`);
    }
  }
}

function formatFileSize(bytes) {
  if (bytes > 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)}M`;
  } else if (bytes > 1024) {
    return `${Math.floor(bytes / 1024)}K`;
  }
  return `${bytes}B`;
}

// =============================================================================
// File System Utilities
// =============================================================================

function cleanBuildDirectory() {
  console.log('Cleaning previous build...');

  if (fs.existsSync(BUILD_DIR)) {
    fs.rmSync(BUILD_DIR, { recursive: true });
  }
  fs.mkdirSync(BUILD_DIR, { recursive: true });
}

// =============================================================================
// Console Output Formatting
// =============================================================================

function printHeader(title) {
  console.log();
  console.log('┌' + '─'.repeat(62) + '┐');
  console.log(`│ ${title.padEnd(60)} │`);
  console.log('└' + '─'.repeat(62) + '┘');
}

function printBanner(title) {
  console.log('╔' + '═'.repeat(62) + '╗');
  console.log(`║${title.padStart(31 + title.length / 2).padEnd(62)}║`);
  console.log('╚' + '═'.repeat(62) + '╝');
}
