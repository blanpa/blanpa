import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from github_stats.queries import Queries


@dataclass
class Stats:
    """GitHub usage statistics — immutable after creation via fetch()."""

    name: str
    stargazers: int
    forks: int
    total_contributions: int
    languages: dict[str, dict[str, Any]]
    repos: set[str]
    lines_changed: tuple[int, int]
    views: int

    @property
    def languages_proportional(self) -> dict[str, float]:
        return {k: v.get("prop", 0) for k, v in self.languages.items()}

    def __str__(self) -> str:
        formatted_languages = "\n  - ".join(
            f"{k}: {v:0.4f}%" for k, v in self.languages_proportional.items()
        )
        return (
            f"Name: {self.name}\n"
            f"Stargazers: {self.stargazers:,}\n"
            f"Forks: {self.forks:,}\n"
            f"All-time contributions: {self.total_contributions:,}\n"
            f"Repositories with contributions: {len(self.repos)}\n"
            f"Lines of code added: {self.lines_changed[0]:,}\n"
            f"Lines of code deleted: {self.lines_changed[1]:,}\n"
            f"Lines of code changed: {self.lines_changed[0] + self.lines_changed[1]:,}\n"
            f"Project page views: {self.views:,}\n"
            f"Languages:\n  - {formatted_languages}"
        )

    @classmethod
    async def fetch(
        cls,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        exclude_repos: set[str] | None = None,
        exclude_langs: set[str] | None = None,
        ignore_forked_repos: bool = False,
    ) -> "Stats":
        queries = Queries(username, access_token, session)

        overview_coro = cls._fetch_overview(
            queries, exclude_repos or set(), exclude_langs or set(), ignore_forked_repos
        )
        contribs_coro = cls._fetch_total_contributions(queries)
        overview, total_contributions = await asyncio.gather(overview_coro, contribs_coro)

        name, stargazers, forks, languages, repos = overview

        lines_coro = cls._fetch_lines_changed(queries, username, repos)
        views_coro = cls._fetch_views(queries, repos)
        lines_changed, views = await asyncio.gather(lines_coro, views_coro)

        return cls(
            name=name,
            stargazers=stargazers,
            forks=forks,
            total_contributions=total_contributions,
            languages=languages,
            repos=repos,
            lines_changed=lines_changed,
            views=views,
        )

    @staticmethod
    async def _fetch_overview(
        queries: Queries,
        exclude_repos: set[str],
        exclude_langs: set[str],
        ignore_forked_repos: bool,
    ) -> tuple[str, int, int, dict[str, dict[str, Any]], set[str]]:
        stargazers = 0
        forks = 0
        languages: dict[str, dict[str, Any]] = {}
        repos: set[str] = set()
        name = "No Name"

        next_owned: str | None = None
        next_contrib: str | None = None

        while True:
            raw = await queries.query(
                Queries.repos_overview(owned_cursor=next_owned, contrib_cursor=next_contrib)
            )
            raw = raw or {}
            viewer = raw.get("data", {}).get("viewer", {})
            name = viewer.get("name") or viewer.get("login", "No Name")

            contrib_section = viewer.get("repositoriesContributedTo", {})
            owned_section = viewer.get("repositories", {})

            repo_nodes = list(owned_section.get("nodes", []))
            if not ignore_forked_repos:
                repo_nodes += contrib_section.get("nodes", [])

            for repo in repo_nodes:
                if repo is None:
                    continue
                repo_name = repo.get("nameWithOwner")
                if repo_name in repos or repo_name in exclude_repos:
                    continue
                repos.add(repo_name)
                stargazers += repo.get("stargazers", {}).get("totalCount", 0)
                forks += repo.get("forkCount", 0)

                for lang in repo.get("languages", {}).get("edges", []):
                    lang_name = lang.get("node", {}).get("name", "Other")
                    if lang_name in exclude_langs:
                        continue
                    if lang_name in languages:
                        languages[lang_name]["size"] += lang.get("size", 0)
                        languages[lang_name]["occurrences"] += 1
                    else:
                        languages[lang_name] = {
                            "size": lang.get("size", 0),
                            "occurrences": 1,
                            "color": lang.get("node", {}).get("color"),
                        }

            has_next_owned = owned_section.get("pageInfo", {}).get("hasNextPage", False)
            has_next_contrib = contrib_section.get("pageInfo", {}).get("hasNextPage", False)
            if has_next_owned or has_next_contrib:
                next_owned = owned_section.get("pageInfo", {}).get("endCursor", next_owned)
                next_contrib = contrib_section.get("pageInfo", {}).get("endCursor", next_contrib)
            else:
                break

        langs_total = sum(v.get("size", 0) for v in languages.values())
        if langs_total > 0:
            for v in languages.values():
                v["prop"] = 100 * (v.get("size", 0) / langs_total)

        return name, stargazers, forks, languages, repos

    @staticmethod
    async def _fetch_total_contributions(queries: Queries) -> int:
        years = (
            (await queries.query(Queries.contrib_years()))
            .get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionYears", [])
        )
        by_year = (
            (await queries.query(Queries.all_contribs(years)))
            .get("data", {})
            .get("viewer", {})
            .values()
        )
        return sum(
            year.get("contributionCalendar", {}).get("totalContributions", 0) for year in by_year
        )

    @staticmethod
    async def _fetch_lines_changed(
        queries: Queries, username: str, repos: set[str]
    ) -> tuple[int, int]:
        additions = 0
        deletions = 0
        for repo in repos:
            r = await queries.query_rest(f"/repos/{repo}/stats/contributors")
            if not isinstance(r, list):
                continue
            for author_obj in r:
                if not isinstance(author_obj, dict):
                    continue
                author = author_obj.get("author")
                if not isinstance(author, dict) or author.get("login") != username:
                    continue
                for week in author_obj.get("weeks", []):
                    additions += week.get("a", 0)
                    deletions += week.get("d", 0)
        return additions, deletions

    @staticmethod
    async def _fetch_views(queries: Queries, repos: set[str]) -> int:
        total = 0
        for repo in repos:
            r = await queries.query_rest(f"/repos/{repo}/traffic/views")
            if not isinstance(r, dict):
                continue
            for view in r.get("views", []):
                total += view.get("count", 0)
        return total
