# Developing Plugins

PaperPi is designed to support additional plugins written in Python 3. Any modules available through PyPi or through a git repository may be used.

## How it works

When PaperPi starts, all plugins that are configured by the user added as `update_function` to a generic `Plugin` class. This happens automatically and is managed by the application.

The `Plugin` class offers several built-in functions and properties that plugins can take advantage of. See the [BUILTIN PROPERTIES](#builtin-properties-available-to-plugins) section below.

See the included [`demo_plugin`](../paperpi/plugins/demo_plugin) for a simple, well documented plugin that can be used as a template for building a plugin.

## Getting Started

1. Clone this repo `https://github.com/txoof/PaperPi.git`
2. Setup the development environment: `PaperPi/utilities/create_devel_environment.sh`
    - this will create a pipenv virtual environment with all the required components
3. Create a branch for your plugin: `git branch my_plugin; git checkout my_plugin`
4. Start developing! A good place to start is to make a copy of the `/paperpi/plugins/demo_plugin` for a relatively complete structure you can begin modifying.
5. Add any python modules your plugin requires using `pipenv install --dev ModuleName`
    - this will help keep your additional modules separate from the PaperPi core modules

## BUILTIN PROPERTIES AVAILABLE TO PLUGINS

### **Plugin Class Methods and Properties**

All plugins have the following functions and properties available. Call the builtin functions by using `self.[method/property]`.

- resolution(`tuple` of `int`): resolution of the epd or similar screen: (Length, Width)
- name(`str`): human readable name of the function for logging and reference
- layout(`dict`): epdlib.Layout.layout dictionary that describes screen layout
- max_priority(`int`): maximum priority for this module values approaching 0 have highest priority, values < 0 are inactive
- refresh_rate(`int`): minimum time in seconds between requests for pulling an update
- min_display_time(`int`): minimum time in seconds plugin should be allowed to display in the loop
- config(`dict`): any kwargs in the plugin configuration from `paperpi.ini` that are not addressed here
  - Any values your plugin requires such as API keys, email addresses, URLs can be accessed from the `self.config` property
- cache(`CacheFiles` obj): object that can be used for downloading remote files and caching.

### **CacheFiles Class Methods and Properties**

Each plugin has access to the cache for the application. This cache is **not secure**. All plugins can access the same cache. **Do not store secrets here**. It is good practice to store plugin data in a subdirectory or prepend the cahced file with the plugin name to prevent other plugins from clobbering downloaded data.

`cache_file(url, file_id, force=False)` download a remote file and return the local path to the file if a local file with the same name is found, download is skipped and path returned

Args:

- url(`str`): url to remote file
- file_id(`str`): name to use for local file
- force(`bool`): force a download ignoring local files with the same name

`cleanup()` recursively remove all cached files and cache path (this is typically only used when shutting down the application)

`cache_path`: pathlib.PosixPath - top-level path to cache

### PLUGIN REQUIREMENTS

Plugin must contain, at minimum, a `[plugin_name].py` file that contains an `update_function()`. Addtional files are also required for a complete plugin package. See the [Packaging Plugins](#packaging-plugins) section below.

**`update_function`**

- Must return a 3-tuple of `(is_updated(bool), data(dict), priority(int))
- Must accept args/kwargs
- Must have a docstring that explains it's basic function and any information an end user may need to configure/setup the plugin. This docstring must end with exactly `%U` on the very last line. The docstring will be displayed when using the `--plugin_info` option.

**User-facing functions**

Plugins may contain user-facing functions that can be run from the command line using the `--run_plugin_func plugin_name.function`. For an example, see the `met_no.get_coord` user-facing function.

User-facing functions should have a docstring that ends with `%U` on the very last line. The docstring should explain the function and it's usage. The docstring will be displayed when using the `--plugin_info plugin_name.function` option.

Example:

```python
def say_hello(name):
    '''
    This fuction says "hello" to the user when called.
    %U'''
    print(f'hello {name}')
```

### BUILTIN FUNCTIONS AVAILABLE TO PLUGINS

All plugins have the following functions and properties available. Call the builtin functions by using `self.[method/property]`.

#### **Plugin Class Methods and Properties**

- resolution(`tuple` of `int`): resolution of the epd or similar screen: (Length, Width)
- name(`str`): human readable name of the function for logging and reference
- layout(`dict`): epdlib.Layout.layout dictionary that describes screen layout
- max_priority(`int`): maximum priority for this module values approaching 0 have highest priority, values < 0 are inactive
- refresh_rate(`int`): minimum time in seconds between requests for pulling an update
- min_display_time(`int`): minimum time in seconds plugin should be allowed to display in the loop
- config(`dict`): any kwargs in the plugin configuration from `paperpi.ini`
- cache(`CacheFiles` obj): object that can be used for downloading remote files and caching
  - `cache_file(self, url, file_id, force=False)` download a remote file and return the local path to the file if a local file with the same name is found, download is skipped and path returned
    - Args:
      - url(`str`): url to remote file
      - file_id(`str`): name to use for local file
      - force(`bool`): force a download ignoring local files with the same name
  - `cleanup(self)` recursively remove all cached files and cache path (this is typically only used when shutting down the application)
    - Properties:
      - cache_path(`pathlib.PosixPath`): top-level path to cache files

Plugins are written in python 3 and should follow the following guidelines to function properly:

### PACKAGING PLUGINS

Installable Plugins consist of a .tar.gz file that contains the basic structure below. Substitute your plugin name for `[plugin_name]` as appropriate All files/directories marked with a `^` are optional and not required.

```text
[plugin_name]/
├── __init__.py
├── constants.py
├── debian_packages-[plugin_name].txt^
├── layout.py
├── [plugin_name].py
├── [plugin_name].layout-sample.png
├── requirements-[plugin_name].txt^
├── README.md
├── README_additional.md^
├── sample.py
├── additional_content^/
│   └── additional_content.foo^
└── additional_files^/
    └── additional_files.bar^
```

#### **--REQUIRED FILES--**

#### `__init__.py`

Purpose: Allows PaperPi to properly import your `update_function()`

Required contents:

```from .[plugin_name] import update_function```

#### `constants.py`

Purpose: Any constants related to your plugin as well as the name, version number data set provided to layouts and a sample configuration.

Required contents:

- `version` version number of plugin
- `data` contains a default data set this information is displayed when `--plugin_info` is called. These are all of the data keys your plugin provides that _can_ be used by layouts.
- `sample_config` docstring that contains a sample, working configuration for your plugin. The `sample_config` string is added to the user or system config when `--add_config` is called.

```python
version = '0.0.0'
name = '[plugin_name]'
data = { 'key0': default_value,
         'key1': default_value,
         'keyn': default_value
       }
sample_config = '''
[Plugin: [Human Readable Name for plugin_name]]
layout = layout
plugin = plugin_name
refresh_rate = 60
min_display_time = 120
max_priority = 2
plugin_specific_kwarg0 = foo
plugin_specific_kwarg1 = bar
# add any notes or comments like this:
# make sure you generate an API key by visiting spam.ham
plugin_name_api_key = YOUR_API_KEY_HERE
'''
```

#### `layout.py`

Purpose: contains all possible layout supported by your plugin. See the [EPDLib Layout](https://github.com/txoof/epdlib#Layout) module for more information on crafting layouts.

Required Contents:

- `layout` default layout for your plugin. It is acceptable to use a variable assignment such as `layout = complex_name_for_layout`.

```python
layout = { layout definition }
```

#### `[plugin_name].py`

Purpose: entry point for your module. This file must contain the `update_function()` for your plugin. This file must have exactly same name as the plugin directory.

Required Contents:

```python
def update_function():
  # do stuff
  return (is_updated, data, priority)
```

#### `[plugin_name].png`

Purpsose: Image used in README for your plugin. This is automatically generated by running `$ pipenv run python ./utilities/create_docs.py`. If you have multiple layouts, a sample png will be generated for each layout.

### README.md

Purpose: Automatically generated by the `create_docs.py` script. This includes the docstring from the `update_function()`, sample images for all of the possible layouts as well as any additional information that is appended from README_additional.py

#### `sample.py`

Purpose: Provides a sample configuration for the `create_docs.py` script. This provides a configuration that will allow plugin to be initiated, and sample images created for all possible plugins.

**NB!** make sure you do not leave any sensitive API keys in this after you have generated your sample images with `create_docs.py`

Required Contents:

```python
config = {
    # this must be a valid layout
    'layout': 'layout',
    'plugin_specific_kwarg_config_option': 'Spam, spam, spam and eggs',
    'additional_config_option': 10 
}
```

#### **--OPTIONAL FILES--**

#### `debian_packages-[plugin_name].txt` -- optional

Purpose: Provides any additional Debian packages that must be installed for your plugin to function.

Required Contents:

```bash
# this is a BASH array, not python! Follow the format shown here exactly!
# Use only spaces, no commas, and surround all names with double quotes
DEBPKG=( "deb-package-name0" "deb-package-name1" )
```

#### `README_additional.md`

Purpose: Provides additional information about the plugin that is not covered in the docstring provided by `update_function()`. This is automatically appended to the README.md by the `create_docs.py` script. The [LMS-Client](../paperpi/plugins/lms_client/) has an example a `README_additional.md` file.

#### `requirements-[plugin_name].txt`

Purpose: Provides any additional python modules that must be installed for your plugin to function. This can be generated by running the `./utilities/find_imports.sh` script.

Required Contents:

```text
foo-module1
bar-module2
py-module3
```

#### Additional Content

Any additional support files or sub directories can be be placed in the root of your plugin directory.

## Adding Plugins to PaperPi

UNDER REVIEW
