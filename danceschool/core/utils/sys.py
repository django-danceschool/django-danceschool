'''
This file contains helper functions used at the time that various apps are loaded
'''

import sys


def isPreliminaryRun():
    '''
    Check the arguments passed at runtime to ensure that this
    program is not being run to perform migrations or load data.
    '''
    prelim_params = ['loaddata','makemigrations','migrate']
    for param in prelim_params:
        if param in sys.argv:
            return True
    return False
