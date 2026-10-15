"""A plugin's ``README.md`` as part of a web page (the Plugin Library's README page).

The README is written for GitHub, next to the code. In the web interface:
- its first heading is left out (the page has its own, with the plugin's title);
- pictures are left out: they are in ``tests/images/``, which is not installed (the
  Library shows the plugin's own example pictures), and so are the "Sample images"
  section and the paragraphs, table rows and tables left empty without them;
- a link to another plugin's README opens that plugin's README page; links to websites
  stay; other links (files of PaperPi's source, places in the page) become plain text;
- HTML written in the README is shown as text, not used.
"""

from __future__ import annotations

import re
from collections.abc import Collection

from markdown_it import MarkdownIt
from markdown_it.token import Token

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")
_OTHER_README = re.compile(r"(?:\.\./)?([a-z][a-z0-9_]*)/README\.md(?:#.*)?")
_EMPTY_LINK = re.compile(r"<a href=\"[^\"]*\">(?:\s|<(em|strong)>\s*</\1>)*</a>")
_EMPTY_PARAGRAPH = re.compile(r"<p>\s*</p>\n?")
_EMPTY_ROW = re.compile(r"<tr>(?:\s*<t[dh](?: [^>]*)?>\s*</t[dh]>)+\s*</tr>\s*")
_EMPTY_BODY = re.compile(r"<tbody>\s*</tbody>\s*")
_HEAD_ONLY = re.compile(r"<table>\s*<thead>(?:(?!</table>).)*</thead>\s*</table>\s*", re.DOTALL)
_EMPTY_TABLE = re.compile(r"<table>\s*(?:<thead>\s*</thead>\s*)?</table>\s*")


def to_html(text: str, plugin_types: Collection[str]) -> str:
    """``text`` (Markdown) as HTML; ``plugin_types`` are the plugins with a README page."""
    tokens = _MD.parse(text)
    if len(tokens) >= 3 and tokens[0].type == "heading_open" and tokens[0].tag == "h1":
        tokens = tokens[3:]
    tokens = _without_section(tokens, "Sample images")
    for token in tokens:
        if token.type == "inline" and token.children:
            token.children = _inline(token.children, plugin_types)
    found = _MD.renderer.render(tokens, _MD.options, {})
    found = _EMPTY_LINK.sub("", found)  # a link that only held a picture
    found = _EMPTY_PARAGRAPH.sub("", found)  # a paragraph that only had pictures
    found = _EMPTY_ROW.sub("", found)
    found = _EMPTY_BODY.sub("", found)
    found = _HEAD_ONLY.sub("", found)
    return _EMPTY_TABLE.sub("", found)


def _without_section(tokens: list[Token], title: str) -> list[Token]:
    """``tokens`` without the ``##`` section called ``title`` (up to the next one)."""
    kept: list[Token] = []
    skipping = False
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag in ("h1", "h2"):
            heading = "".join(t.content for t in tokens[index + 1].children or [])
            skipping = token.tag == "h2" and heading.strip().casefold() == title.casefold()
        if not skipping:
            kept.append(token)
    return kept


def _inline(children: list[Token], plugin_types: Collection[str]) -> list[Token]:
    kept: list[Token] = []
    opened: list[bool] = []  # per open link: is it kept?
    for token in children:
        if token.type == "image":
            continue
        if token.type == "link_open":
            href = _href(str(token.attrGet("href") or ""), plugin_types)
            opened.append(href is not None)
            if href is None:
                continue
            token.attrSet("href", href)
        elif token.type == "link_close" and not opened.pop():
            continue
        kept.append(token)
    return kept


def _href(href: str, plugin_types: Collection[str]) -> str | None:
    """Where a link in a README goes on the web page; ``None``: no link (plain text)."""
    if href.startswith(("https://", "http://")):
        return href
    other = _OTHER_README.fullmatch(href)
    if other and other.group(1) in plugin_types:
        return f"/library/{other.group(1)}/readme"
    return None
