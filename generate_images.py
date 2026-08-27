#!/usr/bin/python3

import asyncio
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
# The values are Primer tokens, so the cards sit on a GitHub page as if they
# were part of it: canvas.default, canvas.subtle, fg.default, fg.muted,
# border.default, the neutral fill GitHub uses behind a language bar, and the
# accent pair a topic tag is drawn in.
THEMES: Dict[str, Dict[str, str]] = {
    "": {
        "bg": "#ffffff",
        "subtle": "#f6f8fa",
        "fg": "#1f2328",
        "muted": "#59636e",
        "border": "#d1d9e0",
        "track": "#eaeef2",
        "accent": "#0969da",
        "accent_bg": "#ddf4ff",
    },
    "-dark": {
        "bg": "#0d1117",
        "subtle": "#151b23",
        "fg": "#f0f6fc",
        "muted": "#9198a1",
        "border": "#3d444d",
        "track": "#30363d",
        "accent": "#4493f8",
        "accent_bg": "#121d2f",
    },
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

# Card geometry, mirrored from the templates. The 16px padding and the 44px
# header strip are the ones Primer's Box uses.
CARD_LEFT = 16
BAR_Y = 64
BAR_WIDTH = 428
LEGEND_TOP = 100
LEGEND_ROW_HEIGHT = 28
LEGEND_ROWS = 3
LEGEND_COLUMN_WIDTH = 206
LEGEND_COLUMN_GAP = 16
STACK_TOP = 60
STACK_ROW_HEIGHT = 32
STACK_ITEMS_LEFT = 152

# A stack item is drawn as the pill GitHub puts a repository topic in: 24px
# tall, fully rounded, 10px of padding on either side of a 12px label.
TAG_HEIGHT = 24
TAG_PADDING = 10
TAG_GAP = 6


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
    Shorten large numbers so a row stays on one line: 525070 becomes 525K
    :param value: number to format
    :return: formatted number
    """
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 10_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:,}"


# Advance widths per 1000 units for the medium weight of a Helvetica-like face,
# which is close enough to the system stack the cards render in to size a pill
# around its label. The text is centred inside the pill, so what little the
# estimate is off by lands in the padding on both sides rather than clipping.
CHAR_WIDTHS: Dict[str, int] = {
    " ": 278, "-": 333, ".": 278, "/": 278, "&": 722, "+": 584,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556,
    "6": 556, "7": 556, "8": 556, "9": 556,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
}


def text_width(text: str, size: int) -> float:
    """
    Estimate how wide a string renders, so a pill can be sized around it
    :param text: string to measure
    :param size: font size in pixels
    :return: width in pixels
    """
    return sum(CHAR_WIDTHS.get(c, 611) for c in text) * size / 1000


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
    for suffix, palette in THEMES.items():
        with open(f"generated/{output_name}{suffix}.svg", "w") as f:
            f.write(render(template, {**values, **palette}))


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
            f'<rect x="{offset:.2f}" y="{BAR_Y}" width="{width:.2f}" '
            f'height="8" fill="{color}" />\n'
        )
        offset += width

    legend = ""
    for i, (lang, color, prop) in enumerate(entries):
        column, row = divmod(i, LEGEND_ROWS)
        x = CARD_LEFT + column * (LEGEND_COLUMN_WIDTH + LEGEND_COLUMN_GAP)
        y = LEGEND_TOP + row * LEGEND_ROW_HEIGHT
        # A filled dot in the language colour, the same marker GitHub puts in
        # front of a language everywhere it lists one
        legend += (
            f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{color}" />\n'
            f'<text class="lang" x="{x + 18}" y="{y}">{escape(lang)}</text>\n'
            f'<text class="pct" x="{x + LEGEND_COLUMN_WIDTH}" y="{y}" '
            f'text-anchor="end">{prop:.1f}%</text>\n'
        )

    write_themed("languages.svg", "languages", {"bar": bar, "legend": legend})


def generate_stack() -> None:
    """
    Generate an SVG card listing the tech stack

    Every item becomes a topic tag, the pill GitHub lists a repository's topics
    in, so the row reads as part of the page rather than as a caption.
    """
    rows = ""
    for i, (label, items) in enumerate(STACK):
        top = STACK_TOP + i * STACK_ROW_HEIGHT
        baseline = top + 16
        rows += f'<text class="label" x="{CARD_LEFT}" y="{baseline}">{escape(label)}</text>\n'

        # The pill fill stays a placeholder: write_themed substitutes the rows
        # before the palette, so it is resolved along with the template's own.
        x = float(STACK_ITEMS_LEFT)
        for item in items:
            width = round(text_width(item, 12)) + 2 * TAG_PADDING
            rows += (
                f'<rect x="{x:.1f}" y="{top}" width="{width}" '
                f'height="{TAG_HEIGHT}" rx="{TAG_HEIGHT / 2}" '
                f'fill="{{{{ accent_bg }}}}" />\n'
                f'<text class="topic" x="{x + width / 2:.1f}" y="{baseline}" '
                f'text-anchor="middle">{escape(item)}</text>\n'
            )
            x += width + TAG_GAP

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
