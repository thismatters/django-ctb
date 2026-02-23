"""
Exceptions bruh
"""

from django_ctb.models import ProjectBuildPartShortage


class InsufficientInventory(Exception):
    """
    When there is not enough stock to fulfill a project build
    """

    def __init__(self, *args, shortages: list[ProjectBuildPartShortage], **kwargs):
        """
        Pass a list of shortages which were created to track this clear to
        build error.
        """
        self.shortages = shortages
        super().__init__(*args, **kwargs)


class MissingVendorPart(Exception):
    """
    When a vendor part cannot be found (maybe part number is wrong?)
    """


class RefNotFoundException(Exception):
    """
    The given commit ref could not be found in the git server
    """
