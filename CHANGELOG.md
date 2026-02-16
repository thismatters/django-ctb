# Changelog
Changes to this project will be documented in this file.

## [Unreleased]
### Added
### Changed
### Removed
### Fixed

## [0.0.2]
### BREAKING CHANGES
- `django-enumfield` was removed as a dependency in favor of the new `models.IntegerChoices` pattern. To affect this change the migrations for this project had to be re-initialized. **YOU WILL HAVE TO RESET YOUR DATABASE TO MIGRATE FROM 0.0.1 TO 0.0.2** See steps below:
  - Dump all your existing data to a file: `python manage.py dumpdata django_ctb > data-backup.json`
  - manually verify that this is accurate!
  - Downgrade your migrations to nada: `python manage.py migrate django_ctb zero`
  - Upgrade your django-ctb version to 0.0.2 (your business!)
  - Run migrations: `python manage.py migrate django_ctb`
  - Load your datafile: `python manage.py loaddata data-backup.json`

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
### Changed
- `MOUSER_API_KEY` setting prefixed to `CTB_MOUSER_API_KEY`
- dependency management to `uv` from `pip`
- supported Python versions to 3.12 thru 3.14
- supported Django versions to 5.0 thru 6.0
### Removed
- `django-enumfield` as a dependency, switched to [IntegerChoices](https://docs.djangoproject.com/en/6.0/ref/models/fields/#field-choices-enum-types)
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