#!/usr/bin/env python3
# coding: utf-8




import logging
from random import choice
from copy import deepcopy






logger = logging.getLogger(__name__)






def text_color(config, mode, default_text='WHITE', default_bkground='BLACK'):
    '''Sanely set text fill and background colors and falling back to default 
    values for 1 bit and grayscale displays. This is useful for setting color for RGB screens
    
    Args:
        config(dict): dictionary containing configuration variables (see below)
        mode(str): string screen mode: '1', 'L', 'RGB'
        default_text(str): color string in ['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']
        default_bkground(str) color string in ['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']
    
    Returns:
        dict of {text_color: string, bkground_color: string}
        
    Notes:
        `config` should include 'text_color' and 'bkground_color' and should be one of
        ['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE'] or 'random'
        
        Choosing 'random' will try choose a random color from the set. Using random for
        both text and bkground will always result in different colors for the text and 
        bkground values.
        
        config = {'text_color': 'RED', 'bkground_color': 'BLUE'}
        
    '''
    
    def pop_color(all_colors, color):
        '''pop `color` from the all_colors list and return the remainder
        
        Args:
            all_colors: list of colors
            color: color to pop from list
            
        returns:
            list of remaining colors'''
        all_colors.pop(all_colors.index(color))
        return all_colors
        
    
    COLOR_CONSTANTS = ['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE', 'BLACK', 'WHITE']
    
    text_color = config.get('text_color', default_text).upper()
    bkground_color = config.get('bkground_color', default_bkground).upper()
    
    if mode == 'RGB':
        logging.debug(f'setting text_color: {text_color}, bkground_color: {bkground_color}')
        
        my_colors = deepcopy(COLOR_CONSTANTS)
        
        if text_color.lower() == 'random':
            if bkground_color.lower() != 'random':
                my_colors = pop_color(my_colors, bkground_color)
            text_color = choice(my_colors)
        elif text_color not in my_colors:
            logging.error(f'invalid text_color: {text_color}; valid choices are {COLOR_CONSTANTS}')
            text_color = default_text
        
        if bkground_color.lower() == 'random':
            pop_color(my_colors, text_color)
            bkground_color = choice(my_colors)
        elif text_color not in my_colors:
            logging.error(f'invalid text_color: {text_color}; valid choices are {COLOR_CONSTANTS}')
            
    else:
        text_color = default_text
        bkground_color = default_bkground
        
    if text_color == bkground_color:
        logging.warning('Set text color matches set background color. This will likely lead to no readable text.')
    
    return {'text_color': text_color, 'bkground_color': bkground_color}




