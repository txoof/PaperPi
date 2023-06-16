#!/usr/bin/env python3
# coding: utf-8






import logging
import hashlib
import time
from epdlib import Layout






logger = logging.getLogger(__name__)






# logging.basicConfig(level='DEBUG')






def strict_enforce(*types):
    """strictly enforce type compliance within classes
    
    Usage:
        @strict_enforce(type1, type2, (type3, type4))
        def foo(val1, val2, val3):
            ...
    """
    def decorator(f):
        def new_f(self, *args, **kwds):
            #we need to convert args into something mutable   
            newargs = []        
            for (a, t) in zip(args, types):
                if not isinstance(a, t):
                    raise TypeError(f'"{a}" is not type {t}')
            return f(self, *args, **kwds)
        return new_f
    return decorator






class Plugin:
    def __repr__(self):
        return f'Plugin({self.name})'
    
    def __str__(self):
        return str(self.name)
    
    def __init__(self, resolution, 
                 name=None,
                 layout={},
                 update_function=None,
                 max_priority = 2**15,
                 refresh_rate=60,
                 min_display_time=30,
                 config={},
                 cache=None,
                 force_onebit=False,
                 screen_mode='1',
                 **kwargs):
        
        '''Create a plugin object that provides consistent methods for providing an image and querying
        various services
        
        Properties:
            hash('str'): unique identifier for this plugin in its current state (used for checking for changes)
            image(PIL image): image generated for this plugin
            data(dict): data returned by this plugin to be used in the Layout
            priority(int): current priority for this plugin (lower numbers are more important in display loop)
            last_ask(float): time in seconds since this plugin was last asked for an update -- used for throttling
        
        Args:
            resolution(`tuple` of `int`): resolution of the epd or similar screen: (Length, Width)
            name(`str`): human readable name of the function for logging and reference
            layout(`dict`): epdlib.Layout.layout dictionary that describes screen layout
            update_function(func): function that returns plugin status, data and priority a
                update_function must accept (self, *args, **kwargs) and must return
                a tuple of (is_updated(bool), data(dict), priority(int))
            max_priority(`int`): maximum priority for this module values approaching 0 have highest
                priority, values < 0 are inactive
            refresh_rate(`int`): minimum time in seconds between requests for pulling an update
            min_display_time(`int`): minimum time in seconds plugin should be allowed to display in the loop
            config(`dict`): any kwargs that update function requires
            cache(`CacheFiles` obj): object that can be used for downloading remote files and caching
            force_onebit(`bool`): force layouts to 1bit mode
            kwargs(): any additional kwargs will be ignored
            '''
        
        self.name = name
        self.resolution = resolution
        self.force_onebit = force_onebit
        self.screen_mode = screen_mode
        self.layout = layout
        self.config = config
        self.cache = cache
        self.update_function = update_function
        self.refresh_rate = refresh_rate
        self.min_display_time = min_display_time
        
        self._last_ask = 0
        self.data = {}
        self.image = None
        self.max_priority = max_priority
        self.hash = self._generate_hash()
        
    
        
    
    def _generate_hash(self):
        '''generate a hash based on the self.name and the current time
            This is updated whenever self.data is updated and can be checked as a 
            proxy for "new data"'''
        my_hash = hashlib.sha1()
        my_hash.update(str(time.time()).encode('utf-8')+str(self.name).encode('utf-8'))
        return my_hash.hexdigest()[:10]        
    
    def _is_ready(self):
        '''simple throttle of update requests
            Checks time between current request (monotonic) and self._last_ask and compares to 
            self.refresh_rate
        
        Returns:
            `bool`: True if cooldown period has expired, false otherwise'''        
        if time.monotonic() - self.last_ask > self.refresh_rate:
            self._last_ask = time.monotonic()
            return True
        else:
            logger.debug(f'throttling in effect {self.refresh_rate - (time.monotonic() - self._last_ask):.1f} seconds left in cooldown period')
            return False
        
    def update(self, *args, **kwargs):
        '''request an update of the plugin data
            requests are throttled if they occur sooner than the cool-down period
            defined by self.refresh_rate
            
            Returns:
                self.hash(hash of time and self.name)
            
            calls self.update_function(*args, **kwargs):
                self.update_function returns: (`tuple` of `bool`, `dict`, `int`): 
                    bool(true when plugin is updated) 
                    dict(data returned from plugin update_function to be passed into a layout)
                    int(priority of this module; values approaching 0 are highest, negative
                        values indicate plugin is inactive)

            
            Set here:
                self.data
                self.layout_obj.update_contents(self.data)
                self.hash'''        
        if self._is_ready():
            is_updated, data, priority = self.update_function(*args, **kwargs)
            if data != self.data:
                self.data = data
                self.layout_obj.update_contents(data)
                self.image = self.layout_obj.concat()
                self.hash = self._generate_hash()
            self.priority = priority
        else:
            pass
        
        return self.hash
    
    @property
    def cache(self):
        '''CacheFiles object used for caching remote files used by plugins
        cache(`CacheFiles` obj)'''
        return self._cache
    
    @cache.setter
    def cache(self, cache):
        self._cache = cache
    
    
    @property
    def last_ask(self):
        return self._last_ask
    
    @last_ask.setter
    def last_ask(self, last_ask):
        self._last_ask = last_ask
    
    @staticmethod
    def _null_update():
        return None
    
        
    @property
    def resolution(self):
        return self._resolution
    
    @resolution.setter
    @strict_enforce((list, tuple))
    def resolution(self, resolution):
        self._resolution = resolution
    
    @property
    def update_function(self):
        '''update function provided by the plugin module
        
        The update_function is called by the update method to provide status and data for 
        the Plugin.
        
        Args:
            function(function): function that accepts self, *args, **kwargs
            
        Returns:
            tuple of is_updated(bool), data(dict), priority(int)'''
        return self._update_function
    
    @update_function.setter
    def update_function(self, function):
        if not function:
            self._update_function = self._null_update
        else:
            self._update_function = function.__get__(self)
    
    @property
    def force_onebit(self):
        '''resolution of attached screen that will be used for output
         resolution(`tuple` of `int`)'''        
        return self._force_onebit
    
    @force_onebit.setter
    @strict_enforce(bool)
    def force_onebit(self, force_onebit):
        self._force_onebit = force_onebit
    
            
    @property
    def layout(self):
        '''epdlib.Layout.layout dictionary used for configuring text and image blocks
            layout(`dict`)'''        
        return self.layout_obj.layout
    
    @layout.setter
    def layout(self, layout):
        # convert blocks to RGB when possible
        for block, values in layout.items():
            if values.get('rgb_support', False) and self.screen_mode == 'RGB' and not self.force_onebit:
                logging.debug(f'{block} supports RGB')
                values['mode'] = 'RGB'
        
        self.layout_obj = Layout(resolution=self.resolution, 
                                 layout=layout,
                                 force_onebit=self.force_onebit,
                                 mode=self.screen_mode)
        
    def force_update(self, *args, **kwargs):
        '''force an immediate update'''
        logging.info(f'forced update of plugin: {self.name}')
        is_updated, data, priority = self.update_function(*args, **kwargs)
        self.data = data
        self.layout_obj.update_contents(data)
        self.image = self.layout_obj.concat()
        self.hash = self._generate_hash()
        self.priority = priority
        logging.debug(f'Data: {self.data}')
        
        return self.hash        
        
        






def main():
    '''demo of Plugin data type'''
    from random import randint, choice
    from IPython.display import display
    from time import sleep
    bogus_layout = {
        'number': {
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
            'bkground': 'BLACK',
            'rgb_support': True
        }
    }

    # update_function that is added to the plugin as the method self.update_function
    def bogus_plugin(self):        
        text = [
            'The quick brown fox jumps over the lazy dog.',
            'Jackdaws love my big sphinx of quartz.',
            'Two driven jocks help fax my big quiz.',
            'By Jove, my quick study of lexicography won a prize!',
            'How vexingly quick daft zebras jump!'
        ]
        data = {'number': str(randint(99,9999)), 'text': choice(text)}
        priority = self.max_priority
        is_updated = True
        

        return (is_updated, data, priority) 


    p = Plugin(resolution=(300, 210), 
               refresh_rate=2, 
               max_priority=1, 
               update_function=bogus_plugin, 
               layout=bogus_layout,
               screen_mode='RGB')

#     Plugin.update_function = bogus_plugin
    
    logger.root.setLevel('INFO')
    print('this demo is best run from inside jupyter notebook')
    p.force_update()
    print('this is a forced update')
    display(p.image)
    p.force_update()
    print('this is a forced update')
    display(p.image)

    for i in range(10):
        colors = ['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']
        fill = choice(colors)
        colors.remove(fill)
        bkground = choice(colors)
        p.layout_obj.update_block_props(block='text', props={'bkground': bkground, 'fill': fill})        
        print('trying to update plugin')
        p.update()
        print('displaying image')
        display(p.image)
        print('sleep for 1 second')
        sleep(1)
    return p






if __name__ == '__main__':
    p = main()


