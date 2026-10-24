"""Links in a setting's help text (its ``description``), written as ``[text](target)``:

    ns_key: SecretStr = Field(..., description="NS API key needed for trains. See the "
                              "[README](readme) for information on obtaining a free key")

The target is ``readme`` (the plugin's README page in the web interface) or a web address
(``https://...``, ``http://...``). The settings page shows the link; the config file and the
other plain-text places show only its text ("See the README for ..."). Anything else in
brackets stays as it is written.
"""

from __future__ import annotations

import re

#: ``[text](target)``: the text may not hold brackets, the target no spaces or parentheses.
LINK = re.compile(r"\[([^\[\]]+)\]\((readme|https?://[^\s()]+)\)")
README = "readme"


def plain(text: str) -> str:
    """``text`` with each link replaced by its text."""
    return LINK.sub(r"\1", text)


def parts(text: str, readme: str) -> tuple[tuple[str, str], ...]:
    """``text`` as (text, address) pairs in order; the address is ``""`` for plain text.
    ``readme`` is the address of the plugin's README page."""
    found = []
    at = 0
    for link in LINK.finditer(text):
        if link.start() > at:
            found.append((text[at : link.start()], ""))
        target = link.group(2)
        found.append((link.group(1), readme if target == README else target))
        at = link.end()
    if at < len(text):
        found.append((text[at:], ""))
    return tuple(found)
