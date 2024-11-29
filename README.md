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
Requires a commit ref (commit hash or tag) which can be found in the project, and the path within the repo to the bill of materials.

#### ProjectPart & ProjectPartFootprintRef

Upon `sync`ing (described below), the parts represented on the bill of materials will be associated to the project.
Each footprint ref (e.g. `R12` and `C3`) that appears in the bill of materials will be represented.

#### ImplicitProjectPart

Sometimes there are parts which don't appear on the bill of materials but that will be included in the final project. An example is the knobs are added to the potentiometer, and the bezels for the LEDs. They're not electrical components, but they are needed for a complete build.

Parts like these can be associated to a given `Package` and will be included in as a `ProjectPart` when the bill of materials for a project version is `sync`ed.

#### ProjectBuild

Represents a manufacturing run of a project version.
Specify the number of instances of the project version that you will build.

When `cleared` (described below), the parts needed to build the lot will be reserved from the inventory.
When `completed` these reservations will be utilized.

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
- make BOM accessible from the clear to build screen
- Clear to build should remove any prior shortfalls
- Picking order/picking aide (inventory locations?)
- Generate vendor order objects from clear to build page
- Generate shopping carts from vendor orders (may have to introspect on how to add items to cart in Tayda with Charlesproxy)


- Start designing frontend!
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
