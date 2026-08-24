#!/usr/bin/python3

import asyncio
import base64
import os
from typing import Dict, List, Tuple

import aiohttp

from github_stats import Stats


################################################################################
# Configuration
################################################################################

# One file is rendered per palette; the README picks the matching one through
# <picture> and prefers-color-scheme. The suffix becomes part of the filename,
# so the light theme writes "overview.svg" and the dark one "overview-dark.svg".
THEMES: Dict[str, Dict[str, str]] = {
    "": {
        "bg": "#faf8f4",
        "fg": "#1b1a17",
        "muted": "#8a857a",
        "accent": "#9c3d18",
        "border": "#e2ddd3",
        "track": "#e2ddd3",
    },
    "-dark": {
        "bg": "#16171a",
        "fg": "#e7e4de",
        "muted": "#6e6a63",
        "accent": "#d9744a",
        "border": "#2c2d31",
        "track": "#2c2d31",
    },
}

# Embedded so the label and figure font survives the <img> context GitHub
# renders the cards in, where no external resource is ever fetched. The
# headings fall back to the same system serif stack the site uses, so nothing
# has to be shipped for them.
MONO_FONTS: Dict[str, str] = {
    "mono_regular": "assets/jetbrains-mono-400.woff2",
    "mono_semibold": "assets/jetbrains-mono-600.woff2",
}

# Languages listed individually before the remainder is folded into "Other".
# The legend is laid out as two columns of three, so six entries fit exactly.
MAX_LANGUAGES = 5
OTHER_COLOR = "#8b949e"

# The stack card is the one hand-maintained image: nothing about it comes from
# the API, so the rows live here and the template holds only the layout.
STACK: List[Tuple[str, Tuple[str, ...]]] = [
    (
        "Protocols",
        (
            "OPC-UA",
            "Siemens S7",
            "EtherNet/IP",
            "Modbus",
            "MQTT",
            "Sparkplug B",
            "NATS",
            "Kafka",
        ),
    ),
    (
        "Platform",
        (
            "Node-RED",
            "Docker",
            "Kubernetes",
            "Ansible",
            "Grafana",
            "Redis",
            "PostgreSQL",
            "TimescaleDB",
        ),
    ),
    (
        "Languages & tools",
        ("Python", "JavaScript", "Go", "C", "Bash", "Linux", "Debian", "Git"),
    ),
    (
        "Data & ML",
        ("pandas", "scikit-learn", "PyTorch", "TensorFlow", "OpenCV"),
    ),
]

# Card geometry, mirrored from the templates
CARD_LEFT = 28
BAR_WIDTH = 404
LEGEND_TOP = 130
LEGEND_ROW_HEIGHT = 24
LEGEND_ROWS = 3
LEGEND_COLUMN_WIDTH = 212
STACK_TOP = 106
STACK_ROW_HEIGHT = 32
STACK_ITEMS_LEFT = 168


################################################################################
# Helper Functions
################################################################################


def generate_output_folder() -> None:
    """
    Create the output folder if it does not already exist
    """
    if not os.path.isdir("generated"):
        os.mkdir("generated")


def escape(text: str) -> str:
    """
    Escape the characters that would break out of an SVG text node
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def compact(value: int) -> str:
    """
    Shorten large numbers so they stay legible at 25px: 525070 becomes 525K
    :param value: number to format
    :return: formatted number
    """
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 10_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:,}"


def embedded_fonts() -> Dict[str, str]:
    """
    :return: every embedded font, base64 encoded for use in a data URI
    """
    fonts = {}
    for placeholder, path in MONO_FONTS.items():
        with open(path, "rb") as f:
            fonts[placeholder] = base64.b64encode(f.read()).decode("ascii")
    return fonts


def render(template: str, values: Dict[str, str]) -> str:
    """
    Substitute every {{ key }} placeholder in a template
    :param template: template contents
    :param values: placeholder names mapped to their replacements
    :return: rendered template
    """
    for key, value in values.items():
        template = template.replace("{{ " + key + " }}", str(value))
    return template


def write_themed(template_name: str, output_name: str, values: Dict[str, str]) -> None:
    """
    Render one template once per palette and write the results
    :param template_name: file name inside templates/
    :param output_name: file name inside generated/, without theme suffix
    :param values: placeholder names mapped to their replacements
    """
    with open(f"templates/{template_name}", "r") as f:
        template = f.read()

    generate_output_folder()
    fonts = embedded_fonts()
    for suffix, palette in THEMES.items():
        with open(f"generated/{output_name}{suffix}.svg", "w") as f:
            f.write(render(template, {**values, **palette, **fonts}))


################################################################################
# Individual Image Generation Functions
################################################################################


async def generate_overview(s: Stats) -> None:
    """
    Generate an SVG card with summary statistics
    :param s: Represents user's GitHub statistics
    """
    added, removed = await s.lines_changed
    write_themed(
        "overview.svg",
        "overview",
        {
            "name": escape(await s.name),
            "stars": compact(await s.stargazers),
            "forks": compact(await s.forks),
            "repos": compact(len(await s.repos)),
            "contributions": compact(await s.total_contributions),
            "lines_changed": compact(added + removed),
            "views": compact(await s.views),
        },
    )


async def generate_languages(s: Stats) -> None:
    """
    Generate an SVG card with the languages used
    :param s: Represents user's GitHub statistics
    """
    sorted_languages = sorted(
        (await s.languages).items(), reverse=True, key=lambda t: t[1].get("size")
    )

    entries: List[Tuple[str, str, float]] = [
        (lang, data.get("color") or OTHER_COLOR, data.get("prop", 0))
        for lang, data in sorted_languages[:MAX_LANGUAGES]
    ]
    remainder = sorted_languages[MAX_LANGUAGES:]
    if remainder:
        entries.append(
            ("Other", OTHER_COLOR, sum(d.get("prop", 0) for _, d in remainder))
        )

    bar = ""
    offset = float(CARD_LEFT)
    for _, color, prop in entries:
        width = BAR_WIDTH * prop / 100
        bar += (
            f'<rect x="{offset:.2f}" y="94" width="{width:.2f}" '
            f'height="8" fill="{color}" />\n'
        )
        offset += width

    legend = ""
    for i, (lang, color, prop) in enumerate(entries):
        column, row = divmod(i, LEGEND_ROWS)
        x = CARD_LEFT + column * LEGEND_COLUMN_WIDTH
        y = LEGEND_TOP + row * LEGEND_ROW_HEIGHT
        legend += (
            f'<rect x="{x}" y="{y - 8}" width="8" height="8" rx="2" '
            f'fill="{color}" />\n'
            f'<text class="lang" x="{x + 17}" y="{y}">{escape(lang)}</text>\n'
            f'<text class="pct" x="{x + 192}" y="{y}" '
            f'text-anchor="end">{prop:.1f}%</text>\n'
        )

    write_themed("languages.svg", "languages", {"bar": bar, "legend": legend})


def generate_stack() -> None:
    """
    Generate an SVG card listing the tech stack

    The items of a row are laid out as tspans so the renderer flows them, which
    keeps the card free of any font measuring on our side.
    """
    rows = ""
    for i, (label, items) in enumerate(STACK):
        y = STACK_TOP + i * STACK_ROW_HEIGHT
        # Non-breaking spaces: a plain space around the separator would be
        # collapsed away by the renderer's default whitespace handling.
        line = '<tspan class="sep">&#160;·&#160;</tspan>'.join(
            f"<tspan>{escape(item)}</tspan>" for item in items
        )
        rows += (
            f'<text class="label" x="{CARD_LEFT}" y="{y}">'
            f"{escape(label.upper())}</text>\n"
            f'<text class="item" x="{STACK_ITEMS_LEFT}" y="{y}">{line}</text>\n'
        )

    write_themed("stack.svg", "stack", {"rows": rows})


################################################################################
# Main Function
################################################################################


async def main() -> None:
    """
    Generate all badges
    """
    # Needs no API data, so it is rendered before the token is even required
    generate_stack()

    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        raise Exception("A personal access token is required to proceed!")
    user = os.getenv("GITHUB_ACTOR")
    if user is None:
        raise RuntimeError("Environment variable GITHUB_ACTOR must be set.")
    exclude_repos = os.getenv("EXCLUDED")
    excluded_repos = (
        {x.strip() for x in exclude_repos.split(",")} if exclude_repos else None
    )
    exclude_langs = os.getenv("EXCLUDED_LANGS")
    excluded_langs = (
        {x.strip() for x in exclude_langs.split(",")} if exclude_langs else None
    )
    # Convert a truthy value to a Boolean
    raw_ignore_forked_repos = os.getenv("EXCLUDE_FORKED_REPOS")
    ignore_forked_repos = (
        not not raw_ignore_forked_repos
        and raw_ignore_forked_repos.strip().lower() != "false"
    )
    async with aiohttp.ClientSession() as session:
        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=excluded_repos,
            exclude_langs=excluded_langs,
            ignore_forked_repos=ignore_forked_repos,
        )
        await asyncio.gather(generate_languages(s), generate_overview(s))


if __name__ == "__main__":
    asyncio.run(main())
