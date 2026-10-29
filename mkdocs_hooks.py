"""MkDocs hooks (see "hooks" in mkdocs.yml): add the pages made from PaperPi's code.

The pages themselves are written by ``paperpi.manual``; this file only hands them to MkDocs:
the settings reference, the list of plugins and a page per plugin (added to the "Plugins"
part of the menu), and the pictures they show. It also fills the tables of screens into
docs/screens.md, and keeps the address of the old Waveshare screens page working.
"""

from __future__ import annotations

from pathlib import Path

from mkdocs.structure.files import File, Files, InclusionLevel
from mkdocs.structure.nav import Navigation

from paperpi import manual, plugins

ROOT = Path(__file__).parent


def on_files(files: Files, config) -> Files:
    types = plugins.available()
    pages = {"settings.md": manual.settings_page()}
    pages["plugins/index.md"], used = manual.plugins_page(types, ROOT)
    for plugin_type in types:
        pages[f"plugins/{plugin_type}.md"], shown = manual.plugin_page(plugin_type, types, ROOT)
        used |= shown
    for path, text in pages.items():
        # The plugins' pages are added to the menu in on_nav, so MkDocs need not warn.
        in_menu = path.startswith("plugins/") and path != "plugins/index.md"
        inclusion = InclusionLevel.NOT_IN_NAV if in_menu else InclusionLevel.UNDEFINED
        files.append(File.generated(config, path, content=text, inclusion=inclusion))
    for path in sorted(used):
        site_path = f"plugins/{manual.FILES}{path}"
        files.append(File.generated(config, site_path, abs_src_path=str(ROOT / path)))
    return files


def on_nav(nav: Navigation, config, files: Files) -> Navigation:
    section = next(item for item in nav.items if item.title == "Plugins")
    for plugin_type in manual.listed(plugins.available()):
        page = files.get_file_from_path(f"plugins/{plugin_type}.md").page
        page.parent = section
        section.children.append(page)
    return nav


def on_page_markdown(markdown: str, page, config, files: Files) -> str:
    if page.file.src_uri == "screens.md":
        markdown = manual.fill_screens(markdown)
    return manual.site_links(markdown, page.file.src_uri, (f.src_uri for f in files))


def on_post_build(config) -> None:
    # The Waveshare screens page is now part of Supported screens; the web interface of
    # PaperPi 2.0.0a1 still links to its old address.
    old = Path(config["site_dir"]) / "waveshare-screens" / "index.html"
    old.parent.mkdir(exist_ok=True)
    old.write_text(
        '<!doctype html><meta charset="utf-8"><title>Supported screens</title>'
        '<meta http-equiv="refresh" content="0; url=../screens/#waveshare">'
        '<a href="../screens/#waveshare">Supported screens</a>\n'
    )
