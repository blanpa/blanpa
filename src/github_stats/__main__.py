import asyncio
import logging
import os
from pathlib import Path

import aiohttp
import jinja2

from github_stats.stats import Stats

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path.cwd()))
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "generated"

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=False,
    keep_trailing_newline=True,
)


def generate_overview(s: Stats) -> None:
    template = env.get_template("overview.svg.j2")
    output = template.render(
        name=s.name,
        stars=f"{s.stargazers:,}",
        forks=f"{s.forks:,}",
        contributions=f"{s.total_contributions:,}",
        lines_changed=f"{s.lines_changed[0] + s.lines_changed[1]:,}",
        views=f"{s.views:,}",
        repos=f"{len(s.repos):,}",
    )
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "overview.svg").write_text(output)


def generate_languages(s: Stats) -> None:
    sorted_languages = sorted(s.languages.items(), reverse=True, key=lambda t: t[1].get("size"))
    languages = [
        {
            "name": name,
            "color": data.get("color") or "#000000",
            "prop": f"{data.get('prop', 0):0.3f}",
        }
        for name, data in sorted_languages
    ]

    template = env.get_template("languages.svg.j2")
    output = template.render(languages=languages)
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "languages.svg").write_text(output)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError("A personal access token is required to proceed!")

    user = os.getenv("GITHUB_ACTOR")

    exclude_repos = os.getenv("EXCLUDED")
    exclude_repos_set = {x.strip() for x in exclude_repos.split(",")} if exclude_repos else None

    exclude_langs = os.getenv("EXCLUDED_LANGS")
    exclude_langs_set = {x.strip() for x in exclude_langs.split(",")} if exclude_langs else None

    raw_ignore = os.getenv("EXCLUDE_FORKED_REPOS")
    ignore_forked = bool(raw_ignore) and raw_ignore.strip().lower() != "false"

    async with aiohttp.ClientSession() as session:
        s = await Stats.fetch(
            user,
            access_token,
            session,
            exclude_repos=exclude_repos_set,
            exclude_langs=exclude_langs_set,
            ignore_forked_repos=ignore_forked,
        )

    generate_overview(s)
    generate_languages(s)


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
