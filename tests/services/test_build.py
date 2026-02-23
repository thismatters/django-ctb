from unittest.mock import Mock

import pytest
from django.utils import timezone

from django_ctb import models as m
from django_ctb import services as s
from django_ctb.exceptions import InsufficientInventory


class TestPartSatisfactionManager:
    """
    :feature: Part Satisfaction is responsive to stock of Parts
    """

    def test_part_satisfaction_no_inventory(self, part, project_part, project_build):
        """
        :scenario: Part Satisfaction indicates missing stock for Project
                   Parts

        | GIVEN a part exists
        | AND there is no inventory line for the part
        | WHEN the part satisfaction ensure reservation process is run targeting
          that part
        | THEN no inventory line will be used in fulfillment
        | AND an InsufficientInventory exception will be raised with the
          unfilfilled need
        """
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        assert satisfaction.needed == 6
        assert satisfaction.unfulfilled == 6
        assert satisfaction.project_parts == [project_part]
        with pytest.raises(InsufficientInventory) as exc:
            satisfaction.ensure_reservation()
        assert exc.value.shortages[0].quantity == 6

    def test_part_satisfaction_insufficient_inventory(
        self, part, inventory_line_factory, project_part, project_build
    ):
        """
        :scenario: Part Satisfaction indicates insufficient stock for Project
                   Parts

        | GIVEN a part exists
        | AND the given part has an inventory line with insufficient stock
        | WHEN the part satisfaction ensure reservation process is run targeting
          that part
        | THEN the inventory line is used for fulfillment
        | AND an InsufficientInventory exception will be raised with the
          unfilfilled need
        | AND no reservation will be created
        | AND no inventory action will be created
        """
        initial_inventory_count = m.InventoryAction.objects.all().count()
        initial_reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        _line = inventory_line_factory(part=part, quantity=1)
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        with pytest.raises(InsufficientInventory) as exc:
            satisfaction.ensure_reservation()
        assert exc.value.shortages[0].quantity == 5
        assert initial_inventory_count == m.InventoryAction.objects.all().count()
        assert (
            initial_reservation_count
            == m.ProjectBuildPartReservation.objects.all().count()
        )

    def test_part_satisfaction_sufficient_inventory(
        self, part, inventory_line_factory, project_part, project_build
    ):
        """
        :scenario: Part Satisfaction indicates sufficient stock for Project
                   Parts

        | GIVEN a part exists
        | AND the given part has two inventory lines with stock
        | WHEN the part satisfaction ensure reservation process is run
          targeting the part
        | THEN the inventory line with the least stock is selected for
          inventory action
        """
        inventory_line_factory(part=part, quantity=20)
        _line = inventory_line_factory(part=part, quantity=10)
        inventory_line_factory(part=part, quantity=30)
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        reservation = satisfaction.ensure_reservation()
        assert reservation.inventory_actions.all().count() == 1
        assert reservation.inventory_actions.all()[0].inventory_line == _line
        assert reservation.inventory_actions.all()[0].delta == -6
        reservation.inventory_actions.all().delete()

    def test_part_satisfaction_sufficient_inventory_split(
        self, part, inventory_line_factory, project_part, project_build
    ):
        """
        :scenario: Part Satisfaction will utilize stock from more than one
                   Inventory Line

        | GIVEN a part exists
        | AND the given part has more than one inventory line with stock
        | AND one of the inventory lines does not have enough stock for the
          project
        | WHEN the part satisfaction ensure reservation process is run
          targeting the part
        | THEN the inventory line with the least stock is used for fulfillment
          first
        | AND the inventory line with the next least stock is used for the
          remainder
        """
        _other_line = inventory_line_factory(part=part, quantity=20)
        _line = inventory_line_factory(part=part, quantity=4)
        inventory_line_factory(part=part, quantity=30)
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        reservation = satisfaction.ensure_reservation()
        assert reservation.inventory_actions.all().count() == 2
        assert reservation.inventory_actions.all()[0].inventory_line == _line
        assert reservation.inventory_actions.all()[0].delta == -4
        assert reservation.inventory_actions.all()[1].inventory_line == _other_line
        assert reservation.inventory_actions.all()[1].delta == -2
        reservation.inventory_actions.all().delete()

    def test_part_satisfaction_sufficient_inventory_split_refund(
        self,
        part,
        inventory_line_factory,
        project_part,
        project_build,
        inventory_action_factory,
        project_build_part_reservation,
    ):
        """
        :scenario: Part Satisfaction will return stock to more than one
                   Inventory Line

        | GIVEN a project build part reservation exists
        | AND the given reservation has more than one inventory action
          associated
        | AND the number of needed parts has been reduced for the build
        | WHEN the part satisfaction ensure reservation process is run
          targeting the part
        | THEN the inventory action for the inventory line with the most
          remaining stock will be refunded
        | AND the inventory action for the inventory line with the next most
          remaining stock will be refunded (and so on)
        | AND in the case of ties, the inventory action with the largest delta
          will be refunded
        """
        _line = inventory_line_factory(part=part, quantity=0)
        inventory_action_factory(
            inventory_line=_line,
            delta=-4,
            reservation=project_build_part_reservation,
        )
        _other_line = inventory_line_factory(part=part, quantity=0)
        inventory_action_factory(
            inventory_line=_other_line,
            delta=-6,
            reservation=project_build_part_reservation,
        )
        _big_line = inventory_line_factory(part=part, quantity=28)
        inventory_action_factory(
            inventory_line=_big_line,
            delta=-2,
            reservation=project_build_part_reservation,
        )
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        reservation = satisfaction.ensure_reservation()
        assert reservation == project_build_part_reservation
        assert reservation.inventory_actions.all().count() == 2
        _other_line.refresh_from_db()
        assert _other_line.quantity == 4
        _line.refresh_from_db()
        assert _line.quantity == 0
        _big_line.refresh_from_db()
        assert _big_line.quantity == 30
        reservation.inventory_actions.all().delete()

    def test_part_satisfaction_sufficient_inventory_deprioritized(
        self, part, inventory_line_factory, project_part, project_build
    ):
        """
        :scenario: Part Satisfaction will respect (de-)prioritization

        | GIVEN a part exists
        | AND the given part has a deprioritized inventory line with stock
        | AND the given part has an inventory line with stock
        | WHEN the part satisfaction ensure reservation process is run
        | THEN the non deprioritized inventory line will be used
        """
        inventory_line_factory(part=part, quantity=6, is_deprioritized=True)
        _prio_line = inventory_line_factory(part=part, quantity=10)
        inventory_line_factory(part=part, quantity=3, is_deprioritized=True)
        satisfaction = s.PartSatisfactionManager(part=part, project_build=project_build)
        satisfaction.add_project_part(project_part=project_part)
        reservation = satisfaction.ensure_reservation()
        assert reservation.inventory_actions.all().count() == 1
        assert reservation.inventory_actions.all()[0].inventory_line == _prio_line
        assert reservation.inventory_actions.all()[0].delta == -6
        reservation.inventory_actions.all().delete()

    def test_part_satisfaction__find_equivalent_parts(self, part_factory, part):
        """
        :scenario: Parts marked equivalent to each other will be found to an
                   arbitrary recursive depth

        | GIVEN there is a branching tree of parts equivalent to a certain part
        | WHEN the part satisfaction manager looks for equivalent parts
        | THEN the equivalent parts will be found to a configurable max depth
        """
        _all_parts = {part}
        _part = None
        for jdx in range(3):
            _part = part
            for idx in range(5):
                _part = part_factory(
                    name=f"{jdx}{idx}", symbol=f"{jdx}{idx}", equivalent_to=_part
                )
                _all_parts.add(_part)

        _not_found_part = part_factory(
            name="cantfindme", symbol="cantfindme", equivalent_to=_part
        )

        found_parts = s.PartSatisfactionManager.find_equivalent_parts(
            part=part, maxdepth=5
        )
        assert _not_found_part not in found_parts
        assert found_parts == _all_parts
        other_way = s.PartSatisfactionManager.find_equivalent_parts(
            part=_not_found_part, maxdepth=11
        )
        assert len(other_way) == 17


class TestProjectBuildServiceClearToBuild:
    """
    :feature: Project Builds will be Cleared when sufficient stock of Parts are
              reserved to cover all Project Parts
    """

    def test_clear_to_build_calls__clear_to_build(self, project_build, monkeypatch):
        """
        :scenario: Clear To Build Wrapper calls Clear To Build Process for
                   Project Builds

        | GIVEN a project build exists
        | WHEN the clear to build wrapper is called for the given project
          build
        | THEN the clear to build process is called for the given project
          build
        """
        mock_clear_to_build = Mock()
        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", mock_clear_to_build
        )
        s.ProjectBuildService().clear_to_build(project_build.pk)
        mock_clear_to_build.assert_called_once_with(project_build)

    def test_clear_to_build__no_build(self, project_build):
        """
        :scenario: Clear To Build Wrapper ignores non-extant Project Builds

        | GIVEN a project build exists
        | AND the given project build has been completed
        | WHEN the clear to build wrapper is called for the given project
          build
        | THEN an exception is raised

        """
        project_build.completed = timezone.now()
        project_build.save()

        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().clear_to_build(project_build.pk)

    def test_clear_to_build__insufficient_inventory(self, project_build, monkeypatch):
        monkeypatch.setattr(
            s.ProjectBuildService,
            "_clear_to_build",
            Mock(side_effect=InsufficientInventory(shortages=[])),
        )
        assert s.ProjectBuildService().clear_to_build(project_build.pk) == []

    def test__clear_to_build(self, project_part, project_build, inventory_line_factory):
        """
        :scenario: Inventory contains reserves stock to complete a Project
                   Build

        | GIVEN a part is used in a project
        | AND there is enough stock of the given part to complete the project
        | WHEN the project clear to build process is run
        | THEN the project will be marked as cleared
        | AND a reservation will be made for all the quantity of parts needed
        | AND the quantity of the parts will be deducted from the inventory for the part
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        s.ProjectBuildService()._clear_to_build(project_build)
        assert project_build.part_reservations.count() == 1
        assert len(m.InventoryAction.objects.all()) == 1
        action = m.InventoryAction.objects.all()[0]
        assert action.inventory_line == _line
        assert action.delta == -6
        assert action.order_line is None
        assert action.reservation.project_build == project_build
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10
        assert project_build.cleared is not None

    def test__clear_to_build__not(
        self, project_part, vendor_part, project_build, inventory_line_factory
    ):
        """
        :scenario: Inventory lacks sufficient stock to complete a Project Build

        | GIVEN a part is used in a project
        | AND there is not enough stock of the given part to complete the project
        | WHEN the project clear to build process is run
        | THEN the project will not be marked clear to build
        | AND the part and quantity of shortfall will be persisted
        """
        _line = inventory_line_factory(part=project_part.part, quantity=1)

        with pytest.raises(InsufficientInventory):
            s.ProjectBuildService()._clear_to_build(project_build)
        assert project_build.shortfalls.all().count() == 1
        assert project_build.shortfalls.all()[0].quantity == 5
        assert project_build.shortfalls.all()[0].part == project_part.part
        project_build.refresh_from_db
        assert project_build.cleared is None

    def test__clear_to_build__accumulates_by_part(
        self, project_build, project_part_factory, inventory_line_factory, part
    ):
        """
        :scenario: Clear To Build Process combines like Project Parts when
                   reserving Parts

        | GIVEN a the same part is used as two separate project parts
        | WHEN the project clear to build process is run
        | THEN only one reservation for the part will be created
        | AND the full quantity of parts will be reserved
        """
        _line = inventory_line_factory(part=part, quantity=10)
        project_part_factory(
            project_version=project_build.project_version,
            part=part,
            quantity=1,
            line_number=2,
        )
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.delta == -9
        _line.refresh_from_db()
        assert _line.quantity == 1
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )
        _line.refresh_from_db()
        assert _line.quantity == 10

    def test__clear_to_build__excluded_part(
        self,
        project_part,
        project_build,
        project_part_factory,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        :scenario: Clear To Build Process ignores excluded Project Parts

        | GIVEN a project build marks a given part as exluded
        | WHEN the project clear to build process is run
        | THEN no reservation is made for the excluded part
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        excluded_part = part_factory(name="omitted", symbol="O")
        excluded_project_part = project_part_factory(
            part=excluded_part,
            project_version=project_build.project_version,
            line_number=2,
            quantity=1,
            is_optional=False,
        )
        project_build.excluded_project_parts.add(excluded_project_part)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.inventory_line.part == part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__equivalent_part(
        self,
        project_part,
        project_build,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        :scenario: Clear To Build Process will fall back to equivalent Parts

        | GIVEN a project uses a part which is not stocked
        | AND the given part is `equivalent_to` another part which is stocked
        | WHEN the project clear to build process is run
        | THEN the other part will be reserved
        """
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=part
        )
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.inventory_line.part == equivalent_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__equivalent_part_original_part_stocked(
        self,
        project_part,
        project_build,
        part,
        part_factory,
        inventory_line_factory,
    ):
        """
        :scenario: Clear To Build Process will prefer original Parts over
                   equivalents

        | GIVEN a project uses a part which is stocked
        | AND the given part is `equivalent_to` another part which is stocked
        | WHEN the project clear to build process is run
        | THEN the original part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=part
        )
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.inventory_line.part == part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__substitute_part(
        self, project_part, project_build, part, part_factory, inventory_line_factory
    ):
        """
        :scenario: Clear To Build Process will not use original Part when
                   substitute Part is named

        | GIVEN a project uses a part which is stocked
        | AND the project part includes a `substitute_part` which is stocked
        | WHEN the project clear to build process is run
        | THEN the other part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        substitute_part = part_factory(name="sub", symbol="S")
        project_part.substitute_part = substitute_part
        project_part.save()
        _line = inventory_line_factory(part=substitute_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.inventory_line.part == substitute_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__substitute_part_out_of_stock(
        self, project_part, project_build, part, part_factory, inventory_line_factory
    ):
        """
        :scenario: Clear To Build Process will log a shortfall when substitute
                   Part is not stocked (even when original part is stocked)

        | GIVEN a project uses a part which is stocked
        | AND the project part includes a `substitute_part` which is not stocked
        | WHEN the project clear to build process is run
        | THEN no part will be reserved
        | AND a shortfall will be created
        """
        inventory_line_factory(part=part, quantity=10)
        substitute_part = part_factory(name="sub", symbol="S")
        project_part.substitute_part = substitute_part
        project_part.save()
        _line = inventory_line_factory(part=substitute_part, quantity=0)
        with pytest.raises(InsufficientInventory):
            s.ProjectBuildService()._clear_to_build(project_build)
        assert m.ProjectBuildPartReservation.objects.count() == 0
        assert m.ProjectBuildPartShortage.objects.count() == 1
        assert m.ProjectBuildPartShortage.objects.all()[0].part == substitute_part
        project_build.excluded_project_parts.clear()
        assert m.ProjectBuildPartShortage.objects.all().delete()

    def test__clear_to_build__equivalent_substitute_part(
        self, project_part, project_build, part, part_factory, inventory_line_factory
    ):
        """
        :scenario: Clear To Build Process will utilize equivalents to substitute
                   Parts

        | GIVEN a project uses a part which is stocked
        | AND the project part includes a `substitute_part` which is not stocked
        | AND the substitute part is `equivalent_to` another part which is stocked
        | WHEN the project clear to build process is run
        | THEN the equivalent part will be reserved
        """
        inventory_line_factory(part=part, quantity=10)
        substitute_part = part_factory(name="sub", symbol="S")
        equivalent_part = part_factory(
            name="equivalent", symbol="E", equivalent_to=substitute_part
        )
        project_part.substitute_part = substitute_part
        project_part.save()
        _line = inventory_line_factory(part=equivalent_part, quantity=10)
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 1
        action = reservations[0].inventory_actions.first()
        assert action is not None
        assert action.inventory_line.part == equivalent_part
        project_build.excluded_project_parts.clear()
        s.ProjectBuildPartReservationService().delete_reservations(
            project_build.part_reservations.all()
        )

    def test__clear_to_build__is_idempotent(
        self,
        part_factory,
        inventory_line_factory,
        inventory_action_factory,
        project_version_factory,
        project_build_factory,
        project_part_factory,
        project_build_part_reservation_factory,
    ):
        """
        :scenario: Clear To Build Process will not duplicate reservations upon
                   additional executions

        | GIVEN a project build has been cleared
        | WHEN the project clear to build process is run
        | THEN no new reservations will be created
        | AND no new inventory actions will be created
        | AND no inventory lines will be altered
        """

        project_version = project_version_factory()
        project_build = project_build_factory(
            project_version=project_version, quantity=1
        )

        def _factory(idx, line_quantity=100, action_delta=-9):
            part = part_factory(name=str(idx), symbol=str(idx))
            project_part_factory(
                part=part,
                line_number=idx,
                quantity=action_delta * -1,
                project_version=project_version,
            )
            reservation = project_build_part_reservation_factory(
                part=part, project_build=project_build
            )
            line = inventory_line_factory(part=part, quantity=line_quantity)
            action = inventory_action_factory(
                inventory_line=line,
                delta=action_delta,
                reservation=reservation,
            )
            return reservation, line, action

        factory_output = []
        for idx in range(10):
            factory_output.append(_factory(idx=idx))

        reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        actions_count = m.InventoryAction.objects.all().count()
        _reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert list(list(zip(*factory_output))[0]) == _reservations
        assert actions_count == m.InventoryAction.objects.all().count()
        assert reservation_count == m.ProjectBuildPartReservation.objects.all().count()
        for _, inventory_line, action in factory_output:
            inventory_line.refresh_from_db()
            assert action.delta == -9
            assert inventory_line.quantity == 100

    def test__clear_to_build__is_idempotent__removes_part(
        self,
        part_factory,
        inventory_line_factory,
        inventory_action_factory,
        project_version_factory,
        project_build_factory,
        project_part_factory,
        project_build_part_reservation_factory,
    ):
        """
        :scenario: Clear To Build Process will remove reservations on
                   subsequent executions when the part is no longer needed

        | GIVEN a project build has been cleared
        | AND a project part has been removed from the project version
        | WHEN the project clear to build process is run
        | THEN the reservation for the removed project part will be deleted
        | AND the inventory action for the deleted reservation will be deleted
        | AND the inventory line will be credited
        | AND no other inventory actions will be created
        | AND no other inventory lines will be altered
        """

        project_version = project_version_factory()
        project_build = project_build_factory(
            project_version=project_version, quantity=1
        )

        def _factory(idx, line_quantity=100, action_delta=-9):
            part = part_factory(name=str(idx), symbol=str(idx))
            project_part = project_part_factory(
                part=part,
                line_number=idx,
                quantity=action_delta * -1,
                project_version=project_version,
            )
            reservation = project_build_part_reservation_factory(
                part=part, project_build=project_build
            )
            line = inventory_line_factory(part=part, quantity=line_quantity)
            action = inventory_action_factory(
                inventory_line=line,
                delta=action_delta,
                reservation=reservation,
            )
            return reservation, line, action, project_part

        factory_output = []
        for idx in range(10):
            factory_output.append(_factory(idx=idx))

        factory_output[0][3].delete()

        reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        actions_count = m.InventoryAction.objects.all().count()
        _reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert list(list(zip(*factory_output))[0])[1:] == _reservations
        assert actions_count == m.InventoryAction.objects.all().count() + 1
        assert (
            reservation_count == m.ProjectBuildPartReservation.objects.all().count() + 1
        )
        for _, inventory_line, action, _ in factory_output[1:]:
            inventory_line.refresh_from_db()
            assert action.delta == -9
            assert inventory_line.quantity == 100
        factory_output[0][1].refresh_from_db()
        assert factory_output[0][1].quantity == 109

    def test__clear_to_build__is_idempotent__adds_part(
        self,
        part_factory,
        inventory_line_factory,
        inventory_action_factory,
        project_version_factory,
        project_build_factory,
        project_part_factory,
        project_build_part_reservation_factory,
    ):
        """
        :scenario: Clear To Build Process will add new reservations on
                   subsequent executions when a part is added newly

        | GIVEN a project build has been cleared
        | AND a project part has been added to the project version
        | WHEN the project clear to build process is run
        | THEN a reservation for the added project part will be created
        | AND an inventory action for the created reservation will be created
        | AND the inventory line will be debited
        | AND no other inventory actions will be created
        | AND no other inventory lines will be altered
        """

        project_version = project_version_factory()
        project_build = project_build_factory(
            project_version=project_version, quantity=1
        )

        def _factory(idx, line_quantity=100, action_delta=-9):
            part = part_factory(name=str(idx), symbol=str(idx))
            project_part = project_part_factory(
                part=part,
                line_number=idx,
                quantity=action_delta * -1,
                project_version=project_version,
            )
            reservation = project_build_part_reservation_factory(
                part=part, project_build=project_build
            )
            line = inventory_line_factory(part=part, quantity=line_quantity)
            action = inventory_action_factory(
                inventory_line=line,
                delta=action_delta,
                reservation=reservation,
            )
            return reservation, line, action, project_part

        factory_output = []
        for idx in range(10):
            factory_output.append(_factory(idx=idx))

        part = part_factory(name="new", symbol="new")
        project_part_factory(
            part=part,
            line_number=11,
            quantity=9,
            project_version=project_version,
        )
        line = inventory_line_factory(part=part, quantity=100)

        reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        actions_count = m.InventoryAction.objects.all().count()
        _reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert list(list(zip(*factory_output))[0]) == _reservations[:-1]
        assert actions_count + 1 == m.InventoryAction.objects.all().count()
        assert (
            reservation_count + 1 == m.ProjectBuildPartReservation.objects.all().count()
        )
        _reservations[-1].inventory_actions.all().count() == 1
        _reservations[-1].inventory_actions.all()[0].delta == -9
        _reservations[-1].inventory_actions.all()[0].inventory_line == line
        _reservations[-1].inventory_actions.all()[0].inventory_line.quantity == 91
        _reservations[-1].inventory_actions.all().delete()
        for _, inventory_line, action, _ in factory_output:
            inventory_line.refresh_from_db()
            assert action.delta == -9
            assert inventory_line.quantity == 100

    def test__clear_to_build__is_idempotent__has_shortage_ongoing(
        self,
        part_factory,
        inventory_line_factory,
        inventory_action_factory,
        project_version_factory,
        project_build_factory,
        project_part_factory,
        project_build_part_shortage_factory,
    ):
        """
        :scenario: Clear To Build Process will not duplicate shortages upon
                   additional executions

        | GIVEN a project build has been cleared
        | AND shortages were found
        | AND shortages still exist
        | WHEN the project clear to build process is run
        | THEN no new shortages will be created
        | AND no new inventory actions will be created
        | AND no inventory lines will be altered
        """

        project_version = project_version_factory()
        project_build = project_build_factory(
            project_version=project_version, quantity=1
        )

        def _factory(idx, line_quantity=5, action_delta=-9):
            part = part_factory(name=str(idx), symbol=str(idx))
            project_part_factory(
                part=part,
                line_number=idx,
                quantity=action_delta * -1,
                project_version=project_version,
            )
            shortage = project_build_part_shortage_factory(
                part=part, project_build=project_build, quantity=action_delta * -1
            )
            line = inventory_line_factory(part=part, quantity=line_quantity)
            return shortage, line

        factory_output = []
        for idx in range(10):
            factory_output.append(_factory(idx=idx))

        reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        shortage_count = m.ProjectBuildPartShortage.objects.all().count()
        actions_count = m.InventoryAction.objects.all().count()
        print(list(list(zip(*factory_output))[0]))
        with pytest.raises(InsufficientInventory) as exc:
            s.ProjectBuildService()._clear_to_build(project_build)
        _shortages = exc.value.shortages
        print(_shortages)
        assert list(list(zip(*factory_output))[0]) == _shortages
        assert actions_count == m.InventoryAction.objects.all().count()
        assert shortage_count == m.ProjectBuildPartShortage.objects.all().count()
        assert reservation_count == m.ProjectBuildPartReservation.objects.all().count()
        for shortage, inv_line in factory_output:
            inv_line.refresh_from_db()
            shortage.refresh_from_db()
            assert shortage.quantity == 4
            assert inv_line.quantity == 5

    def test__clear_to_build__is_idempotent__has_shortage_resolved(
        self,
        part_factory,
        inventory_line_factory,
        inventory_action_factory,
        project_version_factory,
        project_build_factory,
        project_part_factory,
        project_build_part_shortage_factory,
    ):
        """
        :scenario: Clear To Build Process will delete shortages and create
                   reservations upon additional executions when stock has been
                   added

        | GIVEN a project build has been cleared
        | AND shortages were found
        | AND shortages no longer exist
        | WHEN the project clear to build process is run
        | THEN no new shortages will be deleted
        | AND reservations will be created
        | AND inventory actions will be created
        | AND inventory lines will be altered
        """
        project_version = project_version_factory()
        project_build = project_build_factory(
            project_version=project_version, quantity=1
        )

        def _factory(idx, line_quantity=15, action_delta=-9):
            part = part_factory(name=str(idx), symbol=str(idx))
            project_part_factory(
                part=part,
                line_number=idx,
                quantity=action_delta * -1,
                project_version=project_version,
            )
            shortage = project_build_part_shortage_factory(
                part=part, project_build=project_build, quantity=action_delta * -1
            )
            line = inventory_line_factory(part=part, quantity=line_quantity)
            return shortage, line

        factory_output = []
        for idx in range(10):
            factory_output.append(_factory(idx=idx))

        reservation_count = m.ProjectBuildPartReservation.objects.all().count()
        assert reservation_count == 0
        shortage_count = m.ProjectBuildPartShortage.objects.all().count()
        assert shortage_count == 10
        actions_count = m.InventoryAction.objects.all().count()
        assert actions_count == 0
        reservations = s.ProjectBuildService()._clear_to_build(project_build)
        assert len(reservations) == 10

        assert 10 == m.InventoryAction.objects.all().count()
        assert 0 == m.ProjectBuildPartShortage.objects.all().count()
        assert 10 == m.ProjectBuildPartReservation.objects.all().count()
        for _, inv_line in factory_output:
            inv_line.refresh_from_db()
            assert inv_line.quantity == 6
        m.InventoryAction.objects.all().delete()


class TestProjectBuildServiceCompletion:
    """
    :feature: Project Builds can be completed
    """

    def test__complete_build(
        self, project_part, project_build, inventory_line_factory, monkeypatch
    ):
        """
        :scenario: Cleared Project Build can be completed and Part Reservations
                   will be utilized

        | GIVEN a project build has been cleared
        | AND part reservations made
        | WHEN the complete build action is run for the project build
        | THEN the project build is marked completed
        | AND the part reservations are marked utilized
        """
        _line = inventory_line_factory(part=project_part.part, quantity=10)
        project_build.cleared = timezone.now()
        project_build.save()
        reservation = m.ProjectBuildPartReservation.objects.create(
            part=project_part.part,
            project_build=project_build,
        )
        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", Mock(return_value=[reservation])
        )
        s.ProjectBuildService()._complete_build(project_build)
        reservation.refresh_from_db()
        project_build.refresh_from_db()
        assert reservation.utilized is not None
        assert project_build.completed is not None
        reservation.delete()

    def test__complete_build__no_build(
        self, project_part, project_build, inventory_line_factory, monkeypatch
    ):
        """
        :scenario: Project Build must be cleared before it can be completed

        | GIVEN a project build has not been cleared
        | AND there is not sufficient inventory to build the project
        | WHEN the complete build action is run for the project build
        | THEN the clear to build action is run for the project build
        | AND the project is not marked completed
        """
        _line = inventory_line_factory(part=project_part.part, quantity=2)
        mock_clear_to_build = Mock(side_effect=InsufficientInventory(shortages=[]))
        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", mock_clear_to_build
        )
        with pytest.raises(InsufficientInventory):
            s.ProjectBuildService()._complete_build(project_build)
        project_build.refresh_from_db()
        assert project_build.completed is None
        mock_clear_to_build.assert_called_once_with(project_build)

    def test__complete_build__already_completed(self, project_build, monkeypatch):
        """
        :scenario: An already completed Project Build cannot be completed again

        | GIVEN a project build is marked completed
        | WHEN the complete build action is run for the project build
        | THEN no operation is run on the project build
        """
        project_build.completed = timezone.now()
        project_build.save()
        mock_clear_to_build = Mock()
        monkeypatch.setattr(
            s.ProjectBuildService, "_clear_to_build", mock_clear_to_build
        )

        s.ProjectBuildService()._complete_build(project_build)
        mock_clear_to_build.assert_not_called()

    def test_complete_build_calls__complete_build(self, project_build, monkeypatch):
        """
        :scenario: Complete Build Wrapper calls Complete Build Process

        | WHEN the complete build wrapper is called for a cleared project build
        | THEN the complete build process is called for the project build
        """
        print(project_build)
        project_build.cleared = timezone.now()
        project_build.save()

        mock_complete_build = Mock()
        monkeypatch.setattr(
            s.ProjectBuildService, "_complete_build", mock_complete_build
        )
        s.ProjectBuildService().complete_build(project_build.pk)
        mock_complete_build.assert_called_once_with(project_build)

    def test_complete_build__bad(self, project_build, monkeypatch):
        """
        :scenario: Complete Build Wrapper raises for non-extant Project Build

        | WHEN the complete build action is called for a non existent project build
        | THEN an exception is raised
        """
        with pytest.raises(m.ProjectBuild.DoesNotExist):
            s.ProjectBuildService().complete_build(1234)


class TestProjectBuildServiceCancelation:
    """
    :feature: Incomplete Project Builds can be cancelled
    """

    def test_cancel_build_calls__cancel_build(self, project_build, monkeypatch):
        """
        :scenario: Cancel Build Wrapper calls Cancel Build Process

        | WHEN the cancel build wrapper is called for a project build
        | THEN the cancel build process is called for the project build
        """
        mock__cancel_build = Mock()
        monkeypatch.setattr(s.ProjectBuildService, "_cancel_build", mock__cancel_build)
        s.ProjectBuildService().cancel_build(project_build.pk)
        mock__cancel_build.assert_called_once_with(project_build)

    def test__cancel_build(self, project_build, inventory_line_factory, part):
        """
        :scenario: Cancelling a Project Build will remove reservations, free
                   stock, and un-clear the Project Build

        | GIVEN part reservations exist for a project build
        | WHEN the cancel build action is run for the project build
        | THEN the part reservations are deleted
        | AND the inventory lines are credited with the reservation quantities
        | AND the project build clear status is cleared
        """
        _line = inventory_line_factory(part=part, quantity=10)
        s.ProjectBuildService()._clear_to_build(project_build)
        project_build.refresh_from_db()
        assert project_build.cleared is not None
        _line.refresh_from_db()
        assert _line.quantity == 4
        s.ProjectBuildService()._cancel_build(project_build)
        _line.refresh_from_db()
        assert _line.quantity == 10
        project_build.refresh_from_db()
        assert project_build.cleared is None

    def test__cancel_build__completed(self, project_build, monkeypatch):
        """
        :scenario: Cancelling a completed Project Build will do nothing

        | GIVEN a project build has been completed
        | WHEN the cancel build action is run for the project build
        | THEN the project build completed status will be unchanged
        """

        mock_delete_reservations = Mock()
        monkeypatch.setattr(
            s.ProjectBuildPartReservationService,
            "delete_reservations",
            mock_delete_reservations,
        )
        project_build.completed = timezone.now()
        project_build.save()
        s.ProjectBuildService()._cancel_build(project_build)
        project_build.refresh_from_db()
        assert project_build.completed is not None
        mock_delete_reservations.assert_not_called()


class TestProjectBuildPartReservationService:
    def test_delete_reservation_ignores_utilitzed(
        self, project_build_part_reservation, inventory_action_factory
    ):
        inventory_action = inventory_action_factory(
            reservation=project_build_part_reservation, delta=100
        )
        project_build_part_reservation.utilized = timezone.now()
        project_build_part_reservation.save()
        s.ProjectBuildPartReservationService().delete_reservation(
            project_build_part_reservation
        )
        # this will raise an exception if it were deleted
        inventory_action.refresh_from_db()

    def test_delete_reservation(
        self, project_build_part_reservation, inventory_action_factory
    ):
        inventory_action = inventory_action_factory(
            reservation=project_build_part_reservation, delta=100
        )
        s.ProjectBuildPartReservationService().delete_reservation(
            project_build_part_reservation
        )
        with pytest.raises(m.InventoryAction.DoesNotExist):
            # this will raise an exception if it is deleted
            inventory_action.refresh_from_db()
