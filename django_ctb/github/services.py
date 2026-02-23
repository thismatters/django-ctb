"""
Services for interacting with the GitHub API
"""

import requests

from django_ctb.exceptions import RefNotFoundException


class GithubService:
    """
    Service for interacting with the GitHub API. Doesn't use a client, just
    calls directly for these minimal public endpoints.
    """

    base_url: str = "https://api.github.com"

    def _get_commit_hash(self, *, url_prefix: str, commit_ref: str) -> str:
        response = requests.get(f"{url_prefix}/commits/{commit_ref}")
        if response.status_code >= 300:
            # this is not a commit!
            raise RefNotFoundException
        # should be the same thing, but this seems right
        return response.json()["sha"]

    def _get_branch_head_commit_hash(self, *, url_prefix: str, commit_ref: str) -> str:
        response = requests.get(f"{url_prefix}/branches/{commit_ref}")
        if response.status_code >= 300:
            # this is not a branch!
            raise RefNotFoundException
        return response.json()["commit"]["sha"]

    def _get_tag_commit_hash(self, *, url_prefix: str, commit_ref: str) -> str:
        response = requests.get(f"{url_prefix}/tags")
        if response.status_code >= 300:
            # this is a real problem!
            raise RefNotFoundException
        for tag in response.json():
            if tag["name"] == commit_ref:
                return tag["commit"]["sha"]
        raise RefNotFoundException

    def get_commit_hash_for_ref(self, *, user: str, repo: str, commit_ref: str) -> str:
        """
        Find the commit has for the given ``commit_ref``. Uses the Github API to
        check, in this order, if ``commit_ref`` is:

        - A commit hash
        - A branch name
        - A tag

        The commit hash will be derived from the resource it represents.
        """
        # the `commit_ref` could be found at these paths
        # - a commit hash proper: `/repos/{owner}/{repo}/commits/{commit_sha}`
        # - a branch name: `/repos/{owner}/{repo}/branches/{branch_name}`
        # - a tag: `/repos/{owner}/{repo}/tags` <- Only list, no detail...
        url_prefix = f"{self.base_url}/repos/{user}/{repo}"
        try:
            return self._get_commit_hash(url_prefix=url_prefix, commit_ref=commit_ref)
        except RefNotFoundException:
            pass
        try:
            return self._get_branch_head_commit_hash(
                url_prefix=url_prefix, commit_ref=commit_ref
            )
        except RefNotFoundException:
            pass
        try:
            return self._get_tag_commit_hash(
                url_prefix=url_prefix, commit_ref=commit_ref
            )
        except RefNotFoundException:
            pass
        raise RefNotFoundException
