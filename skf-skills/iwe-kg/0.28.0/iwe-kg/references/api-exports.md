# API exports by crate and module

Every export the extraction found, with its declaration citation: `[AST:...]` for the 90 functions an ast-grep recipe matched (T1), `[SRC:...]` for the types and constants read at their declaration line (T1-low). Signatures come from the declarations in the tagged source, normalized. A declaration that rustfmt wraps over several lines is joined onto one line (e.g. `validate_documents` [AST:crates/diwe/src/schema.rs:L108]). Struct and enum rows drop the trailing `{` (e.g. `WorkspaceOptions` [SRC:crates/diwe/src/config.rs:L26]). A very long declaration is cut short with `...`: the `STARTER_KNOBS` value [SRC:crates/iwe/src/internal/claude/hook/store.rs:L65], and `session_read`, which loses its `-> Result<String, String>` return type [AST:crates/iwe/src/internal/claude/session.rs:L299]. Read the cited line for the exact text.

## Contents

- [`crates/diwe/src/config.rs`](#cratesdiwesrcconfigrs)
- [`crates/liwe/src/model/config.rs`](#cratesliwesrcmodelconfigrs)
- [`crates/diwe/src/find.rs`](#cratesdiwesrcfindrs)
- [`crates/diwe/src/retrieve.rs`](#cratesdiwesrcretrievers)
- [`crates/diwe/src/schema.rs`](#cratesdiwesrcschemars)
- [`crates/iwe/src/filter_args.rs`](#cratesiwesrcfilter_argsrs)
- [`crates/iwe/src/init.rs`](#cratesiwesrcinitrs)
- [`crates/iwe/src/init/agents.rs`](#cratesiwesrcinitagentsrs)
- [`crates/iwe/src/init/writer.rs`](#cratesiwesrcinitwriterrs)
- [`crates/iwe/src/internal/claude/digest.rs`](#cratesiwesrcinternalclaudedigestrs)
- [`crates/iwe/src/internal/claude/enable.rs`](#cratesiwesrcinternalclaudeenablers)
- [`crates/iwe/src/internal/claude/hook/index.rs`](#cratesiwesrcinternalclaudehookindexrs)
- [`crates/iwe/src/internal/claude/hook/post_tool.rs`](#cratesiwesrcinternalclaudehookpost_toolrs)
- [`crates/iwe/src/internal/claude/hook/store.rs`](#cratesiwesrcinternalclaudehookstorers)
- [`crates/iwe/src/internal/claude/policy.rs`](#cratesiwesrcinternalclaudepolicyrs)
- [`crates/iwe/src/internal/claude/prompt.rs`](#cratesiwesrcinternalclaudepromptrs)
- [`crates/iwe/src/internal/claude/record.rs`](#cratesiwesrcinternalclauderecordrs)
- [`crates/iwe/src/internal/claude/session.rs`](#cratesiwesrcinternalclaudesessionrs)
- [`crates/iwe/src/new.rs`](#cratesiwesrcnewrs)
- [`crates/iwe/src/projection_args.rs`](#cratesiwesrcprojection_argsrs)
- [`crates/iwe/src/render.rs`](#cratesiwesrcrenderrs)
- [`crates/iwe/src/schema.rs`](#cratesiwesrcschemars)
- [`crates/iwe/src/stats.rs`](#cratesiwesrcstatsrs)
- [`crates/iwec/src/lib.rs`](#cratesiwecsrclibrs)
- [`crates/iwec/src/watcher.rs`](#cratesiwecsrcwatcherrs)
- [`crates/iwes/src/lib.rs`](#cratesiwessrclibrs)
- [`crates/iwes/src/router.rs`](#cratesiwessrcrouterrs)
- [`crates/iwes/src/router/server/actions.rs`](#cratesiwessrcrouterserveractionsrs)

## `crates/diwe/src/config.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `IWE_MARKER` | constant | `pub const IWE_MARKER: &str = ".iwe";` | [SRC:crates/diwe/src/config.rs:L22] |
| `WorkspaceOptions` | struct | `pub struct WorkspaceOptions` | [SRC:crates/diwe/src/config.rs:L26] |
| `LibraryOptions` | type | `pub type LibraryOptions = WorkspaceOptions;` | [SRC:crates/diwe/src/config.rs:L37] |
| `CompletionOptions` | struct | `pub struct CompletionOptions` | [SRC:crates/diwe/src/config.rs:L41] |
| `SearchOptions` | struct | `pub struct SearchOptions` | [SRC:crates/diwe/src/config.rs:L49] |
| `Configuration` | struct | `pub struct Configuration` | [SRC:crates/diwe/src/config.rs:L81] |
| `Command` | struct | `pub struct Command` | [SRC:crates/diwe/src/config.rs:L107] |
| `ActionDefinition` | enum | `pub enum ActionDefinition` | [SRC:crates/diwe/src/config.rs:L118] |
| `Transform` | struct | `pub struct Transform` | [SRC:crates/diwe/src/config.rs:L137] |
| `Attach` | struct | `pub struct Attach` | [SRC:crates/diwe/src/config.rs:L145] |
| `Sort` | struct | `pub struct Sort` | [SRC:crates/diwe/src/config.rs:L153] |
| `Inline` | struct | `pub struct Inline` | [SRC:crates/diwe/src/config.rs:L160] |
| `Extract` | struct | `pub struct Extract` | [SRC:crates/diwe/src/config.rs:L168] |
| `ExtractAll` | struct | `pub struct ExtractAll` | [SRC:crates/diwe/src/config.rs:L176] |
| `Link` | struct | `pub struct Link` | [SRC:crates/diwe/src/config.rs:L184] |
| `NoteTemplate` | struct | `pub struct NoteTemplate` | [SRC:crates/diwe/src/config.rs:L192] |
| `Patterns` | enum | `pub enum Patterns` | [SRC:crates/diwe/src/config.rs:L199] |
| `SchemaBinding` | struct | `pub struct SchemaBinding` | [SRC:crates/diwe/src/config.rs:L215] |
| `schemas_dir` | function | `pub fn schemas_dir() -> Result<PathBuf, String> {` | [AST:crates/diwe/src/config.rs:L448] |
| `schemas_dir_in` | function | `pub fn schemas_dir_in(base: &Path) -> PathBuf {` | [AST:crates/diwe/src/config.rs:L453] |
| `workspace_path_in` | function | `pub fn workspace_path_in(project_root: &Path, configuration: &Configuration) -> PathBuf {` | [AST:crates/diwe/src/config.rs:L457] |
| `library_path_in` | function | `pub fn library_path_in(project_root: &Path, configuration: &Configuration) -> PathBuf {` | [AST:crates/diwe/src/config.rs:L466] |
| `load_config` | function | `pub fn load_config() -> Result<Configuration, String> {` | [AST:crates/diwe/src/config.rs:L470] |
| `migrate_v2_to_v3` | function | `pub fn migrate_v2_to_v3(input: &str) -> String {` | [AST:crates/diwe/src/config.rs:L709] |
| `migrate_v3_to_v4` | function | `pub fn migrate_v3_to_v4(input: &str) -> String {` | [AST:crates/diwe/src/config.rs:L752] |

## `crates/liwe/src/model/config.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `DEFAULT_KEY_DATE_FORMAT` | constant | `pub const DEFAULT_KEY_DATE_FORMAT: &str = "%Y-%m-%d";` | [SRC:crates/liwe/src/model/config.rs:L10] |
| `MarkdownOptions` | struct | `pub struct MarkdownOptions` | [SRC:crates/liwe/src/model/config.rs:L14] |
| `Format` | enum | `pub enum Format` | [SRC:crates/liwe/src/model/config.rs:L32] |
| `DjotOptions` | struct | `pub struct DjotOptions` | [SRC:crates/liwe/src/model/config.rs:L57] |
| `FormatOptions` | enum | `pub enum FormatOptions` | [SRC:crates/liwe/src/model/config.rs:L86] |
| `WikiLinkPath` | enum | `pub enum WikiLinkPath` | [SRC:crates/liwe/src/model/config.rs:L180] |
| `RefsPath` | enum | `pub enum RefsPath` | [SRC:crates/liwe/src/model/config.rs:L189] |
| `RefsText` | enum | `pub enum RefsText` | [SRC:crates/liwe/src/model/config.rs:L197] |
| `LineBreakStyle` | enum | `pub enum LineBreakStyle` | [SRC:crates/liwe/src/model/config.rs:L226] |
| `FormattingOptions` | struct | `pub struct FormattingOptions` | [SRC:crates/liwe/src/model/config.rs:L233] |
| `LinkType` | enum | `pub enum LinkType` | [SRC:crates/liwe/src/model/config.rs:L396] |
| `InlineType` | enum | `pub enum InlineType` | [SRC:crates/liwe/src/model/config.rs:L404] |
| `Operation` | enum | `pub enum Operation` | [SRC:crates/liwe/src/model/config.rs:L412] |
| `TargetType` | enum | `pub enum TargetType` | [SRC:crates/liwe/src/model/config.rs:L417] |

## `crates/diwe/src/find.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `FindResult` | type | `pub type FindResult = Mapping;` | [SRC:crates/diwe/src/find.rs:L14] |
| `FindOutput` | struct | `pub struct FindOutput` | [SRC:crates/diwe/src/find.rs:L18] |
| `FindOptions` | struct | `pub struct FindOptions` | [SRC:crates/diwe/src/find.rs:L32] |
| `DocumentFinder` | struct | `pub struct DocumentFinder<'a>` | [SRC:crates/diwe/src/find.rs:L51] |

## `crates/diwe/src/retrieve.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `DocumentOutput` | struct | `pub struct DocumentOutput` | [SRC:crates/diwe/src/retrieve.rs:L20] |
| `RetrieveOutput` | struct | `pub struct RetrieveOutput` | [SRC:crates/diwe/src/retrieve.rs:L32] |
| `RetrieveOptions` | struct | `pub struct RetrieveOptions` | [SRC:crates/diwe/src/retrieve.rs:L47] |
| `UNBOUNDED` | constant | `pub const UNBOUNDED: u32 = u32::MAX;` | [SRC:crates/diwe/src/retrieve.rs:L63] |
| `expand_depth` | function | `pub fn expand_depth(value: u64) -> u32 {` | [AST:crates/diwe/src/retrieve.rs:L68] |
| `DocumentReader` | struct | `pub struct DocumentReader<'a>` | [SRC:crates/diwe/src/retrieve.rs:L76] |

## `crates/diwe/src/schema.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `SchemaBindings` | struct | `pub struct SchemaBindings` | [SRC:crates/diwe/src/schema.rs:L18] |
| `KeyReport` | struct | `pub struct KeyReport` | [SRC:crates/diwe/src/schema.rs:L85] |
| `ValidationRun` | struct | `pub struct ValidationRun` | [SRC:crates/diwe/src/schema.rs:L102] |
| `validate_documents` | function | `pub fn validate_documents(config: &Configuration, graph: &Graph, keys: &[Key]) -> Result<ValidationRun, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L108] |
| `validate_documents_against_file` | function | `pub fn validate_documents_against_file(graph: &Graph, keys: &[Key], schema_path: &Path) -> Result<ValidationRun, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L117] |
| `explain_documents` | function | `pub fn explain_documents(config: &Configuration, graph: &Graph, keys: &[Key]) -> Result<String, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L163] |
| `explain_documents_against_file` | function | `pub fn explain_documents_against_file(graph: &Graph, keys: &[Key], schema_path: &Path) -> Result<String, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L189] |
| `render_reports_text` | function | `pub fn render_reports_text(reports: &[KeyReport]) -> String {` | [AST:crates/diwe/src/schema.rs:L225] |
| `pending_from_changes` | function | `pub fn pending_from_changes(changes: &Changes) -> Vec<(Key, String)> {` | [AST:crates/diwe/src/schema.rs:L246] |
| `validate_pending_documents` | function | `pub fn validate_pending_documents(config: &Configuration, docs: &[(Key, String)]) -> Result<ValidationRun, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L255] |
| `validate_pending_documents_in` | function | `pub fn validate_pending_documents_in(dir: &Path, config: &Configuration, docs: &[(Key, String)]) -> Result<ValidationRun, Vec<String>> {` | [AST:crates/diwe/src/schema.rs:L263] |

## `crates/iwe/src/filter_args.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `KeyDepth` | struct | `pub struct KeyDepth` | [SRC:crates/iwe/src/filter_args.rs:L9] |
| `FilterArgs` | struct | `pub struct FilterArgs` | [SRC:crates/iwe/src/filter_args.rs:L47] |

## `crates/iwe/src/init.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `IWE_MARKER` | constant | `pub const IWE_MARKER: &str = ".iwe";` | [SRC:crates/iwe/src/init.rs:L28] |
| `CONFIG_FILE_NAME` | constant | `pub const CONFIG_FILE_NAME: &str = "config.toml";` | [SRC:crates/iwe/src/init.rs:L29] |
| `EXIT_OK` | constant | `pub const EXIT_OK: i32 = 0;` | [SRC:crates/iwe/src/init.rs:L31] |
| `EXIT_ERROR` | constant | `pub const EXIT_ERROR: i32 = 1;` | [SRC:crates/iwe/src/init.rs:L32] |
| `EXIT_ALREADY_INITIALIZED` | constant | `pub const EXIT_ALREADY_INITIALIZED: i32 = 2;` | [SRC:crates/iwe/src/init.rs:L33] |
| `Overrides` | struct | `pub struct Overrides` | [SRC:crates/iwe/src/init.rs:L36] |
| `InitOptions` | struct | `pub struct InitOptions` | [SRC:crates/iwe/src/init.rs:L71] |
| `init_workspace` | function | `pub fn init_workspace(root: &Path, options: &InitOptions) -> i32 {` | [AST:crates/iwe/src/init.rs:L80] |
| `current_root` | function | `pub fn current_root() -> PathBuf {` | [AST:crates/iwe/src/init.rs:L367] |

## `crates/iwe/src/init/agents.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `SECTION_START` | constant | `pub const SECTION_START: &str = "<!-- iwe -->";` | [SRC:crates/iwe/src/init/agents.rs:L5] |
| `SECTION_END` | constant | `pub const SECTION_END: &str = "<!-- /iwe -->";` | [SRC:crates/iwe/src/init/agents.rs:L6] |
| `agent_instructions` | function | `pub fn agent_instructions() -> String {` | [AST:crates/iwe/src/init/agents.rs:L8] |
| `mcp_snippet` | function | `pub fn mcp_snippet() -> String {` | [AST:crates/iwe/src/init/agents.rs:L31] |
| `write_agent_instructions` | function | `pub fn write_agent_instructions(root: &Path) -> Result<String, String> {` | [AST:crates/iwe/src/init/agents.rs:L44] |
| `register_mcp` | function | `pub fn register_mcp(root: &Path) -> Result<String, String> {` | [AST:crates/iwe/src/init/agents.rs:L69] |

## `crates/iwe/src/init/writer.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `render` | function | `pub fn render(settings: &Settings) -> String {` | [AST:crates/iwe/src/init/writer.rs:L9] |
| `parse` | function | `pub fn parse(rendered: &str) -> Configuration {` | [AST:crates/iwe/src/init/writer.rs:L107] |
| `to_configuration` | function | `pub fn to_configuration(settings: &Settings) -> Configuration {` | [AST:crates/iwe/src/init/writer.rs:L111] |

## `crates/iwe/src/internal/claude/digest.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `Digest` | struct | `pub struct Digest` | [SRC:crates/iwe/src/internal/claude/digest.rs:L31] |
| `Chunk` | struct | `pub struct Chunk` | [SRC:crates/iwe/src/internal/claude/digest.rs:L36] |
| `digest_claude_chunks` | function | `pub fn digest_claude_chunks(path: &Path, from: usize, chunk_chars: usize, max_chunks: usize) -> Result<Vec<Chunk>> {` | [AST:crates/iwe/src/internal/claude/digest.rs:L43] |
| `count_user_turns` | function | `pub fn count_user_turns(path: &Path, from: usize) -> Result<usize> {` | [AST:crates/iwe/src/internal/claude/digest.rs:L95] |
| `digest_claude_transcript` | function | `pub fn digest_claude_transcript(path: &Path, from: usize, max_chars: usize) -> Result<Digest> {` | [AST:crates/iwe/src/internal/claude/digest.rs:L295] |
| `value_time` | function | `pub fn value_time(value: &Value) -> Option<chrono::DateTime<chrono::Local>> {` | [AST:crates/iwe/src/internal/claude/digest.rs:L408] |
| `value_occurred` | function | `pub fn value_occurred(value: &Value) -> Option<String> {` | [AST:crates/iwe/src/internal/claude/digest.rs:L415] |

## `crates/iwe/src/internal/claude/enable.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `STARTER_BODY` | constant | `pub const STARTER_BODY: &str = include_str!("../../../templates/claude/enable/starter.md");` | [SRC:crates/iwe/src/internal/claude/enable.rs:L12] |
| `TYPED_BODY` | constant | `pub const TYPED_BODY: &str = include_str!("../../../templates/claude/enable/typed.md");` | [SRC:crates/iwe/src/internal/claude/enable.rs:L13] |
| `EnableOptions` | struct | `pub struct EnableOptions` | [SRC:crates/iwe/src/internal/claude/enable.rs:L39] |
| `enable_memory` | function | `pub fn enable_memory(options: &EnableOptions) -> i32 {` | [AST:crates/iwe/src/internal/claude/enable.rs:L49] |

## `crates/iwe/src/internal/claude/hook/index.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `Group` | struct | `pub struct Group` | [SRC:crates/iwe/src/internal/claude/hook/index.rs:L22] |
| `injection_groups` | function | `pub fn injection_groups(store: &MemoryStore) -> Vec<Group> {` | [AST:crates/iwe/src/internal/claude/hook/index.rs:L32] |
| `render_memory_index` | function | `pub fn render_memory_index(store: &MemoryStore, current: Option<String>) -> Option<String> {` | [AST:crates/iwe/src/internal/claude/hook/index.rs:L52] |

## `crates/iwe/src/internal/claude/hook/post_tool.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `PostToolReport` | struct | `pub struct PostToolReport` | [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L17] |
| `post_tool_report` | function | `pub fn post_tool_report(payload: &HookPayload) -> Option<PostToolReport> {` | [AST:crates/iwe/src/internal/claude/hook/post_tool.rs:L22] |

## `crates/iwe/src/internal/claude/hook/store.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `HookPayload` | struct | `pub struct HookPayload` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L14] |
| `read_hook_payload` | function | `pub fn read_hook_payload() -> HookPayload {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L18] |
| `SESSION_START_SECTION` | constant | `pub const SESSION_START_SECTION: &str = "At session start";` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L61] |
| `DEFAULT_HEADING` | constant | `pub const DEFAULT_HEADING: &str = "Most recently recorded, newest first — titles and keys only:";` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L63] |
| `STARTER_KNOBS` | constant | `pub const STARTER_KNOBS: &str = "injection:\n  - { heading: \"Most recently recorded, newest first — titles and keys only:\", filter: { c...` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L65] |
| `MACHINERY_KEYS` | constant | `pub const MACHINERY_KEYS: [&str; 2] = ["MEMORY", "queries"];` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L67] |
| `machinery_exclusion` | function | `pub fn machinery_exclusion() -> Filter {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L69] |
| `Slice` | struct | `pub struct Slice` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L75] |
| `MemoryStore` | struct | `pub struct MemoryStore` | [SRC:crates/iwe/src/internal/claude/hook/store.rs:L99] |
| `enter_memory_store` | function | `pub fn enter_memory_store(cwd: Option<String>) -> Option<MemoryStore> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L105] |
| `non_empty_var` | function | `pub fn non_empty_var(name: &str) -> Option<String> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L136] |
| `project_slug` | function | `pub fn project_slug(project: &str) -> String {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L140] |
| `workspace_path_of` | function | `pub fn workspace_path_of(config: &Configuration) -> PathBuf {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L162] |
| `is_safe_id` | function | `pub fn is_safe_id(value: &str) -> bool {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L170] |
| `field_text` | function | `pub fn field_text(fields: &Mapping, name: &str) -> Option<String> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L189] |
| `field_int` | function | `pub fn field_int(fields: &Mapping, name: &str) -> Option<usize> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L197] |
| `flow_yaml` | function | `pub fn flow_yaml(value: &YamlValue) -> String {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L236] |
| `fields_at` | function | `pub fn fields_at(path: &Path) -> Option<Mapping> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L447] |
| `body_at` | function | `pub fn body_at(path: &Path) -> Option<String> {` | [AST:crates/iwe/src/internal/claude/hook/store.rs:L457] |

## `crates/iwe/src/internal/claude/policy.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `POLICY_SCHEMA` | constant | `pub const POLICY_SCHEMA: &str = include_str!("../../../templates/claude/policy.schema.yaml");` | [SRC:crates/iwe/src/internal/claude/policy.rs:L8] |
| `policy_violations` | function | `pub fn policy_violations(store: &MemoryStore) -> Result<Vec<String>, Vec<String>> {` | [AST:crates/iwe/src/internal/claude/policy.rs:L10] |
| `policy_report` | function | `pub fn policy_report(store: &MemoryStore) -> (String, bool) {` | [AST:crates/iwe/src/internal/claude/policy.rs:L41] |

## `crates/iwe/src/internal/claude/prompt.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `PROMPTS` | constant | `pub const PROMPTS: [(&str, &str); 3] = [` | [SRC:crates/iwe/src/internal/claude/prompt.rs:L3] |
| `prompt_body` | function | `pub fn prompt_body(name: &str) -> Option<&'static str> {` | [AST:crates/iwe/src/internal/claude/prompt.rs:L18] |
| `invocations` | function | `pub fn invocations(body: &str) -> Vec<String> {` | [AST:crates/iwe/src/internal/claude/prompt.rs:L25] |
| `unknown_invocations` | function | `pub fn unknown_invocations(app: &Command, body: &str) -> Vec<String> {` | [AST:crates/iwe/src/internal/claude/prompt.rs:L50] |

## `crates/iwe/src/internal/claude/record.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `STATE_DIRECTORY` | constant | `pub const STATE_DIRECTORY: &str = ".iwe/claude";` | [SRC:crates/iwe/src/internal/claude/record.rs:L8] |
| `RECORDS_DIRECTORY` | constant | `pub const RECORDS_DIRECTORY: &str = ".iwe/claude/sessions";` | [SRC:crates/iwe/src/internal/claude/record.rs:L9] |
| `REMINDED_FILE` | constant | `pub const REMINDED_FILE: &str = ".reminded";` | [SRC:crates/iwe/src/internal/claude/record.rs:L10] |
| `SessionRecord` | struct | `pub struct SessionRecord` | [SRC:crates/iwe/src/internal/claude/record.rs:L16] |
| `Capture` | struct | `pub struct Capture` | [SRC:crates/iwe/src/internal/claude/record.rs:L49] |
| `ProposalStatus` | enum | `pub enum ProposalStatus` | [SRC:crates/iwe/src/internal/claude/record.rs:L59] |
| `Proposal` | struct | `pub struct Proposal` | [SRC:crates/iwe/src/internal/claude/record.rs:L78] |
| `Settled` | struct | `pub struct Settled` | [SRC:crates/iwe/src/internal/claude/record.rs:L105] |
| `state_directory` | function | `pub fn state_directory() -> PathBuf {` | [AST:crates/iwe/src/internal/claude/record.rs:L237] |
| `records_directory` | function | `pub fn records_directory() -> PathBuf {` | [AST:crates/iwe/src/internal/claude/record.rs:L241] |
| `record_path` | function | `pub fn record_path(session: &str) -> PathBuf {` | [AST:crates/iwe/src/internal/claude/record.rs:L245] |
| `load_session_record` | function | `pub fn load_session_record(session: &str) -> Option<SessionRecord> {` | [AST:crates/iwe/src/internal/claude/record.rs:L249] |
| `save_session_record` | function | `pub fn save_session_record(record: &SessionRecord) -> bool {` | [AST:crates/iwe/src/internal/claude/record.rs:L253] |
| `all_session_records` | function | `pub fn all_session_records() -> Vec<SessionRecord> {` | [AST:crates/iwe/src/internal/claude/record.rs:L266] |
| `ensure_state_ignore` | function | `pub fn ensure_state_ignore() {` | [AST:crates/iwe/src/internal/claude/record.rs:L291] |
| `reminded_at` | function | `pub fn reminded_at() -> Option<String> {` | [AST:crates/iwe/src/internal/claude/record.rs:L300] |
| `mark_reminded` | function | `pub fn mark_reminded(now: &str) -> bool {` | [AST:crates/iwe/src/internal/claude/record.rs:L306] |

## `crates/iwe/src/internal/claude/session.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `DEFAULT_MAX_CHUNK_SIZE` | constant | `pub const DEFAULT_MAX_CHUNK_SIZE: usize = 25000;` | [SRC:crates/iwe/src/internal/claude/session.rs:L28] |
| `DEFAULT_MAX_PROPOSALS` | constant | `pub const DEFAULT_MAX_PROPOSALS: usize = 5;` | [SRC:crates/iwe/src/internal/claude/session.rs:L29] |
| `DEFAULT_REMIND_AFTER_DAYS` | constant | `pub const DEFAULT_REMIND_AFTER_DAYS: i64 = 7;` | [SRC:crates/iwe/src/internal/claude/session.rs:L30] |
| `POLICY_SECTIONS` | constant | `pub const POLICY_SECTIONS: [&str; 3] = ["What to capture", "How to write it", "Dedup and updates"];` | [SRC:crates/iwe/src/internal/claude/session.rs:L46] |
| `SessionOptions` | struct | `pub struct SessionOptions` | [SRC:crates/iwe/src/internal/claude/session.rs:L48] |
| `StageOptions` | struct | `pub struct StageOptions` | [SRC:crates/iwe/src/internal/claude/session.rs:L62] |
| `CompleteOptions` | struct | `pub struct CompleteOptions` | [SRC:crates/iwe/src/internal/claude/session.rs:L67] |
| `Backlog` | struct | `pub struct Backlog` | [SRC:crates/iwe/src/internal/claude/session.rs:L78] |
| `current_session` | function | `pub fn current_session() -> Option<String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L143] |
| `policy_problems` | function | `pub fn policy_problems(store: &MemoryStore, app: &Command) -> Vec<String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L147] |
| `legacy_knobs` | function | `pub fn legacy_knobs(store: &MemoryStore) -> Vec<String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L162] |
| `session_brief` | function | `pub fn session_brief(store: &MemoryStore, app: &Command) -> String {` | [AST:crates/iwe/src/internal/claude/session.rs:L170] |
| `session_list` | function | `pub fn session_list(options: &SessionOptions, all: bool) -> Result<String, String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L232] |
| `session_read` | function | `pub fn session_read(store: &MemoryStore, options: &SessionOptions, session: Option<&str>, from: Option<usize>, max_chars: Option<usize>) ...` | [AST:crates/iwe/src/internal/claude/session.rs:L299] |
| `session_stage` | function | `pub fn session_stage(store: &MemoryStore, options: &SessionOptions, stage: &StageOptions) -> Result<String, String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L344] |
| `session_inbox` | function | `pub fn session_inbox(session: Option<&str>) -> Result<String, String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L385] |
| `session_complete` | function | `pub fn session_complete(store: &MemoryStore, options: &SessionOptions, complete: &CompleteOptions) -> Result<String, String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L567] |
| `session_adopt` | function | `pub fn session_adopt(options: &SessionOptions, sessions: &[String]) -> Result<String, String> {` | [AST:crates/iwe/src/internal/claude/session.rs:L871] |
| `backlog_of` | function | `pub fn backlog_of(options: &SessionOptions) -> Option<Backlog> {` | [AST:crates/iwe/src/internal/claude/session.rs:L965] |
| `reminder_due` | function | `pub fn reminder_due(store: &MemoryStore) -> bool {` | [AST:crates/iwe/src/internal/claude/session.rs:L991] |
| `transcripts_directory` | function | `pub fn transcripts_directory(explicit: Option<&Path>) -> Option<PathBuf> {` | [AST:crates/iwe/src/internal/claude/session.rs:L1156] |
| `Stamps` | struct | `pub struct Stamps` | [SRC:crates/iwe/src/internal/claude/session.rs:L1260] |
| `transcript_stamps` | function | `pub fn transcript_stamps(path: &Path) -> Stamps {` | [AST:crates/iwe/src/internal/claude/session.rs:L1266] |

## `crates/iwe/src/new.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `BODY_VARIABLE` | constant | `pub const BODY_VARIABLE: &str = "body";` | [SRC:crates/iwe/src/new.rs:L20] |
| `LEGACY_BODY_VARIABLE` | constant | `pub const LEGACY_BODY_VARIABLE: &str = "content";` | [SRC:crates/iwe/src/new.rs:L21] |
| `TITLE_VARIABLE` | constant | `pub const TITLE_VARIABLE: &str = "title";` | [SRC:crates/iwe/src/new.rs:L22] |
| `RESERVED_VARIABLES` | constant | `pub const RESERVED_VARIABLES: [&str; 4] = ["slug", "today", "now", "id"];` | [SRC:crates/iwe/src/new.rs:L23] |
| `Variables` | type | `pub type Variables = BTreeMap<String, serde_yaml::Value>;` | [SRC:crates/iwe/src/new.rs:L25] |
| `IfExists` | enum | `pub enum IfExists` | [SRC:crates/iwe/src/new.rs:L28] |
| `DocumentCreator` | struct | `pub struct DocumentCreator<'a>` | [SRC:crates/iwe/src/new.rs:L43] |
| `CreateOptions` | struct | `pub struct CreateOptions` | [SRC:crates/iwe/src/new.rs:L48] |
| `ContentOptions` | struct | `pub struct ContentOptions` | [SRC:crates/iwe/src/new.rs:L57] |
| `PreparedDocument` | struct | `pub struct PreparedDocument` | [SRC:crates/iwe/src/new.rs:L63] |
| `CreatedDocument` | struct | `pub struct CreatedDocument` | [SRC:crates/iwe/src/new.rs:L69] |
| `normalize_content` | function | `pub fn normalize_content(config: &Configuration, key: &Key, content: &str) -> String {` | [AST:crates/iwe/src/new.rs:L267] |
| `write_document` | function | `pub fn write_document(prepared: &PreparedDocument) -> Result<CreatedDocument, String> {` | [AST:crates/iwe/src/new.rs:L286] |
| `read_stdin_if_available` | function | `pub fn read_stdin_if_available() -> String {` | [AST:crates/iwe/src/new.rs:L305] |
| `read_stdin` | function | `pub fn read_stdin() -> String {` | [AST:crates/iwe/src/new.rs:L315] |

## `crates/iwe/src/projection_args.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `parse_projection_replace` | function | `pub fn parse_projection_replace(s: &str) -> Result<Projection, String> {` | [AST:crates/iwe/src/projection_args.rs:L5] |
| `parse_projection_extend` | function | `pub fn parse_projection_extend(s: &str) -> Result<Projection, String> {` | [AST:crates/iwe/src/projection_args.rs:L9] |
| `unused_warn` | function | `pub fn unused_warn() -> Mapping {` | [AST:crates/iwe/src/projection_args.rs:L13] |

## `crates/iwe/src/render.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `RetrieveRenderer` | struct | `pub struct RetrieveRenderer<'a>` | [SRC:crates/iwe/src/render.rs:L31] |
| `FindBlockRenderer` | struct | `pub struct FindBlockRenderer<'a>` | [SRC:crates/iwe/src/render.rs:L75] |

## `crates/iwe/src/schema.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `render_schema` | function | `pub fn render_schema(fields: &[FieldSchema]) -> String {` | [AST:crates/iwe/src/schema.rs:L34] |

## `crates/iwe/src/stats.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `render_stats` | function | `pub fn render_stats(stats: &GraphStatistics) -> String {` | [AST:crates/iwe/src/stats.rs:L7] |

## `crates/iwec/src/lib.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `KeyDepthParam` | enum | `pub enum KeyDepthParam` | [SRC:crates/iwec/src/lib.rs:L131] |
| `SelectorParams` | struct | `pub struct SelectorParams` | [SRC:crates/iwec/src/lib.rs:L153] |
| `FindParams` | struct | `pub struct FindParams` | [SRC:crates/iwec/src/lib.rs:L208] |
| `ExpandParams` | struct | `pub struct ExpandParams` | [SRC:crates/iwec/src/lib.rs:L278] |
| `RetrieveParams` | struct | `pub struct RetrieveParams` | [SRC:crates/iwec/src/lib.rs:L292] |
| `TreeParams` | struct | `pub struct TreeParams` | [SRC:crates/iwec/src/lib.rs:L405] |
| `StatsParams` | struct | `pub struct StatsParams` | [SRC:crates/iwec/src/lib.rs:L424] |
| `SquashParams` | struct | `pub struct SquashParams` | [SRC:crates/iwec/src/lib.rs:L432] |
| `CreateIfExists` | enum | `pub enum CreateIfExists` | [SRC:crates/iwec/src/lib.rs:L441] |
| `CreateParams` | struct | `pub struct CreateParams` | [SRC:crates/iwec/src/lib.rs:L447] |
| `UpdateParams` | struct | `pub struct UpdateParams` | [SRC:crates/iwec/src/lib.rs:L471] |
| `DeleteParams` | struct | `pub struct DeleteParams` | [SRC:crates/iwec/src/lib.rs:L479] |
| `QueryKind` | enum | `pub enum QueryKind` | [SRC:crates/iwec/src/lib.rs:L488] |
| `QueryParams` | struct | `pub struct QueryParams` | [SRC:crates/iwec/src/lib.rs:L507] |
| `RenameParams` | struct | `pub struct RenameParams` | [SRC:crates/iwec/src/lib.rs:L535] |
| `ExtractParams` | struct | `pub struct ExtractParams` | [SRC:crates/iwec/src/lib.rs:L582] |
| `InlineParams` | struct | `pub struct InlineParams` | [SRC:crates/iwec/src/lib.rs:L598] |
| `AttachParams` | struct | `pub struct AttachParams` | [SRC:crates/iwec/src/lib.rs:L629] |
| `ReviewPromptArgs` | struct | `pub struct ReviewPromptArgs` | [SRC:crates/iwec/src/lib.rs:L739] |
| `RefactorPromptArgs` | struct | `pub struct RefactorPromptArgs` | [SRC:crates/iwec/src/lib.rs:L745] |
| `IweServer` | struct | `pub struct IweServer` | [SRC:crates/iwec/src/lib.rs:L751] |

## `crates/iwec/src/watcher.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `start` | function | `pub fn start(graph: Arc<Mutex<Graph>>, base_path: PathBuf, format: Format) {` | [AST:crates/iwec/src/watcher.rs:L38] |
| `start_polling` | function | `pub fn start_polling(graph: Arc<Mutex<Graph>>, base_path: PathBuf, format: Format, interval: Duration) {` | [AST:crates/iwec/src/watcher.rs:L47] |

## `crates/iwes/src/lib.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `ServerParams` | struct | `pub struct ServerParams` | [SRC:crates/iwes/src/lib.rs:L19] |
| `main_loop` | function | `pub fn main_loop(connection: Connection, params: ServerParams) -> Result<()> {` | [AST:crates/iwes/src/lib.rs:L31] |

## `crates/iwes/src/router.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `LspClient` | enum | `pub enum LspClient` | [SRC:crates/iwes/src/router.rs:L34] |
| `ServerConfig` | struct | `pub struct ServerConfig` | [SRC:crates/iwes/src/router.rs:L39] |
| `Router` | struct | `pub struct Router` | [SRC:crates/iwes/src/router.rs:L49] |

## `crates/iwes/src/router/server/actions.rs`

| Export | Kind | Declaration | Citation |
|---|---|---|---|
| `ActionContext` | trait | `pub trait ActionContext` | [SRC:crates/iwes/src/router/server/actions.rs:L41] |
| `Action` | struct | `pub struct Action` | [SRC:crates/iwes/src/router/server/actions.rs:L65] |
| `Position` | struct | `pub struct Position` | [SRC:crates/iwes/src/router/server/actions.rs:L73] |
| `TextRange` | struct | `pub struct TextRange` | [SRC:crates/iwes/src/router/server/actions.rs:L79] |
| `Change` | enum | `pub enum Change` | [SRC:crates/iwes/src/router/server/actions.rs:L84] |
| `Changes` | type | `pub type Changes = Vec<Change>;` | [SRC:crates/iwes/src/router/server/actions.rs:L90] |
| `Create` | struct | `pub struct Create` | [SRC:crates/iwes/src/router/server/actions.rs:L92] |
| `Update` | struct | `pub struct Update` | [SRC:crates/iwes/src/router/server/actions.rs:L96] |
| `Remove` | struct | `pub struct Remove` | [SRC:crates/iwes/src/router/server/actions.rs:L101] |
| `ActionProvider` | trait | `pub trait ActionProvider` | [SRC:crates/iwes/src/router/server/actions.rs:L152] |
| `ActionEnum` | enum | `pub enum ActionEnum` | [SRC:crates/iwes/src/router/server/actions.rs:L168] |
| `identifier_to_action_kind` | function | `pub fn identifier_to_action_kind(identifier: String) -> CodeActionKind {` | [AST:crates/iwes/src/router/server/actions.rs:L245] |
| `all_actions` | function | `pub fn all_actions() -> Vec<ActionEnum> {` | [AST:crates/iwes/src/router/server/actions.rs:L254] |
| `all_action_types` | function | `pub fn all_action_types(configuration: &Configuration) -> Vec<ActionEnum> {` | [AST:crates/iwes/src/router/server/actions.rs:L262] |
| `into_lsp_changes` | function | `pub fn into_lsp_changes(liwe_changes: liwe::operations::Changes) -> Changes {` | [AST:crates/iwes/src/router/server/actions.rs:L369] |
