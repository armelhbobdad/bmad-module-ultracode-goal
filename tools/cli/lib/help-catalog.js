/**
 * UCG Help Catalog Registration
 *
 * Registers the module's capability rows into the BMad help catalog so the
 * installed `bmad-help` skill can route users to UltraCode Goal. Source of
 * truth is skills/ultracode-goal/assets/module-help.csv.
 *
 * Targets (both anti-zombie: existing rows whose module column matches a
 * source module code are removed before fresh rows are appended, so install,
 * update, and re-install are all idempotent):
 * - {project}/_bmad/_config/bmad-help.csv — the assembled catalog bmad-help
 *   loads. Created with the catalog's canonical header when absent.
 * - {project}/_bmad/module-help.csv — the standalone self-registration file
 *   some BMad setup flows merge into. Only updated when it already exists;
 *   never created (nothing reads a fresh one in a project without it).
 *
 * The merge is positional: an existing target keeps its own header line, and a
 * missing target is created with the catalog's canonical `preceded-by`/`followed-by`
 * header. Source and catalog now share those names; a legacy source spelling
 * columns 9-10 `after`/`before` still transfers verbatim, since rows map by position.
 *
 * CSV handling is a minimal RFC 4180 implementation (csv-parse is a
 * devDependency; this module ships in the published CLI).
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const ASSEMBLED_CATALOG = path.join('_bmad', '_config', 'bmad-help.csv');
const MODULE_HELP = path.join('_bmad', 'module-help.csv');

// Canonical header of the assembled catalog (what bmad-help parses).
const CATALOG_HEADER = [
  'module',
  'skill',
  'display-name',
  'menu-code',
  'description',
  'action',
  'args',
  'phase',
  'preceded-by',
  'followed-by',
  'required',
  'output-location',
  'outputs',
];

/**
 * Parse CSV text into an array of rows (arrays of string fields).
 * RFC 4180: fields may be quoted; quoted fields may contain commas,
 * newlines, and doubled quotes. Tolerates \r\n and a trailing newline.
 */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  let i = 0;

  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += ch;
      i++;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (ch === ',') {
      row.push(field);
      field = '';
      i++;
      continue;
    }
    if (ch === '\n' || ch === '\r') {
      // Consume \r\n as one terminator
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
      i++;
      continue;
    }
    field += ch;
    i++;
  }
  // Final field/row when the text doesn't end with a newline
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/**
 * Serialize rows back to CSV text. Quotes a field only when it contains a
 * comma, quote, or newline — mirrors how the BMAD-assembled catalog is
 * written.
 */
function serializeCsv(rows) {
  const serializeField = (value) => {
    const s = String(value ?? '');
    if (/[",\n\r]/.test(s)) {
      return `"${s.replaceAll('"', '""')}"`;
    }
    return s;
  };
  return rows.map((row) => row.map(serializeField).join(',')).join('\n') + '\n';
}

/**
 * Unique module codes (column 1) present in data rows.
 */
function extractModuleCodes(rows) {
  const codes = new Set();
  for (const row of rows) {
    const code = (row[0] || '').trim();
    if (code) codes.add(code);
  }
  return codes;
}

/**
 * Anti-zombie merge of source rows into one target file.
 *
 * @param {string} targetPath - Absolute path of the target CSV
 * @param {string[][]} sourceRows - Data rows to register
 * @param {Set<string>} sourceCodes - Module codes the rows belong to
 * @param {boolean} createIfMissing - Create the target (catalog header) when absent
 * @returns {{written: boolean, removed: number, added: number}}
 */
async function mergeIntoTarget(targetPath, sourceRows, sourceCodes, createIfMissing) {
  const exists = await fs.pathExists(targetPath);
  if (!exists && !createIfMissing) {
    return { written: false, removed: 0, added: 0 };
  }

  let header = CATALOG_HEADER;
  let dataRows = [];
  if (exists) {
    const parsed = parseCsv(await fs.readFile(targetPath, 'utf8'));
    if (parsed.length > 0) {
      header = parsed[0];
      // Drop all-empty rows (a hand-edited catalog's stray blank lines parse
      // as [''] data rows) so they neither accumulate nor skew row counts.
      dataRows = parsed.slice(1).filter((row) => row.some((f) => (f || '').trim() !== ''));
    }
  }

  const before = dataRows.length;
  const kept = dataRows.filter((row) => !sourceCodes.has((row[0] || '').trim()));
  const merged = [...kept, ...sourceRows];

  await fs.ensureDir(path.dirname(targetPath));
  await fs.writeFile(targetPath, serializeCsv([header, ...merged]), 'utf8');
  return { written: true, removed: before - kept.length, added: sourceRows.length };
}

/**
 * Build the module's `_meta` catalog row from module.yaml, mirroring how the
 * BMAD installer registers each module's LLM-readable docs. Source CSVs do
 * not author `_meta` rows (the standalone-module validator treats `_meta` as
 * an orphan skill reference) — the assembler adds it.
 *
 * @param {string} moduleYamlPath - Absolute path to assets/module.yaml
 * @returns {string[]|null} the 13-column _meta row, or null without docs_llms
 */
async function buildMetaRow(moduleYamlPath) {
  if (!(await fs.pathExists(moduleYamlPath))) return null;
  const moduleYaml = yaml.load(await fs.readFile(moduleYamlPath, 'utf8')) || {};
  if (!moduleYaml.name || !moduleYaml.docs_llms) return null;
  return [moduleYaml.name, '_meta', '', '', '', '', '', '', '', '', 'false', moduleYaml.docs_llms, ''];
}

/**
 * Register the module's help rows into the project's help catalog(s).
 *
 * @param {string} projectDir - Project root
 * @param {string} sourceCsvPath - Absolute path to assets/module-help.csv
 * @param {string} [moduleYamlPath] - Absolute path to assets/module.yaml (adds the _meta docs row)
 * @returns {{module_codes: string[], targets: string[]}} registration summary
 */
async function registerHelpEntries(projectDir, sourceCsvPath, moduleYamlPath) {
  const parsed = parseCsv(await fs.readFile(sourceCsvPath, 'utf8'));
  const sourceRows = parsed.slice(1).filter((row) => row.some((f) => f !== ''));
  if (sourceRows.length === 0) {
    throw new Error(`No help entries found in ${sourceCsvPath}`);
  }
  if (moduleYamlPath) {
    const metaRow = await buildMetaRow(moduleYamlPath);
    if (metaRow) sourceRows.unshift(metaRow);
  }
  const sourceCodes = extractModuleCodes(sourceRows);
  if (sourceCodes.size === 0) {
    throw new Error(`Could not determine module code from ${sourceCsvPath}`);
  }

  const targets = [];
  const catalogPath = path.join(projectDir, ASSEMBLED_CATALOG);
  const catalogResult = await mergeIntoTarget(catalogPath, sourceRows, sourceCodes, true);
  if (catalogResult.written) targets.push(ASSEMBLED_CATALOG);

  const moduleHelpPath = path.join(projectDir, MODULE_HELP);
  const moduleHelpResult = await mergeIntoTarget(moduleHelpPath, sourceRows, sourceCodes, false);
  if (moduleHelpResult.written) targets.push(MODULE_HELP);

  return { module_codes: [...sourceCodes].sort(), targets };
}

/**
 * Remove the module's rows from the help catalog(s). A target left with no
 * data rows is deleted entirely (it only existed to hold rows; the BMAD
 * installer recreates its own catalog), which also lets the uninstaller's
 * empty-directory cleanup of _bmad/_config/ succeed.
 *
 * @param {string} projectDir - Project root
 * @param {string[]} moduleCodes - Module codes (column 1 values) to remove
 * @returns {string[]} relative paths of targets that were modified or deleted
 */
async function removeHelpEntries(projectDir, moduleCodes) {
  const codes = new Set(moduleCodes);
  const touched = [];

  for (const relTarget of [ASSEMBLED_CATALOG, MODULE_HELP]) {
    const targetPath = path.join(projectDir, relTarget);
    if (!(await fs.pathExists(targetPath))) continue;

    const parsed = parseCsv(await fs.readFile(targetPath, 'utf8'));
    if (parsed.length === 0) continue;
    const header = parsed[0];
    // Drop all-empty rows so a stray blank line in a hand-edited catalog
    // can't defeat the "no data rows left → delete the file" predicate.
    const dataRows = parsed.slice(1).filter((row) => row.some((f) => (f || '').trim() !== ''));
    const kept = dataRows.filter((row) => !codes.has((row[0] || '').trim()));

    if (kept.length === dataRows.length) continue; // nothing of ours in there

    if (kept.length === 0) {
      await fs.remove(targetPath);
    } else {
      await fs.writeFile(targetPath, serializeCsv([header, ...kept]), 'utf8');
    }
    touched.push(relTarget);
  }

  return touched;
}

module.exports = {
  registerHelpEntries,
  removeHelpEntries,
  parseCsv,
  serializeCsv,
  ASSEMBLED_CATALOG,
  MODULE_HELP,
  CATALOG_HEADER,
};
