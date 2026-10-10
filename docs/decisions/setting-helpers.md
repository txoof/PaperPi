# Setting helpers

Status: proposed (M5 part 3c, issue #238). Talked through with txoof on 2026-10-10; the open questions at the end are still to be answered.

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
4. **A helper is a plain function that returns data; PaperPi shows one standard search box and pick list for all of them.** **Chosen.**

## Decision (proposed)

### What a helper is

- A helper is a Python function with a few texts for the page:
  - the text above the search box, e.g. "Place name, e.g. Berlin or Morrison, Colorado";
  - the button text (default "Search"). A helper that needs no typed text (finding music servers) shows only a button, e.g. "Find servers";
  - where the answers come from, with a link, shown under the list (e.g. "Search by Open-Meteo"). The user sees that their typed text goes to an outside service, and the credit that service asks for is given;
  - optional: settings that must be filled in first (the NS API key). Until they are, the box says so instead of searching.
- The function gets what the user typed and the other values in the form, checked as Save would check them. An empty secret field (an API key) gives the saved secret, as in a preview (`web-interface.md`).
- It returns a list of **choices**. Each choice has a label ("Morrison"), a detail line ("Colorado, United States, 1757 m") and the settings it fills in, e.g. `lat`, `lon` and `altitude`.
- It may also stop with a message for the user ("The NS API key was not accepted"). Any other error shows "The search failed" and the details go to the log.
- It uses `paperpi.webrequest` for web requests, like plugins do, so the same time limits and size limits apply.

### Where helpers come from

- **PaperPi's own helpers** are for needs many plugins share. The first is `location`.
- **A plugin's own helpers** are part of the plugin, next to its settings and layouts (e.g. a stop search in the Dutch transport plugin).
- A setting names its helper as now: `setting(..., helper="location")`. The plugin's own helpers are looked up first, then PaperPi's. A name that is found nowhere fails the plugin check, so a typing mistake is caught by the tests and not on the user's page.
- The search box is shown under the setting that names the helper. A choice may fill in several settings; PaperPi fills in only settings the plugin has, and checks the values with the plugin's settings description before they go into the form.

### How a helper runs

- In a new, short-lived process with a time limit, as plugin updates and previews are, so a helper that hangs or crashes can't stop the web interface or PaperPi. Time limit: 30 seconds, the same as one web request with its retry (`errors-and-time-limits.md`).
- One search at a time; a second one meanwhile is asked to wait, as with the Preview button.
- The typed text may be at most 100 characters. At most 10 choices are shown.

### On the settings page

- Under the field: the text, a search box and the button. After a search, the list of choices appears, each with a **Use** button. "Nothing found" comes with a hint (check the spelling, or try a larger place).
- **Use** fills in the form's fields. **Nothing is saved yet**: the user sees the values, can change them, can press Preview, and then Save. The list stays until the next search, so a wrong pick is easy to change.
- No new JavaScript library: htmx (already shipped) sends the search and puts the values in the fields.
- Typing the values by hand keeps working. When the service can't be reached, the page says so and the fields are left as they are.

### Later (described so they fit, not built until a plugin needs them)

- **Logging in to an outside account:** a helper may return a **step** instead of choices: a message with a link and a code ("Open example.com/device on your phone and enter ABCD-1234"). PaperPi then calls the helper again every few seconds, each call in its own process with its own time limit, until it returns a choice (the token, which fills a secret setting) or stops with a message. The rest of the structure stays the same.
- **Sandboxed plugin pages** (option 2 in its safe form), if a plugin ever needs more than a search box and a list.

### The first helper: `location`

- Uses the place search of **Open-Meteo** (`geocoding-api.open-meteo.com`), chosen with txoof on 2026-10-10. No key and no sign-up. It finds towns and cities (not street addresses) and returns region, country, latitude, longitude **and altitude**; Nominatim, which v1 used, returns no altitude. It understands "Morrison, Colorado"; a plain "Morrison" returns 10 towns in several countries, so region and country are shown with each choice.
- Terms: free for non-commercial use, fewer than 10,000 requests a day. The data is CC BY 4.0 and the place data is from GeoNames, so the page shows "Search by Open-Meteo, place data from GeoNames" with links next to the list.
- A choice fills in `lat` and `lon` (4 decimals, about 10 m), `altitude` (whole metres, as met.no asks) and, when it is still empty, the name shown on the screen (`place` in `met_no`).
- `met_no` gets an optional `altitude` setting (whole metres, -500 to 9000), sent to met.no when it is filled in. This closes issue #176. The example in #176 had a sign mistake: `lon = 84.31` is on the Tibetan plateau, where met.no's 4949 m is right; Atlanta is at `-84.31`.
- `moon_phase` uses it for `lat` and `lon` only; altitude doesn't matter for it.

### Planned PRs

1. This note, the helper structure (functions, choices, the separate process, plugin check) and the search box with its pick list, tested with a helper in the `debugging` plugin. About 500 lines.
2. The `location` helper with Open-Meteo, `altitude` for `met_no`, and both plugins using it. About 400 lines.

## Open questions

To be answered with txoof one at a time:
1. Does the search start with the button (and Enter), or while the user types?
2. Should helpers also work from the command line on the Pi (e.g. `paperpi find <plugin id> "Morrison, Colorado"`, printing the choices as lines to copy into the config file), and if so in these PRs or later?
3. Should `location` fill in the name shown on the screen when it is empty, as proposed above?
