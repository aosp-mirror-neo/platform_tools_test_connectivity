#!/usr/bin/env python3
#
#   Copyright 2024 - The Android Open Source Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import socket
import time
from acts import logger

SHORT_SLEEP = 1


def create(configs):
    """Factory method for OTA chambers.

    Args:
        configs: list of dicts with chamber settings. settings must contain the
        following: type (string denoting type of chamber)
    """
    objs = []
    for config in configs:
        try:
            delay_line_class = globals()[config['model']]
        except KeyError:
            raise KeyError('Invalid instrument configuration.')
        objs.append(delay_line_class(config))
    return objs


def detroy(objs):
    for obj in objs:
        obj.teardown()


class DelayLineInstrument(object):
    """Base class implementation for delay line.

    Base class provides functions whose implementation is shared by all
    delay line models.
    """

    def reset(self):
        """Resets the delay line to its zero/home state."""
        raise NotImplementedError

    def set_delay(self, delay):
        """Set delay on delay line.

        Args:
            delay: value of desired delay in nanoseconds
        """
        raise NotImplementedError

    def get_delay(self):
        """Get delay on delay line."""
        raise NotImplementedError

    def teardown(self):
        """Teardown delay line instrument."""

        raise NotImplementedError


class FixedDelayLine(DelayLineInstrument):
    """Class that implements a fixed delay line"""

    def __init__(self, config):
        self.config = config.copy()
        self.delay = self.config['delay']

    def teardown(self):
        pass

    def reset(self):
        pass

    def set_delay(self, delay):
        self.log.error('Delay cannot be set on fixed delay line.')

    def get_delay(self):
        return self.delay


class ColbyXR100(DelayLineInstrument):
    """Class that implements Colby XR100 delay line."""

    def __init__(self, config):
        self.config = config.copy()
        self.device_id = self.config['ip_address']
        self.log = logger.create_tagged_trace_logger('ColbyXR100|{}'.format(
            self.device_id))

        # Create a socket object
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.settimeout(5.0)
            self.socket.connect((self.config['ip_address'], self.config['port']))
            id = self.send_message('*IDN?')
            self.log.info('ID Response: {}'.format(str(id)))
        except socket.error as e:
            raise RuntimeError("Socket error occurred:", str(e))

    def teardown(self):
        self.socket.close()

    def send_message(self, message):
        message += '\n'
        try:
            self.socket.sendall(message.encode())
            self.log.debug("Message sent: {}".format(str(message)))
        except:
            raise RuntimeError("Socket error occurred.")

        if "?" in message:
            try:
                response = self.socket.recv(1024)
                return response
            except socket.timeout:
                print("Timeout occurred while waiting for response.")
        return None

    def set_delay(self, delay):
        """Set delay on delay line.

        Args:
            delay: value of desired delay in nanoseconds
        """
        self.send_message('DEL {} ns'.format(delay))
        self.send_message('*OPC?')
        time.sleep(SHORT_SLEEP)

    def get_delay(self):
        """Get delay on delay line."""
        return self.send_message('DEL?')
