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
from typing import Literal

from acts import logger

SHORT_SLEEP = 0.1
ATTEMPTS_NUM = 50


def create(configs):
    """Factory method for wireless channel emulator.

    Args:
        configs: list of dicts with chamber settings. settings must contain the
        following: type (string denoting type of emulator)
    """
    objs = []
    for config in configs:
        try:
            emulator_class = globals()[config['Model']]
        except KeyError:
            raise KeyError('Invalid instrument configuration.')
        objs.append(emulator_class(config))
    return objs


def detroy(objs):
    for obj in objs:
        obj.teardown()


class SocketInstrument(object):
    """Base class implementation for channel emulator controlled over socket.

    Base class provides functions whose implementation is shared by all
    emulator models.
    """

    def connect(self):
        """Connect to instrument over socket"""
        raise NotImplementedError

    def reset(self):
        """Resets the emulator to its zero/home state."""
        raise NotImplementedError

    def set_output_gain(self, gains):
        """Set gain at output of channels (ports).

        Args:
            gains: list of gain values in dB at the output of corresponding channels (ports)
        """
        raise NotImplementedError

    def get_output_gain(self, channels_list):
        """Get gain at the output of given channels (ports)."""
        raise NotImplementedError

    def set_path_loss(self, losses):
        """Set losses from input to output ports.

        Args:
            losses: list of loss values in dB between input and output ports
        """
        raise NotImplementedError

    def set_attenuation(self, atten):
        """Set attenuation between input and output ports.

        Args:
            atten: list of attenuation values in dB between input and output ports
        """
        raise NotImplementedError

    def set_output_power(self, powers):
        """Set power [dBm] at output of RF ports.

        Args:
            gains: list of power values in dBm at the output of corresponding ports
        """
        raise NotImplementedError

    def get_output_power(self, ports_list):
        """Get power at the output of given port numbers."""
        raise NotImplementedError

    def get_path_loss(self, ports_list):
        """Get path loss between input and output ports."""
        raise NotImplementedError

    def play(self):
        """Start playing channel emulation."""
        raise NotImplementedError

    def stop(self):
        """Stop playing channel emulation."""
        raise NotImplementedError

    def teardown(self):
        """Teardown emulator instrument."""

        raise NotImplementedError


class PropsimF8820B(SocketInstrument):
    """Class that implements Propsim F64 wireless channel emulator."""

    def __init__(self, config):
        self.config = config.copy()
        self.device_id = self.config['Address']
        self.log = logger.create_tagged_trace_logger('PropsimF64|{}'.format(
            self.device_id))

        # Create a socket object
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5.0)

    def connect(self):
        """Connect to instrument over socket"""
        try:
            self.socket.connect((self.config['Address'], self.config['Port']))
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

    def set_output_gain(self, gains):
        """Set gain at output of channels (ports).

        Args:
            gains: list of gain values in dB at the output of corresponding channels (ports)
        """
        for i, gain in enumerate(gains):
            if gain is not None:
                self.send_message('OUTP:GAIN:CH {},{}'.format(i+1, gain))
                self.send_message('*OPC?')
        time.sleep(SHORT_SLEEP)

    def get_output_gain(self, channels_list):
        """Get gain at the output of given channels (ports)."""
        gains = []
        for ch in channels_list:
            gain = self.send_message('OUTP:GAIN:CH? {}'.format(ch))
            gains.append(gain)

        return gains

    def set_attenuation(self, atten_list):
        """Set attenuation between input and output ports.

        Args:
            atten: list of attenuation values in dB between input and output ports
        """
        gains = [-a for a in atten_list]
        self.set_output_gain(gains)

    def play(self):
        """Start playing channel emulation."""
        pass

    def stop(self):
        """Stop playing channel emulation."""
        pass

class VertexSDE410C2(SocketInstrument):
    """Class that implements Spirent Vertex wireless channel emulator."""

    def __init__(self, config):
        self.config = config.copy()
        self.device_id = self.config['Address']
        self.log = logger.create_tagged_trace_logger('VertexSDE410C2|{}'.format(
            self.device_id))

        # Create a socket object
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5.0)

        self.ports_map = ['A1', 'B1', 'A2', 'B2', 'A3', 'B3', 'A4', 'B4']

    def connect(self):
        """Connect to instrument over socket"""
        try:
            self.socket.connect((self.config['Address'], self.config['Port']))
            id = self.send_message('*IDN?')
            self.log.info('ID Response: {}'.format(str(id)))
        except socket.error as e:
            raise RuntimeError("Socket error occurred:", str(e))

    def teardown(self):
        time.sleep(1)
        self.stop()
        self.socket.close()

    def send_message(self, message):
        message += '\r\n'
        try:
            self.socket.sendall(message.encode())
            self.log.debug("Message sent: {}".format(str(message)))
        except:
            raise RuntimeError("Socket error occurred.")

        if "?" in message:
            try:
                response = self.socket.recv(1024)
                return response.decode()
            except socket.timeout:
                print("Timeout occurred while waiting for response.")
        return None

    def set_output_power(self, powers):
        """Set power [dBm] at output of RF ports.

        Args:
            gains: list of power values in dBm at the output of corresponding ports
        """
        assert len(powers) <= len(self.ports_map), '# power values larger than # ports'
        for i, pwr in enumerate(powers):
            if pwr is not None:
                message = f'SYST:PORT:{self.ports_map[i]}:OUTP {pwr}'
                self.send_message(message)
                time.sleep(SHORT_SLEEP)

    def get_output_power(self, ports_list):
        """Get power at the output of given ports."""
        powers = []
        for i in ports_list:
            assert 0 < i <= len(self.ports_map), f'port number {i} out of range [1, {len(self.ports_map)}]'
            message = f'SYST:PORT:{self.ports_map[i]}:OUTP?'
            pwr_str = self.send_message(message)
            idx1 = pwr_str.find('\n') + 1
            idx2 = pwr_str.find('\r')
            pwr  = int(pwr_str[idx1:idx2])
            powers.append(pwr)

        return powers

    def set_path_loss(self, losses):
        """Set losses from input to output ports.

        Args:
            losses: list of loss values in dB between input and output ports
        """
        assert len(losses) <= len(self.ports_map), '# list of losses larger than # ports'
        for i, loss in enumerate(losses):
            if loss is not None:
                for _ in range(ATTEMPTS_NUM):
                    message = f'SYST:PORT:{self.ports_map[i]}:LOSS {loss}'
                    self.send_message(message)

                    message = f'SYST:PORT:{self.ports_map[i]}:LOSS?'
                    response = self.send_message(message)
                    if str(int(loss)) in response:
                        time.sleep(SHORT_SLEEP)
                        break

    def get_path_loss(self, ports_list):
        """Get path loss between input and output ports."""
        losses = []
        for i in ports_list:
            assert 0 < i <= len(self.ports_map), f'port number {i} out of range [1, {len(self.ports_map)}]'
            message = f'SYST:PORT:{self.ports_map[i]}:LOSS?'
            loss_str = self.send_message(message)
            idx1 = loss_str.find('\n') + 1
            idx2 = loss_str.find('\r')
            loss = int(loss_str[idx1:idx2])
            losses.append(loss)

        return losses

    def set_input_power(self, power_list):
        """Set expected power at the input of given ports."""
        for i, power in enumerate(power_list):
            if power is not None:
                for _ in range(ATTEMPTS_NUM):
                    message = f'SYST:PORT:{self.ports_map[i]}:INP {power}'
                    self.send_message(message)

                    message = f'SYST:PORT:{self.ports_map[i]}:INP?'
                    response = self.send_message(message)
                    if str(int(power)) in response:
                        time.sleep(SHORT_SLEEP)
                        break

    def set_attenuation(self, atten_list):
        """Set attenuation between input and output ports.

        Args:
            atten: list of attenuation values in dB between input and output ports
        """
        self.set_path_loss(atten_list)

    def set_frequency(self, freq_list):
        """Set frequency at the input of the ports.

        Args:
            freq_list: list of frequency values in MHz at input ports
        """
        for i, freq in enumerate(freq_list):
            for _ in range(ATTEMPTS_NUM):
                message = f'SYST:PORT:{self.ports_map[i]}:INFREQ {freq}'
                self.send_message(message)

                message = f'SYST:PORT:{self.ports_map[i]}:INFREQ?'
                response = self.send_message(message)
                if str(int(freq)) in response:
                    time.sleep(SHORT_SLEEP)
                    break

    def channel_bypass_mode(self, channel_index, enable=True):
        """Enable/disable fading model on the channel model with specified index.

        Args:
            channel_index: index of the channel model to bypass on current radio configuration
            enable: enable (True) or disable (False) channel model
        """
        bypass_mode = 'ON' if enable else 'OFF'
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:CHM{channel_index}:BYPass {bypass_mode}'
            self.send_message(message)

            message = f'SYST:CHM{channel_index}:BYPass?'
            response = self.send_message(message)
            if bypass_mode in response:
                time.sleep(SHORT_SLEEP)
                break

    def set_bypass_type(self, channel_index, bypass_type: Literal['SISO', 'BUTLER']):
        """Set type of bypass mode on specified channel model index.

        Args:
            channel_index: index of the channel model with specified bypass mode
            bypass_type: type of bypass mode, SISO (direct connection between input/output) or Butler model
        """
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:CHM{channel_index}:BYPTYP {bypass_type}'
            self.send_message(message)

            message = f'SYST:CHM{channel_index}:BYPTYP?'
            response = self.send_message(message)
            if bypass_type in response:
                time.sleep(SHORT_SLEEP)
                break

    def set_propagation_model(self, channel_index: int = 1, propagation_model: str = 'default'):
        """Set fading propagation conditions on specified channel model index.

        Args:
            channel_index: index of the channel model with specified bypass mode
            propagation_model: fading propagation conditions
        """
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:CHM{channel_index}:PROP:LIB {propagation_model}'
            self.send_message(message)

            message = f'SYST:CHM{channel_index}:PROP:LIB?'
            response = self.send_message(message)
            if propagation_model in response:
                time.sleep(SHORT_SLEEP)
                break

    def set_correlation(self, channel_index: int = 1, correlation_model: str = 'Uncorrelated_2x2'):
        """Set spatial correlation on specified channel model index.

        Args:
            channel_index: index of the channel model with specified bypass mode
            correlation_model: correlation model (defining correlation matrix) on specified channel model
        """
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:CHM{channel_index}:CORR:LIB {correlation_model}'
            self.send_message(message)

            message = f'SYST:CHM{channel_index}:CORR:LIB?'
            response = self.send_message(message)

            if correlation_model in response:
                time.sleep(SHORT_SLEEP)
                break

    def set_doppler_frequency(self, channel_index: int, doppler: list[float]):
        """Set Doppler frequency for fading model paths on specified channel model index.
        Resolution of doppler frequency values in Hz is 0.01

        Args:
            channel_index: index of the channel model with specified bypass mode
            doppler: list of Doppler frequency values in Hz corresponding to different paths in the fading model
        """
        for path_idx, freq in enumerate(doppler):
            if freq is None:
                continue
            freq_truncated = round(freq * 100) / 100
            for _ in range(ATTEMPTS_NUM):
                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx+1}:DFR {freq_truncated}'
                self.send_message(message)

                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx+1}:DFR?'
                response = self.send_message(message)

                if str(freq_truncated) in response:
                    time.sleep(SHORT_SLEEP)
                    break
                else:
                    self.send_message('*CLS')

    def set_spike_frequency(self, channel_index: int, spike_doppler: list[float]):
        """Set Doppler frequency for fading model paths on specified channel model index.
        Resolution of doppler frequency values in Hz is 0.01

        Args:
            channel_index: index of the channel model with specified bypass mode
            spike_doppler: list of spike Doppler frequency in Hz corresponding to different paths in the fading model
        """
        for path_idx, freq in enumerate(spike_doppler):
            if freq is None:
                continue
            freq_truncated = round(freq * 100) / 100
            for _ in range(ATTEMPTS_NUM):
                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx+1}:SPFR {freq_truncated}'
                self.send_message(message)

                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx+1}:SPFR?'
                response = self.send_message(message)

                if str(freq_truncated) in response:
                    time.sleep(SHORT_SLEEP)
                    break
                else:
                    self.send_message('*CLS')

    def set_fading_spectrum_shape(self, channel_index: int, shape_vector: list[str]):
        """Set fading spectrum shape for fading model paths on specified channel model index.
        Available options are: C3DB, C6DB, ROUNd, FLAT, R12DB, BELL, BELLSP

        Args:
            channel_index: index of the channel model with specified bypass mode
            shape_vector: list of spectrum shapes corresponding to different paths in the fading model
        """
        for path_idx, shape in enumerate(shape_vector):
            if shape is None:
                continue
            for _ in range(ATTEMPTS_NUM):
                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx + 1}:FSHAPe {shape}'
                self.send_message(message)

                message = f'SYST:CHM{channel_index}:PROP:PATH{path_idx + 1}:FSHAPe?'
                response = self.send_message(message)

                if shape in response:
                    time.sleep(SHORT_SLEEP)
                    break
                else:
                    self.send_message('*CLS')

    def play(self):
        """Start playing channel emulation."""
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:EMUL:PLAY'
            self.send_message(message)

            message = 'SYST:EMUL:STAT?'
            response = self.send_message(message)

            if 'PLAYING' in response:
                time.sleep(SHORT_SLEEP)
                break

    def stop(self):
        """Stop playing channel emulation."""
        for _ in range(ATTEMPTS_NUM):
            message = f'SYST:EMUL:STOP'
            self.send_message(message)

            message = 'SYST:EMUL:STAT?'
            response = self.send_message(message)

            if 'STOPPED' in response:
                time.sleep(SHORT_SLEEP)
                break
