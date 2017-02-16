#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tool for debugging communication issues
between ASSISI system components.
"""

import time
import threading
import zmq

class FakeFw:

    def __init__(self):

        self.ctx = zmq.Context(1)

        # Set up the receiver
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.bind('tcp://*:5556')
        self.sub.setsockopt(zmq.SUBSCRIBE, '')

        # Start the receiver thread
        self.rcv_thread = threading.Thread(target=self.receive)
        self.rcv_thread.start()
        
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind('tcp://*:5555')
        
    def receive(self):
        while True:
            #[name, dev, cmd, data] = self.sub.recv_multipart()
            #print(name,dev,cmd,data)
            print(self.sub.recv_multipart())

    def run(self):
        # Keep sending dummy data
        while(True):
            self.pub.send_multipart(['casu-016','Acc','GetOut','Dummy'])
            time.sleep(1)
        
if __name__ == "__main__":

    fw = FakeFw()
    
    try:
        fw.run()
    except KeyboardInterrupt:
        print('Bye-bye')


