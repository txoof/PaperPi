#wordclock sample config
from copy import deepcopy

config = {
        'layout': 'layout'
}

config_color = deepcopy(config)
config_color.update({
    'text_color': 'random',
    'bkground_color': 'random'
})