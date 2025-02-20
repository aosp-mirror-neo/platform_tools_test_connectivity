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
import acts_contrib.test_utils.bt.bt_test_utils as btutils
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils
from acts_contrib.test_utils.wifi import wifi_test_utils as wutils

SHORT_SLEEP = 1
MED_SLEEP = 5


class UwbRangingLink(object):
    def __init__(self, initiator, responder, uwb_ranging_params):
        self.initiator_dut = initiator
        self.responder_dut = responder
        self.uwb_ranging_params = uwb_ranging_params
        self.responder_dut.adb.shell('cmd uwb force-country-code enabled US')
        self.initiator_dut.adb.shell('cmd uwb force-country-code enabled US')
        self.responder_dut.adb.shell('cmd uwb enable-uwb')
        self.initiator_dut.adb.shell('cmd uwb enable-uwb')
        self.ANTENNA_MAPPING = {'ranging': 'none', 'patch': 'azimuth-only'}

    def setup_initiator(self):
        self.initiator_dut.adb.shell('cmd uwb start-fira-ranging-session '
                                     '-i 1 -c {} -t controller -r initiator -a 11 -d 22 -e {} -j 3600000'.format(
            self.uwb_ranging_params['channel'], self.ANTENNA_MAPPING[self.uwb_ranging_params['initiator_antenna']]))

    def clean_up_initiator(self):
        self.initiator_dut.adb.shell('cmd uwb stop-all-ranging-sessions')

    def measure_range(self, duration):
        self.responder_dut.adb.shell('cmd uwb start-fira-ranging-session '
                                     '-i 1 -c {} -t controlee -r responder -a 22 -d 11 -e {} -j 3600000'.format(
            self.uwb_ranging_params['channel'], self.ANTENNA_MAPPING[self.uwb_ranging_params['responder_antenna']]))
        ranging_output = ''
        for idx in range(int(duration/3)):
            ranging_output = ranging_output + self.responder_dut.adb.shell('cmd uwb get-ranging-session-reports 1')
            time.sleep(3)
        self.responder_dut.adb.shell('cmd uwb stop-all-ranging-sessions')
        logging.debug(ranging_output)
        ranging_result = self.parse_ranging_result(ranging_output)
        return ranging_result

    def parse_ranging_result(self, ranging_output):
        pattern = r"meters: ([\d.]+).*rssiDbm: (-?\d+)"
        matches = re.findall(pattern, ranging_output)

        measurements = []
        for match in matches:
            meters, rssiDbm = match
            measurements.append({"distance": float(meters), "rssi": int(rssiDbm)})
        distance_array = [result['distance'] for result in measurements]
        rssi_array = [result['rssi'] for result in measurements]
        avg_distance = numpy.mean(distance_array)
        std_dev_distance = numpy.std(distance_array)
        avg_rssi = numpy.mean(rssi_array)
        std_dev_rssi = numpy.std(rssi_array)
        result = {
            'raw_results': measurements,
            'compiled_results': {'distance' : distance_array, 'rssi': rssi_array},
            'summary': {'avg_distance': avg_distance, 'avg_rssi': avg_rssi,
                        'std_dev_distance': std_dev_distance, 'std_dev_rssi': std_dev_rssi,
                        }
        }
        return result

class BtRangingLinkV2(object):
    def __init__(self, initiator, responder, bt_ranging_params):
        # self.dut1 = self.android_devices[0]
        # self.dut2 = self.android_devices[1]
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
        #device.adb.shell("input tap {} {}".format(button_reflector_cord[0], button_reflector_cord[1]))
        time.sleep(0.5)

        # step 2
        filename_re = re.compile(r'([^ ]+.xml)')
        #st = subprocess.check_output('adb -s {0} shell uiautomator dump'.format(device.serial), shell=True).decode('utf-8')
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
        #device.adb.shell("input tap {} {}".format(button_start_advertising_cord[0],
        #                                                      button_start_advertising_cord[1]))
        time.sleep(0.5)


    def app_click_initiator(self, device, duration=10):
        # step 1
        filename_re = re.compile(r'([^ ]+.xml)')
        st = device.adb.shell('uiautomator dump')
        #st = subprocess.check_output('adb -s {0} shell uiautomator dump'.format(device.serial), shell=True).decode('utf-8')
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
        #device.adb.shell("input tap {} {}".format(button_initiator_cord[0], button_initiator_cord[1]))
        time.sleep(0.5)

        # step 2
        filename_re = re.compile(r'([^ ]+.xml)')
        st = device.adb.shell('uiautomator dump')
        #st = subprocess.check_output('adb -s {0} shell uiautomator dump'.format(device.serial), shell=True).decode('utf-8')
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
        #device.adb.shell(
        #    "input tap {} {}".format(button_connect_gatt_cord[0], button_connect_gatt_cord[1]))
        time.sleep(MED_SLEEP)

        print("Push [Start Distance Measurement] on initiator")
        self.push_button(device, button_start_distance_measurement_cord)
        #device.adb.shell("input tap {} {}".format(button_start_distance_measurement_cord[0],
        #                                                      button_start_distance_measurement_cord[1]))
        time.sleep(0.5)

        # step 3
        print('wait for {} seconds'.format(duration))
        time.sleep(duration)

        # if want infinite until button press
        # _ = input("Press Enter to continue...")

        print("Push [Stop Distance Measurement] on initiator")
        self.push_button(device, button_start_distance_measurement_cord)
        #device.adb.shell("input tap {} {}".format(button_start_distance_measurement_cord[0],
        #                                                      button_start_distance_measurement_cord[1]))
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
        device.adb.shell('setprop bluetooth.core.cs.channel_map 1FFFFFFFFFFFFC7FFFFC')
        device.adb.shell('setprop bluetooth.core.cs.max_procedure_count 4')
        device.adb.shell('setprop bluetooth.core.cs.max_subevent_len 2000000')


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

        # self.collect_log_and_rename(self.initiator, test_name=test_name)
        log_filepath = "./{0}".format(test_name)
        #adb("pull data/misc/bluetooth/logs {0}".format(log_filepath), device.serial)
        #self.initiator.pull_files('data/misc/bluetooth/logs', log_filepath)

        log_file_path = self.collect_log_and_rename(self.initiator, test_name=test_name)
        result = self.parse_bt_cs_results(log_file_path)

        self.initiator.adb.shell("cmd bluetooth_manager disable")
        self.initiator.adb.shell("rm data/misc/bluetooth/logs/cs_log*")
        return result

class BtRangingLink(object):
    def __init__(self, initiator, responder, bt_ranging_params):
        # self.dut1 = self.android_devices[0]
        # self.dut2 = self.android_devices[1]
        self.initiator = initiator
        self.reflector = responder
        self.bt_ranging_params = bt_ranging_params
        self.CSParameters = bt_ranging_params['CSParameters']
        utils.sync_device_time(self.initiator)
        utils.sync_device_time(self.reflector)
        self.setup_devices()

    def setup_devices(self):
        # CS setprop
        for dut in [self.initiator, self.reflector]:
            self.cs_setprop(dut)
            time.sleep(SHORT_SLEEP)
            logging.info('Loading BT cal')
            subprocess.call([self.bt_ranging_params['calibration_file'], dut.serial])
            #self.load_cal(dut)
            time.sleep(SHORT_SLEEP)
            dut.button_cord = self.app_setup(dut)
        time.sleep(MED_SLEEP)

    def cs_setprop(self, dut):
        logging.info("{0} setting CS prop ...".format(dut.serial))
        for key in self.CSParameters:
            dut.adb.shell("setprop bluetooth.core.cs.{0} {1}".format(key, self.CSParameters[key]))

        ori_mask = dut.adb.getprop("persist.bluetooth.bqr.event_mask")
        new_mask = (int(ori_mask) | 1)
        dut.adb.shell("setprop persist.bluetooth.bqr.event_mask {0}".format(new_mask))
        dut.adb.shell("setprop persist.bluetooth.bqr.min_interval_ms 500")

        dut.adb.shell("touch data/misc/bluetooth/logs/cs_log_tmp.txt")
        dut.adb.shell("cmd bluetooth_manager disable")
        dut.adb.shell("cmd bluetooth_manager wait-for-state:STATE_OFF")
        dut.adb.shell("rm data/misc/bluetooth/logs/cs_log*")
        dut.adb.shell("cmd bluetooth_manager enable")

        time.sleep(MED_SLEEP)

    def load_cal(self, dut):
        logging.info("{0} loading calibration file ...".format(dut.serial))
        with open(self.bt_ranging_params['calibration_file'], 'r') as f:
            for line in f:
                if not line[0] == '#':
                    dut.adb.shell("/vendor/bin/hw/hci_inject -c {0}".format(line))

    def app_setup(self, dut):
        logging.info("{0} restarting CS App ...".format(dut.serial))
        dut.ensure_screen_on()
        dut.unlock_screen()
        self._restart_app(dut)

        button_connect_gatt = re.compile(
            r'text="Connect Gatt" resource-id="com.example.ble_test:id/btn_connect_gatt" class="android.widget.Button" package="com.example.ble_test" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_adv = re.compile(
            r'text="Start Adv" resource-id="com.example.ble_test:id/btn_adv" class="android.widget.Button" package="com.example.ble_test" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_clear_log = re.compile(
            r'text="Clear log" resource-id="com.example.ble_test:id/btn_clear_log" class="android.widget.Button" package="com.example.ble_test" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )
        button_cs = re.compile(
            r'text="Start CS" resource-id="com.example.ble_test:id/btn_cs" class="android.widget.Button" package="com.example.ble_test" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="\[([0-9]*),([0-9]*)]\[([0-9]*),([0-9]*)\]"'
        )

        dut_xml = ""
        filename_re = re.compile(r'([^ ]+.xml)')
        st = subprocess.check_output('adb -s {0} shell uiautomator dump'.format(dut.serial), shell=True).decode('utf-8')
        filename_device = filename_re.findall(st)[0]
        dut.adb.pull("{0} tmp.xml".format(filename_device))
        with open("tmp.xml", 'r') as f:
            dut_xml = f.read()
        connect_gatt_cord = self._get_cord(button_connect_gatt, dut_xml)
        adv_cord = self._get_cord(button_adv, dut_xml)
        clear_log_cord = self._get_cord(button_clear_log, dut_xml)
        cs_cord = self._get_cord(button_cs, dut_xml)
        button_cord = {"connect_gatt": connect_gatt_cord,
                       "adv": adv_cord,
                       "clear_log": clear_log_cord,
                       "cs": cs_cord}

        return button_cord

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

    def collect_bt_metric(self, tag):
        self._get_bt_link_metrics(self.initiator, duration=5, bqr_tag='Monitoring , Handle: 0x0040', tag=tag)
        self._get_bt_link_metrics(self.reflector, duration=5, bqr_tag='Monitoring , Handle: 0x0040', tag=tag)


    def start_advertising(self):
        # Start CS
        logging.info("Push [Start Adv] on reflector")
        self._push_button(self.reflector, self.reflector.button_cord["adv"])
        time.sleep(SHORT_SLEEP)

    def parse_bt_cs_results(self, log_path):
        measurements = []
        with open(log_path,'r') as log:
            for line in log:
                if 'resultMeters' in line:
                    range = float(line.split(' ')[1].rstrip())
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
    def do_channel_sounding(self, test_name="cs_log_temp"):
        self.cs_setprop(self.initiator)
        self.initiator.button_cord = self.app_setup(self.initiator)

        logging.info("Push [Connect Gatt] on initiator")
        self._push_button(self.initiator, self.initiator.button_cord["connect_gatt"])
        found = self._wait_for_keyword(self.initiator, "CYDBG: MTU changed to: 517", start_time=utils.get_current_epoch_time(), timeout=10)
        time.sleep(MED_SLEEP)
        if not found:
            return False

        logging.info("Push [Start CS] on initiator")
        push_button_time = utils.get_current_epoch_time()
        self._push_button(self.initiator, self.initiator.button_cord["cs"])

        keyword_finish_procedures = "CYDBG: Add Node {0} with distance".format(self.CSParameters["max_procedure_count"])
        timeout = self.CSParameters["max_procedure_count"] * self.CSParameters["min_procedure_interval"] *  self.CSParameters["conn_interval"] * 1.25 / 1000 * 1.5 # may need to adjust according to max_procedure_count
        self._wait_for_keyword(self.initiator, keyword_finish_procedures, push_button_time, timeout)
        time.sleep(MED_SLEEP)

        log_file_path = self.collect_log_and_rename(self.initiator, test_name=test_name)
        result = self.parse_bt_cs_results(log_file_path)
        #self.log.info("Total Test run time: {0} s".format((utils.get_current_epoch_time() - self.begin_time)/1000.0))
        return result

    def _restart_app(self, device):
        device.adb.shell("am force-stop com.example.ble_test")
        time.sleep(2)
        device.adb.shell("am start -n com.example.ble_test/com.example.ble_test.MainActivity")

    def _restart_bt(self, device):
        device.adb.shell("cmd bluetooth_manager disable")
        device.adb.shell("cmd bluetooth_manager wait-for-state:STATE_OFF")
        device.adb.shell("cmd bluetooth_manager enable")

    def _get_cord(self, p, fi):
        x1, y1, x2, y2 = p.findall(fi)[0]
        cord = ((int(x1) + int(x2)) // 2, (int(y1) + int(y2)) // 2)
        return cord

    def _wait_for_keyword(self, dut, keyword, start_time, timeout=600):
        wait = True
        while wait:
            if utils.get_current_epoch_time() - start_time > timeout * 1000:
                logging.info("Wait for {0} timeout".format(keyword))
                return False
            time.sleep(0.5)
            result = dut.search_logcat(keyword, start_time, utils.get_current_epoch_time())
            if len(result) > 0:
                wait = False
                logging.info("Found \"{0}\" with wait time {1} s".format(keyword, (
                            utils.get_current_epoch_time() - start_time) / 1000.0))
                return True

    def _push_button(self, dut, button_cord):
        dut.ensure_screen_on()
        #dut.unlock_screen()
        time.sleep(SHORT_SLEEP)
        dut.adb.shell("input tap {0} {1}".format(button_cord[0], button_cord[1]))

    def _read_distance_from_logcat(self, logcat_filename):
        distance_readout = []
        counter_readout = []
        with open(logcat_filename, 'r') as f:
            for line in f:
                if "---- Distance" in line:
                    distance_readout.append(float(line.split()[-2]))
                if "---- End of Procedure complete counter" in line:
                    counter_readout.append(int(line.split()[-6].split(':')[-1]))

        distance_readout = numpy.array(distance_readout)
        counter_readout = numpy.array(counter_readout)

        return counter_readout, distance_readout

    def _get_bt_link_metrics(self, dut, duration=5, bqr_tag='Monitoring , Handle: 0x0040', tag=''):
        """Get bt link metrics such as rssi and tx pwls.

        Returns:
            master_metrics_list: list of metrics of central device
            slave_metrics_list: list of metric of peripheral device
        """

        self.raw_bt_metrics_path = os.path.join(context.get_current_context().get_full_output_path(),
                                                'BT_Raw_Metrics')

        # Get master rssi and power level
        process_data_dict = btutils.get_bt_metric(
            dut, duration=duration, bqr_tag=bqr_tag, tag=tag, log_path=self.raw_bt_metrics_path)
        rssi_master = process_data_dict.get('rssi')
        pwl_master = process_data_dict.get('pwlv')
        rssi_c0_master = process_data_dict.get('rssi_c0')
        rssi_c1_master = process_data_dict.get('rssi_c1')
        txpw_c0_master = process_data_dict.get('txpw_c0')
        txpw_c1_master = process_data_dict.get('txpw_c1')
        bftx_master = process_data_dict.get('bftx')
        divtx_master = process_data_dict.get('divtx')
        linkquality_master = process_data_dict.get('linkquality')

        condition = False
        if condition:
            rssi_slave = btutils.get_bt_rssi(self.bt_device,
                                             tag=tag,
                                             log_path=self.raw_bt_metrics_path)
        else:
            rssi_slave = None

        master_metrics_list = [
            rssi_master, pwl_master, rssi_c0_master, rssi_c1_master,
            txpw_c0_master, txpw_c1_master, bftx_master, divtx_master, linkquality_master
        ]
        slave_metrics_list = [rssi_slave]

        # rssi, pwlv, rssi_c0, rssi_c1, txpw_c0, txpw_c1, bftx, divtx

        return master_metrics_list, slave_metrics_list


class RangingComparisonTest(base_test.BaseTestClass):

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)

    def setup_class(self):
        """Initializes common test hardware and parameters.

        This function initializes hardware and compiles parameters that are
        common to all tests in this class.
        """
        self.duts = self.android_devices
        req_params = [
            'wifi_ranging_params', 'bt_ranging_params', 'uwb_ranging_params'
        ]
        self.unpack_userparams(req_params, [])

        self.testclass_results = {}

    def teardown_test(self):
        self.process_testcase_result()

    def teardown_class(self):
        user_input = input('Please reconnect {} and press enter when done.'.format(self.duts[-1].serial))
        time.sleep(MED_SLEEP)
        self.duts[1].start_services()
        if self.uwb_ranging_params['enabled']:
            self.uwb_ranging_link.clean_up_initiator()
        if self.wifi_ranging_params['11mc_config']['enabled'] or self.wifi_ranging_params['11az_config']['enabled']:
            self.wifi_ranging_link.teardown_ranging_link()
        for dev in self.android_devices:
            wutils.wifi_toggle_state(dev, False)
            dev.go_to_sleep()

    def reset_remote_devices(self):
        user_input = input('Ensure {} is connected and press enter when done.'.format(self.duts[-1].serial))
        for dev in self.android_devices:
            dev.reboot()
        # Turn Wifi On
        for dev in self.android_devices:
            # self.log.info('Turning on airplane mode.')
            # try:
            #     asserts.assert_true(utils.force_airplane_mode(dev, True),
            #                         'Can not turn on airplane mode.')
            # except:
            #     self.log.warning('Could not enable airplane mode!')
            wutils.reset_wifi(dev)
            wutils.wifi_toggle_state(dev, True)

        if self.wifi_ranging_params['11mc_config']['enabled'] or self.wifi_ranging_params['11az_config']['enabled']:
            self.log.info('Setting up WiFi ranging link.')
            self.wifi_ranging_link = wputils.brcm_utils.RangingLink(self.duts[0], self.duts[1])
            self.wifi_ranging_link.setup_ranging_link(self.wifi_ranging_params['channel'],
                                                      self.wifi_ranging_params['bandwidth'],
                                                      self.wifi_ranging_params['associate_initiator'],
                                                      '11mc',
                                                      self.wifi_ranging_params['11az_config']['enabled'])
        if self.uwb_ranging_params['enabled']:
            self.log.info('Setting up UWB ranging link')
            self.uwb_ranging_link = UwbRangingLink(self.duts[1], self.duts[0], self.uwb_ranging_params)
            self.uwb_ranging_link.clean_up_initiator()
            self.uwb_ranging_link.setup_initiator()
        if self.bt_ranging_params['enabled']:
            self.log.info('Setting up BT ranging link')
            self.bt_ranging_link = BtRangingLinkV2(self.duts[0], self.duts[1], self.bt_ranging_params)
            #self.bt_ranging_link.setup_devices()
            #self.bt_ranging_link.start_advertising()

        # try:
        #     self.wifi_ranging_link.teardown_ranging_link()
        # except:
        #     self.log.warning('Could not tear down wifi link')

        self.duts[1].stop_services()
        time.sleep(MED_SLEEP)
        user_input = input('Disconnect {}, position for test, and press enter when done.'.format(self.duts[-1].serial))

    def test_ranging(self):

        self.test_results = collections.OrderedDict()
        self.log.info('Starting ranging test.')
        first_reset_needed = 1
        while 1:
            location = input('Enter location ID. Enter "Done" to stop the test: ')
            if location == 'Done':
                break
            true_distance = input('Enter true distance (in meters) between devices: ')
            if first_reset_needed or self.wifi_ranging_params['reset_devices']:
                self.reset_remote_devices()
                first_reset_needed = 0
            location_result = collections.OrderedDict()
            location_result['location_id'] = location
            location_result['true_distance'] = true_distance
            self.log.info('Starting ranging test at location {} with distance {}.'.format(location, true_distance))
            if self.wifi_ranging_params['11mc_config']['enabled']:
                self.log.info('Starting WiFi ranging test.')
                wifi_11mc_ranging_result = self.wifi_ranging_link.measure_range(self.wifi_ranging_params['num_measurements'],
                                                                           self.wifi_ranging_params['channel'],
                                                                           self.wifi_ranging_params['11mc_config']['bandwidth'],
                                                                           self.wifi_ranging_params['11mc_config']['num_frames'],
                                                                           ranging_method='11mc',
                                                                           ant_diversity=0)
                self.log.info(wifi_11mc_ranging_result['summary'])
                location_result['wifi_11mc_ranging_result'] = wifi_11mc_ranging_result
                # wifi_11mc_ant_diversity_ranging_result = self.wifi_ranging_link.measure_range(self.wifi_ranging_params['num_measurements'],
                #                                                            self.wifi_ranging_params['channel'],
                #                                                            self.wifi_ranging_params['11mc_config']['bandwidth'],
                #                                                            self.wifi_ranging_params['11mc_config']['num_frames'],
                #                                                            ranging_method='11mc',
                #                                                            ant_diversity=1)
                # self.log.info(wifi_11mc_ant_diversity_ranging_result['summary'])
                # location_result['wifi_11mc_ant_diversity_ranging_result'] = wifi_11mc_ant_diversity_ranging_result
            if self.wifi_ranging_params['11az_config']['enabled']:
                wifi_11az_ranging_result = self.wifi_ranging_link.measure_range(self.wifi_ranging_params['num_measurements'],
                                                                           self.wifi_ranging_params['channel'],
                                                                           self.wifi_ranging_params['11az_config']['bandwidth'],
                                                                           self.wifi_ranging_params['11az_config']['num_frames'],
                                                                           ranging_method='11az')
                self.log.info(wifi_11az_ranging_result['summary'])
                location_result['wifi_11az_ranging_result'] = wifi_11az_ranging_result
            if self.uwb_ranging_params['enabled']:
                self.log.info('Starting UWB ranging test.')
                location_result['uwb_ranging_result'] = self.uwb_ranging_link.measure_range(
                    duration=self.uwb_ranging_params['duration'])
                self.log.info(location_result['uwb_ranging_result'])
            if self.bt_ranging_params['enabled']:
                self.log.info('Starting BT ranging test.')
                location_result['bt_ranging_result'] = self.bt_ranging_link.do_channel_sounding(test_name=location)
                self.log.info(location_result['bt_ranging_result']['summary'])
            self.test_results[location] = location_result
            results_file_path = os.path.join(
                context.get_current_context().get_full_output_path(),
                '{}.json'.format(self.current_test_name))
            with open(results_file_path, 'w') as results_file:
                json.dump(wputils.serialize_dict(self.test_results),
                          results_file,
                          indent=4)
        return self.test_results



    def process_testcase_result(self):
        pass