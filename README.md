Django Clear To Build (ctb)
===========================
[![PyPI](https://img.shields.io/pypi/v/django-ctb?color=156741&logo=python&logoColor=ffffff&style=for-the-badge)](https://pypi.org/project/django-ctb/)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/thismatters/django-ctb/test.yml?branch=main&color=156741&label=CI&logo=github&style=for-the-badge)](https://github.com/thismatters/django-ctb/actions)
[![Codecov](https://img.shields.io/codecov/c/github/thismatters/django-ctb?color=156741&logo=codecov&logoColor=ffffff&style=for-the-badge)](https://codecov.io/gh/thismatters/django-ctb)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-ctb?color=156741&logo=python&logoColor=white&style=for-the-badge)](https://pypi.org/project/django-ctb/)
[![PyPI - Django Version](https://img.shields.io/pypi/djversions/django-ctb?color=156741&logo=django&logoColor=ffffff&style=for-the-badge)](https://pypi.org/project/django-ctb/)
[![Read the Docs](https://img.shields.io/readthedocs/django-ctb?color=156741&logo=readthedocs&logoColor=ffffff&style=for-the-badge)](https://django-ctb.readthedocs.io/en/latest/)

A package for tracking inventory for small-scale electronics manufacturing.
It tracks parts, vendors, orders, inventories (the parts that you have on-hand), projects across several versions (and their bills of materials, including cost breakdowns), and finally provides clearance to build---indicating that your inventory of parts is sufficient to complete the project build.

This project was built to facilitate my [DIY Synth build](https://github.com/thismatters/Eurorack) and has built-in support for the [Mouser Search API](https://www.mouser.com/api-search/).
The projects themselves are printed circuit board (PCB) projects designed in [KiCAD](https://www.kicad.org/); I've leaned in to the patterns used in that software and rely on the bill of materials that it generates.
I've built this to support the patterns employed by my prototype manufacturer of choice [OSHPark](https://oshpark.com/).
This project also uses gitops patterns and relies on projects being represented as git repos (although other data sources are definitely possible if you raise an issue).

## Documentation

[See the full documentation](https://django-ctb.readthedocs.io/en/latest/)

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

CTB_MOUSER_API_KEY = "put-your-real-mouser-api-key-here-yall"
```

## Settings

- `CTB_MOUSER_API_KEY` : API key for the [Mouser Search API](https://www.mouser.com/api-search/). Optional.


## Housekeeping

### TODO v0.2.0
- associate inventory/projects to user
- Incorporate analytics methods as actions... maybe persist top recommendations?
  - Test robustly

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