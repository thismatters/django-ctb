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
- `substitute_part` to project build parts, this isn't the same as "equivalent to" (for parts); a substitute part will completely replace the default part listed in the project part.
- Tweaks to make data more visible across admin views:
  - VendorPart item numbers shown on inventory lines index
  - Part name to vendor part name
  - Build status to InventoryLineActionInline
- Build BOM (and link from project build index) to show part reservations for a build with:
  - links to inventory line and part
  - quantities for each part in the build
  - quantities of each part in inventory pre-build
  - projected quantities of each part after all pending and cleared builds have been completed
  - Footprint refs for each part in the build
- unittests to cover everything
- Gherkin scenarios in unittests for service code
- action for generating vendor orders from project build shortfalls
- analytics methods for projecting which parts may need to be procured based on historic past usage, current demand, and inventory levels.


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