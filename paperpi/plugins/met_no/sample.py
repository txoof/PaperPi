# sample for met_no plugin
from copy import deepcopy

config = {
        'layout': 'layout',
        'lat': 52.080,
        'lon': 4.311,
        'location_name': 'Den Haag',
        'email': 'https://github.com/ysadamt/PaperPi/'
}

config_color = deepcopy(config)
config_color.update({
    'text_color': 'BLUE'
})