# Changelog
Changes to this project will be documented in this file.

## [Unreleased]
### Added
### Changed
### Removed
### Fixed

## [0.0.2]
### Added
- "optional" project parts can be marked as `excluded` in project builds
- "equivalent" parts. Parts may be marked as `equivalent_to` another part.
- Classes for predicting part shortages.
- Add "substitute part" to project build parts, this isn't the same as "equivalent to" (for parts).

### Fixed
- Bill of materials link in project version page
- Fixes to test_project
- Edge case which caused crashes when bill of materials specified a non-existant vendor part (non-Mouser)


## [0.0.1]
- Initial release with:
  - Parts
  - Inventory
  - Vendors
  - Projects
  - Clear to build functionality