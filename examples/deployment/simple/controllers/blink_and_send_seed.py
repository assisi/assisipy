#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Seed casu for blinking pattern.
Blinks the red LED every 10 seconds and sends messages to neighbors.
"""

from assisipy import casu

import sys
import time

if __name__ == '__main__':

    f = open('calibration_file.test','w')
    f.writelines(['Dummy file.','this is a test'])
    f.close()

    c = casu.Casu(sys.argv[1], log=True)

    counter = 0
    while True:
        if not counter % 5:
            c.set_diagnostic_led_rgb(r=1)
            time.sleep(1)
            c.set_diagnostic_led_rgb(r=0)
            time.sleep(1)
            
            c.send_message('front','blink')
            c.send_message('right','blink')
            c.send_message('back','blink')
            c.send_message('left','blink')

        counter += 1
        time.sleep(1)
