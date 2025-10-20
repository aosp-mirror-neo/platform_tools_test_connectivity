#!/usr/bin/env python3.8
#
#   Copyright 2024 - The Android Open Source Project
#
#   Licensed under the Apache License, Version 2.0 (the 'License');
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an 'AS IS' BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import collections
import itertools
import json
import logging
import numpy
import pandas
import os
import re
import subprocess
import time
from acts import asserts
from acts import base_test
from acts import context
from acts import utils
from acts.metrics.loggers.blackbox import BlackboxMappedMetricLogger
from acts_contrib.test_utils.wifi import delay_line
from acts_contrib.test_utils.wifi import phase_shifter
import acts_contrib.test_utils.bt.bt_test_utils as btutils
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils
from acts_contrib.test_utils.wifi import wifi_retail_ap as retail_ap
from acts_contrib.test_utils.wifi import wifi_test_utils as wutils
from acts_contrib.test_utils.wifi import channel_emulator
from acts_contrib.test_utils.wifi import wifi_test_utils as wutils
from functools import partial
from matplotlib import pyplot
from acts_contrib.test_utils.wifi.wifi_performance_test_utils.bokeh_figure import BokehFigure


MED_SLEEP = 6
SHORT_SLEEP = 1

class BtRangingLink(object):
    def __init__(self, initiator, responder, bt_ranging_params):
        self.initiator = initiator
        self.reflector = responder
        self.bt_ranging_params = bt_ranging_params
        utils.sync_device_time(self.initiator)
        utils.sync_device_time(self.reflector)
        self.setup_devices()

    def setup_devices(self):
        self.reflector.adb.shell("cmd bluetooth_manager disable")
        time.sleep(MED_SLEEP)
        try:
            self.reflector.adb.shell("rm data/misc/bluetooth/logs/cs_log*")
        except:
            logging.info('Could not delete CS logs')
        self.reflector.adb.shell("cmd bluetooth_manager enable")
        self.setprop_overwrite_default(self.reflector)
        self.restart_app(self.reflector)
        time.sleep(SHORT_SLEEP)
        self.app_click_reflector(self.reflector)

        self.initiator.adb.shell("cmd bluetooth_manager disable")
        time.sleep(MED_SLEEP)
        try:
            self.initiator.adb.shell("rm data/misc/bluetooth/logs/cs_log*")
        except:
            logging.info('Could not delete CS logs')
        self.initiator.adb.shell("cmd bluetooth_manager enable")
        self.setprop_overwrite_default(self.initiator)
    def restart_app(self, device):
        device.ensure_screen_on()
        device.unlock_screen()
        device.adb.shell("am force-stop com.android.bluetooth.channelsoundingtestapp")
        time.sleep(2)
        device.adb.shell(
            "am start -n com.android.bluetooth.channelsoundingtestapp/com.android.bluetooth.channelsoundingtestapp.MainActivity")

    def app_click_reflector(self, device):
        # step 1
        filename_re = re.compile(r'([^ ]+.xml)')
        #st = subprocess.check_output('adb -s {0} shell uiautomator dump'.format(device.serial), shell=True).decode('utf-8')
        st = device.adb.shell('uiautomator dump')
        filename_device = filename_re.findall(st)[0]
        device.adb.pull('{} tmp.xml'.format(filename_device))
        with open("tmp.xml", 'r') as f:
            xml = f.read()

        button_reflector = re.compile(
            r'text="Reflector" resource-id="com.android.bluetooth.channelsoundingtestapp:id/button_reflector" class="android.widget.Button" package="com.android.bluetooth.channelsoundingtestapp" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_reflector_cord = self.get_cord(button_reflector, xml)

        print("Push [Reflector] on reflector")
        self.push_button(device,button_reflector_cord)
        time.sleep(0.5)

        # step 2
        filename_re = re.compile(r'([^ ]+.xml)')
        st = device.adb.shell('uiautomator dump')
        filename_device = filename_re.findall(st)[0]
        device.adb.pull('{} tmp.xml'.format(filename_device))
        with open("tmp.xml", 'r') as f:
            xml = f.read()

        button_start_advertising = re.compile(
            r'text="Start Advertising" resource-id="com.android.bluetooth.channelsoundingtestapp:id/btn_advertising" class="android.widget.Button" package="com.android.bluetooth.channelsoundingtestapp" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_start_advertising_cord = self.get_cord(button_start_advertising, xml)

        print("Push [Start Advertising] on reflector")
        self.push_button(device, button_start_advertising_cord)
        time.sleep(0.5)


    def app_click_initiator(self, device, duration=10):
        # step 1
        filename_re = re.compile(r'([^ ]+.xml)')
        st = device.adb.shell('uiautomator dump')
        filename_device = filename_re.findall(st)[0]
        device.adb.pull('{} tmp.xml'.format(filename_device))
        with open("tmp.xml", 'r') as f:
            xml = f.read()

        button_initiator = re.compile(
            r'text="Initiator" resource-id="com.android.bluetooth.channelsoundingtestapp:id/button_initiator" class="android.widget.Button" package="com.android.bluetooth.channelsoundingtestapp" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_initiator_cord = self.get_cord(button_initiator, xml)

        print("Push [Initiator] on initiator")
        self.push_button(device, button_initiator_cord)
        time.sleep(0.5)

        # step 2
        filename_re = re.compile(r'([^ ]+.xml)')
        st = device.adb.shell('uiautomator dump')
        filename_device = filename_re.findall(st)[0]
        device.adb.pull('{} tmp.xml'.format(filename_device))
        with open("tmp.xml", 'r') as f:
            xml = f.read()

        button_connect_gatt = re.compile(
            r'text="Connect Gatt" resource-id="com.android.bluetooth.channelsoundingtestapp:id/btn_connect_gatt" class="android.widget.Button" package="com.android.bluetooth.channelsoundingtestapp" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_connect_gatt_cord = self.get_cord(button_connect_gatt, xml)

        button_start_distance_measurement = re.compile(
            r'text="Start Distance Measurement" resource-id="com.android.bluetooth.channelsoundingtestapp:id/btn_cs" class="android.widget.Button" package="com.android.bluetooth.channelsoundingtestapp" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_start_distance_measurement_cord = self.get_cord(button_start_distance_measurement, xml)

        print("Push [Connect] on initiator")
        self.push_button(device, button_connect_gatt_cord)
        time.sleep(MED_SLEEP)

        print("Push [Start Distance Measurement] on initiator")
        self.push_button(device, button_start_distance_measurement_cord)
        time.sleep(0.5)

        # step 3
        print('wait for {} seconds'.format(duration))
        time.sleep(duration)


        print("Push [Stop Distance Measurement] on initiator")
        self.push_button(device, button_start_distance_measurement_cord)
        time.sleep(0.5)


    def get_cord(self, p, fi):
        x1, y1, x2, y2 = p.findall(fi)[0]
        cord = ((int(x1) + int(x2)) // 2, (int(y1) + int(y2)) // 2)
        return cord


    def push_button(self, device, button_cord):
        device.ensure_screen_on()
        time.sleep(SHORT_SLEEP)
        device.adb.shell("input tap {0} {1}".format(button_cord[0], button_cord[1]))


    def setprop_and_load_cal(self, device):
        subprocess.run(["./cs_setprop.sh", device])
        time.sleep(SHORT_SLEEP)
        subprocess.run(["./load_cal_P24_zero.sh", device])
        time.sleep(SHORT_SLEEP)


    def setprop_overwrite_default(self, device):
        pass
        #device.adb.shell('setprop bluetooth.core.cs.channel_map 1FFFFFFFFFFFFC7FFFFC')
        #device.adb.shell('setprop bluetooth.core.cs.max_procedure_count 4')
        #device.adb.shell('setprop bluetooth.core.cs.max_subevent_len 2000000')


    def unlock_device(self, device):
        device.adb.shell("input keyevent 82")


    def start_channel_sounding(self, init_device, refl_device):
        self.app_click_reflector(refl_device)
        self.app_click_initiator(init_device)

    def parse_bt_cs_results(self, log_path):
        measurements = []
        with open(log_path,'r') as log:
            for line in log:
                if 'resultMeters' in line:
                    range = float(line.split(' ')[1].rstrip().rstrip(','))
                    if range == -1.976171:
                        measurements.append(float('nan'))
                    else:
                        measurements.append(range)
        avg_distance = numpy.mean(measurements)
        std_dev_distance = numpy.std(measurements)
        avg_rssi = 0
        std_dev_rssi = 0
        result = {
            'measurements': measurements,
            'summary': {'avg_distance': avg_distance, 'avg_rssi': avg_rssi,
                        'std_dev_distance': std_dev_distance, 'std_dev_rssi': std_dev_rssi,
                        }
        }
        return result

    def collect_log_and_rename(self, device, test_name):
        files = device.get_file_names("data/misc/bluetooth/logs")
        log_folder = context.get_current_context().get_full_output_path() + "/cs_logs"
        os.system("mkdir {0}".format(log_folder))
        for filename in files:
            if "cs_log" not in filename:
                continue
            log_path = context.get_current_context().get_full_output_path() + "/cs_logs/" + test_name + ".txt"
            device.pull_files(filename, log_path)
        return log_path
    def do_channel_sounding(self, test_name="temp", duration=20):
        self.initiator.adb.shell("cmd bluetooth_manager enable")

        # App setup
        self.restart_app(self.initiator)
        time.sleep(SHORT_SLEEP)

        self.app_click_initiator(self.initiator, duration)

        log_file_path = self.collect_log_and_rename(self.initiator, test_name=test_name)
        result = self.parse_bt_cs_results(log_file_path)

        self.initiator.adb.shell("cmd bluetooth_manager disable")
        self.initiator.adb.shell("rm data/misc/bluetooth/logs/cs_log*")
        return result

class BtRangingTest(base_test.BaseTestClass):
    """Class to test BT ranging.

    This class implements BT ranging in a conducted setup with programmable
    delay line. The class sets up the instruments, configures them, and characterizes
    ranging performance over different multipath profiles.
    """

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True

    def setup_class(self):
        """Initializes common test hardware and parameters.

        This function initializes hardware and compiles parameters that are
        common to all tests in this class.
        """
        self.duts = self.android_devices
        req_params = [
            'DelayLineInstruments', 'testbed_params', 'bt_ranging_params', 'ranging_test_params'
        ]
        opt_params = ['RetailAccessPoints']
        self.unpack_userparams(req_params, opt_params)
        self.testclass_params = self.ranging_test_params
        self.delay_lines = delay_line.create(self.DelayLineInstruments)
        if hasattr(self, 'RetailAccessPoints'):
            self.access_point = retail_ap.create(self.RetailAccessPoints)[0]
        self.paths = []
        for path in self.testbed_params['paths']:
            self.paths.append({'delay_intrument': self.delay_lines[path['delay_instrument_index']],
                               'attenuator': self.attenuators[path['attenuator_port']],
                               'phase_shifter': phase_shifter.VaunixPhaseShifter() if path.get('phase_shifter', 0) else None
                               })

        # Turn Wifi On
        if self.testclass_params.get('airplane_mode', 1):
            for dev in self.android_devices:
                self.log.info('Turning on airplane mode.')
                asserts.assert_true(utils.force_airplane_mode(dev, True),
                                    'Can not turn on airplane mode.')
                wutils.reset_wifi(dev)
                wutils.wifi_toggle_state(dev, True)
        for dev in self.android_devices:
            dev.droid.wakeLockAcquireDim()
        for atten in self.attenuators:
            atten.set_atten(0)

        self.testclass_results = {}

    def teardown_test(self):
        self.process_testcase_result(self.testclass_results[self.current_test_name])

    def teardown_class(self):
        # Turn WiFi OFF
        if hasattr(self, 'access_point'):
            self.access_point.teardown()
        for dev in self.android_devices:
            wutils.wifi_toggle_state(dev, False)
            dev.go_to_sleep()

    def test_bt_ranging(self):
        testcase_params = self.compile_test_params()
        self.ranging_link = BtRangingLink(self.duts[0], self.duts[1], self.bt_ranging_params)


        for path in self.paths:
            if path == testcase_params['swept_path']:
                continue
            if not isinstance(path['delay_intrument'], delay_line.FixedDelayLine):
                path['delay_intrument'].set_delay(self.testclass_params['fixed_path_delay'])
            path['attenuator'].set_atten(self.testclass_params['fixed_path_attenuation'])
        looped_phase = (self.testclass_params['swept_path_phase']['stop'] == -1)

        ranging_sweep_results = collections.OrderedDict()
        if looped_phase:
            testcase_params['swept_path']['phase_shifter'].start_phase_loop(
                self.testclass_params['swept_path_phase']['step'],
                self.testclass_params['swept_path_phase']['dwell_time'])
        for attenuation in testcase_params['attenuation_sweep']:
            ranging_sweep_results[attenuation] = collections.OrderedDict()
            for delay in testcase_params['delay_sweep']:
                ranging_sweep_results[attenuation][delay] = collections.OrderedDict()
                phase_sweep = [1] if looped_phase else testcase_params['phase_sweep']
                for phase in phase_sweep:
                    self.log.info('Swept Path Config: {}ns, {}dB, {}deg'.format(delay, attenuation, phase))
                    testcase_params['swept_path']['delay_intrument'].set_delay(delay)
                    testcase_params['swept_path']['attenuator'].set_atten(attenuation)
                    if not looped_phase:
                        testcase_params['swept_path']['phase_shifter'].set_phase(phase)
                    try:
                        result = self.ranging_link.do_channel_sounding(test_name='{}_{}_{}'.format(attenuation, delay, phase))
                    except:
                        result = {"summary": {
                            "avg_distance": float("nan"),
                            "std_dev_distance": float("nan")
                        }}
                    if not result:
                        result = {"summary": {
                            "avg_distance": float("nan"),
                            "std_dev_distance": float("nan")
                        }}
                    self.log.info(result['summary'])
                    ranging_sweep_results[attenuation][delay][phase] = result
        if looped_phase:
            testcase_params['swept_path']['phase_shifter'].stop_phase_loop()

        test_result = {}
        test_result['testcase_params']=testcase_params
        test_result['ranging_sweep_results'] = ranging_sweep_results
        self.testclass_results[self.current_test_name] = test_result

    def process_testcase_result(self, test_result):
        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.json'.format(self.current_test_name))
        with open(results_file_path, 'w') as results_file:
            json.dump(wputils.serialize_dict(test_result),
                      results_file,
                      indent=4)
        compiled_sweep_results = {'distance': [],'std_dev_distance': [],
                                  'rtt': [], 'std_dev_rtt': [],
                                  'rssi': [], 'std_dev_rssi': [],
                                  'std_dev': []}
        for current_attenuation, attenuation_results in test_result['ranging_sweep_results'].items():
            compiled_sweep_results['distance'].append([])
            compiled_sweep_results['std_dev_distance'].append([])
            compiled_sweep_results['rssi'].append([])
            compiled_sweep_results['std_dev_rssi'].append([])
            for current_delay, delay_results in attenuation_results.items():
                distance = numpy.mean([val['summary']['avg_distance'] for key, val in delay_results.items()])
                std_dev_distance = numpy.mean([val['summary']['std_dev_distance'] for key, val in delay_results.items()])
                compiled_sweep_results['distance'][-1].append(distance)
                compiled_sweep_results['std_dev_distance'][-1].append(std_dev_distance)

        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['distance'],
            'distance')
        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['std_dev_distance'],
            'std_dev_distance')

    def plot_attenuation_delay_sweep_results(self, row_axis_data, column_axis_data, plot_data, plot_name):
        idx = pandas.Index(row_axis_data)
        df = pandas.DataFrame(plot_data, index=idx, columns=column_axis_data)
        results_file_name = '{} - {}.csv'.format(self.current_test_name, plot_name)
        current_context = context.get_current_context().get_full_output_path()
        results_file_path = os.path.join(current_context, results_file_name)
        df.to_csv(results_file_path)
        vals = numpy.around(df.values, 2)
        norm = pyplot.Normalize(vals.min() - 1, vals.max() + 1)
        colours = pyplot.cm.coolwarm(norm(vals))

        fig = pyplot.figure(figsize=(15, 8))
        ax = fig.add_subplot(111, frameon=True, xticks=[], yticks=[])

        the_table = pyplot.table(cellText=vals, rowLabels=df.index, colLabels=df.columns,
                                 colWidths=[0.03] * vals.shape[1], loc='center',
                                 cellColours=colours)

        results_file_name = '{} - {}.png'.format(self.current_test_name, plot_name)
        current_context = context.get_current_context().get_full_output_path()
        results_file_path = os.path.join(current_context, results_file_name)
        pyplot.savefig(results_file_path, bbox_inches='tight')

    def compile_test_params(self):
        testcase_params = {
            'swept_path_index': 1,
            'num_paths': 2
            }

        testcase_params['swept_path'] = self.paths[testcase_params['swept_path_index']]
        num_atten_steps = int(
            (self.testclass_params['swept_path_attenuation']['stop'] - self.testclass_params['swept_path_attenuation']['start']) /
            self.testclass_params['swept_path_attenuation']['step'])+1
        testcase_params['attenuation_sweep'] = [
            self.testclass_params['swept_path_attenuation']['start'] + x * self.testclass_params['swept_path_attenuation']['step']
            for x in range(0, num_atten_steps)
        ]
        testcase_params['delay_sweep'] = numpy.arange(self.testclass_params['swept_path_delay']['start'],
                                                      self.testclass_params['swept_path_delay']['stop'],
                                                      self.testclass_params['swept_path_delay']['step'])
        testcase_params['phase_sweep'] = numpy.arange(self.testclass_params['swept_path_phase']['start'],
                                                      self.testclass_params['swept_path_phase']['stop'],
                                                      self.testclass_params['swept_path_phase']['step'])
        return testcase_params

class BtRangingFadingTest(base_test.BaseTestClass):
    """Class to test BT ranging.

    This class implements BT ranging in a conducted setup with programmable
    delay line. The class sets up the instruments, configures them, and characterizes
    ranging performance over different multipath profiles.
    """

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True
        self.tests = self.generate_test_cases()

    def setup_class(self):
        """Initializes common test hardware and parameters.

        This function initializes hardware and compiles parameters that are
        common to all tests in this class.
        """
        self.duts = self.android_devices
        req_params = [
            'testbed_params', 'bt_ranging_params', 'ranging_fading_test_params'
        ]
        opt_params = []
        self.unpack_userparams(req_params, opt_params)
        self.testclass_params = self.ranging_fading_test_params

        self.emulator, self.replace_attenuator, self.emul_gain = self.get_emulator_instrument()

        if self.emulator:
            if self.emulator_active:
                self.emulator.connect()

        self.emulator.set_input_power([5, 5])

        self.emulator.set_frequency([2437, 2437])
        self.correlation_map = {'non': None,
                           'med': 'LTE_2x2_Medium',
                           'high': 'LTE_2x2_High'}

        self.AVAILABLE_FADING_MODELS = {'A': 'WLAN_TGn_A_NLOS',
                                   'B': 'WLAN_TGax_B_NLOS_80M',
                                   'C': 'WLAN_TGax_C_NLOS_80M_PR',
                                   'D': 'WLAN_TGax_D_NLOS_80M_PR',
                                   'E': 'WLAN_TGax_E_NLOS_80M_PR',
                                   'F': 'WLAN_TGax_F_NLOS_NFL__80M_PR',
                                   'F-1': 'WLAN_TGax_F_NLOS_NFL_80M_1',
                                   'F-2': 'WLAN_TGax_F_NLOS_NFL_80M_2',
                                   'F-nospike': 'WLAN_TGax_F_NLOS_NFL_No_Spike',
                                   'Bypass-SISO': 'SISO',
                                   'Bypass-BUTLER': 'BUTLER',
                                   'delay1_loss3': 'WLAN_TGax_D_NLOS_80M_PR_Delay_1_Loss2nd_3'}

        # Turn Wifi On
        if self.testclass_params.get('airplane_mode', 1):
            for dev in self.android_devices:
                self.log.info('Turning on airplane mode.')
                asserts.assert_true(utils.force_airplane_mode(dev, True),
                                    'Can not turn on airplane mode.')
                wutils.reset_wifi(dev)
                wutils.wifi_toggle_state(dev, True)
        for dev in self.android_devices:
            dev.droid.wakeLockAcquireDim()

        self.testclass_results = {}

    def teardown_test(self):
        self.process_testcase_result(self.testclass_results[self.current_test_name])

    def teardown_class(self):
        # Turn WiFi OFF
        if hasattr(self, 'access_point'):
            self.access_point.teardown()
        for dev in self.android_devices:
            wutils.wifi_toggle_state(dev, False)
            dev.go_to_sleep()
        if self.emulator and self.emulator_active:
            if self.replace_attenuator:
                self.emulator.set_attenuation([-self.emul_gain]*4)
            self.emulator.teardown()

    def get_emulator_instrument(self):
        emulators = None
        if 'Emulator' in self.controller_configs:
            emulator_config = self.controller_configs['Emulator']
            emulators = channel_emulator.create(emulator_config)

        self.emulator_active, replace_attenuator = False, False
        emulator = None
        emulator_gain = 0.
        if emulators:
            emulator = emulators[0]
            if emulator_config[0]['Active'] == 'True':
                self.emulator_active = True
            if emulator_config[0]['ReplaceAttenuator'] == 'True':
                replace_attenuator = self.emulator_active and True

            if 'Gain' in emulator_config[0]:
                emulator_gain = float(emulator_config[0]['Gain'])

        return emulator, replace_attenuator, emulator_gain

    def _test_bt_ranging(self, testcase_params):
        testcase_params = self.compile_test_params(testcase_params)
        self.ranging_link = BtRangingLink(self.duts[0], self.duts[1], self.bt_ranging_params)

        self.emulator.set_attenuation([testcase_params['attenuation_sweep'][0]- self.emul_gain,
                                       testcase_params['attenuation_sweep'][0]- self.emul_gain])
        fading_model_name = self.AVAILABLE_FADING_MODELS[testcase_params['fading_model']]
        if fading_model_name in ['SISO', 'BUTLER']:
            self.emulator.channel_bypass_mode(channel_index=1, enable=True)
            self.emulator.set_bypass_type(channel_index=1, bypass_type=fading_model_name)
        else:
            self.emulator.set_propagation_model(propagation_model=fading_model_name)
            self.emulator.set_fading_spectrum_shape(1, [self.testclass_params['doppler_spectrum']] * 24)
        self.emulator.play()

        ranging_sweep_results = collections.OrderedDict()
        for doppler, attenuation in itertools.product(testcase_params['doppler_sweep'],
                                                      testcase_params['attenuation_sweep']
                                                      ):
            self.log.info("Testing {} Hz, {} dB".format(doppler,attenuation))
            ranging_sweep_results.setdefault(doppler, collections.OrderedDict())
            self.emulator.set_doppler_frequency(1, doppler=[doppler]*24)
            self.emulator.set_attenuation([attenuation - self.emul_gain, attenuation - self.emul_gain])
            try:
                result = self.ranging_link.do_channel_sounding(
                    test_name='{}_{}'.format(doppler,attenuation),
                    duration=self.testclass_params['bt_ranging_duration'])
            except:
                result = {"summary": {
                    "avg_distance": float("nan"),
                    "std_dev_distance": float("nan")
                 }}
            if not result:
                        result = {"summary": {
                            "avg_distance": float("nan"),
                            "std_dev_distance": float("nan")
                        }}
            self.log.info(result['summary'])
            ranging_sweep_results[doppler][attenuation] = result

        test_result = {}
        test_result['testcase_params']=testcase_params
        test_result['ranging_sweep_results'] = ranging_sweep_results
        self.testclass_results[self.current_test_name] = test_result

    def compute_cdf_stats(self, data, percentile_low=5, percentile_high=95):
        x, CDF_counts = numpy.unique(data, return_counts=True)
        y = numpy.cumsum(CDF_counts) / numpy.sum(CDF_counts)
        percentile_high_value = min(x[y > percentile_high/100])
        percentile_low_value = max(x[y < percentile_low/100]) if min(y) < percentile_low/100 else x[1]
        spread = percentile_high_value - percentile_low_value
        return x, y, spread
    def process_testcase_result(self, test_result):
        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.json'.format(self.current_test_name))
        with open(results_file_path, 'w') as results_file:
            json.dump(wputils.serialize_dict(test_result),
                      results_file,
                      indent=4)

        figure_distance = BokehFigure(title='Ranging Performance',
                                      x_label='Estimated Distance (m)',
                                      primary_y_label='Prob(Est. Dist<x)',
                                      legend_location='bottom_right')
        figure_distance_per_config = BokehFigure(title='Ranging Performance',
                                      x_label='Estimated Distance (m)',
                                      primary_y_label='Prob(Est. Dist<x)',
                                      legend_location='bottom_right')
        for curr_doppler in test_result["ranging_sweep_results"]:
            measurements = []
            for attenuation in test_result["ranging_sweep_results"][curr_doppler]:
                current_results = test_result["ranging_sweep_results"][curr_doppler][attenuation]["measurements"]
                x, y, spread = self.compute_cdf_stats(current_results, 5, 95)
                figure_distance_per_config.add_line(x_data=x, y_data=y,
                                         legend="Doppler: {}Hz, Att: {}dB".format(curr_doppler, attenuation) + ' (5/95 Spread: {:.1f})'.format(
                                             spread)
                                         )
                measurements.extend(current_results)
            x,y,spread = self.compute_cdf_stats(measurements, 5, 95)
            figure_distance.add_line(x_data=x, y_data=y,
                                  legend="Doppler {} Hz".format(curr_doppler) + ' (5/95 Spread: {:.1f})'.format(spread)
                                  )
        figure_distance.generate_figure()
        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.html'.format(test_result['testcase_params']['fading_model']))
        figure_distance.save_figure(results_file_path)

        figure_distance_per_config.generate_figure()
        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}_per_config.html'.format(test_result['testcase_params']['fading_model']))
        figure_distance_per_config.save_figure(results_file_path)




    def compile_test_params(self, testcase_params):
        num_atten_steps = int(
            (self.testclass_params['attenuation_sweep_params']['stop'] - self.testclass_params['attenuation_sweep_params']['start']) /
            self.testclass_params['attenuation_sweep_params']['step'])
        testcase_params['attenuation_sweep'] = [
            self.testclass_params['attenuation_sweep_params']['start'] + x * self.testclass_params['attenuation_sweep_params']['step']
            for x in range(0, num_atten_steps)
        ]
        if 'doppler_sweep_params' in self.testclass_params:
            num_doppler_steps = int(
                (self.testclass_params['doppler_sweep_params']['stop'] - self.testclass_params['doppler_sweep_params']['start']) /
                self.testclass_params['doppler_sweep_params']['step'])
            testcase_params['doppler_sweep'] = [
                self.testclass_params['doppler_sweep_params']['start'] + x * self.testclass_params['doppler_sweep_params']['step']
                for x in range(0, num_doppler_steps)
            ]
        else:
            testcase_params['doppler_sweep']=[None]
        return testcase_params

    def generate_test_cases(self, ranging_method = '11mc'):
        """Function that auto-generates test cases for a test class."""
        test_cases = []

        fading_model_vector = ['Bypass-SISO','Bypass-BUTLER', 'A', 'C', 'D', 'E', 'F', 'F-nospike']
        correlation_vector = ['non', 'med', 'high']

        for fading_model, correlation in itertools.product(fading_model_vector, correlation_vector):
            test_name = 'test_bt_ranging_fading_{}_{}'.format(
                fading_model, correlation)
            test_params = collections.OrderedDict(
                fading_model=fading_model,
                correlation=correlation,
                ranging_method=ranging_method
            )
            setattr(self, test_name, partial(self._test_bt_ranging, test_params))
            test_cases.append(test_name)
        print(test_cases)
        return test_cases