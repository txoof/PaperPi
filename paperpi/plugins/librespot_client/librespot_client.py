# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.1
#   kernelspec:
#     display_name: venv_paperpi-9876705927
#     language: python
#     name: venv_paperpi-9876705927
# ---

# %load_ext autoreload
# %autoreload 2

import logging

import requests
from epdlib.Screen import Update
from dictor import dictor
from copy import copy, deepcopy

try:
    from . import layout
    from . import constants
except ImportError:
    import layout
    import constants

logger = logging.getLogger(__name__)


def _request(method='get', url='', **kwargs):
    '''wrap request in try/except'''
    
    try:
        result = requests.request(method, url, **kwargs)
    except requests.exceptions.RequestException as e:
        logger.info(f'query: {method} {url} failed with error: {e}')
        result = None
        
    return result


def _detect_api(port=constants.port):
    '''detect which API is running on the specified port

    Args:
        port(int)
    
    returns:
        dict'''
    logger.info('searching for local librespot instances')
    api = None
    api_dict = deepcopy(constants.local_api)
    
    for api, value in api_dict.items():
        key = None
        url = value.get('url', '').format(port=port)
        logger.debug(f'Polling API {api}: {url}')
        method = value.get('method')
        r = _request(method=method, url=url)
        try:
            key = r.json().get(value.get('key', None))
            if key:
                logger.info(f'{api} API found at {url}')
                break
            
        except (AttributeError, ValueError) as e:
            api = ''
            r = None
    if not api:
        logger.info(f'no local librespot APIs found on port {port}')
        logger.debug(f'is there a go-librespot or librespot-java (spocon) instance configured on {port}?')
        logger.debug(f'try starting a stream first')
    retval = api_dict.get(api, {})
    retval['result'] = r
    retval['url'] = url

    

    return retval


def _clean_data(data):
    try:
        return {k: str(v) if not v and not v == False else v for k, v in data.items() }
    except ValueError:
        return {}


def query_ljava(api_dict):
    # make a shallow copy so the data object can be updated
    data = copy(constants.data)
    try:
        result = api_dict.get('result', None)
        token = result.json().get('token')
    except (AttributeError, ValueError):
        logger.warning('no token was returned; aborting query')
        return data

    headers = copy(api_dict.get('func_args', {}).get('headers', {}))
    if not headers:
        logger.error('critical error in constants.local_api.librespot_java.function_args.headers')
        return data
    headers['Authorization'] = headers['Authorization'] + token

    query_url = api_dict.get('func_args', {}).get('query_url', '')

   # use the token to fetch player information from spotify
    logger.debug(f'fetch player status from Spotify at {query_url}')
    player_status = _request('get', query_url, headers=headers)

    try:
        player_json = player_status.json()
    except (AttributeError, ValueError):
        logger.info('no player JSON data returned; aborting query')
        return data
    
    mapping = api_dict.get('func_args', {}).get('mapping', None)
    if not mapping:
        logger.error('critical error in constants.librespot_java.function_args.mapping')
        return data

    for key in mapping:
        data[key] = dictor(player_json, mapping[key])

    if data['is_playing']:
        data['mode'] = 'play'
    else:
        data['mode'] = 'stop'

    return data


def query_lgo(api_dict):
    data = copy(constants.data)
    try: 
        # result = api_dict.get('result', None)
        result = _request(url=api_dict.get('url', ''), method=api_dict.get('method', 'get'))
        player_json = result.json()
    except (AttributeError, ValueError):
        logger.warning('no valid data was returned')
        return data

    mapping = api_dict.get('func_args', {}).get('mapping', None)
    if not mapping:
        logger.error('critical error in constants file')
        return data

    
    for key in mapping:
        data[key] = dictor(player_json, mapping[key])
    
    # the key returned is titled "stopped" - invert this to get "is_playing"
    # may need to do further logic with 'paused' boolean to get if it's actually stopped
    data['is_playing'] = not data['is_playing']

    if data.get('is_playing', False) and not data.get('paused', True):
        data['mode'] = 'play'
    else:
        data['mode'] = 'stop'
    
    return data


def update_function(self):
    '''update function for librespot_client provides now-playing Spotify information
    
    This plugin pulls and displays now-playing information from a Librespot instance running on the same host. 
    Two librespot services are supported:

    * (go-librespot)[https://github.com/devgianlu/go-librespot]
    * (SpoCon)[https://github.com/spocon/spocon]: [librespot-java wrapper](https://github.com/librespot-org/librespot-java) -- Deprecated in favor of go-librespot
    
      
    This plugin dynamically changes the priority depending on the status of the librespot
    player. Remember, lower priority values are considered **more** important
    Condition         Priority
    ------------------------------
    playing           max_priority
    track change      max_priority -1
    paused            max_priority +1
    stopped           max_priority +3
    non-functional    32,768 (2^15)

      
    Requirements:
        self.config(`dict`): {
        'player_name': 'LibreSpot-Spotify',   # name of player to track
        'idle_timeout': 10,               # timeout for disabling plugin
    }
    self.cache(`CacheFiles` object)

    Args:
        self(namespace): namespace from plugin object
        
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))    
    %U'''
    def _init():
        self.inited = True
        # add a play_state attribute
        self.play_state = 'None'
        
        # add the idle timer on first run
        self.idle_timer = Update()

        # add a data dictionary
        self.data = copy(constants.data)
        
        # add port attribute
        self.port = self.config.get('port') or constants.port

        self.max_priority = self.config.get('max_priority', 0)

    if not hasattr(self, 'inited'):
        _init()
    
    def _failure(reason=None):
        if reason:
            logger.info(f'update aborted due to: {reason}')
        else:
            logger.info('update aborted for uknown reason')
        return (False, constants.data, 2**15)        
        
    self.api = _detect_api(port=self.port)
    is_updated = False
    data = copy(constants.data)
    priority = 2**15    

    if  not self.api.get('result'):
        reason =  f'No API appears to be available on configured port {self.config.get("port")}'
        return _failure(reason)

    query_function = self.api.get('function', None)
    if query_function in globals():
        logger.debug(f'using query function {query_function}')
        self.query_function = globals()[query_function]
    else:
        reason = ('failed to find a local librespot API query function')
        logging.warning(reason)
        return _failure(reason)


    query_data = self.query_function(self.api)

    if not query_data:
        reason = f'{self.query_function} failed to return data'
        return _failure(reason)

    logging.debug(f'query data:\n{query_data}')

    player_name = query_data.get('player_name', '')

    if player_name.lower() == self.config.get('player_name').lower() or self.config.get('player_name') == '*':
        logger.debug(f'found player with name: {player_name}')
    else:
        reason = f'this plugin is set to track player "{self.config.get("player_name")}", but found player name: "{player_name}"'
        return _failure(reason)

    # save the query_data into the data object
    for key in data:
        logger.debug(f'{key}:{query_data.get(key)}')
        data[key] = query_data.get(key, "Not Provided")
        
    if data.get('mode', False) == 'play':
        priority = self.max_priority - 1
        logger.info(f'configured player, {self.config["player_name"]}, is playing')
        if data.get('artwork_url'):
            file_id = f'{constants.private_cache}/{data.get("artwork_url").split("/")[-1]}'
            logger.debug(f'file_id to cache: {file_id}')
            data['coverart'] = self.cache.cache_file(url=data.get('artwork_url'), file_id=file_id)
        if data.get('id') != self.data.get('id'):
            priority = self.max_priority - 1
            logger.debug(f'increasing priority to {priority}')
        is_updated = True
    elif data.get('mode', False) == 'stop':
        logger.info(f'configured player, {self.config["player_name"]} is stopped')
        # check the previous data['mode'] state
        if self.data.get('mode') == 'play':
            priority = self.max_priority + 1
            logger.info(f'entering "pause" mode & starting idle timer and changing priority to {priority}')
            self.idle_timer.update()
            is_updated = True

        # set the priority low if the idle_timer expires
        if self.idle_timer.last_updated >= self.config.get('idle_timeout', 5) and priority < self.max_priority + 3:
            priority = self.max_priority + 3
            logger.info(f'idle_timer expired, enering low priority mode: {priority}')
            is_updated = True    

    

    
    return (is_updated, data, priority)



# +
# this code snip simulates running from within the display loop use this and the following
# # cell to test the output
# # !ln -s ../library
# import logging
# logger.root.setLevel('DEBUG')
# from library.CacheFiles import CacheFiles
# from library.Plugin import Plugin
# from IPython.display import display
# test_plugin = Plugin(resolution=(800, 600), screen_mode='RGB')
# test_plugin.config = {
#     'player_name': 'SpoCon-Spotify',
#     'bkground_color': 'White',
#     'port': 24879
# }
# test_plugin.refresh_rate = 5
# # l = layout.layout
# # test_plugin.layout = l
# test_plugin.cache = CacheFiles()
# test_plugin.update_function = update_function
# # test_plugin.update()
# # test_plugin.image
# test_plugin.update_function()
