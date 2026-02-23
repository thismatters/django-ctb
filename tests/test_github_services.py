from unittest.mock import Mock, patch

import pytest
import requests

from django_ctb.exceptions import RefNotFoundException
from django_ctb.github.services import GithubService

from .github_services_test_data import (
    BRANCHES_RESPONSE,
    COMMITS_RESPONSE,
    TAGS_RESPONSE,
)


class TestGithubService:
    """
    :feature: Projects hosted on Github will have commit-level traceability
              of commit references
    """

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=200, json=lambda: COMMITS_RESPONSE)),
    )
    def test__get_commit_hash(self):
        """
        :scenario: Commit hashes will be found when requesting commits

        | GIVEN a commit hash exists in github
        | WHEN _get_commit_hash is called with the commit hash
        | THEN the commit hash will be returned
        """
        commit_hash = GithubService()._get_commit_hash(
            url_prefix="asdf", commit_ref="asdf"
        )
        assert commit_hash == "4ddd1280a3a048c6ef0d0463296c636ed7f1c0fe"

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=404, json=lambda: COMMITS_RESPONSE)),
    )
    def test__get_commit_hash__missing(self):
        """
        :scenario: Non hash commit refs will not be found by requesting commits

        | GIVEN a commit hash exists in github
        | WHEN _get_commit_hash is called with something other than the commit
          hash
        | THEN an exception will be raised
        """
        with pytest.raises(RefNotFoundException):
            GithubService()._get_commit_hash(url_prefix="asdf", commit_ref="asdf")

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=200, json=lambda: BRANCHES_RESPONSE)),
    )
    def test__get_branch_head_commit_hash(self):
        """
        :scenario: Commit hashes will be found when requesting branches

        | GIVEN a branch exists in github
        | WHEN _get_branch_head_commit_hash is called with the branch name
        | THEN the commit hash will be returned
        """
        commit_hash = GithubService()._get_branch_head_commit_hash(
            url_prefix="asdf", commit_ref="asdf"
        )
        assert commit_hash == "69db8442ac20fe9be7998f2a6cd497413062b2af"

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=404, json=lambda: BRANCHES_RESPONSE)),
    )
    def test__get_branch_head_commit_hash__missing(self):
        """
        :scenario: Non hash commit refs will not be found by requesting commits

        | GIVEN a branch exists in github
        | WHEN _get_branch_head_commit_hash is called with something other
          than the branch name
        | THEN an exception will be raised
        """
        with pytest.raises(RefNotFoundException):
            GithubService()._get_branch_head_commit_hash(
                url_prefix="asdf", commit_ref="asdf"
            )

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=200, json=lambda: TAGS_RESPONSE)),
    )
    def test__get_tag_commit_hash(self):
        """
        :scenario: Commit hashes will be found when requesting tags

        | GIVEN a tag exists in github
        | WHEN _get_tag_commit_hash is called with the tag name
        | THEN the commit hash will be returned
        """
        commit_hash = GithubService()._get_tag_commit_hash(
            url_prefix="asdf", commit_ref="v1"
        )
        assert commit_hash == "4ddd1280a3a048c6ef0d0463296c636ed7f1c0fe"

        commit_hash = GithubService()._get_tag_commit_hash(
            url_prefix="asdf", commit_ref="v2"
        )
        assert commit_hash == "69db8442ac20fe9be7998f2a6cd497413062b2af"

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=200, json=lambda: TAGS_RESPONSE)),
    )
    def test__get_tag_commit_hash__missing_tag(self):
        """
        :scenario: Non hash commit refs will not be found by requesting commits

        | GIVEN a tag does not exists in github
        | WHEN _get_tag_commit_hash is called with something other
          than the tag name
        | THEN an exception will be raised
        """
        with pytest.raises(RefNotFoundException):
            GithubService()._get_tag_commit_hash(url_prefix="asdf", commit_ref="v3")

    @patch.object(
        requests,
        "get",
        Mock(return_value=Mock(status_code=404, json=lambda: TAGS_RESPONSE)),
    )
    def test__get_tag_commit_hash__wtf_happened(self):
        with pytest.raises(RefNotFoundException):
            GithubService()._get_tag_commit_hash(url_prefix="asdf", commit_ref="v2")

    @patch.object(GithubService, "_get_commit_hash", Mock(return_value="sdafasdf"))
    def test_get_commit_hash_for_ref__is_commit(self):
        ret = GithubService().get_commit_hash_for_ref(
            user="user", repo="repo", commit_ref="qwerqwer"
        )
        assert ret == "sdafasdf"

    @patch.object(
        GithubService, "_get_commit_hash", Mock(side_effect=RefNotFoundException)
    )
    @patch.object(
        GithubService, "_get_branch_head_commit_hash", Mock(return_value="sdafasdf")
    )
    def test_get_commit_hash_for_ref__is_branch(self):
        ret = GithubService().get_commit_hash_for_ref(
            user="user", repo="repo", commit_ref="qwerqwer"
        )
        assert ret == "sdafasdf"

    @patch.object(
        GithubService, "_get_commit_hash", Mock(side_effect=RefNotFoundException)
    )
    @patch.object(
        GithubService,
        "_get_branch_head_commit_hash",
        Mock(side_effect=RefNotFoundException),
    )
    @patch.object(GithubService, "_get_tag_commit_hash", Mock(return_value="sdafasdf"))
    def test_get_commit_hash_for_ref__is_tag(self):
        ret = GithubService().get_commit_hash_for_ref(
            user="user", repo="repo", commit_ref="qwerqwer"
        )
        assert ret == "sdafasdf"

    @patch.object(
        GithubService, "_get_commit_hash", Mock(side_effect=RefNotFoundException)
    )
    @patch.object(
        GithubService,
        "_get_branch_head_commit_hash",
        Mock(side_effect=RefNotFoundException),
    )
    @patch.object(
        GithubService, "_get_tag_commit_hash", Mock(side_effect=RefNotFoundException)
    )
    def test_get_commit_hash_for_ref__is_somehow_none(self):
        with pytest.raises(RefNotFoundException):
            GithubService().get_commit_hash_for_ref(
                user="user", repo="repo", commit_ref="qwerqwer"
            )
