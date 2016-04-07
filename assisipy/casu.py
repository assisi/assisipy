#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Python interface to CASU functionality. """

import threading
import time

import zmq

import yaml # For parsing configuration (.rtc) files

# For logging
from datetime import datetime
import csv

from msg import dev_msgs_pb2
from msg import base_msgs_pb2

# Device ID definitions (for convenience)

""" IR range sensors """

IR_F = 0 
""" Range sensor pointing to 0° (FRONT) """
IR_FR = 1
""" Range sensor pointing to 45° (FRONT-RIGHT) """
IR_BR = 2
""" Range sensor pointing to 135° (BACK-RIGHT)"""
IR_B = 3
""" Range sensor pointing to 180° (BACK) """
IR_BL = 4
""" Range sensor pointing to 225° (BACK-LEFT) """
IR_FL = 5
""" Range sensor pointing to 270° (FRONT-LEFT) """

LIGHT_ACT = 6
""" Light stimulus actuator """

DLED_TOP = 7
""" Top diagnostic LED """

TEMP_F = 8 
""" Temperature sensor at 0° (FRONT) """
TEMP_R = 9
""" Temperature sensor at 90° (RIGHT) """
TEMP_B = 10
""" Temperature sensor at 180° (BACK) """
TEMP_L = 11
""" Temperature sensor at 270° (LEFT) """
TEMP_TOP = 12
""" Top temperature sensor (Casu top) """
TEMP_CASU = 13
""" Estimated casu-body temperature """
TEMP_WAX = 14
""" Estimated casu-wax temperature """

PELTIER_ACT = 15
""" Peltier temperature actuator """

ACC_F = 16
""" Vibration sensor at 0° (FRONT) """
ACC_R = 17
""" Vibration sensors 90° (RIGHT) """
ACC_B = 18
""" Vibration sensors 180° (BACK) """
ACC_L = 19
""" Vibration sensors 270° (LEFT) """

VIBE_ACT = 20
""" Vibration actuator """

TEMP_MIN = 10
"""
Minimum allowed setpoint for the Peltier heater, in °C.
"""
TEMP_MAX = 50
"""
Maximum allowed setpoint for the peltier heater, in °C.
"""

AIRFLOW_ACT = 21
""" Airflow actuator """

ARRAY = 10000
"""
Special value to get all sensor values from an array of sensors
(e.g. all proximity sensors)
"""

class Casu:
    """
    The low-level interface to Casu devices.

    Initializes the object and starts listening for data.
    The fully constructed object is returned only after
    the data connection has been established.

    :param string rtc_file_name: Name of the run-time configuration (RTC) file. If no file is provided, the default configuration is used; if `name` is provided, this parameter is ignored (and no RTC file is read).
    :param string name: Casu name (note: this value takes precedence over `rtc_file_name` if both provided: thus no RTC file is read)
    :param bool log: A variable indicating whether to log all incoming and outgoing data. If set to true, a logfile in the form 'YYYY-MM-DD-HH-MM-SS-name.csv' is created.
    """

    def __init__(self, rtc_file_name='casu.rtc', name = '', log = False, log_folder = '.'):


        if name:
            # Use default values
            self.__pub_addr = 'tcp://127.0.0.1:5556'
            self.__sub_addr = 'tcp://127.0.0.1:5555'
            self.__name = name
            self.__neighbors = None
            self.__msg_pub_addr = None
            self.__msg_sub = None
            self.__phys_logi_map = {}
        else:
            # Parse the rtc file
            with open(rtc_file_name) as rtc_file:
                rtc = yaml.safe_load(rtc_file)
            self.__name = rtc['name']
            self.__pub_addr = rtc['pub_addr']
            self.__sub_addr = rtc['sub_addr']
            self.__msg_pub_addr = rtc['msg_addr']
            self.__neighbors = rtc['neighbors']
            self.__msg_sub = None
            self.__phys_logi_map = self.__read_comm_links(rtc_file_name)


        self.__stop = False

        # TODO: Fill readings with fake data
        #       to prevent program crashes.
        self.__ir_range_readings = dev_msgs_pb2.RangeArray()
        self.__temp_readings = dev_msgs_pb2.TemperatureArray()
        self.__diagnostic_led = [0,0,0,0] # Not used!
        self.__acc_readings = dev_msgs_pb2.VibrationReadingArray()
        self.__peltier_setpoint = dev_msgs_pb2.Temperature()
        self.__peltier_on = False

        # Create the data update thread
        self.__connected = False
        self.__context = zmq.Context(1)
        self.__comm_thread = threading.Thread(target=self.__update_readings)
        self.__comm_thread.daemon = True
        self.__lock =threading.Lock()

        # Set up logging
        self.__log = log
        if log:
            now_str = datetime.now().__str__().split('.')[0]
            now_str = now_str.replace(' ','-').replace(':','-')
            if log_folder[-1] != '/':
                log_folder = log_folder + '/'
            self.log_path = log_folder + now_str + '-' + self.__name + '.csv'
            self.__logfile = open(self.log_path,'wb')
            self.__logger = csv.writer(self.__logfile,delimiter=';')

        # Create inter-casu communication sockets
        self.__msg_queue = []
        if self.__msg_pub_addr and self.__neighbors:
            self.__msg_pub = self.__context.socket(zmq.PUB)
            self.__msg_pub.bind(self.__msg_pub_addr)
            self.__msg_sub = self.__context.socket(zmq.SUB)
            for direction in self.__neighbors:
                self.__msg_sub.connect(self.__neighbors[direction]['address'])
            self.__msg_sub.setsockopt(zmq.SUBSCRIBE, self.__name)

        # Connect the control publisher socket
        self.__pub = self.__context.socket(zmq.PUB)
        self.__pub.connect(self.__pub_addr)

        # Connect to the device and start receiving data
        self.__comm_thread.start()
        # Wait for the connection
        while not self.__connected:
            time.sleep(1)
        print('{0} connected!'.format(self.__name))


    def __update_readings(self):
        """
        Get data from Casu and update local data.
        """
        self.__sub = self.__context.socket(zmq.SUB)
        self.__sub.connect(self.__sub_addr)
        self.__sub.setsockopt(zmq.SUBSCRIBE, self.__name)

        while not self.__stop:
            [name, dev, cmd, data] = self.__sub.recv_multipart()
            self.__connected = True
            if dev == 'IR':
                if cmd == 'Ranges':
                    # Protect write with a lock
                    # to make sure all data is written before access
                    with self.__lock:
                        self.__ir_range_readings.ParseFromString(data)
                    self.__write_to_log(['ir_range', time.time()] + [r for r in self.__ir_range_readings.range])
                    self.__write_to_log(['ir_raw', time.time()] + [r for r in self.__ir_range_readings.raw_value])
                else:
                    print('Unknown command {0} for {1}'.format(cmd, self.__name))
            elif dev == 'Temp':
                if cmd == 'Temperatures':
                    with self.__lock:
                        self.__temp_readings.ParseFromString(data)
                    self.__write_to_log(['temp', time.time()] + [t for t in self.__temp_readings.temp])
                else:
                    print('Unknown command {0} for {1}'.format(cmd, self.__name))
            elif dev == 'Acc':
                if cmd == 'Measurements':
                    with self.__lock:
                        self.__acc_readings.ParseFromString(data)

                    if self.__acc_readings.reading:
                        acc_freqs = [0, 0, 0, 0]
                        acc_amps = [0, 0, 0, 0]

                        for i in range(0, 4):
                            acc_freqs[i] = self.__acc_readings.reading[i].freq
                            acc_amps[i] = self.__acc_readings.reading[i].amplitude

                        self.__write_to_log(['acc_freq', time.time()] + [f for f in acc_freqs])
                        self.__write_to_log(['acc_amp', time.time()] + [a for a in acc_amps])
            elif dev == 'Peltier':
                if cmd == 'Off':
                    self.__peltier_on = False
                    with self.__lock:
                        self.__peltier_setpoint.ParseFromString(data)
                    self.__write_to_log(['Peltier', time.time(), '0', self.__peltier_setpoint.temp])
                elif cmd == 'On':
                    self.__peltier_on = True
                    with self.__lock:
                        self.__peltier_setpoint.ParseFromString(data)
                    self.__write_to_log(['Peltier', time.time(), '1',  self.__peltier_setpoint.temp])
                else:
                    print('Unknown command {0} for {1}'.format(cmd, self.__name))
            else:
                print('Unknown device {0} for {1}'.format(dev, self.__name))

            if self.__msg_sub:
                try:
                    [name, msg, sender, data] = self.__msg_sub.recv_multipart(zmq.NOBLOCK)
                    # Protect the message queue update with a lock
                    with self.__lock:
                        self.__msg_queue.append({'sender':sender, 'data':data})
                except zmq.ZMQError:
                    # Nobody is sending us a message. No biggie.
                    pass

    def __cleanup(self):
        """
        Performs necessary cleanup operations, i.e. stops communication threads,
        closes connections and files.
        """
        # Wait for communicaton threads to finish
        self.__comm_thread.join()

        if self.__log:
            self.__logfile.close()

    def name(self):
        """
        Returns the name of this Casu instance.
        """
        return self.__name

    def stop(self):
        """
        Stops the Casu interface and cleans up.

        TODO: Need to disable all object access once Casu is stopped!
        """

        # Stop all devices
        self.temp_standby()
        self.vibration_standby()
        self.light_standby()
        self.diagnostic_led_standby()

        self.__stop = True
        self.__cleanup()
        print('{0} disconnected!'.format(self.__name))

    def get_range(self, id):
        """
        Returns the range reading (in cm) corresponding to sensor id.

        .. note::

           This API call might become deprecated in favor of get_raw_value,
           to better reflect actual sensor capabilities.
        """
        with self.__lock:
            if self.__ir_range_readings.range:
                return self.__ir_range_readings.range[id]
            else:
                return -1

    def get_ir_raw_value(self, id):
        """
        Returns the raw value from the IR proximity sensor corresponding to sensor id.

        """
        with self.__lock:
            if self.__ir_range_readings.raw_value:
                if id == ARRAY:
                    return [raw for raw in self.__ir_range_readings.raw_value]
                else:
                    return self.__ir_range_readings.raw_value[id]
            else:
                return -1

    def get_temp(self, id):
        """
        Returns the temperature reading of sensor id.

         """
        with self.__lock:
            if self.__temp_readings.temp:
                if id == ARRAY:
                    return [t for t in self.__temp_readings.temp]
                else:
                    return self.__temp_readings.temp[id - TEMP_F]
            else:
                return -1

    def set_temp(self, temp, id = PELTIER_ACT):
        """
        Sets the temperature reference of actuator id to temp.

        """
        if temp < TEMP_MIN:
            temp = TEMP_MIN
            print('Temperature reference limited to {0}!'.format(temp))
        elif temp > TEMP_MAX:
            temp = TEMP_MAX
            print('Temperature reference limited to {0}!'.format(temp))
        temp_msg = dev_msgs_pb2.Temperature()
        temp_msg.temp = temp
        device = "Peltier"
        self.__pub.send_multipart([self.__name, device, "temp",
                                   temp_msg.SerializeToString()])
        self.__write_to_log([device + "_temp", time.time(), temp])

    def temp_standby(self, id = PELTIER_ACT):
        """
        Turn the temperature actuator off.

        """
        temp_msg = dev_msgs_pb2.Temperature()
        temp_msg.temp = 0
        device = "Peltier"
        self.__pub.send_multipart([self.__name, device, "Off",
                                   temp_msg.SerializeToString()])
        self.__write_to_log([device + "_temp", time.time(), 0])

    def get_peltier_setpoint(self, id = PELTIER_ACT):
        """
        Get the temperature actuator setpoint and state.

        :return: (temp,on) tuple, where temp is the temperature setpoint,
        and on is True if the actuator is switched on.
        """
        return(self.__peltier_setpoint.temp,self.__peltier_on)

    #def set_vibration_freq(self, f, id = VIBE_ACT):
        """
        Sets the vibration frequency of the pwm motor.

        :param float f: Vibration frequency, between 0 and 500 Hz.
        """

    #    vibration = dev_msgs_pb2.VibrationSetpoint()
    #    vibration.freq = f
    #    vibration.amplitude = 0
    #    self.__pub.send_multipart([self.__name, "VibeMotor", "On",
    #                               vibration.SerializeToString()])
    #    self.__write_to_log(["vibe_ref", time.time(), f])

    def set_speaker_vibration(self, freq, intens,  id = VIBE_ACT):
        """
        Sets intensity value (0-100) and frequency to the speaker.

        :param float intens: Speaker intensity value , between 0 and 100 %.
               float freq: Speaker frequency value, between 0 and 500
        """
        if intens < 0:
            intens = 0
            print('Intensity value limited to {0}!'.format(intens))
        elif intens > 100:
            intens = 100
            print('Intensity value limited to {0}!'.format(intens))

        if freq < 0:
            freq = 0
            print('Frequency limited to {0}!'.format(freq))
        elif freq > 500:
            freq = 500
            print('Frequency limited to {0}!'.format(freq))

        vibration = dev_msgs_pb2.VibrationSetpoint()
        vibration.freq = freq
        vibration.amplitude = intens
        self.__pub.send_multipart([self.__name, "Speaker", "On",
                                   vibration.SerializeToString()])
        self.__write_to_log(["speaker_freq_pwm", time.time(), freq, intens])


    def set_motor_vibration(self, intens, id = VIBE_ACT):
        """
        Sets intens value (0-100) to the vibration motor.

        :param float : Motor intens value , between 0 and 100 %.
        """
        if intens < 0:
            intens = 0
            print('Motor intens value limited to {0}!'.format(intens))
        elif intens > 100:
            intens = 100
            print('Motor intens value limited to {0}!'.format(intens))

        vibration = dev_msgs_pb2.VibrationSetpoint()
        vibration.freq = 0
        vibration.amplitude = intens
        self.__pub.send_multipart([self.__name, "VibeMotor", "On",
                                   vibration.SerializeToString()])
        self.__write_to_log(["vibe_intens", time.time(), intens])

    def get_vibration_freq(self, id):
        """
        Returns the vibration frequency of actuator id.

        .. note::

           NOT implemented!
        """
        pass

    def get_vibration_amplitude(self, id):
        """
        Returns the vibration amplitude reported by sensor id.

        .. note::

           NOT implemented!
        """
        pass

    def vibration_standby(self, id  = VIBE_ACT):
        """
        Turn the vibration actuators (bot motor and speaker) off.
        """

        vibration = dev_msgs_pb2.VibrationSetpoint()
        vibration.freq = 0
        vibration.amplitude = 0
        self.__pub.send_multipart([self.__name, "VibeMotor", "Off",
                                   vibration.SerializeToString()])
        self.__pub.send_multipart([self.__name, "Speaker", "Off",
                                   vibration.SerializeToString()])
        self.__write_to_log(["vibe_ref", time.time(), 0])
        self.__write_to_log(["speaker_freq_intens", time.time(), 0, 0])


    def set_light_rgb(self, r = 0, g = 0, b = 0, id = LIGHT_ACT):
        """
        Set the color and intensity of the light actuator.
        Automatically turns the actuator on.

        :param float r: Red component intensity, between 0 and 1.
        :param float g: Green component intensity, between 0 and 1.
        :param float b: Blue component intensity, between 0 and 1.
        """
        # Limit values to [0,1] range
        r = sorted([0, r, 1])[1]
        g = sorted([0, g, 1])[1]
        b = sorted([0, b, 1])[1]
        light = base_msgs_pb2.ColorStamped()
        light.color.red = r
        light.color.green = g
        light.color.blue = b
        self.__pub.send_multipart([self.__name, "Light", "On",
                                   light.SerializeToString()])
        self.__write_to_log(["light_ref", time.time(), r, g, b])

    def light_standby(self, id = LIGHT_ACT):
        """
        Turn the light actuator off.
        """
        light = base_msgs_pb2.ColorStamped()
        light.color.red = 0
        light.color.green = 0
        light.color.blue = 0
        self.__pub.send_multipart([self.__name, "Light", "Off",
                                   light.SerializeToString()])
        self.__write_to_log(["light_ref", time.time(), 0, 0, 0])

    def set_diagnostic_led_rgb(self, r = 0, g = 0, b = 0, id = DLED_TOP):
        """
        Set the diagnostic LED light color. Automatically turns the actuator on.

        :param float r: Red component intensity, between 0 and 1.
        :param float g: Green component intensity, between 0 and 1.
        :param float b: Blue component intensity, between 0 and 1.
        """

        # Limit values to [0,1] range
        r = sorted([0, r, 1])[1]
        g = sorted([0, g, 1])[1]
        b = sorted([0, b, 1])[1]

        light = base_msgs_pb2.ColorStamped()
        light.color.red = r
        light.color.green = g
        light.color.blue = b
        self.__pub.send_multipart([self.__name, "DiagnosticLed", "On",
                                   light.SerializeToString()])
        self.__write_to_log(["dled_ref", time.time(), r, g, b])

    def get_diagnostic_led_rgb(self, id = DLED_TOP):
        """
        Get the diagnostic light RGB value.

        :return: An (r,g,b) tuple (values between 0 and 1).
        """
        pass

    def diagnostic_led_standby(self, id = DLED_TOP):
        """
        Turn the diagnostic LED off.
        """
        light = base_msgs_pb2.ColorStamped();
        light.color.red = 0
        light.color.green = 0
        light.color.blue = 0
        self.__pub.send_multipart([self.__name, "DiagnosticLed", "Off",
                                  light.SerializeToString()])
        self.__write_to_log(["dled_ref", time.time(), 0, 0, 0])

    def set_airflow(self, state = "", id = AIRFLOW_ACT):
        """
        Set the airflow intensity.

        :param float intensity: Airflow intensity (in precentage of maximum actuator value).
        """
        states = ["on", "off"]

        if state in states:
            self.__pub.send_multipart([self.__name, "Airflow", state, ""])
            self.__write_to_log(["airflow_set", time.time(), state])
            success = True
        else:
            print('Invalid airflow state')
            success = False

        return success




    '''
    def airflow_standby(self, id  = AIRFLOW_ACT):
        """
        Puts the airflow actuator on standby.
        """
        int_msg = dev_msgs_pb2.Airflow()
        int_msg.intensity = 0
        self.__pub.send_multipart([self.__name, "Airflow", "Off",
                                   int_msg.SerializeToString()])
        self.__write_to_log(["airflow_ref", time.time(), 0])
    '''

    def send_message(self, direction, msg):
        """
        Send a simple string message to one of the neighbors.
        """
        success = False
        if direction in self.__neighbors:
            self.__msg_pub.send_multipart([self.__neighbors[direction]['name'], 'Message',
                                           self.__name, msg])
            success = True

        return success

    def read_message(self):
        """
        Retrieve the latest message from the buffer.

        Returns a dictionary with sender(string), and data (string) fields.
        """
        msg = []
        if self.__msg_queue:
            with self.__lock:
                msg = self.__msg_queue.pop()

                # attempt to find the label (logical name for neighbour) from
                # the records found in the RTC file (now part of the Casu
                # instance)
                msg['label'] = self.__phys_logi_map.get(msg['sender'], None)

        return msg

    def __write_to_log(self, data):
        """
        Write one line of data to the logfile.
        """
        if self.__log:
            self.__logger.writerow(data)

    def __read_comm_links(self, rtc):
        '''
        parse the RTC file for communication links and return as a map.
        '''
        phys_logi_map = {}

        try:
            deploy = yaml.safe_load(file(rtc, 'r'))
            if 'neighbors' in deploy and deploy['neighbors'] is not None:
                for k, v in deploy['neighbors'].iteritems():
                    neigh = v.get('name', None)
                    if neigh:
                        phys_logi_map[neigh] = k

        except IOError:
            print "[W] could not read rtc conf file {}".format(rtc)

        return phys_logi_map




if __name__ == '__main__':

    casu1 = Casu()
    switch = -1
    count = 0
    while count < 10:
        print(casu1.get_range(IR_F))
        if switch > 0:
            casu1.diagnostic_led_standby(DLED_TOP)
        else:
            casu1.set_diagnostic_led_rgb(DLED_TOP, 1, 0, 0)
        switch *= -1
        time.sleep(1)
        count = count + 1

    casu1.stop()
