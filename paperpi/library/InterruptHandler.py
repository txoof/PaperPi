#!/usr/bin/env python3
# coding: utf-8




import logging
import signal






logger = logging.getLogger(__name__)






class InterruptHandler:
    kill_now = False
    kill_signal = None
    kill_signal_name = None
    
    def __init__(self):
        '''class for catching and handling SIGINT and SIGTERM signals
        
        Based heavily on https://stackoverflow.com/a/31464349/5530152

        Attributes:
            kill_now(bool): False until SIGINT or SIGTERM intercepted
            kill_signal(int): integer value of signal intercepted
            kill_signal_name(str): string equivelent of signal'''
        
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        
    def exit_gracefully(self, signum, *args):
        '''Exit handler'''
        self.kill_now = True
        self.kill_signal = signum
        self.kill_signal_name = signal.Signals(signum).name                











