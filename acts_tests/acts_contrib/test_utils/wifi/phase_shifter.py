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


import subprocess
import threading
import time
from acts import logger

SHORT_SLEEP = 1

class VaunixPhaseShifter():
    """Class that implements Colby XR100 delay line."""

    def __init__(self):
        self.log = logger.create_tagged_trace_logger('VaunixPhaseShifter')
        self.binary = '/usr/local/bin/VaunixLPSController'
        self.frequency = 4000
        self.phase = 0

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.log.debug('')
        command = '{} {} 0'.format(self.binary, self.frequency)
        self.log.debug(command)
        output = subprocess.check_output(command, shell=True)
        self.log.debug(output)

    def set_phase(self, phase):
        self.phase = phase
        command = '{} {} {}'.format(self.binary, self.frequency, phase)
        self.log.debug(command)
        output = subprocess.check_output(command, shell=True)
        self.log.debug(output)

    def _loop_phase(self, phase_increment = 45, dwell_time=1):
        self.t = threading.current_thread()
        phase = 0
        while getattr(self.t, "do_run", True):
            self.log.info('Setting Phase to {}.'.format(phase))
            self.set_phase(phase)
            time.sleep(dwell_time)
            self.log.info('Computing next phase')
            phase = int((phase + phase_increment) % 360)
            self.log.info('Next Phase = {}.'.format(phase))
        print("Stopping phase loop.")

    def start_phase_loop(self, phase_increment = 45, dwell_time=1):
        t = threading.Thread(target=self._loop_phase, args=(phase_increment, dwell_time))
        t.start()

    def stop_phase_loop(self):
        self.t.do_run = False
