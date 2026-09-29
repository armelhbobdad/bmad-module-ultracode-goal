# Installer API exports (AST-verified)

Every name exported through a `module.exports` barrel in `tools/installer/**` at v6.12.0, with its AST-located definition (`ast-grep`, T1). Names whose barrel entry is an object property or a re-export of Node's `fs` have no separate definition and cite the `module.exports` line. Class methods are listed under their class.

## Contents

- [cli-utils.js](#cli-utilsjs)
- [commands/install.js](#commandsinstalljs)
- [commands/status.js](#commandsstatusjs)
- [commands/uninstall.js](#commandsuninstalljs)
- [core/config.js](#coreconfigjs)
- [core/existing-install.js](#coreexisting-installjs)
- [core/install-paths.js](#coreinstall-pathsjs)
- [core/installer.js](#coreinstallerjs)
- [core/legacy-warnings.js](#corelegacy-warningsjs)
- [core/manifest-generator.js](#coremanifest-generatorjs)
- [core/manifest.js](#coremanifestjs)
- [core/shim-policy.js](#coreshim-policyjs)
- [core/uv-check.js](#coreuv-checkjs)
- [core/wsl-node-check.js](#corewsl-node-checkjs)
- [file-ops.js](#file-opsjs)
- [fs-native.js](#fs-nativejs)
- [ide/_config-driven.js](#ide_config-drivenjs)
- [ide/manager.js](#idemanagerjs)
- [ide/platform-codes.js](#ideplatform-codesjs)
- [ide/shared/installed-skills.js](#idesharedinstalled-skillsjs)
- [ide/shared/path-utils.js](#idesharedpath-utilsjs)
- [ide/shared/skill-manifest.js](#idesharedskill-manifestjs)
- [list-options.js](#list-optionsjs)
- [message-loader.js](#message-loaderjs)
- [modules/channel-plan.js](#moduleschannel-planjs)
- [modules/channel-resolver.js](#moduleschannel-resolverjs)
- [modules/custom-module-manager.js](#modulescustom-module-managerjs)
- [modules/external-manager.js](#modulesexternal-managerjs)
- [modules/git-env.js](#modulesgit-envjs)
- [modules/module-help-schema.js](#modulesmodule-help-schemajs)
- [modules/official-modules.js](#modulesofficial-modulesjs)
- [modules/plugin-resolver.js](#modulesplugin-resolverjs)
- [modules/version-resolver.js](#modulesversion-resolverjs)
- [project-root.js](#project-rootjs)
- [prompts.js](#promptsjs)
- [set-overrides.js](#set-overridesjs)
- [ui.js](#uijs)
- [yaml-format.js](#yaml-formatjs)

## cli-utils.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `CLIUtils` | constant | `const CLIUtils = {` | [AST:tools/installer/cli-utils.js:L3] |

## commands/install.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `command` | property / re-export | — | [SRC:tools/installer/commands/install.js:L9] |
| `description` | property / re-export | — | [SRC:tools/installer/commands/install.js:L9] |
| `options` | property / re-export | — | [SRC:tools/installer/commands/install.js:L9] |
| `update` | property / re-export | — | [SRC:tools/installer/commands/install.js:L9] |
| `action` | property / re-export | — | [SRC:tools/installer/commands/install.js:L9] |

## commands/status.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `command` | property / re-export | — | [SRC:tools/installer/commands/status.js:L11] |
| `description` | property / re-export | — | [SRC:tools/installer/commands/status.js:L11] |
| `options` | property / re-export | — | [SRC:tools/installer/commands/status.js:L11] |
| `action` | property / re-export | — | [SRC:tools/installer/commands/status.js:L11] |

## commands/uninstall.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `command` | property / re-export | — | [SRC:tools/installer/commands/uninstall.js:L8] |
| `description` | property / re-export | — | [SRC:tools/installer/commands/uninstall.js:L8] |
| `options` | property / re-export | — | [SRC:tools/installer/commands/uninstall.js:L8] |
| `action` | property / re-export | — | [SRC:tools/installer/commands/uninstall.js:L8] |

## core/config.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `Config` | class | `class Config {` | [AST:tools/installer/core/config.js:L5] |

**`Config` methods (4):** `constructor()` [AST:tools/installer/core/config.js:L6], `build()` [AST:tools/installer/core/config.js:L45], `hasCoreConfig()` [AST:tools/installer/core/config.js:L67], `isQuickUpdate()` [AST:tools/installer/core/config.js:L71]

## core/existing-install.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `ExistingInstall` | class | `class ExistingInstall {` | [AST:tools/installer/core/existing-install.js:L10] |

**`ExistingInstall` methods (4):** `constructor()` [AST:tools/installer/core/existing-install.js:L13], `get version()` [AST:tools/installer/core/existing-install.js:L23], `empty()` [AST:tools/installer/core/existing-install.js:L30], `detect()` [AST:tools/installer/core/existing-install.js:L45]

## core/install-paths.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `InstallPaths` | class | `class InstallPaths {` | [AST:tools/installer/core/install-paths.js:L6] |

**`InstallPaths` methods (9):** `create()` [AST:tools/installer/core/install-paths.js:L7], `constructor()` [AST:tools/installer/core/install-paths.js:L49], `manifestFile()` [AST:tools/installer/core/install-paths.js:L54], `centralConfig()` [AST:tools/installer/core/install-paths.js:L57], `centralUserConfig()` [AST:tools/installer/core/install-paths.js:L60], `filesManifest()` [AST:tools/installer/core/install-paths.js:L63], `helpCatalog()` [AST:tools/installer/core/install-paths.js:L66], `moduleDir()` [AST:tools/installer/core/install-paths.js:L69], `moduleConfig()` [AST:tools/installer/core/install-paths.js:L72]

## core/installer.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `Installer` | class | `class Installer {` | [AST:tools/installer/core/installer.js:L28] |

**`Installer` methods (37):** `constructor()` [AST:tools/installer/core/installer.js:L29], `install()` [AST:tools/installer/core/installer.js:L45], `_removeDeselectedModules()` [AST:tools/installer/core/installer.js:L193], `_validateIdeSelection()` [AST:tools/installer/core/installer.js:L214], `_removeDeselectedIdes()` [AST:tools/installer/core/installer.js:L238], `_installAndConfigure()` [AST:tools/installer/core/installer.js:L262], `_setupIdes()` [AST:tools/installer/core/installer.js:L425], `_cleanupSkillDirs()` [AST:tools/installer/core/installer.js:L459], `_removeEmptyParents()` [AST:tools/installer/core/installer.js:L487], `_readSkillManifestRows()` [AST:tools/installer/core/installer.js:L504], `_getPreviousSkillIdsForCleanup()` [AST:tools/installer/core/installer.js:L518], `_appendPreservedSkillManifestRows()` [AST:tools/installer/core/installer.js:L529], `_restoreUserFiles()` [AST:tools/installer/core/installer.js:L567], `_prepareUpdateState()` [AST:tools/installer/core/installer.js:L638], `_backupUserFiles()` [AST:tools/installer/core/installer.js:L677], `_installSharedScripts()` [AST:tools/installer/core/installer.js:L716], `_trackFilesRecursive()` [AST:tools/installer/core/installer.js:L747], `_trackPreservedModuleFiles()` [AST:tools/installer/core/installer.js:L759], `_installOfficialModules()` [AST:tools/installer/core/installer.js:L777], `readFilesManifest()` [AST:tools/installer/core/installer.js:L836], `detectCustomFiles()` [AST:tools/installer/core/installer.js:L893], `generateModuleConfigs()` [AST:tools/installer/core/installer.js:L1011], `mergeModuleHelpCatalogs()` [AST:tools/installer/core/installer.js:L1108], `renderInstallSummary()` [AST:tools/installer/core/installer.js:L1221], `_displayPostInstallMessages()` [AST:tools/installer/core/installer.js:L1344], `quickUpdate()` [AST:tools/installer/core/installer.js:L1386], `uninstall()` [AST:tools/installer/core/installer.js:L1599], `uninstallIdeConfigs()` [AST:tools/installer/core/installer.js:L1639], `uninstallOutputFolder()` [AST:tools/installer/core/installer.js:L1655], `uninstallModules()` [AST:tools/installer/core/installer.js:L1674], `getStatus()` [AST:tools/installer/core/installer.js:L1686], `getAvailableModules()` [AST:tools/installer/core/installer.js:L1695], `getOutputFolder()` [AST:tools/installer/core/installer.js:L1705], `findBmadDir()` [AST:tools/installer/core/installer.js:L1716], `_readOutputFolder()` [AST:tools/installer/core/installer.js:L1727], `parseCSVLine()` [AST:tools/installer/core/installer.js:L1776], `escapeCSVField()` [AST:tools/installer/core/installer.js:L1810]

## core/legacy-warnings.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `warnPreNativeSkillsLegacy` | function | `async function warnPreNativeSkillsLegacy({ projectRoot, existingVersion } = {}) {` | [AST:tools/installer/core/legacy-warnings.js:L111] |
| `findStaleLegacyDirs` | function | `async function findStaleLegacyDirs(projectRoot) {` | [AST:tools/installer/core/legacy-warnings.js:L83] |
| `isPreNativeSkillsVersion` | function | `function isPreNativeSkillsVersion(version) {` | [AST:tools/installer/core/legacy-warnings.js:L104] |
| `LEGACY_PATHS` | constant | `const LEGACY_PATHS = [...LEGACY_COMMAND_PATHS, ...LEGACY_SKILL_PATHS];` | [AST:tools/installer/core/legacy-warnings.js:L70] |
| `MIN_NATIVE_SKILLS_VERSION` | constant | `const MIN_NATIVE_SKILLS_VERSION = '6.1.0';` | [AST:tools/installer/core/legacy-warnings.js:L9] |

## core/manifest-generator.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `ManifestGenerator` | class | `class ManifestGenerator {` | [AST:tools/installer/core/manifest-generator.js:L14] |

**`ManifestGenerator` methods (14):** `constructor()` [AST:tools/installer/core/manifest-generator.js:L15], `cleanForCSV()` [AST:tools/installer/core/manifest-generator.js:L29], `generateManifests()` [AST:tools/installer/core/manifest-generator.js:L40], `collectSkills()` [AST:tools/installer/core/manifest-generator.js:L112], `parseSkillMd()` [AST:tools/installer/core/manifest-generator.js:L197], `collectAgentsFromModuleYaml()` [AST:tools/installer/core/manifest-generator.js:L244], `writeMainManifest()` [AST:tools/installer/core/manifest-generator.js:L301], `writeSkillManifest()` [AST:tools/installer/core/manifest-generator.js:L406], `writeCentralConfig()` [AST:tools/installer/core/manifest-generator.js:L434], `ensureCustomConfigStubs()` [AST:tools/installer/core/manifest-generator.js:L632], `calculateFileHash()` [AST:tools/installer/core/manifest-generator.js:L675], `writeFilesManifest()` [AST:tools/installer/core/manifest-generator.js:L687], `scanInstalledModules()` [AST:tools/installer/core/manifest-generator.js:L754], `_hasSkillMdRecursive()` [AST:tools/installer/core/manifest-generator.js:L788]

## core/manifest.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `Manifest` | class | `class Manifest {` | [AST:tools/installer/core/manifest.js:L18] |

**`Manifest` methods (11):** `create()` [AST:tools/installer/core/manifest.js:L25], `read()` [AST:tools/installer/core/manifest.js:L89], `_readRaw()` [AST:tools/installer/core/manifest.js:L131], `_flattenManifest()` [AST:tools/installer/core/manifest.js:L152], `addModule()` [AST:tools/installer/core/manifest.js:L175], `getAllModuleVersions()` [AST:tools/installer/core/manifest.js:L234], `_writeRaw()` [AST:tools/installer/core/manifest.js:L248], `calculateFileHash()` [AST:tools/installer/core/manifest.js:L271], `getModuleVersionInfo()` [AST:tools/installer/core/manifest.js:L287], `fetchNpmVersion()` [AST:tools/installer/core/manifest.js:L359], `checkForUpdates()` [AST:tools/installer/core/manifest.js:L406]

## core/shim-policy.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `describeShim` | function | `function describeShim(shim) {` | [AST:tools/installer/core/shim-policy.js:L112] |
| `formatRemovedShimNotice` | function | `function formatRemovedShimNotice(removedShims = [], { canReinstall = true } = {}) {` | [AST:tools/installer/core/shim-policy.js:L132] |
| `discoverShims` | function | `async function discoverShims(modulePath) {` | [AST:tools/installer/core/shim-policy.js:L23] |
| `formatRetainedShimNotice` | function | `function formatRetainedShimNotice(availableShims = []) {` | [AST:tools/installer/core/shim-policy.js:L118] |
| `inferShimPreference` | function | `function inferShimPreference({ requested, persisted, availableShims = [], installedSkil...` | [AST:tools/installer/core/shim-policy.js:L92] |
| `isShimSkill` | function | `function isShimSkill(metadata) {` | [AST:tools/installer/core/shim-policy.js:L19] |
| `parseSkillMetadata` | function | `function parseSkillMetadata(content) {` | [AST:tools/installer/core/shim-policy.js:L6] |
| `readInstalledShims` | function | `async function readInstalledShims(bmadDir) {` | [AST:tools/installer/core/shim-policy.js:L83] |
| `readInstalledSkillIds` | function | `async function readInstalledSkillIds(bmadDir) {` | [AST:tools/installer/core/shim-policy.js:L72] |
| `selectShimOutcome` | function | `function selectShimOutcome({ installedShims = [], availableShims = [], install = false ...` | [AST:tools/installer/core/shim-policy.js:L103] |

## core/uv-check.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `checkUvEnvironment` | function | `async function checkUvEnvironment() {` | [AST:tools/installer/core/uv-check.js:L165] |
| `detectUv` | function | `function detectUv() {` | [AST:tools/installer/core/uv-check.js:L101] |
| `detectPython3` | function | `function detectPython3() {` | [AST:tools/installer/core/uv-check.js:L109] |
| `parseUvVersion` | function | `function parseUvVersion(output) {` | [AST:tools/installer/core/uv-check.js:L34] |
| `parsePythonVersion` | function | `function parsePythonVersion(output) {` | [AST:tools/installer/core/uv-check.js:L52] |
| `pythonMeetsMinimum` | function | `function pythonMeetsMinimum(version) {` | [AST:tools/installer/core/uv-check.js:L69] |
| `MIN_PYTHON` | constant | `const MIN_PYTHON = { major: 3, minor: 11 };` | [AST:tools/installer/core/uv-check.js:L26] |

## core/wsl-node-check.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `checkWindowsNodeFromWsl` | function | `async function checkWindowsNodeFromWsl() {` | [AST:tools/installer/core/wsl-node-check.js:L95] |
| `detectWindowsNodeFromWsl` | function | `function detectWindowsNodeFromWsl(runtime = {}) {` | [AST:tools/installer/core/wsl-node-check.js:L32] |
| `formatWindowsNodeFromWslMessage` | function | `function formatWindowsNodeFromWslMessage(detection) {` | [AST:tools/installer/core/wsl-node-check.js:L74] |

## file-ops.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `FileOps` | class | `class FileOps {` | [AST:tools/installer/file-ops.js:L8] |

**`FileOps` methods (11):** `copyDirectory()` [AST:tools/installer/file-ops.js:L15], `syncDirectory()` [AST:tools/installer/file-ops.js:L31], `getFileList()` [AST:tools/installer/file-ops.js:L82], `getFileHash()` [AST:tools/installer/file-ops.js:L112], `shouldIgnore()` [AST:tools/installer/file-ops.js:L128], `ensureDir()` [AST:tools/installer/file-ops.js:L152], `remove()` [AST:tools/installer/file-ops.js:L160], `readFile()` [AST:tools/installer/file-ops.js:L171], `writeFile()` [AST:tools/installer/file-ops.js:L180], `exists()` [AST:tools/installer/file-ops.js:L190], `stat()` [AST:tools/installer/file-ops.js:L199]

## fs-native.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `readFile` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `writeFile` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `stat` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `readdir` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `access` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `realpath` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `rename` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `rmdir` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `unlink` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `chmod` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `mkdir` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `mkdtemp` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `copyFile` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `rm` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `pathExists` | function | `async function pathExists(p) {` | [AST:tools/installer/fs-native.js:L8] |
| `ensureDir` | function | `async function ensureDir(dir) {` | [AST:tools/installer/fs-native.js:L17] |
| `remove` | function | `async function remove(p) {` | [AST:tools/installer/fs-native.js:L21] |
| `copy` | function | `async function copy(src, dest, options = {}) {` | [AST:tools/installer/fs-native.js:L25] |
| `move` | function | `async function move(src, dest) {` | [AST:tools/installer/fs-native.js:L56] |
| `readJsonSync` | function | `function readJsonSync(p) {` | [AST:tools/installer/fs-native.js:L69] |
| `writeJson` | function | `async function writeJson(p, data, options = {}) {` | [AST:tools/installer/fs-native.js:L73] |
| `existsSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `readFileSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `writeFileSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `statSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `accessSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `readdirSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `createReadStream` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `pathExistsSync` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |
| `constants` | property / re-export | — | [SRC:tools/installer/fs-native.js:L78] |

## ide/_config-driven.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `ConfigDrivenIdeSetup` | class | `class ConfigDrivenIdeSetup {` | [AST:tools/installer/ide/_config-driven.js:L140] |

**`ConfigDrivenIdeSetup` methods (20):** `constructor()` [AST:tools/installer/ide/_config-driven.js:L141], `setBmadFolderName()` [AST:tools/installer/ide/_config-driven.js:L153], `detect()` [AST:tools/installer/ide/_config-driven.js:L163], `setup()` [AST:tools/installer/ide/_config-driven.js:L189], `installToTarget()` [AST:tools/installer/ide/_config-driven.js:L245], `installCommandPointers()` [AST:tools/installer/ide/_config-driven.js:L292], `installVerbatimSkills()` [AST:tools/installer/ide/_config-driven.js:L417], `printSummary()` [AST:tools/installer/ide/_config-driven.js:L475], `cleanup()` [AST:tools/installer/ide/_config-driven.js:L499], `_findBmadDir()` [AST:tools/installer/ide/_config-driven.js:L579], `_buildUninstallSet()` [AST:tools/installer/ide/_config-driven.js:L590], `loadRemovalLists()` [AST:tools/installer/ide/_config-driven.js:L618], `_readRemovalFile()` [AST:tools/installer/ide/_config-driven.js:L646], `cleanupCommandPointers()` [AST:tools/installer/ide/_config-driven.js:L682], `_readActiveSkillIds()` [AST:tools/installer/ide/_config-driven.js:L735], `cleanupTarget()` [AST:tools/installer/ide/_config-driven.js:L762], `cleanupCopilotInstructions()` [AST:tools/installer/ide/_config-driven.js:L826], `cleanupKiloModes()` [AST:tools/installer/ide/_config-driven.js:L864], `cleanupRovoDevPrompts()` [AST:tools/installer/ide/_config-driven.js:L901], `findAncestorConflict()` [AST:tools/installer/ide/_config-driven.js:L943]

## ide/manager.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `IdeManager` | class | `class IdeManager {` | [AST:tools/installer/ide/manager.js:L11] |

**`IdeManager` methods (13):** `constructor()` [AST:tools/installer/ide/manager.js:L12], `setBmadFolderName()` [AST:tools/installer/ide/manager.js:L22], `ensureInitialized()` [AST:tools/installer/ide/manager.js:L35], `loadHandlers()` [AST:tools/installer/ide/manager.js:L45], `loadConfigDrivenHandlers()` [AST:tools/installer/ide/manager.js:L53], `getAvailableIdes()` [AST:tools/installer/ide/manager.js:L75], `getPreferredIdes()` [AST:tools/installer/ide/manager.js:L113], `getOtherIdes()` [AST:tools/installer/ide/manager.js:L121], `setup()` [AST:tools/installer/ide/manager.js:L132], `setupBatch()` [AST:tools/installer/ide/manager.js:L195], `cleanup()` [AST:tools/installer/ide/manager.js:L241], `cleanupByList()` [AST:tools/installer/ide/manager.js:L266], `detectInstalledIdes()` [AST:tools/installer/ide/manager.js:L311]

## ide/platform-codes.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `loadPlatformCodes` | function | `async function loadPlatformCodes() {` | [AST:tools/installer/ide/platform-codes.js:L13] |
| `clearCache` | function | `function clearCache() {` | [AST:tools/installer/ide/platform-codes.js:L30] |
| `formatPlatformList` | function | `async function formatPlatformList() {` | [AST:tools/installer/ide/platform-codes.js:L40] |

## ide/shared/installed-skills.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `getInstalledCanonicalIds` | function | `async function getInstalledCanonicalIds(bmadDir) {` | [AST:tools/installer/ide/shared/installed-skills.js:L14] |
| `isBmadOwnedEntry` | function | `function isBmadOwnedEntry(entry, canonicalIds) {` | [AST:tools/installer/ide/shared/installed-skills.js:L43] |

## ide/shared/path-utils.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `toDashName` | function | `function toDashName(module, type, name) {` | [AST:tools/installer/ide/shared/path-utils.js:L35] |
| `toDashPath` | function | `function toDashPath(relativePath) {` | [AST:tools/installer/ide/shared/path-utils.js:L63] |
| `resolveSkillName` | function | `function resolveSkillName(artifact) {` | [AST:tools/installer/ide/shared/path-utils.js:L203] |
| `customAgentDashName` | function | `function customAgentDashName(agentName) {` | [AST:tools/installer/ide/shared/path-utils.js:L98] |
| `isDashFormat` | function | `function isDashFormat(filename) {` | [AST:tools/installer/ide/shared/path-utils.js:L107] |
| `parseDashName` | function | `function parseDashName(filename) {` | [AST:tools/installer/ide/shared/path-utils.js:L123] |
| `AGENT_SEGMENT` | constant | `const AGENT_SEGMENT = 'agents';` | [AST:tools/installer/ide/shared/path-utils.js:L18] |
| `BMAD_FOLDER_NAME` | constant | `const BMAD_FOLDER_NAME = '_bmad';` | [AST:tools/installer/ide/shared/path-utils.js:L21] |

## ide/shared/skill-manifest.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `loadSkillManifest` | function | `async function loadSkillManifest(dirPath) {` | [AST:tools/installer/ide/shared/skill-manifest.js:L12] |
| `getCanonicalId` | function | `function getCanonicalId(manifest, filename) {` | [AST:tools/installer/ide/shared/skill-manifest.js:L33] |
| `getArtifactType` | function | `function getArtifactType(manifest, filename) {` | [AST:tools/installer/ide/shared/skill-manifest.js:L48] |

## list-options.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `formatOptionsList` | function | `async function formatOptionsList(moduleCode) {` | [AST:tools/installer/list-options.js:L155] |
| `discoverOfficialModuleYamls` | function | `async function discoverOfficialModuleYamls() {` | [AST:tools/installer/list-options.js:L34] |

## message-loader.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `MessageLoader` | class | `class MessageLoader {` | [AST:tools/installer/message-loader.js:L9] |

**`MessageLoader` methods (7):** `constructor()` [AST:tools/installer/message-loader.js:L10], `load()` [AST:tools/installer/message-loader.js:L16], `getStartMessage()` [AST:tools/installer/message-loader.js:L37], `getEndMessage()` [AST:tools/installer/message-loader.js:L46], `displayStartMessage()` [AST:tools/installer/message-loader.js:L54], `displayEndMessage()` [AST:tools/installer/message-loader.js:L64], `isCurrent()` [AST:tools/installer/message-loader.js:L76]

## modules/channel-plan.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `parseChannelOptions` | function | `function parseChannelOptions(options = {}) {` | [AST:tools/installer/modules/channel-plan.js:L31] |
| `decideChannelForModule` | function | `function decideChannelForModule({ code, channelOptions, registryDefault }) {` | [AST:tools/installer/modules/channel-plan.js:L110] |
| `buildPlan` | function | `function buildPlan({ modules, channelOptions }) {` | [AST:tools/installer/modules/channel-plan.js:L138] |
| `orphanPinWarnings` | function | `function orphanPinWarnings(channelOptions, selectedCodes) {` | [AST:tools/installer/modules/channel-plan.js:L157] |
| `bundledTargetWarnings` | function | `function bundledTargetWarnings(channelOptions, bundledCodes) {` | [AST:tools/installer/modules/channel-plan.js:L179] |
| `parsePinSpec` | function | `function parsePinSpec(spec) {` | [AST:tools/installer/modules/channel-plan.js:L90] |

## modules/channel-resolver.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `parseGitHubRepo` | function | `function parseGitHubRepo(url) {` | [AST:tools/installer/modules/channel-resolver.js:L29] |
| `fetchStableTags` | function | `async function fetchStableTags(owner, repo, { timeout } = {}) {` | [AST:tools/installer/modules/channel-resolver.js:L104] |
| `resolveChannel` | function | `async function resolveChannel({ channel, pin, repoUrl, timeout }) {` | [AST:tools/installer/modules/channel-resolver.js:L144] |
| `tagExists` | function | `async function tagExists(owner, repo, tagName, { timeout } = {}) {` | [AST:tools/installer/modules/channel-resolver.js:L182] |
| `classifyUpgrade` | function | `function classifyUpgrade(currentVersion, newVersion) {` | [AST:tools/installer/modules/channel-resolver.js:L201] |
| `releaseNotesUrl` | function | `function releaseNotesUrl(repoUrl, tag) {` | [AST:tools/installer/modules/channel-resolver.js:L219] |
| `normalizeStableTag` | function | `function normalizeStableTag(tagName) {` | [AST:tools/installer/modules/channel-resolver.js:L86] |
| `_clearTagCache` | function | `function _clearTagCache() {` | [AST:tools/installer/modules/channel-resolver.js:L228] |

## modules/custom-module-manager.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `CustomModuleManager` | class | `class CustomModuleManager {` | [AST:tools/installer/modules/custom-module-manager.js:L32] |

**`CustomModuleManager` methods (18):** `parseSource()` [AST:tools/installer/modules/custom-module-manager.js:L52], `_parseLocalPath()` [AST:tools/installer/modules/custom-module-manager.js:L257], `readMarketplaceJsonFromDisk()` [AST:tools/installer/modules/custom-module-manager.js:L293], `discoverModules()` [AST:tools/installer/modules/custom-module-manager.js:L311], `resolveSource()` [AST:tools/installer/modules/custom-module-manager.js:L329], `getCacheDir()` [AST:tools/installer/modules/custom-module-manager.js:L363], `cloneRepo()` [AST:tools/installer/modules/custom-module-manager.js:L376], `start()` [AST:tools/installer/modules/custom-module-manager.js:L394], `stop()` [AST:tools/installer/modules/custom-module-manager.js:L394], `error()` [AST:tools/installer/modules/custom-module-manager.js:L394], `resolvePlugin()` [AST:tools/installer/modules/custom-module-manager.js:L589], `getResolution()` [AST:tools/installer/modules/custom-module-manager.js:L625], `findModuleSource()` [AST:tools/installer/modules/custom-module-manager.js:L637], `findModuleSourceByCode()` [AST:tools/installer/modules/custom-module-manager.js:L696], `_refreshRepoCacheOnce()` [AST:tools/installer/modules/custom-module-manager.js:L783], `_findLocalSourceFromManifest()` [AST:tools/installer/modules/custom-module-manager.js:L824], `_findCacheRepoRoots()` [AST:tools/installer/modules/custom-module-manager.js:L859], `_normalizeCustomModule()` [AST:tools/installer/modules/custom-module-manager.js:L904]

## modules/external-manager.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `ExternalModuleManager` | class | `class ExternalModuleManager {` | [AST:tools/installer/modules/external-manager.js:L59] |

**`ExternalModuleManager` methods (20):** `constructor()` [AST:tools/installer/modules/external-manager.js:L73], `getResolution()` [AST:tools/installer/modules/external-manager.js:L80], `getPluginResolution()` [AST:tools/installer/modules/external-manager.js:L89], `loadExternalModulesConfig()` [AST:tools/installer/modules/external-manager.js:L97], `_normalizeModule()` [AST:tools/installer/modules/external-manager.js:L120], `listAvailable()` [AST:tools/installer/modules/external-manager.js:L150], `getModuleByCode()` [AST:tools/installer/modules/external-manager.js:L173], `resolveCanonicalCode()` [AST:tools/installer/modules/external-manager.js:L185], `getExternalCacheDir()` [AST:tools/installer/modules/external-manager.js:L194], `cloneExternalModule()` [AST:tools/installer/modules/external-manager.js:L211], `start()` [AST:tools/installer/modules/external-manager.js:L234], `stop()` [AST:tools/installer/modules/external-manager.js:L235], `error()` [AST:tools/installer/modules/external-manager.js:L236], `message()` [AST:tools/installer/modules/external-manager.js:L237], `cancel()` [AST:tools/installer/modules/external-manager.js:L238], `clear()` [AST:tools/installer/modules/external-manager.js:L239], `get isSpinning()` [AST:tools/installer/modules/external-manager.js:L240], `get isCancelled()` [AST:tools/installer/modules/external-manager.js:L243], `findExternalModuleSource()` [AST:tools/installer/modules/external-manager.js:L511], `resolvePluginModule()` [AST:tools/installer/modules/external-manager.js:L600]

## modules/git-env.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `gitEnv` | function | `function gitEnv(extra = {}) {` | [AST:tools/installer/modules/git-env.js:L38] |

## modules/module-help-schema.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `MODULE_HELP_CSV_HEADER` | constant | `const MODULE_HELP_CSV_HEADER =` | [AST:tools/installer/modules/module-help-schema.js:L10] |

## modules/official-modules.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `OfficialModules` | class | `class OfficialModules {` | [AST:tools/installer/modules/official-modules.js:L10] |

**`OfficialModules` methods (38):** `constructor()` [AST:tools/installer/modules/official-modules.js:L11], `get moduleConfigs()` [AST:tools/installer/modules/official-modules.js:L29], `get existingConfig()` [AST:tools/installer/modules/official-modules.js:L36], `build()` [AST:tools/installer/modules/official-modules.js:L46], `copyFile()` [AST:tools/installer/modules/official-modules.js:L80], `copyDirectory()` [AST:tools/installer/modules/official-modules.js:L90], `listAvailable()` [AST:tools/installer/modules/official-modules.js:L111], `discoverShims()` [AST:tools/installer/modules/official-modules.js:L135], `getModuleInfo()` [AST:tools/installer/modules/official-modules.js:L159], `findModuleSource()` [AST:tools/installer/modules/official-modules.js:L221], `install()` [AST:tools/installer/modules/official-modules.js:L273], `_copyResolvedSkills()` [AST:tools/installer/modules/official-modules.js:L361], `installFromResolution()` [AST:tools/installer/modules/official-modules.js:L403], `update()` [AST:tools/installer/modules/official-modules.js:L457], `remove()` [AST:tools/installer/modules/official-modules.js:L483], `isInstalled()` [AST:tools/installer/modules/official-modules.js:L504], `getInstalledInfo()` [AST:tools/installer/modules/official-modules.js:L515], `copyModuleWithFiltering()` [AST:tools/installer/modules/official-modules.js:L549], `createModuleDirectories()` [AST:tools/installer/modules/official-modules.js:L627], `syncModule()` [AST:tools/installer/modules/official-modules.js:L793], `getFileList()` [AST:tools/installer/modules/official-modules.js:L823], `findBmadDir()` [AST:tools/installer/modules/official-modules.js:L849], `detectExistingBmadFolder()` [AST:tools/installer/modules/official-modules.js:L883], `loadExistingConfig()` [AST:tools/installer/modules/official-modules.js:L912], `_hoistCoreKeysFromLegacyModuleConfigs()` [AST:tools/installer/modules/official-modules.js:L998], `scanModuleSchemas()` [AST:tools/installer/modules/official-modules.js:L1042], `collectAllConfigurations()` [AST:tools/installer/modules/official-modules.js:L1102], `collectModuleConfigQuick()` [AST:tools/installer/modules/official-modules.js:L1231], `processResultTemplate()` [AST:tools/installer/modules/official-modules.js:L1441], `getDefaultUsername()` [AST:tools/installer/modules/official-modules.js:L1500], `collectModuleConfig()` [AST:tools/installer/modules/official-modules.js:L1522], `replacePlaceholders()` [AST:tools/installer/modules/official-modules.js:L1807], `cleanPromptValue()` [AST:tools/installer/modules/official-modules.js:L1829], `resolveConfigValue()` [AST:tools/installer/modules/official-modules.js:L1844], `normalizeExistingValueForPrompt()` [AST:tools/installer/modules/official-modules.js:L1903], `buildQuestion()` [AST:tools/installer/modules/official-modules.js:L1942], `displayModulePostConfigNotes()` [AST:tools/installer/modules/official-modules.js:L2167], `deepMerge()` [AST:tools/installer/modules/official-modules.js:L2214]

## modules/plugin-resolver.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `PluginResolver` | class | `class PluginResolver {` | [AST:tools/installer/modules/plugin-resolver.js:L17] |

**`PluginResolver` methods (13):** `resolve()` [AST:tools/installer/modules/plugin-resolver.js:L29], `_tryRootModuleFiles()` [AST:tools/installer/modules/plugin-resolver.js:L72], `_trySetupSkill()` [AST:tools/installer/modules/plugin-resolver.js:L106], `_trySingleStandalone()` [AST:tools/installer/modules/plugin-resolver.js:L146], `_tryMultipleStandalone()` [AST:tools/installer/modules/plugin-resolver.js:L183], `_synthesizeFallback()` [AST:tools/installer/modules/plugin-resolver.js:L229], `_computeCommonParent()` [AST:tools/installer/modules/plugin-resolver.js:L278], `_readModuleYaml()` [AST:tools/installer/modules/plugin-resolver.js:L303], `_parseSkillFrontmatter()` [AST:tools/installer/modules/plugin-resolver.js:L317], `_buildSynthesizedHelpCsv()` [AST:tools/installer/modules/plugin-resolver.js:L341], `_formatDisplayName()` [AST:tools/installer/modules/plugin-resolver.js:L361], `_generateMenuCode()` [AST:tools/installer/modules/plugin-resolver.js:L375], `_escapeCSVField()` [AST:tools/installer/modules/plugin-resolver.js:L389]

## modules/version-resolver.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `resolveModuleVersion` | function | `async function resolveModuleVersion(moduleName, options = {}) {` | [AST:tools/installer/modules/version-resolver.js:L24] |

## project-root.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `getProjectRoot` | function | `function getProjectRoot() {` | [AST:tools/installer/project-root.js:L44] |
| `getSourcePath` | function | `function getSourcePath(...segments) {` | [AST:tools/installer/project-root.js:L54] |
| `getModulePath` | function | `function getModulePath(moduleName, ...segments) {` | [AST:tools/installer/project-root.js:L64] |
| `getExternalModuleCachePath` | function | `function getExternalModuleCachePath(moduleName, ...segments) {` | [AST:tools/installer/project-root.js:L79] |
| `resolveInstalledModuleYaml` | function | `async function resolveInstalledModuleYaml(moduleName) {` | [AST:tools/installer/project-root.js:L102] |
| `findProjectRoot` | function | `function findProjectRoot(startPath = __dirname) {` | [AST:tools/installer/project-root.js:L10] |

## prompts.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `getClack` | function | `async function getClack() {` | [AST:tools/installer/prompts.js:L21] |
| `getColor` | function | `async function getColor() {` | [AST:tools/installer/prompts.js:L680] |
| `handleCancel` | function | `async function handleCancel(value, message = 'Operation cancelled') {` | [AST:tools/installer/prompts.js:L56] |
| `intro` | function | `async function intro(message) {` | [AST:tools/installer/prompts.js:L69] |
| `outro` | function | `async function outro(message) {` | [AST:tools/installer/prompts.js:L78] |
| `cancel` | function | `async function cancel(message = 'Operation cancelled') {` | [AST:tools/installer/prompts.js:L561] |
| `note` | function | `async function note(message, title) {` | [AST:tools/installer/prompts.js:L88] |
| `box` | function | `async function box(content, title, options) {` | [AST:tools/installer/prompts.js:L572] |
| `spinner` | function | `async function spinner() {` | [AST:tools/installer/prompts.js:L98] |
| `select` | function | `async function select(options) {` | [AST:tools/installer/prompts.js:L150] |
| `multiselect` | function | `async function multiselect(options) {` | [AST:tools/installer/prompts.js:L192] |
| `autocompleteMultiselect` | function | `async function autocompleteMultiselect(options) {` | [AST:tools/installer/prompts.js:L261] |
| `autocomplete` | function | `async function autocomplete(options) {` | [AST:tools/installer/prompts.js:L587] |
| `directory` | function | `async function directory(options) {` | [AST:tools/installer/prompts.js:L638] |
| `resolveDirectoryInput` | function | `function resolveDirectoryInput(input, options = {}) {` | [AST:tools/installer/prompts.js:L608] |
| `confirm` | function | `async function confirm(options) {` | [AST:tools/installer/prompts.js:L410] |
| `text` | function | `async function text(options) {` | [AST:tools/installer/prompts.js:L436] |
| `password` | function | `async function password(options) {` | [AST:tools/installer/prompts.js:L505] |
| `tasks` | function | `async function tasks(taskList) {` | [AST:tools/installer/prompts.js:L522] |
| `log` | constant | `const log = {` | [AST:tools/installer/prompts.js:L530] |
| `prompt` | function | `async function prompt(questions) {` | [AST:tools/installer/prompts.js:L690] |

## set-overrides.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `parseSetEntry` | function | `function parseSetEntry(entry) {` | [AST:tools/installer/set-overrides.js:L35] |
| `parseSetEntries` | function | `function parseSetEntries(entries) {` | [AST:tools/installer/set-overrides.js:L74] |
| `applySetOverrides` | function | `async function applySetOverrides(overrides, bmadDir) {` | [AST:tools/installer/set-overrides.js:L237] |
| `upsertTomlKey` | function | `function upsertTomlKey(content, section, key, valueToml) {` | [AST:tools/installer/set-overrides.js:L137] |
| `tomlString` | function | `function tomlString(value) {` | [AST:tools/installer/set-overrides.js:L89] |

## ui.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `UI` | class | `class UI {` | [AST:tools/installer/ui.js:L113] |

**`UI` methods (32):** `_selectShimPreference()` [AST:tools/installer/ui.js:L114], `_warnDeprecatedModules()` [AST:tools/installer/ui.js:L162], `_retainUnavailableInstalledModules()` [AST:tools/installer/ui.js:L189], `promptInstall()` [AST:tools/installer/ui.js:L237], `_parseToolsFlag()` [AST:tools/installer/ui.js:L592], `promptToolSelection()` [AST:tools/installer/ui.js:L623], `promptUpdate()` [AST:tools/installer/ui.js:L809], `confirm()` [AST:tools/installer/ui.js:L829], `getConfirmedDirectory()` [AST:tools/installer/ui.js:L840], `getExistingInstallation()` [AST:tools/installer/ui.js:L858], `collectModuleConfigs()` [AST:tools/installer/ui.js:L895], `selectAllModules()` [AST:tools/installer/ui.js:L1021], `_selectOfficialModules()` [AST:tools/installer/ui.js:L1049], `_addCustomUrlModules()` [AST:tools/installer/ui.js:L1164], `_resolveCustomSourcesCli()` [AST:tools/installer/ui.js:L1346], `getDefaultModules()` [AST:tools/installer/ui.js:L1441], `promptForDirectory()` [AST:tools/installer/ui.js:L1479], `displayDirectoryInfo()` [AST:tools/installer/ui.js:L1503], `confirmDirectory()` [AST:tools/installer/ui.js:L1534], `validateDirectorySync()` [AST:tools/installer/ui.js:L1568], `validateDirectory()` [AST:tools/installer/ui.js:L1624], `findExistingParentSync()` [AST:tools/installer/ui.js:L1680], `findExistingParent()` [AST:tools/installer/ui.js:L1701], `expandUserPath()` [AST:tools/installer/ui.js:L1722], `getConfiguredIdes()` [AST:tools/installer/ui.js:L1755], `displayModuleVersions()` [AST:tools/installer/ui.js:L1769], `promptUpdateSelection()` [AST:tools/installer/ui.js:L1806], `displayStatus()` [AST:tools/installer/ui.js:L1852], `displaySelectedTools()` [AST:tools/installer/ui.js:L1883], `_bundledModuleCodes()` [AST:tools/installer/ui.js:L1900], `_interactiveChannelGate()` [AST:tools/installer/ui.js:L1923], `_resolveUpdateChannels()` [AST:tools/installer/ui.js:L2013]

## yaml-format.js

| Export | Kind | Definition | Citation |
|--------|------|------------|----------|
| `formatYamlContent` | function | `async function formatYamlContent(content, filename) {` | [AST:tools/installer/yaml-format.js:L21] |
| `processMarkdownFile` | function | `async function processMarkdownFile(filePath) {` | [AST:tools/installer/yaml-format.js:L75] |
| `processYamlFile` | function | `async function processYamlFile(filePath) {` | [AST:tools/installer/yaml-format.js:L126] |

