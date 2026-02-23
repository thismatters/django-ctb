from unittest.mock import Mock

import pytest
import requests

from django_ctb import models as m
from django_ctb import services as s
from django_ctb.exceptions import MissingVendorPart, RefNotFoundException
from django_ctb.github.services import GithubService
from django_ctb.mouser.services import MouserPartService


class TestProjectVersionBomServiceSync:
    """
    :feature: Bills of Material are Synced to Project Versions yielding Project
              Parts, and this process can be repeated as needed
    """

    def test__sync_footprints(self, project_part):
        """
        :scenario: Footprint Refs for components will update as the BOM goes
                   through revisions by resyncing the Project Version

        | GIVEN a project_part exists which is associated with outdated footprint refs
        | WHEN _sync_footprints is run for the project part providing new footprint refs
        | THEN existing footprint references which were not provided will be deleted
        | AND existing footprint references which are provided will be retained
        | AND non-existing footprint references whic are provided will be created
        """
        _old_footprint_ref = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F2",
        )
        _old_footprint_ref3 = m.ProjectPartFootprintRef.objects.create(
            project_part=project_part,
            footprint_ref="F3",
        )
        s.ProjectVersionBomService()._sync_footprints(
            {"F1", "F3"}, project_part=project_part
        )
        with pytest.raises(m.ProjectPartFootprintRef.DoesNotExist):
            _old_footprint_ref.refresh_from_db()
        refs = m.ProjectPartFootprintRef.objects.filter(project_part=project_part)
        assert _old_footprint_ref3 in refs
        refs_list = refs.values_list("footprint_ref", flat=True)
        assert "F1" in refs_list
        assert "F3" in refs_list
        assert len(refs_list) == 2

    def test__sync_implicit_parts(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        :scenario: Implicit Project Parts will be created whenever a BOM which
                   uses a Package with implicit parts is synced, and the
                   quanitities will be appropriate

        | GIVEN a project part references a part
        | AND the given part's package is associated with an ImplicitProjectPart
        | WHEN _sync_implicit_parts is run for the project part
        | THEN a project part is created for the ImplicitProjectPart
        | AND the created project part references an appropriate quantity of parts
        | AND the created project part has the same line number as the given
          project part
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 0
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        pp.delete()

    def test__sync_implicit_parts__remove_old(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        :scenario: Implicit Project Parts will be deleted and recreated when a
                   BOM is re-synced which changes which Packages are use

        | GIVEN a BOM has been synced yielding a project part
        | AND the project part has an associated implicit project part instance
        | AND the ImplicitProjectPart definition has changed such that the
          aforementioned project part instance is no longer representing the
          correct part
        | WHEN _sync_implicit_parts is run for the yielded project part
        | THEN the old implicit part instance will be deleted
        | AND a new implicit part instance reflecting the correct part will be
          created
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        old_implicit_part = part_factory(name="old part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_implicit_project_part_instance = project_part_factory(
            project_version=project_version,
            part=old_implicit_part,
            line_number=69,
            is_implicit=True,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        # The old ImplicitProjectPart instance
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        # The new ImplicitProjectPart instance
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp.part == implicit_part
        with pytest.raises(m.ProjectPart.DoesNotExist):
            old_implicit_project_part_instance.refresh_from_db()
        pp.delete()

    def test__sync_implicit_parts__update(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        :scenario: Implicit Project Parts will be updated when a BOM is
                   re-synced which changes the quantity of components required

        | GIVEN a BOM has been synced yielding a project part
        | AND the project part has an associated implicit project part instance
        | AND the ImplicitProjectPart definitions has changed such that the
          quantity of implicit parts called for is different
        | WHEN _sync_implicit_parts is run for the yielded project part
        | THEN the old implicit part instance will be altered to reflect the
          updated quantity
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_project_part = project_part_factory(
            project_version=project_version,
            part=implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=9,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 1
        pp = m.ProjectPart.objects.filter(is_implicit=True)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp.part == implicit_part
        assert pp == old_project_part
        pp.delete()

    def test__sync_implicit_parts__multiple(
        self,
        project_version,
        part,
        part_factory,
        project_part_factory,
        implicit_project_part_factory,
    ):
        """
        :scenario: Implicit Project Parts will remain unchanged when a BOM is
                   re-synced with changes to other rows

        | GIVEN a BOM has been synced yielding a project part
        | AND the project part has associated implicit project part instances
        | AND the ImplicitProjectPart definitions have not changed
        | WHEN _sync_implicit_parts is run for the yielded project part
        | THEN the existing implicit part instances will not be altered
        | AND no new implicit part instances will be created
        """
        implicit_part = part_factory(name="implicit part", symbol="IP")
        other_implicit_part = part_factory(name="other_implicit part", symbol="IP")
        project_part = project_part_factory(
            project_version=project_version, part=part, line_number=69
        )
        old_project_part = project_part_factory(
            project_version=project_version,
            part=implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=9,
        )
        other_old_project_part = project_part_factory(
            project_version=project_version,
            part=other_implicit_part,
            line_number=69,
            is_implicit=True,
            quantity=2,
        )
        implicit_project_part_factory(
            for_package=part.package, part=implicit_part, quantity=3
        )
        implicit_project_part_factory(
            for_package=part.package, part=other_implicit_part, quantity=2
        )
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 2
        s.ProjectVersionBomService()._sync_implicit_parts(project_part=project_part)
        assert m.ProjectPart.objects.filter(is_implicit=True).count() == 2
        pp = m.ProjectPart.objects.filter(is_implicit=True, part=implicit_part)[0]
        assert pp.quantity == 6
        assert pp.line_number == project_part.line_number
        assert pp == old_project_part
        pp.delete()
        opp = m.ProjectPart.objects.filter(is_implicit=True, part=other_implicit_part)[
            0
        ]
        assert opp == other_old_project_part
        assert opp.line_number == project_part.line_number
        assert opp.quantity == 4
        opp.delete()

    def test__sync_row(self, project_version, part, monkeypatch):
        """
        :scenario: Syncing a row from a Bill of Materials will result in a
                   Project Part with matching Value and Footprint (or vendor
                   and part number), quantity and footprints will also be
                   reproduced

        | GIVEN a valid BOM row exists for a project version
        | AND there exists at least one part which will match the attributes of
          the BOM row
        | WHEN _sync_row is run for the BOM row
        | THEN a project part will be returned
        | AND the project part will reference the aforementioned project version
        | AND the project part will reference an a part with matching "Value"
          and reference symbol
        | AND the project part will show the correct part quantity for the
          project version
        | AND the project part will reference the footprint references from the
          BOM row
        """
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "Reference": "A1, A2, A33, D12",
                "#": 69,
                "Qty": 420,
                "PartNum": None,
                "Vendor": None,
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )

        mock_get_part = Mock(return_value=part)
        monkeypatch.setattr(s.ProjectVersionBomService, "_get_part", mock_get_part)
        project_part = s.ProjectVersionBomService()._sync_row(
            row=_row, project_version=project_version
        )
        assert project_part.project_version == project_version
        assert project_part.part == part
        assert project_part.line_number == 69
        assert project_part.quantity == 420
        refs = project_part.footprint_refs.all()
        assert len(refs) == 4
        _refs = {"A1", "A2", "A33", "D12"}
        for ref in refs:
            _refs.remove(ref.footprint_ref)
        assert len(_refs) == 0
        mock_get_part.assert_called_once_with(row=_row)
        assert _row.symbols == {"A", "D"}
        project_part.delete()

    def test__sync_row__missing_vendor_part(self, project_version, monkeypatch):
        """
        :scenario: Syncing a row from a Bill of Materials with a Vendor (other
                   than "Mouser") and PartNum will result in a Project Part
                   with a missing part description when an appropriate Part
                   cannot be found in the system.

        | GIVEN a valid BOM row exists for a project version
        | AND the BOM row provides a vendor and part number
        | AND the vendor is not Mouser
        | AND there does not exist any part which will match the attributes of
          the BOM row
        | WHEN _sync_row is run for the BOM row
        | THEN a project part will be returned
        | AND the project part will reference the aforementioned project version
        | AND the project part will have a missing part description which
          possesses the information in the BOM row
        | AND the project part will not have a reference to a part
        """
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "Reference": "A1, A2, A33, D12",
                "#": 69,
                "Qty": 420,
                "PartNum": "real-part",
                "Vendor": "AmazingVendor",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )

        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_part", Mock(side_effect=MissingVendorPart)
        )
        project_part = s.ProjectVersionBomService()._sync_row(
            row=_row, project_version=project_version
        )
        assert project_part.project_version == project_version
        assert project_part.part is None
        assert project_part.missing_part_description is not None
        project_part.delete()

    def test__sync(self, project_version, monkeypatch, project_part_factory, part):
        """
        :scenario: Bills of Material will be retrieved (http) and parsed into
                   Project Parts

        | GIVEN a BOM has been synced yielding project parts
        | AND the BOM has been altered such that there are now fewer rows
        | WHEN _sync is run for the BOM
        | THEN _sync_row will be run for each row of the BOM
        | AND any project parts associated with a row removed from the BOM will
          be deleted
        | AND any project parts associated with a retained row from the BOM will
          be retained
        | AND the commit hash of the BOM will be saved on the project version
        """

        class Closable:
            def __init__(self, content):
                self.content = content

            def close(self):
                pass

        _real_project_part = project_part_factory(
            project_version=project_version, part=part
        )
        _bad_project_part = project_part_factory(
            project_version=project_version, part=part
        )

        mock_sync_row = Mock(return_value=_real_project_part)
        monkeypatch.setattr(s.ProjectVersionBomService, "_sync_row", mock_sync_row)
        monkeypatch.setattr(
            requests,
            "get",
            Mock(
                return_value=Closable(
                    b"""Qty,Reference,Vendor,PartNum,Footprint,Value
3,"A1, A2, A3","test vendor","test-item-number","Test Footprint","asdf" """
                )
            ),
        )

        s.ProjectVersionBomService()._sync(
            project_version=project_version, synced_commit="asdfasdfsadf"
        )
        with pytest.raises(m.ProjectPart.DoesNotExist):
            _bad_project_part.refresh_from_db()
        _project_parts = project_version.project_parts.all()
        assert len(_project_parts) == 1
        assert _real_project_part in _project_parts
        mock_sync_row.assert_called_once()
        assert project_version.last_synced_commit == "asdfasdfsadf"

    def test__sync__cannot_get_commit(
        self, project_version, monkeypatch, project_part_factory, part
    ):
        """
        :scenario: Only valid commit refs will be synced

        | GIVEN a commit ref cannot be found in the project repo
        | WHEN sync is run for the project
        | THEN _sync will not be run
        """
        monkeypatch.setattr(
            GithubService,
            "get_commit_hash_for_ref",
            Mock(side_effect=RefNotFoundException),
        )

        mock_sync_row = Mock()
        monkeypatch.setattr(s.ProjectVersionBomService, "_sync", mock_sync_row)

        s.ProjectVersionBomService().sync(project_version_pk=project_version.pk)
        mock_sync_row.assert_not_called()

    def test__sync__missing_part(
        self, project_version, monkeypatch, project_part_factory, part
    ):
        """
        :scenario: When resyncing a Bill of Materials Project Parts which are
                   not longer represented on the BOM will be deleted and new
                   Project Parts will be created as needed to represent the BOM

        | GIVEN a BOM for a project version has not been synced
        | AND project parts exist for that project version anyhow
        | AND the BOM calls for a part which does not exist
        | WHEN _sync is run for the BOM
        | THEN _sync_row will be run for each row of the BOM
        | AND any project parts which are not associatew with a BOM row will
          be deleted
        | AND project parts will be created for each row in the BOM
        | AND project parts created without a matching part will have a missing
          part description with all details from the BOM row
        | AND the commit hash of the BOM will be saved on the project version
        """

        class Closable:
            def __init__(self, content):
                self.content = content

            def close(self):
                pass

        _bad_project_part = project_part_factory(
            project_version=project_version, part=part, line_number=2
        )
        print(_bad_project_part)
        print(_bad_project_part.line_number)

        monkeypatch.setattr(
            requests,
            "get",
            Mock(
                return_value=Closable(
                    b"""#,Qty,Reference,Vendor,PartNum,Footprint,Value
1,3,"A1, A2, A3",,,"Unknown Footprint","zxcv" """
                )
            ),
        )

        s.ProjectVersionBomService()._sync(
            project_version=project_version, synced_commit="asdfasdfsadf"
        )
        with pytest.raises(m.ProjectPart.DoesNotExist):
            _bad_project_part.refresh_from_db()
        _project_parts = project_version.project_parts.all()
        assert len(_project_parts) == 1
        assert _project_parts[0].part is None
        assert _project_parts[0].missing_part_description is not None
        assert project_version.last_synced_commit == "asdfasdfsadf"

    def test_sync_calls__sync(self, project_version, monkeypatch):
        monkeypatch.setattr(
            GithubService,
            "get_commit_hash_for_ref",
            Mock(return_value="asdfasdf"),
        )
        mock_sync = Mock(return_value={})
        monkeypatch.setattr(s.ProjectVersionBomService, "_sync", mock_sync)
        s.ProjectVersionBomService().sync(project_version.pk)
        mock_sync.assert_called_once_with(
            project_version=project_version, synced_commit="asdfasdf"
        )


class TestProjectVersionBomServicePartSelection:
    """
    :feature: Parts are selected based on fields on a Bill of Materials
    """

    def test__get_vendor_part(self, vendor_part):
        """
        :scenario: "Vendor" and "PartNum" BOM fields will be used to find Parts

        | GIVEN a BOM row references a known vendor part by matching the columns
          for "Vendor" and "PartNum"
        | WHEN _get_vendor_part is run for that BOM rown
        | THEN the known vendor part will be returned
        """
        _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": vendor_part.item_number,
                    "Vendor": vendor_part.vendor.name,
                    "Value": "LED",
                    "Footprint": "asdf6789",
                }
            ),
        )
        assert _vendor_part == vendor_part

    def test__get_vendor_part__missing(self, vendor_part):
        """
        :scenario: Unknown "PartNum" BOM fields will raise exceptions unless
                   the "Vendor" is API enabled

        | GIVEN a BOM row references an unknown "PartNum"
        | AND the "Vendor" for the BOM row is not "Mouser"
        | WHEN _get_vendor_part is run for that BOM rown
        | THEN a `MissingVendorPart` exception is raised
        """
        with pytest.raises(MissingVendorPart):
            _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
                row=m.BillOfMaterialsRow.model_validate(
                    {
                        "#": 1,
                        "Reference": "D1, D2",
                        "Qty": 2,
                        "PartNum": vendor_part.item_number,
                        "Vendor": "nothing",
                        "Value": "LED",
                        "Footprint": "asdf6789",
                    }
                ),
            )

    def test__get_vendor_part__missing_mouser(self, vendor_part_mouser, monkeypatch):
        """
        :scenario: Parts and Vendor Parts will be created and autopopulated for
                   BOM rows with unknown "PartNum" and the "Vendor" is "Mouser"

        | GIVEN a BOM row references an unknown vendor part
        | AND the "Vendor" for the BOM row is "Mouser"
        | WHEN _get_vendor_part is run for that BOM rown
        | THEN the process to create a placeholder vendor part and populate it
          with real data is initiated
        | AND the placeholder part is returned
        """
        # SEE: TestMouserPartService.test_create_vendor_part
        monkeypatch.setattr(
            MouserPartService,
            "create_vendor_part",
            Mock(return_value=vendor_part_mouser),
        )
        _vendor_part = s.ProjectVersionBomService()._get_vendor_part(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "Mouser",
                    "Value": "LED",
                    "Footprint": "asdf6789",
                }
            ),
        )
        assert _vendor_part == vendor_part_mouser

    def test__get_matching_parts(self, part_factory, footprint):
        """
        :scenario: Parts are selected by the "Value" and "Footprint" BOM fields

        | GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        | WHEN _get_matching_parts is called for the given BOM row
        | THEN all catalog parts which match the value and symbol will be returned
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        white_led = part_factory(name="LED White", value="LED", symbol="D")
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert green_led in parts
        assert white_led in parts

    def test__get_matching_parts__discriminating(self, part_factory, footprint):
        """
        :scenario: Parts are not selected if they do not match both "Value" and
                   "Footprint" BOM rows

        | GIVEN a BOM row references a symbol which describes more than one part
          in the catalog
        | AND the BOM row references a value which describes more than one part
          in the catalog
        | WHEN _get_matching_parts is called for the given BOM row
        | THEN all catalog parts which match the value and symbol will be returned
        | AND any catalog partch which do not match the value or symbol will not
          be returned
        """
        log_pot = part_factory(name="Spinny Boi Pot", value="A100K", symbol="RV")
        lin_pot = part_factory(name="Spinny Boi Pot", value="B100K", symbol="RV")
        idk_my_bff_jill = part_factory(
            name="Spinny Boi Pot", value="B100K", symbol="VR"
        )
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "RV1, RV2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "B100K",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert lin_pot in parts
        assert log_pot not in parts
        assert idk_my_bff_jill not in parts

    def test__get_matching_parts__quantity_sorting(
        self, part_factory, footprint, inventory_line_factory
    ):
        """
        :scenario: When a BOM row matches more than one Part, the Part with the
                   lowest stock will be preferred

        | GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        | AND the parts are in stock
        | WHEN _get_matching_parts is called for the given BOM row
        | THEN all catalog parts which match the value and symbol will be returned
        | AND the parts will be returned sorted descending by the quantity in stock
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        purple_led = part_factory(name="LED purple", value="LED", symbol="D")
        white_led = part_factory(name="LED White", value="LED", symbol="D")
        inventory_line_factory(part=green_led, quantity=53)
        inventory_line_factory(part=white_led, quantity=47)
        inventory_line_factory(part=purple_led, quantity=22)
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert green_led == parts[0]
        assert white_led == parts[1]
        assert purple_led == parts[2]
        assert len(parts) == 3
        for part in parts:
            if part == green_led:
                assert part.qty_in_inventory == 53
            elif part == white_led:
                assert part.qty_in_inventory == 47
            elif part == purple_led:
                assert part.qty_in_inventory == 22

    def test__get_matching_parts__deprioritized(
        self, part_factory, footprint, inventory_line_factory
    ):
        """
        :scenario: When a BOM row matches more than one Part, the deprioritized
                   Part will not be preferred

        | GIVEN a BOM row references a value and symbol which describes more than
          one part in the catalog
        | AND any of the parts are marked `is_deprioritized`
        | WHEN _get_matching_parts is called for the given BOM row
        | THEN no parts marked `is_deprioritized` will be returned
        | AND all other catalog parts which match the value and symbol will be
          returned
        """
        green_led = part_factory(name="LED Green", value="LED", symbol="D")
        white_led = part_factory(name="LED white", value="LED", symbol="D")
        inventory_line_factory(part=green_led, quantity=53)
        inventory_line_factory(part=white_led, quantity=22, is_deprioritized=True)
        parts = s.ProjectVersionBomService()._get_matching_parts(
            row=m.BillOfMaterialsRow.model_validate(
                {
                    "#": 1,
                    "Reference": "D1, D2",
                    "Qty": 2,
                    "PartNum": "asdf1234",
                    "Vendor": "vendor",
                    "Value": "LED",
                    "Footprint": footprint.name,
                }
            ),
        )
        assert white_led not in parts

    def test__get_part_calls__get_vendor_part(self, monkeypatch, vendor_part):
        """
        :scenario: "Vendor" and "PartNum" fields on BOM rows will resolve to a
                   single Vendor Part

        | GIVEN a BOM row does reference a vendor and part number
        | WHEN _get_part is run for that BOM row
        | THEN _get_vendor_part is run for that BOM row
        | AND the first result is returned
        """
        mock_get_vendor_part = Mock(return_value=vendor_part)
        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_vendor_part", mock_get_vendor_part
        )
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "F1, F2",
                "Qty": 2,
                "PartNum": "asdf1234",
                "Vendor": "vendor",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )
        part = s.ProjectVersionBomService()._get_part(row=_row)
        assert part == vendor_part.part
        mock_get_vendor_part.assert_called_once_with(row=_row)

    def test__get_part_calls__get_vendor_part__missing(self, monkeypatch, vendor_part):
        """
        :scenario: "Vendor" and "PartNum" fields on BOM rows which do not
                   resolve to a single part will raise an exception

        | GIVEN a BOM row does reference a vendor and part number
        | AND the part number is not represented by a vendor part
        | WHEN _get_part is run for that BOM row
        | THEN _get_vendor_part is run for that BOM row
        | AND a MissingVendorPart exception is raised
        """
        mock_get_vendor_part = Mock(side_effect=MissingVendorPart("asdf"))
        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_vendor_part", mock_get_vendor_part
        )
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "F1, F2",
                "Qty": 2,
                "PartNum": "asdf1234",
                "Vendor": "vendor",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )
        with pytest.raises(MissingVendorPart):
            s.ProjectVersionBomService()._get_part(row=_row)
        mock_get_vendor_part.assert_called_once_with(row=_row)

    def test__get_part_calls__get_matching_parts(
        self, monkeypatch, part_queryset, part
    ):
        """
        :scenario: BOM rows without "Vendor" or "PartNum" fields will be matched
                   to Parts by "Value" and "Footprint" fields

        | GIVEN a BOM row does not reference either a vendor or a part number
        | AND the BOM row references a value and symbol which describes at least
          one part in the catalog
        | WHEN _get_part is run for that BOM row
        | THEN _get_matching_parts is run for that BOM row
        | AND the first result is returned
        """
        mock_get_matching_part = Mock(return_value=part_queryset)
        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_matching_parts", mock_get_matching_part
        )
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "F1, F2",
                "Qty": 2,
                "PartNum": "asdf",
                "Vendor": "",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )
        _part = s.ProjectVersionBomService()._get_part(
            row=_row,
        )
        assert _part == part
        mock_get_matching_part.assert_called_once_with(row=_row)

    def test__get_part__missing(self, monkeypatch):
        """
        :scenario: BOM rows without "Vendor" or "PartNum" fields and which do
                   not match any Parts by "Value" and "Footprint" fields will
                   not match to any Part

        | GIVEN a BOM row does not reference either a vendor or a part number
        | AND th BOM row references a value and symbol which describes no part
          in the catalog
        | WHEN _get_part is run for that BOM row
        | THEN _get_matching_parts is run for that BOM row
        | AND null is returned
        """
        mock_get_matching_part = Mock(return_value=m.Part.objects.none())
        monkeypatch.setattr(
            s.ProjectVersionBomService, "_get_matching_parts", mock_get_matching_part
        )
        _row = m.BillOfMaterialsRow.model_validate(
            {
                "#": 1,
                "Reference": "F1, F2",
                "Qty": 2,
                "PartNum": "",
                "Vendor": "",
                "Value": "asdf6789",
                "Footprint": "asdf1234",
            }
        )
        _part = s.ProjectVersionBomService()._get_part(
            row=_row,
        )
        mock_get_matching_part.assert_called_once_with(row=_row)
        assert _part is None
