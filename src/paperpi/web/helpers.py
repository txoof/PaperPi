"""Setting helpers: an extra part of the settings page, under one setting's field, for a
setting that needs more than a plain field (``docs/decisions/web-interface.md``).

A plugin names a helper with ``paperpi.plugin.setting(..., helper="location")``. A helper
here is a function that gets the field (:class:`paperpi.web.forms.FormField`) and returns
the HTML to show under it. A name that is not in :data:`HELPERS` (yet) shows nothing, so
the plain field still works. The first helper, ``location`` (look up a place's latitude
and longitude), comes in M5 part 3c; new ones are added when a plugin needs one.
"""

from __future__ import annotations

from collections.abc import Callable

from markupsafe import Markup

from .forms import FormField

#: The helpers the settings page knows, by name.
HELPERS: dict[str, Callable[[FormField], Markup]] = {}


def helper_html(field: FormField) -> Markup:
    """The HTML of the helper ``field`` names, or nothing."""
    helper = HELPERS.get(field.helper) if field.helper else None
    return helper(field) if helper is not None else Markup("")
