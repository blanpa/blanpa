import asyncio
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)


class Queries:
    """Query the GitHub GraphQL (v4) and REST (v3) APIs."""

    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        max_connections: int = 10,
    ):
        self.username = username
        self.access_token = access_token
        self.session = session
        self.semaphore = asyncio.Semaphore(max_connections)

    async def query(self, generated_query: str) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with self.semaphore:
                r = await self.session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
            result = await r.json()
            if result is not None:
                return result
        except Exception:
            log.exception("GraphQL query failed")
        return {}

    async def query_rest(self, path: str, params: dict | None = None) -> Any:
        headers = {"Authorization": f"token {self.access_token}"}
        if params is None:
            params = {}
        if path.startswith("/"):
            path = path[1:]

        for attempt in range(10):
            try:
                async with self.semaphore:
                    r = await self.session.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                if r.status == 202:
                    delay = min(2**attempt, 30)
                    log.info("%s returned 202, retrying in %ds (attempt %d)", path, delay, attempt)
                    await asyncio.sleep(delay)
                    continue
                result = await r.json()
                if result is not None:
                    return result
            except Exception:
                log.exception("REST query failed for %s", path)

        log.warning("Too many retries for %s — data will be incomplete", path)
        return {}

    @staticmethod
    def repos_overview(
        contrib_cursor: str | None = None,
        owned_cursor: str | None = None,
    ) -> str:
        return f"""{{
  viewer {{
    login,
    name,
    repositories(
        first: 100,
        orderBy: {{field: UPDATED_AT, direction: DESC}},
        isFork: false,
        after: {"null" if owned_cursor is None else '"' + owned_cursor + '"'}
    ) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        nameWithOwner
        stargazers {{ totalCount }}
        forkCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{ size node {{ name color }} }}
        }}
      }}
    }}
    repositoriesContributedTo(
        first: 100,
        includeUserRepositories: false,
        orderBy: {{field: UPDATED_AT, direction: DESC}},
        contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]
        after: {"null" if contrib_cursor is None else '"' + contrib_cursor + '"'}
    ) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        nameWithOwner
        stargazers {{ totalCount }}
        forkCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{ size node {{ name color }} }}
        }}
      }}
    }}
  }}
}}"""

    @staticmethod
    def contrib_years() -> str:
        return """
query {
  viewer {
    contributionsCollection {
      contributionYears
    }
  }
}"""

    @staticmethod
    def contribs_by_year(year: str) -> str:
        return f"""
    year{year}: contributionsCollection(
        from: "{year}-01-01T00:00:00Z",
        to: "{int(year) + 1}-01-01T00:00:00Z"
    ) {{
      contributionCalendar {{ totalContributions }}
    }}"""

    @classmethod
    def all_contribs(cls, years: list[str]) -> str:
        by_years = "\n".join(map(cls.contribs_by_year, years))
        return f"""
query {{
  viewer {{
    {by_years}
  }}
}}"""
