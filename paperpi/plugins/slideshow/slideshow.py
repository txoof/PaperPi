#!/usr/bin/env python3
# coding: utf-8






# your function must import layout and constants
# this is structured to work both in Jupyter notebook and from the command line
try:
    from . import layout
    from . import constants
except ImportError:
    import layout
    import constants
import logging   
from datetime import datetime
from pathlib import Path
# from os import walk, path
from os import listdir
from random import randint
import pickle






def _index_images(image_path):
    image_path = Path(image_path)
    image_array = []
    logging.info(f'indexing {image_path}')
    if image_path.is_dir():
        try:
            for file in listdir(image_path):
                file = image_path/file
                if file.is_file() and file.suffix.lower() in constants.supported_image_types:
                    image_array.append(file)
                else:
                    logging.info(f'skipping unsupported file type: {file}')
        except (OSError) as e:
            logging.warning(f'failed to index images in directory: {e}')
    else: 
        logging.warning(f'{image_path} does not appear to be a directory')
    image_array.sort()
    return image_array






# make sure this function can accept *args and **kwargs even if you don't intend to use them
def update_function(self, *args, **kwargs):
    '''update function for slideshow plugin
    
    This plugin choose an image from a specified directory and displays it
    along with some optional information such as the time and a filename. 
    
    Images are displayed in either `random` or `sequential` order. 
    
    Each time the plugin runs the `image_path` is re-indexed. If images are added
    or removed from the `image_path`, they will be used in the rotation. 
    
    
    Requirements:
        self.config(dict): {
            'image_path': '/absolute/path/to/images',
            'order': 'random',
        }
        
    Args: 
        self(namespace): namespace from plugin object
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))

    %U'''   
    logging.debug(f'updating plugin {constants.name}')
        
    # get the time in HH:MM format
    time = datetime.now().strftime('%H:%M')
        
    is_updated = False
    data = {
        'image': None,
        'time': time,
        'filename': None,
    }
    priority = self.max_priority
    
    failure = (is_updated, data, priority)
    
    # make sure temporary path exists
    tmp_path = Path(self.cache.path/constants.name)
    try:
        tmp_path.mkdir(exist_ok=True)
    except (FileNotFoundError) as e:
        logging.error(f'error creating cachepath: {e}')
        return failure
    except Exception as e:
        logging.error(f'{e} while attempting to access cache')
        return failure


    # pull the most recently displayed images 
    recent_image_pickle = self.cache.path/constants.name/constants.recent_images
    try:
        with open(recent_image_pickle, 'rb') as f:
            recent_image_dict = pickle.load(f)            
    except (FileNotFoundError):
        logging.debug(f'no pickle file found')
        dict_failure = True
        recent_image_dict = {}
    except Exception as e:
        logging.error(f'failed to access pickle file: {e}')
        return failure
    
    # check that dictionary is not corrupt:
    dict_failure = False
    if not isinstance(recent_image_dict, dict):
        logging.warning('dictionary pickle does not contain type `dict`')
        dict_failure = True
    for i in (0, 1):
        if i not in recent_image_dict.keys():
            logging.warning('dictionary pickle has bad data')
            dict_failure = True
    
    if dict_failure:
        logging.info('setting dictionary values due to previous issue')
        recent_image_dict = {0: None,
                              1: None}        
    
    # check that the config has valid values
    for key, value in constants.expected_config.items():
        try:
            self.config[key]
        except KeyError:
            logging.warning(f'config value not found for key: {key}')
            self.config[key] = value[1]

        if not isinstance(self.config[key], value[0]):
            logging.warning(f'config value does not match expected type: {value[0]}')
            logging.warning(f'falling back to default value: {value[1]}')
            self.config[key] = value[1]

    
    # reindex the images each run to handle removed or added images
    image_path = Path(self.config['image_path'])
    
    image_array = _index_images(image_path)
    
    if len(image_array) < 1:
        logging.warning(f'no images were found in {image_path}')

        image_path = constants.default_image_path
        logging.warning(f'falling back to {image_path}')
        image_array = _index_images(image_path)
        if len(image_array) < 1:
            logging.warning('no images could be found; aborting')
            return failure
    
#     logging.info(f'scanning {image_path} for images')    
#     image_array = []
#     for (dir_path, dir_names, file_names) in walk(image_path):
#         for f in file_names:
#             p = Path(dir_path)/f
#             if p.suffix in constants.supported_image_types:
#                 image_array.append(p)
#             else:
#                 logging.info(f'skipping unsupported file type: {f}')
#     image_array.sort()
                
    logging.debug(f'found {len(image_array)} images')
    
    # set strategy for chosing image
    if self.config['order'] in ('sequential', 'random'):
        order = self.config['order']
    else:
        logging.warning(f'unknown order value: {self.config["order"]}; falling back to "random"')
        order = 'random'
    

    # use sequential strategy for chosing next image
    if order == 'sequential':
        logging.debug('selecting next sequential image in directory')
        last_image = recent_image_dict.get(0, None)
        
        if last_image:
            try:
                last_image_idx = image_array.index(last_image)
                next_image_idx = last_image_idx + 1
            except ValueError:
                logging.info(f'last image: "{last_image}" could not be found; restarting sequence.')
                next_image_idx = 0
        else:
            next_image_idx = 0
        
        # wrap around
        if next_image_idx >= len(image_array):
            next_image_idx = 0
        
    # use random strategy; try not to show the same image twice
    if order == 'random':
        logging.debug('selecting random image in directory')
        next_image_idx = randint(0, len(image_array)-1)
        # if possible, try to pick an image that was not recently used
        if len(image_array) > 2:
            counter = 0
            while image_array[next_image_idx] in recent_image_dict.values() and counter < 100:
                logging.debug(f'chose recently used image, trying again')
                next_image_idx = randint(0, len(image_array)-1)
                counter += 1
                
    logging.debug(f'next_image_idx: {next_image_idx}')
                
    current_image = image_array[next_image_idx]
    recent_image_dict[1] = recent_image_dict[0]
    recent_image_dict[0] = current_image

        
    logging.debug(f'using image: {current_image}')
    
    data = {
        'image': current_image,
        'time': time,
        'filename': current_image.name,
    }
    
    try:
        logging.debug(f'writing dict pickle to {recent_image_pickle}')
        with open(recent_image_pickle, 'wb') as f:
            pickle.dump(recent_image_dict, f)
    except OSError as e:
        logging.error(f'failed to write cache file: {recent_image_pickle}: {e}')
        logging.error('sequential display of photos will likely fail completely')
    
    is_updated = True
    return (is_updated, data, priority)











