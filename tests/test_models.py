from decimal import Decimal

import pytest


class TestPartModel:
    def test_unit_cost_no_vendor(self, part):
        assert part.unit_cost == 0

    def test_unit_cost(self, vendor_part):
        assert vendor_part.part.unit_cost == Decimal("0.0100")


class TestProjectVersionModel:
    def test_pcb_unit_cost_no_cost(self, project_version):
        project_version.pcb_cost = None
        project_version.save()
        assert project_version.pcb_unit_cost == 0

    def test_pcb_unit_cost(self, project_version):
        assert project_version.pcb_unit_cost == pytest.approx(14.23)

    def test_total_cost(self, project_version, project_part_factory, vendor_part):
        project_part_factory(vendor_part.part, project_version, quantity=102)
        print(project_version.project_parts.all()[0].quantity)
        print(project_version.project_parts.all()[0].part.unit_cost)
        project_version.refresh_from_db()
        assert float(project_version.total_cost) == pytest.approx(15.25)
