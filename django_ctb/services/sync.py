"""
Services and helpers for syncing bills of material (BOM) to project versions
"""

import csv
import io
import logging
from contextlib import closing

import requests
from django.db.models import Sum
from django.utils import timezone

from django_ctb import models
from django_ctb.exceptions import MissingVendorPart, RefNotFoundException
from django_ctb.github.services import GithubService
from django_ctb.mouser.services import MouserPartService

logger = logging.getLogger(__name__)


class ProjectVersionBomService:
    """Downloads BOM from repo at specified commit and creates project
    parts for each line."""

    def _get_vendor_part(self, *, row):
        try:
            vendor_part = models.VendorPart.objects.get(
                vendor__name=row.vendor_name, item_number=row.item_number
            )
        except models.VendorPart.DoesNotExist:
            # such a vendor part will need to exist before this project
            #  bom can be validated
            logger.info(
                f"Project BOM includes vendor specified part which is not "
                f"in parts library: {row.vendor_name}: {row.item_number}"
            )
            # If the vendor is Mouser then the part can be looked up via API
            if row.vendor_name == "Mouser":
                vendor_part = MouserPartService().create_vendor_part(
                    row=row,
                )
            else:
                raise MissingVendorPart(
                    f"Vendor Part not found {row.vendor_name}: {row.item_number}"
                )
        return vendor_part

    def _get_matching_parts(self, *, row):
        # Consider cases where there is more than one part that satisfies,
        #  e.g. an LED (parts may include a "white LED" and a "green LED").
        #  * Don't choose the part which is deprioritized
        #  * Choose the part which has inventory!
        return (
            models.Part.objects.filter(
                value=row.value,
                package__footprints__name=row.footprint_name,
                symbol__in=row.symbols,
            )
            .exclude(inventory_lines__is_deprioritized=True)
            .annotate(qty_in_inventory=Sum("inventory_lines__quantity"))
            .order_by("-qty_in_inventory")
        )

    def _get_part(self, *, row):
        if row.item_number and row.vendor_name:
            return self._get_vendor_part(row=row).part
        _part = self._get_matching_parts(row=row).first()
        return _part

    def _sync_footprints(serf, footprint_refs, *, project_part):
        # get rid of any outdated/altered refs
        models.ProjectPartFootprintRef.objects.filter(
            project_part=project_part
        ).exclude(footprint_ref__in=footprint_refs).delete()
        # create any missing refs
        for footprint_ref in footprint_refs:
            models.ProjectPartFootprintRef.objects.get_or_create(
                footprint_ref=footprint_ref, project_part=project_part
            )

    def _sync_implicit_parts(self, *, project_part):
        if project_part.part is None:
            logger.info(
                "!!!! Cannot create implicit parts for project_part lacking a "
                f"part {project_part}"
            )
            return
        implicit_project_parts = models.ImplicitProjectPart.objects.filter(
            for_package=project_part.part.package
        )
        project_part_pks = []
        for implicit_project_part in implicit_project_parts:
            quantity = implicit_project_part.quantity * project_part.quantity
            _implicit_project_part, _ = models.ProjectPart.objects.update_or_create(
                project_version=project_part.project_version,
                line_number=project_part.line_number,
                is_implicit=True,
                part=implicit_project_part.part,
                defaults={
                    "quantity": quantity,
                },
            )
            logger.info(
                f">>>> Created implicit project part {_implicit_project_part.pk}"
            )
            project_part_pks.append(_implicit_project_part.pk)
        # clean up any vestiges
        models.ProjectPart.objects.exclude(pk__in=project_part_pks).filter(
            line_number=project_part.line_number, is_implicit=True
        ).delete()

    def _sync_row(self, *, row, project_version):
        _part = None
        try:
            _part = self._get_part(row=row)
        except MissingVendorPart:
            pass
        defaults = {
            "part": _part,
            "quantity": row.quantity,
            "is_optional": row.optional,
        }
        if _part is None:
            defaults.update({"missing_part_description": f"{row}"})
        project_part, _ = models.ProjectPart.objects.update_or_create(
            project_version=project_version,
            line_number=row.line_number,
            is_implicit=False,
            defaults=defaults,
        )

        self._sync_footprints(row.references, project_part=project_part)
        self._sync_implicit_parts(project_part=project_part)
        return project_part

    def _get_commit_hash(self, project_version) -> str:
        ret = ""
        if project_version.project.git_server == models.Project.GitServer.GITHUB:
            ret = GithubService().get_commit_hash_for_ref(
                user=project_version.project.git_user,
                repo=project_version.project.git_repo,
                commit_ref=project_version.commit_ref,
            )
        return ret

    def _sync(self, *, project_version: models.ProjectVersion, synced_commit: str):
        row_errors = {}
        project_part_pks = []
        _bom_url = project_version.bom_url_for_commit(synced_commit)
        logger.info(f">> Getting BOM from {_bom_url}")
        file_response = requests.get(_bom_url)
        with (
            closing(file_response),
            io.StringIO(file_response.content.decode("utf-8")) as bom,
        ):
            reader = csv.DictReader(bom)
            logger.info(">> Parsing csv")
            for line_number, _row in enumerate(reader, start=1):
                if "#" not in _row:
                    _row["#"] = line_number
                row = models.BillOfMaterialsRow.model_validate(_row)
                logger.info(f">>>> Line {row.line_number}")
                project_part = self._sync_row(row=row, project_version=project_version)
                if project_part.part is None:
                    logger.info(f">>>> Part missing for line {row}")
                    logger.info(row.symbols)
                    row_errors.setdefault("part_missing", []).append(row.line_number)
                project_part_pks.append(project_part.pk)
        logger.info(f">> Created these project parts {project_part_pks}")
        # remove any outdated lines (implicit parts are cleaned up in
        #  _sync_implicit_parts)
        models.ProjectPart.objects.filter(
            project_version=project_version, is_implicit=False
        ).exclude(pk__in=project_part_pks).delete()
        project_version.last_synced_commit = synced_commit
        project_version.synced = timezone.now()
        project_version.save()
        return row_errors

    def sync(self, project_version_pk):
        """
        Finds a project version by PK then downloads BOM from repository and
        creates project parts for each row. BOM rows which cannot be matched
        to any part in the system will be flagged with a
        ``missing_part_description``. Parts available through supported
        vendors (Mouser) will be autopopulated provided the PartNum is known.

        Rows referencing footprints which are configured with implicit project
        parts will cause additional project parts to be created to represent
        the implicit parts.

        Upon completion of the sync process the commit hash where the BOM was
        found will be saved and the project version will be marked synced.
        """
        project_version = models.ProjectVersion.objects.get(pk=project_version_pk)
        logger.info(f"Starting project version sync for {project_version}")
        try:
            synced_commit = self._get_commit_hash(project_version=project_version)
        except RefNotFoundException:
            logger.info(
                f"!! Cannot find commit ref {project_version.commit_ref}. Aborting!"
            )
            return
        return self._sync(project_version=project_version, synced_commit=synced_commit)
