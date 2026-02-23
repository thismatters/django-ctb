import datetime

import dramatiq
import pytest
from django.utils import timezone

from django_ctb import models as m


@pytest.fixture
def broker():
    broker = dramatiq.get_broker()
    broker.flush_all()
    return broker


@pytest.fixture
def worker(broker):
    worker = dramatiq.Worker(broker, worker_timeout=100)
    worker.start()
    yield worker
    worker.stop()


@pytest.fixture
def vendor_factory(db):
    lines = []

    def _factory(*, name="test vendor", base_url="https://testvend.or"):
        line = m.Vendor.objects.create(name=name, base_url=base_url)
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def vendor(vendor_factory):
    return vendor_factory()


@pytest.fixture
def vendor_mouser(vendor_factory):
    return vendor_factory(name="Mouser", base_url="https://www.mouser.com")


@pytest.fixture
def footprint(db):
    footprint = m.Footprint.objects.create(name="Test Footprint")
    yield footprint
    footprint.delete()


@pytest.fixture
def package(db, footprint):
    package = m.Package.objects.create(
        technology=m.Package.Technology.THROUGH_HOLE,
        name="Test Package",
    )
    package.footprints.add(footprint)
    yield package
    package.delete()


@pytest.fixture
def part_factory(db, package):
    parts = []

    def _factory(*, name, symbol, **kwargs):
        part = m.Part.objects.create(
            name=name, symbol=symbol, package=package, **kwargs
        )
        parts.append(part)
        return part

    yield _factory
    [p.delete() for p in parts]


@pytest.fixture
def part(db, part_factory):
    return part_factory(name="Test Part", symbol="T")


@pytest.fixture
def part_queryset(db, part):
    return m.Part.objects.filter(id=part.id)


@pytest.fixture
def implicit_project_part_factory(db, part_factory, package):
    implicit_project_parts = []

    def _factory(*, part, quantity=1, for_package=package):
        implicit_project_part = m.ImplicitProjectPart.objects.create(
            for_package=for_package,
            part=part,
            quantity=quantity,
        )
        implicit_project_parts.append(implicit_project_part)
        return implicit_project_part

    yield _factory
    [ipp.delete() for ipp in implicit_project_parts]


@pytest.fixture
def vendor_part_factory(db, part_factory, vendor):
    parts = []

    def _factory(
        *,
        part,
        vendor=vendor,
        item_number="test-item-number",
        cost=0.01,
        volume=12,
        url_path="/best-part",
    ):
        part = m.VendorPart.objects.create(
            vendor=vendor,
            part=part,
            item_number=item_number,
            cost=cost,
            volume=volume,
            url_path=url_path,
        )
        parts.append(part)
        return part

    yield _factory
    [p.delete() for p in parts]


@pytest.fixture
def vendor_part(db, part, vendor_part_factory):
    return vendor_part_factory(part=part)


@pytest.fixture
def vendor_part_mouser(db, part, vendor_mouser, vendor_part_factory):
    return vendor_part_factory(part=part, vendor=vendor_mouser)


@pytest.fixture
def inventory(db):
    inventory = m.Inventory.objects.create(name="Test inventory")
    yield inventory
    inventory.delete()


@pytest.fixture
def inventory_line_factory(db, inventory, part):
    lines = []

    def _factory(*, part=part, quantity, is_deprioritized=False):
        line = m.InventoryLine.objects.create(
            inventory=inventory,
            part=part,
            quantity=quantity,
            is_deprioritized=is_deprioritized,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def inventory_line(inventory_line_factory):
    return inventory_line_factory(quantity=20)


@pytest.fixture
def project(db):
    project = m.Project.objects.create(
        name="Test Project",
        git_server=m.Project.GitServer.GITHUB,
        git_user="fake",
        git_repo="fake",
    )
    yield project
    project.delete()


@pytest.fixture
def project_version_factory(db, project):
    lines = []

    def _factory(*, project=project):
        line = m.ProjectVersion.objects.create(
            project=project,
            revision=0,
            commit_ref="v0",
            bom_path="nested/deep/test.csv",
            pcb_cost=42.69,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def project_version(db, project_version_factory):
    return project_version_factory()


@pytest.fixture
def project_part_factory(db, part_factory, part, project_version):
    parts = []

    def _factory(
        *,
        part=part,
        project_version=project_version,
        line_number=1,
        quantity=2,
        is_implicit=False,
        is_optional=False,
    ):
        part = m.ProjectPart.objects.create(
            part=part,
            project_version=project_version,
            line_number=line_number,
            quantity=quantity,
            is_implicit=is_implicit,
            is_optional=is_optional,
        )
        parts.append(part)
        return part

    yield _factory
    for part in parts:
        try:
            part.delete()
        except ValueError:
            pass


@pytest.fixture
def project_part(db, project_version, part, project_part_factory):
    """
    Creates a `ProjectPart` instance using `part` and `project_version`
    """
    return project_part_factory(
        part=part, project_version=project_version, line_number=1, quantity=2
    )


@pytest.fixture
def project_part_footprint_ref_factory(db, project_part):
    lines = []

    def _factory(*, project_part=project_part, footprint_ref="F0"):
        line = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part, footprint_ref=footprint_ref
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def project_build_factory(db, project_version, project_part_factory):
    lines = []

    def _factory(
        *, project_version=project_version, quantity=3, cleared=None, completed=None
    ):
        line = m.ProjectBuild.objects.create(
            project_version=project_version,
            quantity=quantity,
            cleared=cleared,
            completed=completed,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def project_build(db, project_build_factory, project_part):
    """
    Creates a `ProjectBuild` using `project_version` and populates it with
    `project_part`
    """
    return project_build_factory()


@pytest.fixture
def vendor_order(db, vendor):
    order = m.VendorOrder.objects.create(vendor=vendor, order_number="test")
    yield order
    order.delete()


@pytest.fixture
def vendor_order_line_factory(db, vendor_order, inventory, vendor_part):
    lines = []

    def _factory(*, vendor_part=vendor_part, quantity=10, cost=1):
        line = m.VendorOrderLine.objects.create(
            vendor_order=vendor_order,
            for_inventory=inventory,
            quantity=quantity,
            cost=vendor_part.cost,
            vendor_part=vendor_part,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def vendor_order_line(vendor_order_line_factory):
    return vendor_order_line_factory()


@pytest.fixture
def inventory_action_factory(
    db,
    vendor_order_line_factory,
    inventory_line,
    project_build_part_reservation_factory,
):
    lines = []

    def _factory(*, inventory_line=inventory_line, delta, days_ago=None, **kwargs):
        if days_ago is not None:
            kwargs["created"] = timezone.now() - datetime.timedelta(days=days_ago)
        line = m.InventoryAction.objects.create(
            inventory_line=inventory_line,
            delta=delta,
            **kwargs,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def project_build_part_shortage_factory(db):
    lines = []

    def _factory(*, part, quantity, project_build):
        line = m.ProjectBuildPartShortage.objects.create(
            part=part,
            quantity=quantity,
            project_build=project_build,
        )
        lines.append(line)
        return line

    yield _factory
    [line.delete() for line in lines]


@pytest.fixture
def project_build_part_reservation_factory(db, project_build, part):
    lines = []

    def _factory(*, project_build=project_build, part=part, **kwargs):
        line = m.ProjectBuildPartReservation.objects.create(
            project_build=project_build, part=part, **kwargs
        )
        lines.append(line)
        return line

    yield _factory
    for line in lines:
        try:
            line.delete()
        except ValueError:
            pass


@pytest.fixture
def project_build_part_reservation(project_build_part_reservation_factory):
    return project_build_part_reservation_factory()


# @pytest.fixture
# def project_part_footprint_ref(db, project_part):
#     footprint_ref = m.ProjectPartFootprintRef.objects.create(
#         project_part=project_part,
#         footprint_ref="F2",
#     )
#     yield footprint_ref
#     footprint_ref.delete()
