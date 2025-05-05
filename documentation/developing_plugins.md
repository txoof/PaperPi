# Developing Plugins

PaperPi is designed to support additional plugins written in Python 3. Any modules available through PyPi or through a git repository may be used.

## How it works

When PaperPi starts, all plugins that are configured by the user  added as `update_function` to a generic `Plugin` class. This happens automatically and is managed for you.

The `Plugin` class offers several built-in functions and properties that plugins can take advantage of. See the "BUILTIN PROPERTIES" section below.

See the included [`demo_plugin`](../paperpi/plugins/demo_plugin) for a simple, well documented plugin that can be used as a template for building a plugin.

## Getting Started

1. Clone this repo `https://github.com/ysadamt/PaperPi.git`
2. Setup the development environment: `PaperPi/utilities/create_devel_environment.sh`
    - this will create a pipenv virtual environment with all the required components
3. Create a branch for your plugin: `git branch my_plugin; git checkout my_plugin`
4. Start developing! A good place to start is to make a copy of the `/paperpi/plugins/demo_plugin` for a relatively complete structure you can begin modifying.
5. Add any python modules your plugin requires using `pipenv install --dev ModuleName`
    - this will help keep your additional modules separate from the PaperPi core modules

### TOOLS AVAILABLE TO PLUGINS

PaperPi offers additional tools that can be used for setting up managing plugins.

The tools are part of the `PluginTools` library. To take advantage of this library append the following import to your plugin:

```Python
import sys
sys.path.append('../../library/')
from library import PluginTools
```

#### text_color

Sanely set text fill and background colors and falling back to default  values for 1 bit and grayscale displays. This is useful for setting color for RGB screens
    
Args:
    * `config` (dict): dictionary containing configuration variables (see below)
    * `mode` (str): string screen mode: '1', 'L', 'RGB'
    * `default_text` (str): color string in `['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']`
    * `default_bkground` (str) color string in `['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']`

Returns:
    * dict of `{text_color: string, bkground_color: string}`
    
Notes:
`config` should include `'text_color'` and `'bkground_color'` and should be one of `['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']` or `'random'`
    
Choosing 'random' will try choose a random color from the set. Using random for both text and bkground will always result in different colors for the text and bkground values.
    
`config = {'text_color': 'RED', 'bkground_color': 'BLUE'}`

##### Example

```Python
def update_function(self):

    foo = {'bar': 'spam'}

    # handle colors passed from the config file  in the self.config property
    if 'text_color' in self.config or 'bkground_color' in self.config:
        logging.info('using user-defined colors')
        colors = PluginTools.text_color(config=self.config, mode=self.screen_mode,
                               default_text=self.layout.get('fill', 'WHITE'),
                               default_bkground=self.layout.get('bkground', 'BLACK'))

        text_color = colors['text_color']
        bkground_color = colors['bkground_color']


        # set the colors
        for section in self.layout:
            logging.debug(f'setting {section} layout colors to fill: {text_color}, bkground: {bkground_color}')
            self.layout_obj.update_block_props(section, {'fill': text_color, 'bkground': bkground_color})
    
    return (True, foo, self.max_priority)
```


### BUILTIN PROPERTIES AVAILABLE TO PLUGINS

All plugins have the following functions and properties available. Call the builtin functions by using `self.[method/property]`.

**Plugin Class Methods and Properties**

* resolution(`tuple` of `int`): resolution of the epd or similar screen: (Length, Width)
* name(`str`): human readable name of the function for logging and reference
* layout(`dict`): epdlib.Layout.layout dictionary that describes screen layout
* max_priority(`int`): maximum priority for this module values approaching 0 have highest priority, values < 0 are inactive
* refresh_rate(`int`): minimum time in seconds between requests for pulling an update
* min_display_time(`int`): minimum time in seconds plugin should be allowed to display in the loop
* config(`dict`): any kwargs in the plugin configuration from `paperpi.ini` that are not addressed here
  * Any values your plugin requires such as API keys, email addresses, URLs can be accessed from the `self.config` property
* cache(`CacheFiles` obj): object that can be used for downloading remote files and caching.

**CacheFiles Class Methods and Properties**
`cache_file(url, file_id, force=False)` download a remote file and return the local path to the file if a local file with the same name is found, download is skipped and path returned

Args:
* url(`str`): url to remote file
* file_id(`str`): name to use for local file
* force(`bool`): force a download ignoring local files with the same name

`cleanup()` recursively remove all cached files and cache path (this is typically only used when shutting down the application)

`cache_path: pathlib.PosixPath - top-level path to cache

### REQUIREMENTS CHECKLIST

* [ ] Plugin modules are added to the `paperpi/plugins` directory
* [ ] Plugin modules must be named with exactly the same name as their module directory: `plugins/my_new_plugin/my_new_plugin.py`
* [ ] Include a `__init__.py` -- see below
* [ ] Plugin modules must contain at minimum one function called `update_function()`
* [ ] Include a file called `debian_packages-myplugin.txt` with any debian packages your plugin relies on (optional) -- see below for an example
* [ ] Include a file called `requirements-myplugin_hidden.txt` for any python dependencies that are not explicitly imported (optional) -- see below for an example
* [ ] Include a `constants.py` see below for specification
* [ ] Plugin modules must at minimum contain a `layout.py` file that contains a layout file. See the specifications below.
* [ ] At minimum the `update_function` should contain a docstring that completely documents the plugin's use and behavior
  * See the example below
  * End all user-facing docstrings with `%U`; to ensure they are included in the auto-documenting build scripts

**layout.py**
Within the `layout.py` file, the default layout should be named `layout`. It is acceptable to use a complex name and set:

    `layout = my_complex_name`
Layouts that require fonts should use paths in the following format: `'font': dir_path+'/../../fonts/<FONT NAME>/<FONT FILE>` Add additional publicly available fonts to the `fonts` directory (<https://fonts.google.com/> is a good source)

See the [epdlib Layout module](https://github.com/ysadamt/epdlib#layout-module) for more information on creating layouts

In addition to the keys supported by the `epdlib.Layout` module, the following block keys are also accepted:

#### `'rgb_support': True`

Adding the `rgb_support` key within a plugin block indicates that that block should attempt to use RGB color when rendering. If the attached screen does not support RGB color, the block will default to gray or 1 bit mode.

```Python
# example layout with `rgb_support`
my_layout = {
        'number': {
            # this block will render as a 1 bit block always
            'type': 'TextBlock',
            'image': None,
            'max_lines': 1,
            'width': 1,
            'height': .5,
            'abs_coordinates': (0, 0),
            'rand': True,
            'font': '../fonts/Anton/Anton-Regular.ttf',
            },
        'text': {
            # this block will render as an RGB block 
            # only if an RGB screen is attached
            'rgb_support': True,
            'abs_coordinates': (0, None),
            'relative': ('text', 'number'),
            'type': 'TextBlock',
            'image': None,
            'max_lines': 3,
            'height': .5,
            'width': 1,
            'rand': True,
            'font': '../fonts/Anton/Anton-Regular.ttf',
            'fill': 'ORANGE',
            'bkground': 'BLACK'
            }   
}
```

See the [`basic_clock` layout](../paperpi/plugins/basic_clock/layout.py) for a simple layout template

**\_\_init\_\_.py**

The `__init__.py` file must contain at minimum an import of the update function from your plugin. See the example below

```python
from .my_new_plugin_name import update_function
```

**constants.py**

The `constants.py` is used in generating documentation and populating the deployed `paperpi.ini` file. The constants file must contain the following:

* `name = my_new_plugin` - plugin name that matches module directory name
* `version = 'version'` - version information
* sample configuration as docstring. This will be added to the .ini file on demand by the user to assist in configuration.
* optional: `include_ini = False` -- if this plugin should not be included in the deployed `paperpi.ini`

Example `constants.py`

```python
name = 'my_plugin_name`
version = '1.2.3.foo'
sample_config = '''
[Plugin: Human Readable Name for Plugin]
layout = layout
plugin = my_new_plugin
refresh_rate = 60
min_display_time = 60
max_priority = 2
additional_key = foo '''
```


**debian_packages-myplugin.txt**

If your plugin depends on any external debian packages they must be included in a `debian_packages-myplugin.txt` file where "myplugin" is the name of your plugin. Provide any additional debian packages as a bash array named `DEBPKG`. Bash arrays do not use commas to separate elements:

```bash
DEBPKG=( "libfoo-dev" "formatter-FooBar" )
```

**requirements-myplugin_hidden.txt**

If your plugin fails to install correctly due to hidden python imports that are not correctly detected, they can be added using a flat file that lists one module per line. Use the name from PyPi.

```text
cairocffi
cffi
CairoSVG
```

**OPTIONAL**

Plugin modules may have user-facing helper functions that can help the user setup or configure the plugin. User facing plugins should be documented using a docstring that contains the `%U` as the last character. See the `lms_client` plugin for an example of a helper function that can be used to locate Logitech Media Servers on the local network. The `met_no` plugin also provides a function for finding the LAT/LON of a city or location. 

Example:

```python
def say_hello(name):
    '''
    This fuction says "hello" to the user when called.
    %U'''
    print(f'hello {name}')
```

**update_function() specifications**

The update_function is added to a `library.Plugin()` object as a method. The update_function will have access to the `self` namespace of the Plugin object including the `max_priority` and `cache`. The `Plugin()` API is internally documented.

Checklist:
- [ ] `update_function` must accept `*args, **kwargs` even if they are not used
- [ ] `update_function` must return a tuple of: (is_updated(bool), data(dict), priority(int))
  * `is_updated` indicates if the module is up-to-date and functioning; return `False` if your module is not functioning properly or is not currently operating (e.g. has no relevant data to display)
  * `data` is a dictionary that contains key/value pairs of either strings or an image (path to an image or PIL image object).
  * `priority` indicates your modules priority
    * The default should be to return `self.max_priority`; it is allowed to return a negative number if your plugin detects an important event.
    * If the module is in a passive state (e.g. there is no interesting data to show) set `priority` to `2**15` to ensure it is not included in the display loop
- [ ] Returns a 3 tuple of `(is_updated(bool), data(dict), priority(int))`
- [ ] Required docstring:

    ```python
    '''
    update function for my_plugin_name provides foo information
    
    # longer description of what this plugin does
    This plugin provides...
    
    # required configuration elements that must be passed to this plugin
    Requirements:
        self.config(dict): {
            key1: value1
            key2: value2
        }
        self.cache(CacheFiles object): location to store downloaded images
    
    # arguments the update_function accepts
    Args:
       self(namespace): namespace from plugin object
     
    # return values
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))
    # marker '%U' that indicates this is a user-facing function that should be included when producing 
    # documentation
    %U'''
    ```

**sample.py**

To provide a sample image and automatically create documentation provide a `sample.py` file. When documentation is automatically generated, a sample image will be produced using each available layout. 

```python
config = {
    # this is required
    'layout': 'layout_name_to_use_for_sample_img',
    # optional below this point
    'config_option': 'value',
    'config_option2': 12345
}
```

## Adding Plugins to PaperPi

Once you've built an tested your plugin, you can add it to PaperPi by submitting a pull request. You should do the following to make sure your plugin is ready to go:

* Test your plugin and make sure it doesn't crash when an internet connection is unavailable, or a bad data is returned
* Run `$pipenv run python ./utilities/find_imports.sh` to update all of the python module dependencies for your plugin
* Run  `$ pipenv run python ./utilities/create_docs.py` script to make sure your README and sample images are built properly.
* Submit a PR that includes your plugin 
