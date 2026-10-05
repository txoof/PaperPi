"""The plugins that come with PaperPi, one folder each.

Each folder's ``__init__.py`` defines ``PLUGIN``, a :class:`paperpi.plugin.Plugin`.
"""

from __future__ import annotations

import importlib
import pkgutil

from ..plugin import Plugin, PluginDefinitionError


def available(package: str = __name__) -> list[str]:
    """The plugin types in ``package`` (default: this folder), sorted. Doesn't import them."""
    path = importlib.import_module(package).__path__
    return sorted(m.name for m in pkgutil.iter_modules(path) if m.ispkg)


def load(plugin_type: str, package: str = __name__) -> Plugin:
    """Import the plugin ``plugin_type`` and return its ``PLUGIN``.

    ``package`` is where to look; tests use it for fake plugins. Raises ``KeyError`` for
    an unknown type and :class:`PluginDefinitionError` for a plugin that breaks the
    interface.
    """
    if plugin_type not in available(package):
        raise KeyError(plugin_type)
    module = importlib.import_module(f"{package}.{plugin_type}")
    plugin = getattr(module, "PLUGIN", None)
    if not isinstance(plugin, Plugin):
        raise PluginDefinitionError(f"plugin {plugin_type!r}: __init__.py has no PLUGIN")
    if plugin.type != plugin_type:
        raise PluginDefinitionError(
            f"plugin {plugin_type!r}: PLUGIN.type is {plugin.type!r}, must match the folder"
        )
    return plugin
