# v1 inventory: what to keep, what to drop

Milestone M1, issue #184. Decisions confirmed by txoof in PR #192.

## Problem

PaperPi v2 and epdlib v1 are new code; nothing is copied from PaperPi `v1` or epdlib `v0.6`.
Every old feature, setting and open issue therefore needs a decision, so nothing good is lost
and nothing unwanted comes back.

**Decisions:** **Keep** = same behaviour, new code. **Change** = same goal, done differently.
**Drop** = not in v2. **Add** = new in v2. For issues: **Carry (Mx)** = becomes a v2 issue in
milestone Mx; **Solved** = the v2 design removes the cause; **Close** = no longer relevant;
**Later** = after 2.0.

**Milestones:** M2 IT8951 driver test, M3 epdlib v1, M4 PaperPi core, M5 web interface,
M6 Docker install, M7 remaining plugins, M8 docs and 2.0 release, Later (M9, M10 and the
items marked Later here).

**Terms:** *schema* = a written description of every setting (name, type, allowed values,
default), used to check the config file and to build web forms. *Docker* = runs PaperPi in a
sealed-off box with all its software inside. *CI* = the automatic checks GitHub runs on every
pull request. *IT8951* = the controller chip of the 9.7" display ("HD display" in v1).

**Test hardware:** the 9.7" IT8951 display on the Pi 4 (with the HiFiBerry) for all testing,
plus a Pi 3 with a Waveshare 7.5" (`epd7in5_V2`). One display at a time.

## Options considered

1. Port v1 feature by feature: rejected, it brings back v1 workarounds (several config files,
   daemon mode, `xPlugin:` to switch a plugin off).
2. Ignore v1 and follow the plan only: rejected, v1 has good ideas and real user reports.
3. Decide item by item (chosen): this document.

## Decision

### Principle

Everything is set up through the web interface unless a command line is truly needed.

### 1. PaperPi core

| v1 feature | Decision | Why / how | Milestone |
|---|---|---|---|
| Plugin = folder with update function, layouts, sample config, sample image | Keep | Adds a settings schema and sample data. | M4 |
| Rotation by priority and minimum display time; plugins changing their own priority; higher priority interrupting | Change | txoof does not want the v1 priority method. Replacement designed in #194 (`docs/decisions/plugin-scheduling.md`). | M4 |
| Same plugin several times with different settings | Keep | E.g. weather for two cities. | M4 |
| `refresh_rate`: fetch data at most once per N seconds | Keep | Protects web services. | M4 |
| Skip unchanged screens | Change | v1 compared a marker set on every "updated"; v2 compares the image itself. | M4 |
| Crashed plugin drops to lowest priority | Change | Log clearly, retry with growing wait, never show a broken image (#159). Part of #194. | M4 |
| Plugin time limit via the alarm signal | Change | Only works in the main thread. Redesigned in #190. | M4 |
| `default` (fallback) and `splash_screen` plugins | Keep | Normal plugins, same structure and display path, no special handling. Part of the default plugin set. | M4 |
| Clean shutdown, then clear screen | Keep | Setting, see `no_wipe` below. | M4 |
| Full clear every N writes on IT8951 (`max_refresh`) | Keep | Removes leftover ghost images. In the driver. | M3 |
| Clear message when SPI is off | Keep | Common first-time mistake. | M4, M6 |
| Cache in `/tmp`, expiry by age | Change | `/tmp` uses memory on trixie. v2: on disk, with a size limit. | M4 |
| `logging.cfg` | Change | One log level setting, logs with a size limit. | M4 |
| Bundled open-licence fonts | Keep | | M4 |
| Text/background colour (incl. `random`) for colour displays | Keep | Shared by all plugins. | M7 |
| Plugins in a folder outside the application (#13) | Later | No more copying plugins into the app. Low priority. | Later |
| Jupyter notebooks, deprecated `crypto` plugin | Drop | Plain `.py` only; crypto already retired. | – |

### 2. Config

v1 merged up to three `.ini` files (base, `/etc/default` or `~/.config`, `-c`). **Change:**
one config file, checked against a schema (#186), edited in the web interface (M5).
**No import of v1 `paperpi.ini`**: v2 is set up from scratch.

| Setting | Decision | Why / how | Milestone |
|---|---|---|---|
| `display_type` | Keep | Picked from the generated driver list. | M3, M4 |
| `vcom` | Keep | Needed by IT8951. | M3 |
| `max_refresh`, `rotation`, `mirror` | Keep | Display settings. | M3 |
| `color` | Change | Driver says what it can show; one "force black and white" setting remains. | M3 |
| `log_level`, `splash`, `plugin_timeout` | Keep | Time limit: default for all, override per plugin. | M4 |
| `no_wipe` | Change | Setting "screen on exit": default clear to blank, option to keep the last image. | M4 |
| `CONFIG_VERSION` comment | Change | Real `config_version` field for later upgrades. | M4 |
| `force_onebit`, `screen_mode` (set by code) | Drop | Come from the driver. | – |
| `[Plugin: name]` section, `plugin`, `layout`, `refresh_rate`, `min_display_time` | Keep | New file format; layout picked from a list. | M4 |
| `max_priority` | Change | Depends on #194. | M4 |
| `[xPlugin: ...]` to switch off | Change | Explicit on/off setting. | M4 |

### 3. Plugins

Every M7 plugin issue starts by checking that the plugin's data source still works. If not,
ask txoof before going further. Each plugin's settings move into its schema.

| Plugin | Settings | Decision | Milestone |
|---|---|---|---|
| basic_clock | none | Keep | M4 |
| word_clock | none | Keep (txoof's favourite) | M4 |
| system_info | `storage_unit` | Keep | M4 |
| met_no | `location_name`, `lat`, `lon`, `email`, `temp_units`, `rain_units`, `windspeed` | Keep, add `altitude` (#176) | M4 |
| default, splash_screen | none | Keep as normal plugins (see core) | M4 |
| debugging | `title`, `crash_rate`, `max_priority_rate`, `min_priority` | Keep, for testing plugin crashes and changing importance | M4 |
| demo_plugin | `your_name`, `your_color` | Change: becomes the plugin template | M8 |
| dec_binary_clock | none | Keep (v1 sample config had a wrong plugin name) | M7 |
| moon_phase | `location_name` (timezone), `lat`, `lon`, `email` | Keep; timezone picked from a list | M7 |
| xkcd_comic | `max_x`, `max_y`, `resize`, `max_retries` | Keep; fix #61, #63, #64 | M7 |
| newyorker | `day_range` | Keep, if the feed still works | M7 |
| reddit_quote | `max_length`, `max_retries` | Change: same idea, different free quote source | M7 |
| slideshow | `image_path`, `order`, `frame` | Keep; image folder shared into Docker | M7 |
| lms_client | `player_name`, `idle_timeout` | Keep | M7 |
| librespot_client | `player_name`, `idle_timeout`, `port` | Change: go-librespot only, drop librespot-java/SpoCon | M7 |

### 4. Command line

| v1 option | Decision | Why / how | Milestone |
|---|---|---|---|
| `-c`, `-l`, `-V`, `--list_plugins` | Keep | Testing and troubleshooting. | M4 |
| `-C` (supported displays) | Change | Generated table in the docs and the web display list. | M3, M8 |
| `--plugin_info` | Change | From the schema, shown in docs and web interface. | M4, M5 |
| `--run_plugin_func` (find lat/lon, list timezones, find LMS servers) | Change | Web interface only, no command-line version. | M5, M7 |
| `-d`, `--add_config` | Drop | Docker runs the service; plugins are added in the web interface. | – |
| `render <plugin>` | Add | Render a plugin to PNG without a display. | M4 |

### 5. Install and docs

| v1 feature | Decision | Why / how | Milestone |
|---|---|---|---|
| `install.sh` (venv, `paperpi` user, systemd service) and `remote_install.sh` | Change | Docker + one-line install from released images. Kept: no root, uninstall and purge options. | M6 |
| systemd `Restart=on-failure` | Change | Plus a watchdog that restarts PaperPi when it stops responding. | M4, M6 |
| Waveshare drivers copied into PaperPi | Change | Drivers live in epdlib only. | M3 |
| Per-plugin requirements files, Pipfile, dev scripts, `package.sh`, Debian package lists | Drop | `uv`, `pyproject.toml` and the Docker image. | – |
| Docs generator: runs each plugin, saves sample images, writes plugin pages | Change | Same idea, run in CI, published with MkDocs. | M8 |
| Docs generator rebuilding `paperpi.ini` | Drop | Caused #98. Config reference comes from the schemas. | M8 |
| Hand-written guides (install, troubleshooting, frame/cable/case, plugin development) | Change | Rewritten for v2. | M8 |
| Spell check in CI | Keep | | M8 |

### 6. epdlib v0.6

| Feature | Decision | Why / how | Milestone |
|---|---|---|---|
| Layouts as data: block sizes as a share of the screen, fixed or relative position, explicit `type` | Keep | Core idea of epdlib. | M3 |
| Automatic font size | Change | Same method, but a size set in the layout wins (#58); documented (#19). | M3 |
| `chardist` / `maxchar` (guess characters per line from typical letter mix) | Change | Measure the real text instead. | M3 |
| TextBlock wrap, `max_lines`, "...", alignment | Keep | | M3 |
| ImageBlock fit, transparency removal, centring | Keep | Add left/right/top/bottom (#23). | M3 |
| DrawBlock shapes; padding, inverse, random position, border, colours, HTML colour names, 7-colour mapping, changes while running | Keep | | M3 |
| Image modes 1 bit / grey / colour | Change | Driver lists its modes; the layout renders in that mode. | M3 |
| 16-level grey on the 9.7" IT8951 | Keep | Core of M3, tested on the 9.7". | M3 |
| 7-colour palette reduction, optional dithering | Keep | | M3 |
| `Screen` class loading any driver by name | Change | Driver interface with time limits and guaranteed release of SPI/GPIO (#188). | M3 |
| IT8951 partial refresh | Keep | Measured in M2. | M2, M3 |
| Supported-screens table | Change | Generated from the driver list. | M3 |
| `ScreenShot` (debug images) | Change | Replaced by a virtual driver that writes PNG files. | M3 |
| `strict_enforce`, `RPi.GPIO` | Drop | Type hints with `mypy`; only `gpiod`/`spidev`. | M3 |

### 7. 4-grey mode for small Waveshare displays

epdlib PR #72 (ThomasR) added 4 grey levels for small black-and-white Waveshare displays.
His tests showed smoother text but worse photos, and grey that looked different depending on
neighbouring pixels. The Waveshare drivers for 2.7", 2.9", 3.7", 4.2" and 4.26" have this
mode; the 7.5" `epd7in5_V2` does not, so it cannot be tested here.
**Decision: Later.** The M3 driver interface lets drivers list their modes, so it can be added
without redesign.

### 8. Open v1 issues: PaperPi (28)

| Issue | Decision | Reason |
|---|---|---|
| #177 Trixie install fails | Solved (M3, M6) | Python 3.13, no `distutils`/`RPi.GPIO`, Docker. |
| #176 Weather altitude | Carry (M4) | Wrong forecasts without it. |
| #174, #172 Blank screen, "padded area too small" | Solved (M4, M5) | Layout too dense; v2 has a preview and a clear message. |
| #173 4inch HAT+ (E) | Later | No test display. |
| #167 No module ArgConfigParse | Solved (M6) | Not used; Docker has all packages. |
| #166 Grey for B/W displays | Later | See section 7. |
| #165 Releases for installer | Solved (M6) | Released Docker images. |
| #159 Stops showing images after hours | Carry (M4) | Freeze work (#185); never show a broken image. |
| #150 Waveshare displays stop HiFiBerry sound | Carry (M3) | Driver claims GPIO 24; make the pin configurable. Tested only if the 7.5" is put on a Pi with the HiFiBerry. |
| #144 Moon phase helper prompts | Solved (M5, M7) | Helpers move to the web interface. |
| #143 Requirements scripts | Close | `uv` replaces them. |
| #140 JSON config refactor | Solved (M4) | New config and schema (#186). |
| #139 Menu-driven command-line setup | Close | The web interface does this. |
| #130 Docs builder updates | Solved (M8) | Docs generated in CI. |
| #123 Web interface | Solved (M5) | Milestone M5. |
| #98 Docs builder overwrites ini | Close | v2 builder writes no config. |
| #56 Bad config file exit | Solved (M4) | Schema check with clear messages. |
| #42 install.sh prompt | Close | Installer replaced. |
| #41 Pipfile dev script | Close | Gone. |
| #35 Conflicting ini files | Solved (M4) | One config file. |
| #13 Packaging plugins | Later | Configurable plugin folder outside the app. |
| #60 Missing font crashes PaperPi | Carry (M4) | Switch off that plugin with a clear error. |
| #61, #63, #64 xkcd resize, comic number, border | Carry (M7) | |
| #65 Reddit quote clean-up | Close | New quote source (section 3). |
| #62 Layouts without restart | Solved (M5) | Changes apply without restart (#189). |

### 9. Open v1 issues: epdlib (6)

| Issue | Decision | Reason |
|---|---|---|
| #73 3.7" screen | Later | No test display. |
| #71 4-grey for epd2in7 | Later | See section 7. |
| #58 Force larger font size | Carry (M3) | Layout font size must win. |
| #23 Image alignment | Carry (M3) | |
| #19 Docs on font size and overflow | Carry (M3) | |
| #14 Italic fonts cut off | Carry (M3) | Measure the real outline; image test. |

txoof closes the old issues marked Solved and Close; Carry and Later items become new issues.

## Decisions by txoof

1. Test hardware: 9.7" IT8951 on the Pi 4 (preferred), and a Waveshare 7.5" `epd7in5_V2` on a Pi 3. One display at a time.
2. 16-level grey on the 9.7" is core M3; 4-grey for small Waveshare displays is Later.
3. reddit_quote: same idea, different free quote source (M7).
4. librespot_client: go-librespot only.
5. Every M7 plugin issue first checks its data source still works; if not, ask txoof.
6. basic_clock and word_clock are M4 plugins, not M7.
7. default and splash_screen are normal plugins in the default set, built in M4.
8. debugging stays as a test plugin; demo_plugin becomes the template; priority is redesigned in #194.
9. Screen on exit is a setting: default clear, option to keep the last image.
10. Everything goes through the web interface unless truly necessary; plugin helpers are web only.
11. Close #139.
12. #13 becomes Later: a configurable plugin folder outside the app.
13. No import of v1 `paperpi.ini`.
