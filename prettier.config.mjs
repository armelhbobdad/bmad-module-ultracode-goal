export default {
  $schema: 'https://json.schemastore.org/prettierrc',
  printWidth: 140,
  tabWidth: 2,
  useTabs: false,
  semi: true,
  singleQuote: true,
  trailingComma: 'all',
  bracketSpacing: true,
  arrowParens: 'always',
  // 'auto' tolerates whatever line endings git produces in the working tree
  // (LF on POSIX, possibly CRLF on Windows checkouts without the .gitattributes
  // normalization yet applied). Repo storage is enforced LF via .gitattributes,
  // so this only affects the local working copy — no committed CRLF leakage.
  endOfLine: 'auto',
  proseWrap: 'preserve',
  overrides: [
    {
      files: ['*.md'],
      options: { proseWrap: 'preserve' },
    },
    {
      files: ['*.yaml'],
      options: { singleQuote: false },
    },
    {
      files: ['*.json', '*.jsonc'],
      options: { singleQuote: false },
    },
    {
      files: ['*.cjs'],
      options: { parser: 'babel' },
    },
  ],
  plugins: ['prettier-plugin-packagejson'],
};
