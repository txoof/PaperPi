# Setting helpers

Status: decided with txoof on 2026-10-10 (M5 part 3c, issue #238).

## Problem

Some plugin settings are hard to fill in by hand:
- `met_no` and `moon_phase` need latitude and longitude. Most people don't know them for their town. `met_no` also gives better temperatures with the place's altitude (issue #176; met.no calls altitude "optional but recommended", because its own height map is coarse in hilly places).
- The planned Dutch public transport plugin needs stop and station codes. Users should find them by name and pick from a list, never type codes. The NS station search needs the NS API key typed in the same form.
- `lms_client` (M7) needs the address of a music server on the home network. PaperPi can find it by asking the network.
- A later plugin may need the user to log in to an outside account (a calendar, Spotify): open a link on another device, enter a code, wait until it is confirmed, then save a token.

v1 had a command per plugin for latitude and longitude (`met_no.get_coord`). It used OpenStreetMap's Nominatim, printed only the first match (so a town with a common name could give the wrong place without anyone noticing), had no time limit, and didn't send the contact name Nominatim's rules ask for.

v2 so far: a setting can name a helper (`setting(..., helper="location")`), and the web code has a list of helpers that each return a piece of HTML for the settings page (`src/paperpi/web/helpers.py`). The list is still empty. With that design every new helper means new web code, and a plugin can't bring a helper of its own.

## Options considered

1. **Each helper is written in the web code** (the design so far). Rejected: every plugin with a special need changes the web code, and a plugin's own search (the Dutch stops) would live outside the plugin.
2. **A plugin sends its own HTML or script.** Rejected:
   - It would run inside the logged-in page, where it could read and change every setting, API keys too. The pages now allow only PaperPi's own files (`default-src 'self'`), and that rule would have to be loosened.
   - Each plugin's part would look different and could break on phones or when the web interface changes.
   - It can't be used from the command line.
   - A safer form exists: the plugin's page runs in a locked box inside the page (a "sandboxed iframe") that can't reach the rest. That is a lot of work no plugin needs yet; it stays on the "Later" list.
3. **A map to search on** (a small map library such as Leaflet, with map pictures from OpenStreetMap). Rejected by txoof on 2026-10-10: a place or stop is searched once, when the plugin is set up, so a map is too much work and upkeep for it.
4. **A helper is a plain function of the plugin that returns data (a dictionary per choice); PaperPi shows one standard search box and pick list for all of them.** **Chosen.**

## Decision

### Who does what

- **PaperPi owns the page:** a search box, a list of choices, and putting the chosen one into the form. It doesn't need to know what a place, a stop or a server is.
- **The plugin owns its settings:** what they mean and which ones a search changes. So the logic of a search lives in the plugin, and a new kind of plugin needs nothing new from PaperPi.
- Agreed with txoof on 2026-10-10. An earlier draft gave each choice fixed parts (a label, a detail line, values that are "set" or "suggested") guessed from the few plugins we know; a dictionary of kinds (below) fits plugins nobody has thought of yet.

### What a helper is

- A helper is a Python function of the plugin, with a few texts for the page:
  - the text above the search box, e.g. "Place name, e.g. Berlin or Morrison, Colorado";
  - the button text (default "Search"). A helper that needs no typed text (finding music servers) shows only a button, e.g. "Find servers";
  - where the answers come from, with a link, shown under the list (e.g. "Search by Open-Meteo"). The user sees that their typed text goes to an outside service, and the credit that service asks for is given;
  - optional: settings that must be filled in first (the NS API key). Until they are, the box says so instead of searching.
- The function gets what the user typed and the form's current settings, checked as Save would check them. An empty secret field (an API key) gives the saved secret, as in a preview (`web-interface.md`).
- It returns a **result**: a list of **choices**, and optionally a `note` for the whole result (below).
- It may also stop with a message for the user ("The NS API key was not accepted"). Any other error shows "The search failed" and the details go to the log.
- It uses `paperpi.webrequest` for web requests, like plugins do, so the same time limits and size limits apply.

### What a choice is

A choice is a dictionary. Each key is a **kind** that says what PaperPi does with its value. For a Dutch transport stop:

```python
{
    "fill": {"stop_code": "3104", "stop_name": "Nieuwe Duinweg"},
    "show": {"Stop": "Nieuwe Duinweg", "Town": "Den Haag", "Lines": "9, 21", "Distance": "120 m"},
    "link": {"See on map": "https://www.openstreetmap.org/?mlat=52.09&mlon=4.29"},
}
```

**Kinds built now** (three kinds for a choice, plus `note` for the whole result; the first helper, `location`, uses all of them):

| Kind | Where | What PaperPi does with it |
|---|---|---|
| `fill` | choice | Settings put into the form when the user presses **Use**. The keys are the plugin's own setting names. PaperPi checks them with the plugin's settings description, as Save does, so a wrong name or value is an error and never a broken setting. Only what is in `fill` changes, so a helper leaves a setting alone by leaving it out (e.g. the name shown on the screen, when the user has already typed one). Only settings the form shows as a field: not secrets, and not settings that are changed in the file. |
| `show` | choice | Information to help the user pick: label and text, shown in the order given. The first entry is the heading of the choice. |
| `link` | choice | Web addresses the user can open in a new tab, e.g. "See on map". Only `http` and `https` addresses; others are left out and logged. |
| `note` | result | A message for the whole result, e.g. "Only the first 10 matches are shown; type more to narrow it down". |

**Kinds planned** (same dictionary shape; each is built with the first plugin that needs it):

| Kind | What it would do | Likely first user |
|---|---|---|
| `add` | Adds an item to a list setting instead of replacing a field (each **Use** adds one stop). | Dutch transport plugin |
| `next` | Choosing starts a second search instead of filling in fields: pick a stop, then a direction or line; pick a music server, then a player on it. | Dutch transport plugin, `lms_client` |
| `disabled` | The choice is shown but can't be used, with the reason ("No trains to Utrecht from this station"). | NS trains |
| `picture` | A small image next to the choice (a station logo, an album cover), sent inside the page like preview images. | music plugins |
| `wait` | For logging in to an outside account: show a message, a link and a code ("Open example.com/device on your phone and enter ABCD-1234"), and ask the helper again every few seconds, each call in its own process with its own time limit, until it returns a choice (e.g. a token in a secret setting) or stops with a message. | a calendar or Spotify plugin |

- **A kind PaperPi doesn't know is ignored and logged**, so a plugin written for a newer PaperPi still works on an older one.
- **All texts are shown as plain text**, so a stop name with odd characters can't change the page. Each text is put on one line and cut to 200 characters.
- What happens after **Use** (such as drawing a preview at once) is the same for every plugin, so the page decides it, not each helper.

### Where helpers come from

- Helpers are part of the plugin, next to its settings and layouts. A setting names one as now: `setting(..., helper="location")`, and the search box is shown just before that setting, so name the first of the settings it fills. A name the plugin doesn't have fails the plugin check, so a typing mistake is caught by the tests and not on the user's page.
- **PaperPi offers search functions** for needs many plugins share. The first is a place search: "find places for this text" returns places with name, region, country, latitude, longitude and altitude. A plugin's helper calls it and turns each place into a choice for its own settings.
- For the common case PaperPi also has a **ready-made location helper**: the plugin only names its settings for latitude, longitude and, if it has them, altitude and the name shown on the screen. This is a shortcut built on the place search, not a separate idea.

### How a helper runs

- In a new, short-lived process with a time limit, as plugin updates and previews are, so a helper that hangs or crashes can't stop the web interface or PaperPi. Time limit: 30 seconds, the same as one web request with its retry (`errors-and-time-limits.md`).
- One search at a time; a second one meanwhile is asked to wait, as with the Preview button.
- The typed text may be at most 100 characters. At most 10 choices are shown.

### On the settings page

- Just before the setting's field: the text, a search box and the button (txoof, 2026-10-10: the search comes first, then the fields it fills). The search starts with the button or the Enter key, not while the user types (txoof, 2026-10-10): one request per search, which matters for services with a daily limit such as NS. After a search, the list of choices appears, each with a **Use** button. "Nothing found" comes with a hint (check the spelling, or try a larger place).
- **Use** fills in the form's fields. **Nothing is saved yet**: the user sees the values, can change them, can press Preview, and then Save. The list stays until the next search, so a wrong pick is easy to change.
- No new JavaScript library: htmx (the small script the pages already use) sends the search and puts the values in the fields.
- Typing the values by hand keeps working. When the service can't be reached, the page says so and the fields are left as they are.

### Later (described so they fit, not built until a plugin needs them)

- **On the command line** (txoof, 2026-10-10: later, as its own issue): `paperpi helper <plugin type>.<helper> "<text>"`, e.g. `paperpi helper met_no.location "Morrison, Colorado"`. It prints each choice's `show` and `link` texts and its `fill` values as lines to copy into the plugin's block in the config file. It names the plugin type, not a plugin `id`, so it works before the plugin is in the config file. To decide in that issue: how a helper that needs other settings first (the NS API key) gets them, e.g. from a plugin block in the config file or typed after the text.
- **The planned kinds** in the table above.
- **Sandboxed plugin pages** (option 2 in its safe form), if a plugin ever needs more than a search box and a list.

### The first helper: `location` in `met_no` and `moon_phase`

- The place search uses **Open-Meteo** (`geocoding-api.open-meteo.com`), chosen with txoof on 2026-10-10. No key and no sign-up. It finds towns and cities (not street addresses) and returns region, country, latitude, longitude **and altitude**; Nominatim, which v1 used, returns no altitude. It understands "Morrison, Colorado"; a plain "Morrison" returns 10 towns in several countries, so region and country are shown with each choice.
- Terms: free for non-commercial use, fewer than 10,000 requests a day. The data is CC BY 4.0 and the place data is from GeoNames, so the page shows "Search by Open-Meteo, place data from GeoNames" with links next to the list.
- A choice:
  - `fill`: `lat` and `lon` (4 decimals, about 10 m), `altitude` (whole metres, as met.no asks), and the name shown on the screen (`place` in `met_no`) only when it is still empty, so a name the user typed ("Home", "Cabin") is kept;
  - `show`: place, region, country, altitude;
  - `link`: "See on map" (OpenStreetMap at that point), so the user can check the place without a map in PaperPi.
- `met_no` gets an optional `altitude` setting (whole metres, -500 to 9000), sent to met.no when it is filled in. This closes issue #176. The example in #176 had a sign mistake: `lon = 84.31` is on the Tibetan plateau, where met.no's 4949 m is right; Atlanta is at `-84.31`.
- `moon_phase` uses it for `lat` and `lon` only; altitude doesn't matter for it.

### Planned PRs

1. This note, the helper structure (helper functions, results with the four kinds, the separate process, plugin check) and the search box with its pick list, tested with a helper in the `debugging` plugin. About 900 lines (txoof chose one PR over two on 2026-10-10).
2. The place search with Open-Meteo, the ready-made location helper, `altitude` for `met_no`, and both plugins using it. About 400 lines.

## Open questions

None. Answered with txoof on 2026-10-10:
1. The search starts with the button or the Enter key, not while the user types.
2. The command line comes later, as its own issue, as `paperpi helper met_no.location "Morrison, Colorado"` (see "Later").
3. The name shown on the screen is filled in only when it is empty. This is decided by the helper (it leaves `place` out of `fill`), not by a rule in PaperPi (see "What a choice is").
