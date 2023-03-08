# sample config for lms_client
from copy import deepcopy
config = {
        'layout': 'layout',
        'player_name': 'SqueezePlay',
        'idle_timeout': 10 
}

config_color = deepcopy(config)
config_color.update({})