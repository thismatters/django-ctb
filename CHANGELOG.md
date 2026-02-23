# Changelog
Changes to this project will be documented in this file.

## [Unreleased]
### Added
### Changed
### Removed
### Fixed

## [0.1.0]
### DATABASE BREAKING CHANGES
- `django-enumfield` was removed as a dependency in favor of the new `models.IntegerChoices` pattern. To affect this change the migrations for this project had to be re-initialized. **YOU WILL HAVE TO RESET YOUR DATABASE TO MIGRATE FROM 0.0.1 TO 0.0.2**; I'm pretty sure there are no users for this package at this point, so I'm not sweating it too much. If you are a user with data who wants to migrate I will provide support (within reason) to facilitate the migration without data loss. Please raise an issue on the board!

### Added
- "optional" project parts can be marked as `excluded` in project builds
- "equivalent" parts. Parts may be marked as `equivalent_to` another part.
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
- action for generating vendor orders from project build shortfalls
- tracking of commit hash when project version sync occurs.
- type hints
- [test] unittests to cover everything
- [test] Gherkin scenarios in unittests for service code
- [doc] BDD Gherkin syntax features and scenarios to document test surface
- [doc] provisions to documentation generation to display gherkin syntax from docstrings. This borrows/steals from the sphinx autodoc extension extensively, replicating and abusing their (now-deprecated) class based documenters.
### Changed
- clear to build functionality to be idempotent
- `MOUSER_API_KEY` setting prefixed to `CTB_MOUSER_API_KEY`
- how project version specify git repo details; there are now separate fields for the git server, the git user, and the git repo.
- organization of services
- [proj] dependency management to `uv` from `pip`
- [proj] supported Python versions to 3.12 thru 3.14
- [proj] supported Django versions to 5.0 thru 6.0
### Removed
- `django-enumfield` as a dependency, switched to [IntegerChoices](https://docs.djangoproject.com/en/6.0/ref/models/fields/#field-choices-enum-types)
### Fixed
- Bill of materials link in project version page
- Fixes to test_project
- Edge case which caused crashes when bill of materials specified a non-extant vendor part (non-Mouser)


## [0.0.1]
- Initial release with:
  - Parts
  - Inventory
  - Vendors
  - Projects
  - Clear to build functionality