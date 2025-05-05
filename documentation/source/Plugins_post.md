## Configuration
Each plugin is configured through a [Plugin: Name] section in the configuration files. 

Plugins can be added multiple times (e.g. to show weather in multiple locations or track multiple LMS Players), but each plugin configuration section must have a unique name.

To use a plugin, add a configuration section for each plugin instance to the appropriate configuration file:
 * user: `~/.config/com.ysadamt.paperpi/paperpi.ini`
  * daemon: `/etc/default/paperpi.ini`
   
   Plugin configuration sections follow this pattern. Some plugins require extra configuration such as API keys or lat/lon data.

   *NB: whitespace and comments are ignored*
   ```
   [Plugin: Human Friendly Name For Plugin]
   # layout to use
   layout = layout
   # this should match the directory and plugin name exactly
   plugin = plugin_name
   # maximum refresh rate in seconds
   refresh_rate = int
   # maximum priority for this plugin -- lower numbers are higher priority, -1 will always display
   max_priority = int
   # minimum amount of time plugin should stay on the screen when displayed
   min_display_time = int
   ```

   Plugins provide a sample configuration in their documentation. Use the following commands to find a list of plugins and view their sample configurations:

   **List Available Plugins**

   `paperpi --list_plugins`

   **Show Plugin Documentation**

   `paperpi --plugin_info plugin_name`

   **Add Default Configuration**

   Paperpi can add the default plugin configuration to either the user or daemon config files.

   `paperpi --add_config plugin_name user|daemon`

   *NB:* It is important to check the configuration file; some plugins require additional configuration

### Configuration Elements

**Section Header**: `[Plugin: Human-Friendly Name for Plugin]`
* all plugin sections must **start** with `[Plugin: XXXX]` where XXX is a user-chosen descriptive string
* all section headers must be unique
* enabled: `[Plugin: name]`
* disabled: `[xPlugin: name]`

**Plugin Name**: `plugin = plugin_name`
* module name of plugin
* use `--list_plugins` to see available plugin names

**Layout Definition**: `layout = layout`
* screen layout that defines how to organize plugin graphical and text elements
* use `--plugin_info plugin_name` to see available layouts
* see the documentation for each plugin for a sample of all available layouts
* some layouts may be more appropriate for smaller screens

**Refresh Rate**: `refresh_rate = integer in seconds`
* this controls how often the plugin is checked for new data
* some services such as spotify or MET.NO will ban users that request updates too frequently. Use caution when setting this.
* each plugin has a recommended `refresh_rate` use `--plugin_info plugin_name` to view a sample configuration

**Maximum Priority**: `max_priority = integer`
* **LOWER** numbers are a higher priority (-1 is very high and will likely display immediately, 64000 will never be shown)
* a music plugin should likely be set to `0` to ensure that when a track change happens the display is updated
* a clock plugin that displays when music players are idle should be set to 2
* plugins with the lowest integer value will be displayed in the display loop
* some plugins change their priority when events happen such as when an audio track changes, music is paused, or a device becomes idle
* this value determines the maximum priority the plugin will use when it determines an important event has occurred.
* recommended values can be found by using `--plugin_info plugin_name`

**Minimum Display Time** `min_display_time = integer in seconds`
* number of seconds plugin should stay on the screen before another plugin is cycled
* recommended values can be found using `--plugin_info plugin_name`


### Additional Configuration Elements

Some plugins require additional configuration such as API keys, location information or other configuration details. Use `--plugin_info plugin_name` to find a sample configuration. Check the plugin README for additional information.


## Developing Plugins

PaperPi is designed to support additional plugins written in Python 3. Any modules available through PyPi or through a git repository may be used.

For more information see [Developing Plugins](./developing_plugins.md)