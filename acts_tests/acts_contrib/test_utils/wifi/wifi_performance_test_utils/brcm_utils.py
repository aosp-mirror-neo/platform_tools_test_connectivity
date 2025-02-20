#!/usr/bin/env python3.4
#
#   Copyright 2021 - The Android Open Source Project
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
import hashlib
import itertools
import logging
import math
import numpy
import re
import statistics
import time
from acts_contrib.test_utils.wifi import wifi_test_utils as wutils

VERY_SHORT_SLEEP = 0.5
SHORT_SLEEP = 1
MED_SLEEP = 6
DISCONNECTION_MESSAGE_BRCM = 'driver adapter not found'
RSSI_ERROR_VAL = float('nan')
RATE_TABLE = {
    'HT': {
        1: {
            20: [7.2, 14.4, 21.7, 28.9, 43.4, 57.8, 65.0, 72.2],
            40: [15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0]
        },
        2: {
            20: [
                0, 0, 0, 0, 0, 0, 0, 0, 14.4, 28.8, 43.4, 57.8, 86.8, 115.6,
                130, 144.4
            ],
            40: [0, 0, 0, 0, 0, 0, 0, 0, 30, 60, 90, 120, 180, 240, 270, 300]
        }
    },
    'VHT': {
        1: {
            20: [
                7.2, 14.4, 21.7, 28.9, 43.4, 57.8, 65.0, 72.2, 86.7, 96.2,
                129.0, 143.4
            ],
            40: [
                15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0, 180.0,
                200.0, 258, 286.8
            ],
            80: [
                32.5, 65.0, 97.5, 130.0, 195.0, 260.0, 292.5, 325.0, 390.0,
                433.3, 540.4, 600.4
            ],
            160: [
                65.0, 130.0, 195.0, 260.0, 390.0, 520.0, 585.0, 650.0, 780.0,
                1080.8, 1200.8
            ]
        },
        2: {
            20: [
                14.4, 28.8, 43.4, 57.8, 86.8, 115.6, 130, 144.4, 173.4, 192.4,
                258, 286.8
            ],
            40: [30, 60, 90, 120, 180, 240, 270, 300, 360, 400, 516, 573.6],
            80: [
                65, 130, 195, 260, 390, 520, 585, 650, 780, 866.6, 1080.8,
                1200.8
            ],
            160:
            [130, 260, 390, 520, 780, 1040, 1170, 1300, 1560, 2161.6, 2401.6]
        },
    },
    'HE': {
        1: {
            20: [
                8.6, 17.2, 25.8, 34.4, 51.6, 68.8, 77.4, 86.0, 103.2, 114.7,
                129.0, 143.4
            ],
            40: [
                17.2, 34.4, 51.6, 68.8, 103.2, 137.6, 154.8, 172, 206.4, 229.4,
                258, 286.8
            ],
            80: [
                36.0, 72.1, 108.1, 144.1, 216.2, 288.2, 324.3, 360.3, 432.4,
                480.4, 540.4, 600.4
            ],
            160: [
                72, 144.2, 216.2, 288.2, 432.4, 576.4, 648.6, 720.6, 864.8,
                960.8, 1080.8, 1200.8
            ]
        },
        2: {
            20: [
                17.2, 34.4, 51.6, 68.8, 103.2, 137.6, 154.8, 172, 206.4, 229.4,
                258, 286.8
            ],
            40: [
                34.4, 68.8, 103.2, 137.6, 206.4, 275.2, 309.6, 344, 412.8,
                458.8, 516, 573.6
            ],
            80: [
                72, 144.2, 216.2, 288.2, 432.4, 576.4, 648.6, 720.6, 864.8,
                960.8, 1080.8, 1200.8
            ],
            160: [
                144, 288.4, 432.4, 576.4, 864.8, 1152.8, 1297.2, 1441.2,
                1729.6, 1921.6, 2161.6, 2401.6
            ]
        },
    },
    'EHT': {
        1: {
            20: [
                8.6, 17.2, 25.8, 34.4, 51.6, 68.8, 77.4, 86.0, 103.2, 114.7,
                129.0, 143.4, 154.9, 172.1, 0, 4.3
            ],
            40: [
                17.2, 34.4, 51.6, 68.8, 103.2, 137.6, 154.9, 172.1, 206.5, 229.4,
                258.1, 286.8, 309.7, 344.1, 0, 8.6
            ],
            80: [
                36.0, 72.1, 108.1, 144.1, 216.2, 288.2, 324.3, 360.3, 432.4,
                480.4, 540.4, 600.4, 648.5, 720.6, 8.6, 18.0
            ],
            160: [
                72.1, 144.1, 216.2, 288.2, 432.4, 576.5, 648.5, 720.6, 864.7,
                960.7, 1080.9, 1201, 1297.1, 1441.2, 18.0, 36.0
            ]
        },
        2: {
            20: [
                17.2, 34.4, 51.6, 68.8, 103.2, 137.6, 154.8, 172, 206.4, 229.4,
                258, 286.8, 309.8, 344.2, 0, 0
            ],
            40: [
                34.4, 68.8, 103.2, 137.6, 206.4, 275.2, 309.6, 344, 412.8,
                458.8, 516, 573.6, 619.4, 688.2, 0, 0
            ],
            80: [
                72, 144.2, 216.2, 288.2, 432.4, 576.4, 648.6, 720.6, 864.8,
                960.8, 1080.8, 1200.8, 1297, 1441.2, 0, 0
            ],
            160: [
                144, 288.4, 432.4, 576.4, 864.8, 1152.8, 1297.2, 1441.2,
                1729.6, 1921.6, 2161.6, 2401.6, 2594.2, 2882.4, 0, 0
            ]
        },
    },
}


# Rssi Utilities
def empty_rssi_result():
    return collections.OrderedDict([('data', []), ('mean', None),
                                    ('stdev', None)])


def get_connected_rssi(dut,
                       num_measurements=1,
                       polling_frequency=SHORT_SLEEP,
                       first_measurement_delay=0,
                       disconnect_warning=True,
                       ignore_samples=0,
                       interface='wlan0'):
    # yapf: disable
    connected_rssi = collections.OrderedDict(
        [('time_stamp', []),
         ('bssid', []), ('ssid', []), ('frequency', []),
         ('signal_poll_rssi', empty_rssi_result()),
         ('signal_poll_avg_rssi', empty_rssi_result()),
         ('reported_rssi', empty_rssi_result()),
         ('chain_0_rssi', empty_rssi_result()),
         ('chain_1_rssi', empty_rssi_result())])

    # yapf: enable
    previous_bssid = 'disconnected'
    t0 = time.time()
    time.sleep(first_measurement_delay)
    for idx in range(num_measurements):
        measurement_start_time = time.time()
        connected_rssi['time_stamp'].append(measurement_start_time - t0)
        # Get signal poll RSSI
        try:
            status_output = dut.adb.shell(
                'wpa_cli -i {} status'.format(interface))
        except:
            status_output = ''
        match = re.search('bssid=.*', status_output)
        if match:
            current_bssid = match.group(0).split('=')[1]
            connected_rssi['bssid'].append(current_bssid)
        else:
            current_bssid = 'disconnected'
            connected_rssi['bssid'].append(current_bssid)
            if disconnect_warning and previous_bssid != 'disconnected':
                logging.warning('WIFI DISCONNECT DETECTED!')

        previous_bssid = current_bssid
        match = re.search('\s+ssid=.*', status_output)
        if match:
            ssid = match.group(0).split('=')[1]
            connected_rssi['ssid'].append(ssid)
        else:
            connected_rssi['ssid'].append('disconnected')

        #TODO: SEARCH MAP ; PICK CENTER CHANNEL
        match = re.search('\s+freq=.*', status_output)
        if match:
            frequency = int(match.group(0).split('=')[1])
            connected_rssi['frequency'].append(frequency)
        else:
            connected_rssi['frequency'].append(RSSI_ERROR_VAL)

        if interface == 'wlan0':
            try:
                per_chain_rssi = dut.adb.shell('wl phy_rssi_ant')
                reported_rssi = int(dut.adb.shell('wl rssi'))
                chain_0_rssi = re.search(
                    r'rssi\[0\]\s(?P<chain_0_rssi>[0-9\-]*)', per_chain_rssi)
                if chain_0_rssi:
                    chain_0_rssi = int(chain_0_rssi.group('chain_0_rssi'))
                else:
                    chain_0_rssi = -float('inf')
                chain_1_rssi = re.search(
                    r'rssi\[1\]\s(?P<chain_1_rssi>[0-9\-]*)', per_chain_rssi)
                if chain_1_rssi:
                    chain_1_rssi = int(chain_1_rssi.group('chain_1_rssi'))
                else:
                    chain_1_rssi = -float('inf')
            except:
                chain_0_rssi = RSSI_ERROR_VAL
                chain_1_rssi = RSSI_ERROR_VAL
                reported_rssi = RSSI_ERROR_VAL
            connected_rssi['chain_0_rssi']['data'].append(chain_0_rssi)
            connected_rssi['chain_1_rssi']['data'].append(chain_1_rssi)
            connected_rssi['reported_rssi']['data'].append(reported_rssi)
            combined_rssi = math.pow(10, chain_0_rssi / 10) + math.pow(
                10, chain_1_rssi / 10)
            combined_rssi = 10 * math.log10(combined_rssi)
            connected_rssi['signal_poll_rssi']['data'].append(combined_rssi)
            connected_rssi['signal_poll_avg_rssi']['data'].append(
                combined_rssi)
        else:
            try:
                signal_poll_output = dut.adb.shell(
                    'wpa_cli -i {} signal_poll'.format(interface))
            except:
                signal_poll_output = ''
            match = re.search('RSSI=.*', signal_poll_output)
            if match:
                temp_rssi = int(match.group(0).split('=')[1])
                if temp_rssi == -9999 or temp_rssi == 0:
                    connected_rssi['signal_poll_rssi']['data'].append(
                        RSSI_ERROR_VAL)
                else:
                    connected_rssi['signal_poll_rssi']['data'].append(
                        temp_rssi)
            else:
                connected_rssi['signal_poll_rssi']['data'].append(
                    RSSI_ERROR_VAL)
            connected_rssi['chain_0_rssi']['data'].append(RSSI_ERROR_VAL)
            connected_rssi['chain_1_rssi']['data'].append(RSSI_ERROR_VAL)
        measurement_elapsed_time = time.time() - measurement_start_time
        time.sleep(max(0, polling_frequency - measurement_elapsed_time))

    # Statistics, Statistics
    for key, val in connected_rssi.copy().items():
        if 'data' not in val:
            continue
        filtered_rssi_values = [x for x in val['data'] if not (math.isnan(x) or math.isinf(x))]
        if len(filtered_rssi_values) > ignore_samples:
            filtered_rssi_values = filtered_rssi_values[ignore_samples:]
        if filtered_rssi_values:
            connected_rssi[key]['mean'] = statistics.mean(filtered_rssi_values)
            if len(filtered_rssi_values) > 1:
                connected_rssi[key]['stdev'] = statistics.stdev(
                    filtered_rssi_values)
            else:
                connected_rssi[key]['stdev'] = 0
        else:
            connected_rssi[key]['mean'] = RSSI_ERROR_VAL
            connected_rssi[key]['stdev'] = RSSI_ERROR_VAL

    return connected_rssi


def get_scan_rssi(dut, tracked_bssids, num_measurements=1):
    scan_rssi = collections.OrderedDict()
    for bssid in tracked_bssids:
        scan_rssi[bssid] = empty_rssi_result()
    for idx in range(num_measurements):
        scan_output = dut.adb.shell('cmd wifi start-scan')
        time.sleep(MED_SLEEP)
        scan_output = dut.adb.shell('cmd wifi list-scan-results')
        for bssid in tracked_bssids:
            bssid_result = re.search(bssid + '.*',
                                     scan_output,
                                     flags=re.IGNORECASE)
            if bssid_result:
                bssid_result = bssid_result.group(0).split()
                scan_rssi[bssid]['data'].append(int(bssid_result[2]))
            else:
                scan_rssi[bssid]['data'].append(RSSI_ERROR_VAL)
    # Compute mean RSSIs. Only average valid readings.
    # Output RSSI_ERROR_VAL if no readings found.
    for key, val in scan_rssi.items():
        filtered_rssi_values = [x for x in val['data'] if not math.isnan(x)]
        if filtered_rssi_values:
            scan_rssi[key]['mean'] = statistics.mean(filtered_rssi_values)
            if len(filtered_rssi_values) > 1:
                scan_rssi[key]['stdev'] = statistics.stdev(
                    filtered_rssi_values)
            else:
                scan_rssi[key]['stdev'] = 0
        else:
            scan_rssi[key]['mean'] = RSSI_ERROR_VAL
            scan_rssi[key]['stdev'] = RSSI_ERROR_VAL
    return scan_rssi


def get_sw_signature(dut):
    bdf_output = dut.adb.shell('cksum /vendor/firmware/bcmdhd*')
    logging.debug('BDF Checksum output: {}'.format(bdf_output))
    bdf_signature = sum(
        [int(line.split(' ')[0]) for line in bdf_output.splitlines()]) % 1000

    fw_version = dut.adb.shell('getprop vendor.wlan.firmware.version')
    driver_version = dut.adb.shell('getprop vendor.wlan.driver.version')
    logging.debug('Firmware version : {}. Driver version: {}'.format(
        fw_version, driver_version))
    fw_signature = '{}+{}'.format(fw_version, driver_version)
    fw_signature = int(hashlib.md5(fw_signature.encode()).hexdigest(),
                       16) % 1000
    serial_hash = int(hashlib.md5(dut.serial.encode()).hexdigest(), 16) % 1000
    return {
        'config_signature': bdf_signature,
        'fw_signature': fw_signature,
        'serial_hash': serial_hash
    }


def get_country_code(dut):
    try:
        country_code = dut.adb.shell('wl country').split(' ')[0]
    except:
        country_code = 'XZ'
    if country_code == 'XZ':
        country_code = 'WW'
    logging.debug('Country code: {}'.format(country_code))
    return country_code


def push_config(dut, config_file):
    config_files_list = dut.adb.shell('ls /vendor/etc/*.cal').splitlines()
    for dst_file in config_files_list:
        dut.push_system_file(config_file, dst_file)
    dut.reboot()


def start_wifi_logging(dut):
    pass


def stop_wifi_logging(dut):
    pass


def push_firmware(dut, firmware_files):
    """Function to push Wifi firmware files

    Args:
        dut: dut to push bdf file to
        firmware_files: path to wlanmdsp.mbn file
        datamsc_file: path to Data.msc file
    """
    for file in firmware_files:
        dut.push_system_file(file, '/vendor/firmware/')
    dut.reboot()


def disable_beamforming(dut):
    dut.adb.shell('wl down')
    time.sleep(VERY_SHORT_SLEEP)
    try:
        dut.adb.shell('wl txbf 0')
        dut.adb.shell('wl txbf_bfe_cap 0')
    except:
        logging.warning('Could not disable beamforming.')
    dut.adb.shell('wl up')


def set_nss_capability(dut, nss):
    dut.adb.shell('wl he omi -r {} -t {}'.format(nss, nss))


def set_chain_mask(dut, chain):
    if chain == '2x2':
        chain = 3
    else:
        chain = chain + 1
    # Get current chain mask
    try:
        curr_tx_chain = int(dut.adb.shell('wl txchain'))
        curr_rx_chain = int(dut.adb.shell('wl rxchain'))
    except:
        curr_tx_chain = -1
        curr_rx_chain = -1
    if curr_tx_chain == chain and curr_rx_chain == chain:
        return
    # Set chain mask if needed
    dut.adb.shell('wl down')
    time.sleep(SHORT_SLEEP)
    dut.adb.shell('wl txchain 0x{}'.format(chain))
    dut.adb.shell('wl rxchain 0x{}'.format(chain))
    dut.adb.shell('wl up')

    try:
        curr_tx_chain = int(dut.adb.shell('wl txchain'))
        curr_rx_chain = int(dut.adb.shell('wl rxchain'))
    except:
        curr_tx_chain = -1
        curr_rx_chain = -1
    if curr_tx_chain != chain or curr_rx_chain != chain:
        logging.error('Set chain mask failed.')


class LinkLayerStats():

    LLSTATS_CMD = 'wl dump ampdu; wl counters;'
    LL_STATS_CLEAR_CMD = 'wl dump_clear ampdu; wl reset_cnts;'
    BRCM_PHY_LOG_CLEAR_CMD = 'wl dump phycal; wl dump_clear txbf;'
    BRCM_PHY_LOG_CMD = 'wl phy_rssi_ant; wl phy_snr_ant; wl nrate; wl dump phycal; wl tvpm; wl dump txbf;'
    BW_REGEX = re.compile(r'Chanspec:.+ (?P<bandwidth>[0-9]+)MHz')
    MCS_REGEX = re.compile(r'(?P<count>[0-9]+)\((?P<percent>[0-9]+)%\)')
    RX_REGEX = re.compile(
        r'RX (?P<mode>MCS|VHT|HE|EHT)\s+:\s*(?P<nss1>[0-9, ,(,),%]*)'
        '\n\s*:?\s*(?P<nss2>[0-9, ,(,),%]*)')
    TX_REGEX = re.compile(
        r'TX (?P<mode>MCS|VHT|HE|EHT)\s+:\s*(?P<nss1>[0-9, ,(,),%]*)'
        '\n\s*:?\s*(?P<nss2>[0-9, ,(,),%]*)')
    TX_PER_REGEX = re.compile(
        r'(?P<mode>\S+) PER\s+:\s*(?P<nss1>[0-9, ,(,),%]*)'
        '\n\s*:?\s*(?P<nss2>[0-9, ,(,),%]*)')
    TX_BW = re.compile(
        r'TX BW[\s+]?:\s*(?P<tx_bw>[0-9, ,(,),%]*)')
    RX_BW = re.compile(
        r'RX BW\s+:\s*(?P<rx_bw>[0-9, ,(,),%]*)')
    TXRX_BW_REGEX = re.compile(r'(?P<count>[0-9]+)\((?P<percent>[0-9]+)%\)')
    RX_GOOD_FCS_REGEX = re.compile(r'goodfcs (?P<rx_good_fcs>[0-9]*)')
    RX_BAD_FCS_REGEX = re.compile(r'rxbadfcs (?P<rx_bad_fcs>[0-9]*)')
    RX_AGG_REGEX = re.compile(r'rxmpduperampdu (?P<aggregation>[0-9]*)')
    TX_AGG_REGEX = re.compile(r' mpduperampdu (?P<aggregation>[0-9]*)')
    TX_AGG_STOP_REGEX = re.compile(
        r'agg stop reason: tot_agg_tried (?P<agg_tried>[0-9]+) agg_txcancel (?P<agg_canceled>[0-9]+) (?P<agg_stop_reason>.+)'
    )
    TX_AGG_STOP_REASON_REGEX = re.compile(
        r'(?P<reason>\w+) [0-9]+ \((?P<value>[0-9]+%)\)')
    MCS_ID = collections.namedtuple(
        'mcs_id', ['mode', 'num_streams', 'bandwidth', 'mcs', 'gi'])
    MODE_MAP = {'0': '11a/g', '1': '11b', '2': '11n', '3': '11ac'}
    BW_MAP = {'0': 20, '1': 40, '2': 80, '3': 160}


    def __init__(self, dut, llstats_enabled=True):
        self.dut = dut
        self.llstats_enabled = llstats_enabled
        self.llstats_cumulative = self._empty_llstats()
        self.llstats_incremental = self._empty_llstats()
        self.bandwidth = None

    def update_stats(self):
        if self.llstats_enabled:
            try:
                llstats_output = self.dut.adb.shell(self.LLSTATS_CMD,
                                                    timeout=1)

                self.dut.adb.shell_nb(self.LL_STATS_CLEAR_CMD)

                wl_join = self.dut.adb.shell("wl status")
                if not self.bandwidth:
                    self.bandwidth = int(
                        re.search(self.BW_REGEX, wl_join).group('bandwidth'))
            except:
                logging.debug('Failed to get counters and ampdu dumps.')
                llstats_output = ''
            try:
                phy_log_output = self.dut.adb.shell(self.BRCM_PHY_LOG_CMD,
                                                    ignore_status=True,
                                                    timeout=1)
                self.dut.adb.shell_nb(self.BRCM_PHY_LOG_CLEAR_CMD)
            except:
                logging.debug('Failed to get phy log.')
                phy_log_output = ''
        else:
            llstats_output = ''
            phy_log_output = ''
        self._update_stats(llstats_output, phy_log_output)

    def reset_stats(self):
        self.llstats_cumulative = self._empty_llstats()
        self.llstats_incremental = self._empty_llstats()

    def _empty_llstats(self):
        return collections.OrderedDict(mcs_stats=collections.OrderedDict(),
                                       mpdu_stats=collections.OrderedDict(),
                                       summary=collections.OrderedDict())

    def _empty_mcs_stat(self):
        return collections.OrderedDict(txmpdu=0,
                                       rxmpdu=0,
                                       mpdu_lost=0,
                                       retries=0,
                                       retries_short=0,
                                       retries_long=0)

    def _mcs_id_to_string(self, mcs_id):
        mcs_string = '{} Nss{} MCS{} GI{}'.format(mcs_id.mode,
                                                  mcs_id.num_streams,
                                                  mcs_id.mcs, mcs_id.gi)
        return mcs_string

    def _parse_mcs_stats(self, llstats_output):
        llstats_dict = {}
        # Look for per-peer stats
        match = re.search(self.RX_REGEX, llstats_output)
        if not match:
            self.reset_stats()
            return collections.OrderedDict()
        # Find and process all matches for per stream stats
        rx_match_iter = re.finditer(self.RX_REGEX, llstats_output)
        tx_match_iter = re.finditer(self.TX_REGEX, llstats_output)
        tx_per_match_iter = re.finditer(self.TX_PER_REGEX, llstats_output)
        for rx_match, tx_match, tx_per_match in zip(rx_match_iter,
                                                    tx_match_iter,
                                                    tx_per_match_iter):
            mode = rx_match.group('mode')
            mode = 'HT' if mode == 'MCS' else mode
            for nss in [1, 2]:
                rx_mcs_iter = re.finditer(self.MCS_REGEX,
                                          rx_match.group(nss + 1))
                tx_mcs_iter = re.finditer(self.MCS_REGEX,
                                          tx_match.group(nss + 1))
                tx_per_iter = re.finditer(self.MCS_REGEX,
                                          tx_per_match.group(nss + 1))
                for mcs, (rx_mcs_stats, tx_mcs_stats,
                          tx_per_mcs_stats) in enumerate(
                              itertools.zip_longest(rx_mcs_iter, tx_mcs_iter,
                                                    tx_per_iter)):
                    current_mcs = self.MCS_ID(
                        mode, nss, self.bandwidth,
                        mcs + int(8 * (mode == 'HT') * (nss - 1)), 0)
                    current_stats = collections.OrderedDict(
                        txmpdu=int(tx_mcs_stats.group('count'))
                        if tx_mcs_stats else 0,
                        rxmpdu=int(rx_mcs_stats.group('count'))
                        if rx_mcs_stats else 0,
                        mpdu_lost=0,
                        retries=tx_per_mcs_stats.group('count')
                        if tx_per_mcs_stats else 0,
                        retries_short=0,
                        retries_long=0,
                        mcs_id=current_mcs)
                    llstats_dict[self._mcs_id_to_string(
                        current_mcs)] = current_stats
        return llstats_dict

    def _parse_mpdu_stats(self, llstats_output):
        rx_agg_match = re.search(self.RX_AGG_REGEX, llstats_output)
        tx_agg_match = re.search(self.TX_AGG_REGEX, llstats_output)
        tx_agg_stop_match = re.search(self.TX_AGG_STOP_REGEX, llstats_output)
        rx_good_fcs_match = re.search(self.RX_GOOD_FCS_REGEX, llstats_output)
        rx_bad_fcs_match = re.search(self.RX_BAD_FCS_REGEX, llstats_output)

        mpdu_stats = collections.OrderedDict(
            rx_aggregation=int(rx_agg_match.group('aggregation'))
            if rx_agg_match else 0,
            tx_aggregation=int(tx_agg_match.group('aggregation'))
            if tx_agg_match else 0,
            tx_agg_tried=int(tx_agg_stop_match.group('agg_tried'))
            if tx_agg_stop_match else 0,
            tx_agg_canceled=int(tx_agg_stop_match.group('agg_canceled'))
            if tx_agg_stop_match else 0,
            rx_good_fcs=int(rx_good_fcs_match.group('rx_good_fcs'))
            if rx_good_fcs_match else 0,
            rx_bad_fcs=int(rx_bad_fcs_match.group('rx_bad_fcs'))
            if rx_bad_fcs_match else 0,
            agg_stop_reason=collections.OrderedDict())
        if tx_agg_stop_match:
            agg_reason_match = re.finditer(
                self.TX_AGG_STOP_REASON_REGEX,
                tx_agg_stop_match.group('agg_stop_reason'))
            for reason_match in agg_reason_match:
                mpdu_stats['agg_stop_reason'][reason_match.group(
                    'reason')] = reason_match.group('value')

        return mpdu_stats

    def _parse_bw_stats(self, llstats_output):
        tx_bw_match_iter = re.finditer(self.TX_BW, llstats_output)
        rx_bw_match_iter = re.finditer(self.RX_BW, llstats_output)
        bw_stats = {}
        for rx_bw_match, tx_bw_match, in zip(rx_bw_match_iter, tx_bw_match_iter):
            rx_bw_cnt_iter = re.finditer(self.TXRX_BW_REGEX, rx_bw_match.group('rx_bw'))
            tx_bw_cnt_iter = re.finditer(self.TXRX_BW_REGEX, tx_bw_match.group('tx_bw'))
            tx_phy_bw_weight_sum = 0
            rx_phy_bw_weight_sum = 0
            tx_bw_adjust_cnt = 0
            rx_bw_adjust_cnt = 0
            rx_common_bw = self.bandwidth
            tx_common_bw = self.bandwidth
            rx_common_bw_pct = 0
            tx_common_bw_pct = 0
            for bw_id, (rx_bw_stats, tx_bw_stats) in enumerate(
                              itertools.zip_longest(rx_bw_cnt_iter, tx_bw_cnt_iter)):
                current_bw = self.BW_MAP[str(bw_id)]
                current_bw_stats = collections.OrderedDict(
                    txbwcnt = int(tx_bw_stats.group('count'))
                    if tx_bw_stats else 0,
                    txbwpct = int(tx_bw_stats.group('percent'))
                    if tx_bw_stats else 0,
                    rxbwcnt = int(rx_bw_stats.group('count'))
                    if rx_bw_stats else 0,
                    rxbwpct = int(rx_bw_stats.group('percent'))
                    if rx_bw_stats else 0,
                    bw=current_bw)
                if current_bw_stats['rxbwpct'] > rx_common_bw_pct:
                    rx_common_bw_pct = current_bw_stats['rxbwpct']
                    rx_common_bw = current_bw
                if current_bw_stats['txbwpct'] > tx_common_bw_pct:
                    tx_common_bw_pct = current_bw_stats['txbwpct']
                    tx_common_bw = current_bw
                bw_stats[current_bw] = current_bw_stats
                if int(current_bw) != int(self.bandwidth) and current_bw_stats['txbwpct'] > 0:
                    tx_bw_adjust_cnt = tx_bw_adjust_cnt + 1
                if int(current_bw) != int(self.bandwidth) and current_bw_stats['rxbwpct'] > 0:
                    rx_bw_adjust_cnt = rx_bw_adjust_cnt + 1
                if float(current_bw) <= float(self.bandwidth):
                    tx_phy_bw_weight_sum = tx_phy_bw_weight_sum + (float(current_bw)/float(self.bandwidth)) * (float(current_bw_stats['txbwpct'])/float(100))
                    rx_phy_bw_weight_sum = rx_phy_bw_weight_sum + (float(current_bw)/float(self.bandwidth)) * (float(current_bw_stats['rxbwpct'])/float(100))
            if tx_phy_bw_weight_sum != 0:
                bw_stats['tx_phy_bw_weight'] = float(tx_phy_bw_weight_sum)
            else:
                bw_stats['tx_phy_bw_weight'] = 1
            if rx_phy_bw_weight_sum != 0:
                bw_stats['rx_phy_bw_weight'] = float(rx_phy_bw_weight_sum)
            else:
                bw_stats['rx_phy_bw_weight'] = 1
            if tx_bw_adjust_cnt > 0:
                bw_stats['tx_bw_adjusted_flag'] = True
                bw_stats['tx_common_bw'] = tx_common_bw
                bw_stats['tx_common_bw_pct'] = tx_common_bw_pct
            else:
                bw_stats['tx_bw_adjusted_flag'] = False
                bw_stats['tx_common_bw'] = self.bandwidth
                bw_stats['tx_common_bw_pct'] = 100
            if rx_bw_adjust_cnt > 0:
                bw_stats['rx_bw_adjusted_flag'] = True
                bw_stats['rx_common_bw'] = rx_common_bw
                bw_stats['rx_common_bw_pct'] = rx_common_bw_pct
            else:
                bw_stats['rx_bw_adjusted_flag'] = False
                bw_stats['rx_common_bw'] = self.bandwidth
                bw_stats['rx_common_bw_pct'] = 100
        return bw_stats


    def _generate_stats_summary(self, llstats_dict):
        llstats_summary = collections.OrderedDict(common_tx_mcs=None,
                                                  common_tx_mcs_count=0,
                                                  common_tx_mcs_freq=0,
                                                  common_rx_mcs=None,
                                                  common_rx_mcs_count=0,
                                                  common_rx_mcs_freq=0,
                                                  common_rx_bw = None,
                                                  common_rx_bw_pct = 0,
                                                  common_tx_bw = None,
                                                  common_tx_bw_pct = 0,
                                                  rx_per=float('nan'))
        mcs_ids = []
        tx_mpdu = []
        rx_mpdu = []
        phy_rates = []
        for mcs_str, mcs_stats in llstats_dict['mcs_stats'].items():
            mcs_id = mcs_stats['mcs_id']
            mcs_ids.append(mcs_str)
            tx_mpdu.append(mcs_stats['txmpdu'])
            rx_mpdu.append(mcs_stats['rxmpdu'])
            phy_rates.append(RATE_TABLE[mcs_id.mode][mcs_id.num_streams][
                mcs_id.bandwidth][mcs_id.mcs])
        if len(tx_mpdu) == 0 or len(rx_mpdu) == 0:
            return llstats_summary
        llstats_summary['common_tx_mcs'] = mcs_ids[numpy.argmax(tx_mpdu)]
        llstats_summary['common_tx_mcs_count'] = numpy.max(tx_mpdu)
        llstats_summary['common_rx_mcs'] = mcs_ids[numpy.argmax(rx_mpdu)]
        llstats_summary['common_rx_mcs_count'] = numpy.max(rx_mpdu)
        llstats_summary['common_rx_bw'] = llstats_dict['bw_stats']['rx_common_bw']
        llstats_summary['common_rx_bw_pct'] = llstats_dict['bw_stats']['rx_common_bw_pct']
        llstats_summary['common_tx_bw'] = llstats_dict['bw_stats']['tx_common_bw']
        llstats_summary['common_tx_bw_pct'] = llstats_dict['bw_stats']['tx_common_bw_pct']
        if sum(tx_mpdu):
            llstats_summary['mean_tx_phy_rate'] = numpy.multiply(numpy.average(
                phy_rates, weights=tx_mpdu), llstats_dict['bw_stats']['tx_phy_bw_weight'])
            llstats_summary['common_tx_mcs_freq'] = (
                llstats_summary['common_tx_mcs_count'] / sum(tx_mpdu))
        else:
            llstats_summary['mean_tx_phy_rate'] = 0
            llstats_summary['common_tx_mcs_freq'] = 0
        if sum(rx_mpdu):
            llstats_summary['mean_rx_phy_rate'] = numpy.multiply(numpy.average(
                phy_rates, weights=rx_mpdu), llstats_dict['bw_stats']['rx_phy_bw_weight'])
            llstats_summary['common_rx_mcs_freq'] = (
                llstats_summary['common_rx_mcs_count'] / sum(rx_mpdu))
            total_rx_frames = llstats_dict['mpdu_stats'][
                'rx_good_fcs'] + llstats_dict['mpdu_stats']['rx_bad_fcs']
            if total_rx_frames:
                llstats_summary['rx_per'] = (
                    llstats_dict['mpdu_stats']['rx_bad_fcs'] /
                    total_rx_frames) * 100
        else:
            llstats_summary['mean_rx_phy_rate'] = 0
            llstats_summary['common_rx_mcs_freq'] = 0
            llstats_summary['rx_per'] = 0
        return llstats_summary

    def _update_stats(self, llstats_output, phy_log_output):
        self.llstats_cumulative = self._empty_llstats()
        self.llstats_incremental = self._empty_llstats()
        self.llstats_incremental['raw_output'] = llstats_output
        self.llstats_incremental['phy_log_output'] = phy_log_output
        self.llstats_incremental['mcs_stats'] = self._parse_mcs_stats(
            llstats_output)
        self.llstats_incremental['bw_stats'] = self._parse_bw_stats(
            llstats_output)
        self.llstats_incremental['mpdu_stats'] = self._parse_mpdu_stats(
            llstats_output)
        self.llstats_incremental['summary'] = self._generate_stats_summary(
            self.llstats_incremental)
        self.llstats_cumulative['summary'] = self._generate_stats_summary(
            self.llstats_cumulative)


class RangingLink():
    def __init__(self, initiator, responder):
        self.initiator_dut = initiator
        self.responder_dut = responder
        self.soft_ap_mac_address = '00:12:32:45:76:85'
        self.SUPPORTED_BANDWIDTHS = [20, 40, 80, 160]

    def reset_device(self, dut, associate):
        if associate:
            # dut.adb.shell('echo 1 > /sys/wifi/wl_accel_force_reg_on')
            # time.sleep(SHORT_SLEEP)
            # dut.adb.shell('ifconfig wlan0 down')
            # time.sleep(MED_SLEEP)
            # dut.adb.shell('echo 1 > /sys/wifi/wl_accel_force_reg_on')
            # time.sleep(SHORT_SLEEP)
            # dut.adb.shell('ifconfig wlan0 up')
            # time.sleep(MED_SLEEP)
            dut.adb.shell('wl down')
            time.sleep(MED_SLEEP)
            dut.adb.shell('wl up')

        else:
            dut.adb.shell('wl down')
            time.sleep(MED_SLEEP)
            dut.adb.shell('wl up')

    def get_ap_intf(self, soft_ap_output):
        """Reads the AP interface from a file"""
        SOFT_AP_REGEX = r"ifname:\s*(.*?)\s"
        match = re.search(SOFT_AP_REGEX, soft_ap_output)
        if match:
            return match.group(1)
        else:
            raise RuntimeError('Could not find soft ap interface')

    def setup_soft_ap(self, channel, bandwidth, ranging_method, az_enabled):

        """Sets up a Soft-AP on responder DUT"""
        # To allow DFS channels
        self.responder_dut.adb.shell('wl down')
        self.responder_dut.adb.shell('wl spect 0')
        self.responder_dut.adb.shell('wl up')

        # Create AP interface
        # added for 11az
        soft_ap_out = self.responder_dut.adb.shell('wl interface_create ap -m {}'.format(self.soft_ap_mac_address))
        self.soft_ap_interface = self.get_ap_intf(soft_ap_out)
        time.sleep(SHORT_SLEEP)
        # if ranging_method == '11mc':
        #     self.responder_dut.adb.shell('wl -i {} chanspec {}/{}'.format(self.soft_ap_interface, channel, bandwidth))
        #elif ranging_method == '11az':
        self.responder_dut.adb.shell('wl -i {} bss down'.format(self.soft_ap_interface))
        time.sleep(SHORT_SLEEP)
        if channel < 13:
            self.responder_dut.adb.shell('wl -i {} chanspec {}'.format(self.soft_ap_interface, channel))
        else:
            self.responder_dut.adb.shell('wl -i {} chanspec {}/{}'.format(self.soft_ap_interface, channel, bandwidth))
        time.sleep(SHORT_SLEEP)
        self.responder_dut.adb.shell('wl -i {} oce fd_tx_duration 0'.format(self.soft_ap_interface))
        time.sleep(SHORT_SLEEP)
        self.responder_dut.adb.shell('wl -i {} up'.format(self.soft_ap_interface))
        time.sleep(SHORT_SLEEP)
        self.responder_dut.adb.shell("wl -i {} ssid testftm".format(self.soft_ap_interface))
        time.sleep(SHORT_SLEEP)
        self.responder_dut.adb.shell('wl -i {} status'.format(self.soft_ap_interface))
        if 'one_sided' not in ranging_method:
            self.enable_ranging_at_responder(bandwidth, az_enabled)
        self.test_network = {"SSID": "testftm"}

    def check_soft_ap_status(self):
        return self.responder_dut.adb.shell('wl -i {} status'.format(self.soft_ap_interface))

    def enable_ranging_at_responder(self, bandwidth_11az, az_enabled=1):
        BW_MAPPING = {160: 5, 80: 2, 40: 1, 20: 0}
        self.responder_dut.adb.shell('wl -i {} scansuppress 1'.format(self.soft_ap_interface))
        self.responder_dut.adb.shell('wl scansuppress 1')
        self.responder_dut.adb.shell('wl -i {} ftm enable'.format(self.soft_ap_interface))
        if az_enabled:
            self.responder_dut.adb.shell('wl -i {} ftm ntb config min-delta 100ms'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-delta 500ms'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config format-bw {}'.format(self.soft_ap_interface,
                                                                                       BW_MAPPING[bandwidth_11az]))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config num-meas 100'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-i2r-sts-leq-80 2'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-r2i-sts-leq-80 2'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-i2r-sts-gt-80 2'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-r2i-sts-gt-80 2'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-i2r-rep 0'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config max-r2i-rep 0'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config options -sec-ltf-supported'.format(self.soft_ap_interface))
            self.responder_dut.adb.shell('wl -i {} ftm ntb config options -sec-ltf-required'.format(self.soft_ap_interface))


    def enable_ranging_at_initiator(self):
        self.initiator_dut.adb.shell('wl -i wlan0 ftm enable')

    def setup_ranging_link(self, channel, bandwidth, associate_initiator=0, ranging_method='11mc', az_enabled=1, country_code='US'):
        self.reset_device(self.initiator_dut, associate_initiator)
        self.reset_device(self.responder_dut, associate_initiator)
        wutils.set_wifi_country_code(self.initiator_dut, country_code)
        wutils.set_wifi_country_code(self.responder_dut, country_code)

        self.setup_soft_ap(channel, bandwidth, ranging_method, az_enabled)
        if associate_initiator:
            #self.initiator_dut.adb.shell('wl -i wlan0 join testftm')
            self.initiator_dut.adb.shell('cmd wifi connect-network testftm open')
            associated = 0
            for idx in range(10):
                status = self.initiator_dut.adb.shell('wl -i wlan0 status')
                if 'testftm' in status:
                    associated = 1
                    break
                else:
                    time.sleep(SHORT_SLEEP)
            if not associated:
                raise RuntimeError('Could not connect to soft AP.')
        self.enable_ranging_at_initiator()

    def run_single_11mc_range(self, channel, bandwidth, no_meas_frames=8, one_sided = 0, ant_diversity = 0):
        """Triggers the 11mc ranging measurements"""
        # TODO: Debug why an extra 'wl -i wlan0 proxd ftm 1 delete' is often needed here on P22
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config burst-duration 128')
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config burst-timeout 128')
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config ftm-sep 3400us')
        if one_sided:
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config options +randmac +auto-vhtack')
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config options +initiator +no_scan_cache +one-way')
        else:
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config options +initiator +randmac +auto-vhtack')
        if ant_diversity:
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config options +ant_diversity')
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config ant_div_mode 1')
        if channel < 13:
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config chanspec {}'.format(channel))
        else:
            self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config chanspec {}/{}'.format(channel, bandwidth))
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config peer {}'.format(self.soft_ap_mac_address))
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 config num-ftm {}'.format(no_meas_frames))
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 start')
        time.sleep(VERY_SHORT_SLEEP)
        result = self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 result')
        result = self.parse_11mc_ranging_result(result)
        self.initiator_dut.adb.shell('wl -i wlan0 proxd ftm 1 delete')
        return result

    def run_single_11az_range(self, channel, bandwidth, no_meas_frames=8):
        BW_MAPPING = {160: 5, 80: 2, 40: 1, 20: 0}
        # result = self.initiator_dut.adb.shell('halutil -rtt -sta {} {} {} 0 3'.format(
        #     self.soft_ap_mac_address, channel, BW_MAPPING[bandwidth]))
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb 1 config chanspec {}/{}'.format(channel, bandwidth))
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb 1 config peer {}'.format(self.soft_ap_mac_address))
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb 1 config options +initiator')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config min-delta 100ms')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-delta 1s')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config format-bw {}'.format(BW_MAPPING[bandwidth]))
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config num-meas {}'.format(no_meas_frames))
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-i2r-sts-leq-80 2')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-r2i-sts-leq-80 2')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-i2r-sts-gt-80 2')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-r2i-sts-gt-80 2')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-i2r-rep 0')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config max-r2i-rep 0')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config options -sec-ltf-supported')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm ntb config options -sec-ltf-required')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm 1 start')
        time.sleep(no_meas_frames*VERY_SHORT_SLEEP)
        result = self.initiator_dut.adb.shell('wl -i wlan0 ftm 1 result')
        result = self.parse_11az_ranging_result(result)
        self.initiator_dut.adb.shell('wl -i wlan0 ftm 1 result')
        self.initiator_dut.adb.shell('wl -i wlan0 ftm 1 delete')
        return result


    def measure_range(self, num_iterations, channel, bandwidth, no_meas_frames=8, ranging_method='11mc', ant_diversity=0, verbose = 1):
        ranging_results = {'raw_results': [], 'compiled_results': {}, 'summary': {}}
        try:
            logging.info(self.check_soft_ap_status())
        except:
            logging.warning('Soft AP may have crashed.')
        try:
            association_status = self.initiator_dut.adb.shell('wl status')
            logging.info(association_status)
            if 'testftm' not in association_status:
                logging.warning('Initiator DUT may have disconnected from AP')
        except:
            logging.warning('Initiator DUT may have disconnected from AP')
        for idx in range(num_iterations):
            try:
                logging.debug(self.check_soft_ap_status())
            except:
                logging.debug('Soft AP may have crashed.')
            if '11mc' in ranging_method:
                one_sided = ('one_sided' in ranging_method)
                result = self.run_single_11mc_range(channel, bandwidth, no_meas_frames, one_sided=one_sided, ant_diversity=ant_diversity)
            elif ranging_method == '11az':
                result = self.run_single_11az_range(channel, bandwidth, no_meas_frames)
            ranging_results['raw_results'].append(result)
            if verbose:
                logging.info(result)
        ranging_results['compiled_results']['distance'] = [x['avg_dist'] for x in ranging_results['raw_results']]
        ranging_results['compiled_results']['std_dev'] = [x['std_deviation'] for x in ranging_results['raw_results']]
        ranging_results['compiled_results']['rtt'] = [x['rtt'] for x in ranging_results['raw_results']]
        ranging_results['compiled_results']['rssi'] = [x['rssi'] for x in ranging_results['raw_results']]

        ranging_results['summary']['avg_distance'] = numpy.mean(ranging_results['compiled_results']['distance'])
        ranging_results['summary']['std_dev_distance'] = numpy.std(ranging_results['compiled_results']['distance'])
        ranging_results['summary']['avg_rtt'] = numpy.mean(ranging_results['compiled_results']['rtt'])
        ranging_results['summary']['std_dev_rtt'] = numpy.std(ranging_results['compiled_results']['rtt'])
        ranging_results['summary']['avg_rssi'] = numpy.mean(ranging_results['compiled_results']['rssi'])
        ranging_results['summary']['std_dev_rssi'] = numpy.std(ranging_results['compiled_results']['rssi'])
        return ranging_results

    def parse_11mc_ranging_result(self, ranging_output):
        pattern = r"(\w+)[ :=]+([-:.x\d]+)"
        matches = re.findall(pattern, ranging_output, re.MULTILINE)
        matches = dict(matches)
        numerical_fields = ['sessionId', 'state', 'status','avg_dist', 'burst_duration', 'burst_num', 'valid_measure_cnt',
                            'num_ftm', 'num_measurements', 'snr', 'bitflips','rtt', 'rssi', 'std_deviation']
        for key in numerical_fields:
            matches[key]=float(matches[key])
        return matches

    def parse_11az_ranging_result(self, ranging_output):
        pattern = r"(\w+)[ :=]+([-:.x\d]+)"
        matches = re.findall(pattern, ranging_output, re.MULTILINE)
        matches = dict(matches)
        # numerical_fields = ['burst_num', 'measurement_number', 'success_number', 'number_per_burst_peer',
        #                     'status', 'retry_after_duration', 'type', 'rssi', 'rx_rate', 'rtt', 'rtt_sd', 'distance',
        #                     'burst_duration', 'negotiated_burst_num', 'frequency', 'packet_bw',
        #                     'i2r_tx_ltf_repetition_cnt', 'r2i_tx_ltf_repetition_cnt']
        numerical_fields = ['id', 'status', 'state', 'rtt_mean', 'rtt_sd', 'distance', 'rssi_mean']
        result = {}
        for key in numerical_fields:
            result[key] = float(matches[key])
        result['avg_dist'] = result['distance']
        result['std_deviation'] = result['rtt_sd']
        result['rtt'] = result['rtt_mean']
        result['rssi'] = result['rssi_mean']
        return result

    def cleanup_soft_ap(self):
        """Cleans up the soft-AP interface"""
        self.responder_dut.adb.shell('wl -i {} interface_remove'.format(self.soft_ap_interface))
        self.responder_dut.adb.shell('wl scansuppress 0')

    def teardown_ranging_link(self):
        self.initiator_dut.adb.shell('wl -i wlan0 disassoc')
        self.cleanup_soft_ap()