Django Clear To Build (ctb)
===========================
[![PyPI](https://img.shields.io/pypi/v/django-ctb?color=156741&logo=python&logoColor=ffffff&style=for-the-badge)](https://pypi.org/project/django-ctb/)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/thismatters/django-ctb/test.yml?branch=main&color=156741&label=CI&logo=github&style=for-the-badge)](https://github.com/thismatters/django-ctb/actions)
[![Codecov](https://img.shields.io/codecov/c/github/thismatters/django-ctb?color=156741&logo=codecov&logoColor=ffffff&style=for-the-badge)](https://codecov.io/gh/thismatters/django-ctb)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-ctb?color=156741&logo=python&logoColor=white&style=for-the-badge)](https://pypi.org/project/django-ctb/)
[![PyPI - Django Version](https://img.shields.io/pypi/djversions/django-ctb?color=156741&logo=django&logoColor=ffffff&style=for-the-badge)](https://pypi.org/project/django-ctb/)

`django-ctb` is a package for tracking inventory for small-scale electronics manufacturing.
It tracks parts, vendors, orders, inventories (the parts that you have on-hand), projects across several versions (and their bills of materials, including cost breakdowns), and finally provides clearance to build---indicating that your inventory of parts is sufficient to complete the project build.

This project was built to facilitate my [DIY Synth build](https://github.com/thismatters/Eurorack) and has built-in support for the [Mouser Search API](https://www.mouser.com/api-search/).
The projects themselves are printed circuit board (PCB) projects designed in [KiCAD](https://www.kicad.org/); I've leaned in to the patterns used in that software and rely on the bill of materials that it generates.
I've built this to support the patterns employed by my prototype manufacturer of choice [OSHPark](https://oshpark.com/).
This project also uses gitops patterns and relies on projects being represented as git repos (although other data sources are definitely possible if you raise an issue).

## Documentation

Work in progress...

## Installation

```
pip install django-ctb
```

## Configuration

Add `django_ctb` to your `INSTALLED_APPS` list and (optionally) create a setting for your Mouser API key:
```
INSTALLED_APPS = [
    ...
    "django_ctb",
    ...
]

CTB_MOUSER_API_KEY = os.environ.get("MOUSER_API_KEY", None)
```

## Settings

- `CTB_MOUSER_API_KEY` : API key for the [Mouser Search API](https://www.mouser.com/api-search/). Optional.


## Functionality

### Models

There are several models which comprise this package:

#### Vendor

Places where parts can be procured. E.g. Mouser

#### Part

Individual parts which are available for procurement from a vendor and will be assembled into a project. E.g. a 100 Ohm surface mount (0805) resistor, or an NPN TO-92 transistor.

The `value` attribute of the part will be matched to the `value` row on the bill of materials.

#### Package

The form factor for a part. E.g. Surface mount 0805, or TO-92.

#### Footprint

The manifestation of the part onto the printed circuit board. The footprint appears on the bill of materials, parts will be selected based in part on the footprint name match.

#### VendorPart

The representation of a part as sold by a vendor. Pricing, item numbers, url paths are stored here.

#### VendorOrder & VendorOrderLine

Individual orders (and the line items of the order) of parts from a vendor.
When orders are `fulfilled` the parts in the order will be represented as inventory lines.

#### Inventory & InventoryLine

A collection of parts on hand as represented by individual lines.

#### InventoryAction

Tracks changes to inventory lines when orders are fulfilled and when projects are built.

#### Project

A thing you are building. This is a thin model with just a name and a url to a git repo.

#### ProjectVersion

A point-in-time representation of the project.
Requires a commit ref (branch, tag, or commit hash) which exists in the repository, and the path within the repo to the bill of materials.

It is recommened that you set the `commit_ref` to the default branch for the repo until your bill of materials has stabilized, after this point a git tag is a useful placeholder for the state of a repository at a specific project version. (The author uses tags like `v0`, `v1`, etc. once manufacturing of a project version has begun.)

#### ProjectPart & ProjectPartFootprintRef

Upon `sync`ing (described below), the parts represented on the bill of materials will be associated to the project.
Each footprint ref (e.g. `R12` and `C3`) that appears in the bill of materials will be represented.

`ProjectPart` may be marked as "optional" (via the `is_optional` attribute), indicating that they may be excluded from a `ProjectBuild`. `ProjectPart` may have a `substitute_part` which, when provided, will completely replace the `part` in the clear-to-buld process (adding a `substitute_part` to an already cleared project will have no effect).

#### ImplicitProjectPart

Sometimes there are parts which don't appear on the bill of materials but that will be included in the final project. An example is the knobs are added to the potentiometer, and the bezels for the LEDs. They're not electrical components, but they are needed for a complete build.

Parts like these can be associated to a given `Package` and will be included in as a `ProjectPart` when the bill of materials for a project version is `sync`ed.

#### ProjectBuild

Represents a manufacturing run of a project version.
Specify the number of instances of the project version that you will build.

Any `ProjectPart`s which were marked "optional" may be added to the `excluded_project_parts`. When added, these project parts will not be omitted from clearing actvities.

When `cleared` (described below), the parts needed to build the lot will be reserved from the inventory.
When `completed` these reservations will be utilized.

`VendorOrder`s and lines therein can be created for any `ProjectBuild` object which has shortfalls by selecting the project build from the admin index and running the "Generate orders from shortfalls" action.

#### ProjectBuildPartShortage

When a project build cannot be `cleared` due to a lack of parts in the inventory a part shortage will be created.

#### ProjectBuildPartReservation

When a project build is cleared reservations for each part will be created.
If the build is canceled then the reservations will be disolved and the parts will be returned to the inventory.
When the build is complete the reservations are utilized and will not be recovered.

### Actions

There are some services which facilitate the function of this package, but this document will not go into detail about those.
The fundamental actions that those services provide are described below, each of these is available as a [`dramatiq` task](https://dramatiq.io/) and as an action on the model (in Django Admin):

#### Complete Order

- For each `VendorOrderLine` in the current vendor order:
  - Creates an `InventoryLineAction`,
  - Adds the ordered quantity of parts to the `InventoryLine` associated with the `Part` in the vendor order.
- Persiss the `fulfilled` time for the vendor order

#### Sync Project Version

- Reads the current project version bill of materials (BOM) from the git repo and commit associated to the `Project` and `ProjectVersion`.
- Creates `ProjectPart`s and `ProjectPartFootprintRef`s for each line on the BOM.
  - If there is are any `ImplicitProjectParts` associated to the `Part`s `Package` then a `ProjectPart` will be created for the implicit part.
  - If a BOM line cannot be matched to any part then:
    - If the BOM line has "Vendor" equal to "Mouser" and the `CTB_MOUSER_API_KEY` is set then a `Part` will be created to match the resource in the Mouser Search API wich matches the "PartNum" from the BOM line,
    - Else a `ProjectPart` will be created with a `missing_part_desription` rather than a `part` relation. This dissonance must be resolved manually by correcting the BOM or by creating a suitable `Part` and re-syncing the project version.
- Removes any old `ProjectPart`s.
- Persists the `sync` time for the project version.

#### Clear to Build

- Looks for sufficient quantity in inventory to cover the bill of materials for the project build lot.
- If sufficient quantity is found then those parts necessary are reserved from their inventory lines, and the `ProjectBuild` `cleared` time is persisted.
- Otherwise, a `ProjectBuildPartShortage` is created for each part that is short indicating lacking quantity.

#### Cancel Build

- Releases any `ProjectBuildPartReservation`s which are associated with the project build, returning that number of parts to their respective inventory lines.

#### Complete Build

- Utilizes the `ProjectBuildPartReservation`s which are associated with the project build, forever removing that number of parts from their respective inventory lines.


## Housekeeping

### TODO
- Sync version should capture the commit hash of the repo when the BOM is pulled; still respect the `commit_ref`, but provide better traceability.
- Clear to build should remove any prior shortfalls/be idempotent
- Incorporate analytics methods as actions... maybe persist top recommendations?
  - Test robustly
- Document package
  - Installation
  - Usage
  - Settings
  - [x] "features" via test docstrings
    - [x] Sphinx setup
    - [x] Add scenario names
    - [x] Fix formatting  (use line block syntax)
    - [x] Organize into features
  - UML diagrams
    - [x] models (autogen)
    - [x] sequence
      - [x] full project E2E
        - [x] BOM revision loops
        - [x] Build part subsitutions
        - [x] Vendor orders
- Document workflows -- flowcharts for:
  - Create new project
  - Figuring out what part to use for a design

- Picking order/picking aide (inventory locations?) (add arbitrary labels to all models?)
- Generate shopping carts from vendor orders (may have to introspect on how to add items to cart in Tayda with Charlesproxy)

- Start designing frontend!
  - Minimal means to create a Mouser Part (mouser part number, Symbol (e.g. "U"), Footprint)
  - Project index
    - breakdown of versions
      - BOM link
        - Sortable BOM
      - breakdown of builds
    - Repo links
  - Parts index which helps to do footprint assignment.
    - Shows appropriate name (e.g. "LED_GREEN")
    - Shows footprint
    - Shows availability
    - Commonly used parts (high number of project parts)
    - Filtering by component type, footprint, availability
    - Sortable by component value, symbol, name
    - Store links


### Processes

#### Design and Schematic Layout

As I place parts into the schematic I check:
- Whether the part is stocked, if not:
  - Revise design to use a stocked part
  - Order part
  For this I use the "Inventory Lines" index and sort by prefix and (sometimes) by footprint. If I don't see what I want to use there then I fall back to the "Parts" index again sorting by prefix. Ideally I would be able to see the quantity on hand from the parts index to avoid double searching.
- What part number to annotate onto schematic part (have to click through to "part" from "inventory line")
- What footprint to associate to schematic part (have to click through to "package" from "part")