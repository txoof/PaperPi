name = 'librespot_client'
version = '0.3.0'
data = {
        'title': 'Error: No Data!',
        'artist': 'No local librespot found!',
        'album': 'Check Logs!',
        'artwork_url': 'Err: no data',
        'duration': 0,
        'player_name': 'No active player',
        'mode': 'None',
        'id': False,
        'is_playing': False}

#  path for private cache with the temp directory
private_cache = f'{name}/'
# days worth of album images to retain in cache
expire_cache = 3

# Spotify Constants
# API V1 -- https://developer.spotify.com/documentation/general/guides/scopes/
spot_scope = 'user-read-playback-state' # read the player state
spot_version = 'v1' # API end point version
spot_base_url = 'https://api.spotify.com' # API URL
spot_player_endpoint = 'me/player' # endpoint for player requests

# +
# default localhost port
port = 24879

# failure count before resetting api function
failure_count = 30
# -

local_api = {
    'librespot-java': 
        {
            'url': 'http://localhost:{port}/token/user-read-playback-state',
            'method': 'post',
            'key': 'token',
            'function': 'query_ljava',
            'api_type': 'librespot-java',
            'result': None,
            'func_args': {
                'headers': {'Authorization': 'Bearer '},
                'query_url': '/'.join((spot_base_url, spot_version, spot_player_endpoint)),
                'mapping': {
                    'title': 'item.name',
                    'artist': 'item.album.artists.0.name',
                    'album': 'item.album.name',
                    'artwork_url': 'item.album.images.0.url',
                    'duration': 'item.duration_ms',
                    'player_name': 'device.name',
                    'id': 'item.id',
                    'is_playing': 'is_playing',
                    'paused': 'None'
                }
            }
            
        },
    'go-librespot': 
        {
            'url': 'http://localhost:{port}/status',
            'method': 'get',
            'key': 'device_id',
            'function': 'query_lgo',
            'api_type': 'go-librespot',
            'result': None,
            'func_args': {
                'mapping': {
                    'title': 'track.name',
                    'artist': 'track.artist_names.0',
                    'album': 'track.album_name',
                    'artwork_url': 'track.album_cover_url',
                    'duration': 'track.duration',
                    'player_name': 'device_name',
                    'id': 'track.uri',
                    'is_playing': 'stopped',
                    'paused': 'paused'
                } 
            }
        }
}

sample_config = '''
[Plugin: Librespot]
layout = layout
plugin = librespot_client
refresh_rate = 10
max_priority = 0
min_display_time = 15
# name of librespot player - use ("*"" to track any and all spotify players)
player_name = LibreSpot-Spotify
# time in seconds before plugin is removed from the display loop
idle_timeout = 10
# port to search for librespot (if unset, defaults to 24879)
port = 24879
'''
