# Changelog

## [Unreleased]

### Added
- Initial release

### Changed
- Extracted `build_parser()` from `main()` so the CLI surface can be unit-tested
  without patching `sys.argv`. No behaviour change: `--help` output is
  byte-identical.
