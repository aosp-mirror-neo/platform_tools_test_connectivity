#!/usr/bin/env python3.4
#
#   Copyright 2022 - The Android Open Source Project
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
import csv
import numpy
import json
import re
import os
import time
from acts import context
from acts import base_test
from acts.metrics.loggers.blackbox import BlackboxMappedMetricLogger
from acts_contrib.test_utils.cellular.performance import cellular_performance_test_utils as cputils
from acts_contrib.test_utils.cellular.performance.CellularThroughputBaseTest import CellularThroughputBaseTest
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils
from acts_contrib.test_utils.wifi.wifi_performance_test_utils.bokeh_figure import BokehFigure
from functools import partial

VERY_SHORT_SLEEP = 0.1
SHORT_SLEEP = 1
MEDIUM_SLEEP = 5
LONG_SLEEP = 10
STOP_COUNTER_LIMIT = 3


class CellularPageDecodeTest(CellularThroughputBaseTest):
    """Class to test ENDC sensitivity"""

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True
        self.testclass_params = self.user_params['page_decode_test_params']
        self.tests = self.generate_test_cases()

    def _test_page_decode(self, testcase_params):
        """Test function to run cellular throughput and BLER measurements.

        The function runs BLER/throughput measurement after configuring the
        callbox and DUT. The test supports running PHY or TCP/UDP layer traffic
        in a variety of band/carrier/mcs/etc configurations.

        Args:
            testcase_params: dict containing test-specific parameters
        Returns:
            result: dict containing throughput results and meta data
        """
        # Prepare results dicts
        testcase_params = self.compile_test_params(testcase_params)
        testcase_results = collections.OrderedDict()
        testcase_results['testcase_params'] = testcase_params
        testcase_results['results'] = []

        # Setup ota chamber if needed
        if hasattr(self,
                   'keysight_chamber') and 'orientation' in testcase_params:
            self.keysight_chamber.move_theta_phi_abs(
                self.keysight_chamber.preset_orientations[
                    testcase_params['orientation']]['theta'],
                self.keysight_chamber.preset_orientations[
                    testcase_params['orientation']]['phi'])

        # Setup tester and wait for DUT to connect
        self.setup_tester(testcase_params)
        test_cell = testcase_params['endc_combo_config']['cell_list'][0]

        # Release RRC connection
        self.keysight_test_app.release_rrc_connection(test_cell['cell_type'],
                                                      test_cell['cell_number'])
        # Set tester to ignore RACH
        self.keysight_test_app.enable_rach(test_cell['cell_type'],
                                           test_cell['cell_number'],
                                           enabled=0)
        self.keysight_test_app.enable_preamble_report(test_cell['cell_type'],
                                                      1)
        stop_counter = 0
        for power_idx in range(len(testcase_params['cell_power_sweep'][0])):
            result = collections.OrderedDict()
            # Set DL cell power
            for cell_idx, cell in enumerate(
                    testcase_params['endc_combo_config']['cell_list']):
                cell_power_array = []
                current_cell_power = testcase_params['cell_power_sweep'][
                    cell_idx][power_idx]
                cell_power_array.append(current_cell_power)
                self.keysight_test_app.set_cell_dl_power(
                    cell['cell_type'], cell['cell_number'], current_cell_power,
                    1)
            result['cell_power'] = cell_power_array
            # Start BLER and throughput measurements
            decode_counter = 0
            for idx in range(self.testclass_params['num_measurements']):
                # Page device
                self.keysight_test_app.send_rrc_paging(
                    test_cell['cell_type'], test_cell['cell_number'])
                time.sleep(MEDIUM_SLEEP)
                # Fetch page result
                preamble_report = self.keysight_test_app.fetch_preamble_report(
                    test_cell['cell_type'], test_cell['cell_number'])
                self.log.info(preamble_report)
                # If rach attempted, increment decode counter.
                if preamble_report:
                    decode_counter = decode_counter + 1
            lte_rx_meas = self.dut_utils.get_rx_measurements('LTE')
            nr_rx_meas = self.dut_utils.get_rx_measurements('NR5G')
            result[
                'decode_probability'] = decode_counter / self.testclass_params[
                    'num_measurements']

            if self.testclass_params.get('log_rsrp_metrics', 1):
                result['lte_rx_measurements'] = lte_rx_meas
                result['nr_rx_measurements'] = nr_rx_meas
                self.log.info('LTE Rx Measurements: {}'.format(lte_rx_meas))
                self.log.info('NR Rx Measurements: {}'.format(nr_rx_meas))

            testcase_results['results'].append(result)
            if result['decode_probability'] == 0:
                stop_counter = stop_counter + 1
            else:
                stop_counter = 0
            if stop_counter == STOP_COUNTER_LIMIT:
                break
        self.keysight_test_app.enable_rach(test_cell['cell_type'],
                                           test_cell['cell_number'],
                                           enabled=1)

        # Save results
        self.testclass_results[self.current_test_name] = testcase_results

    def get_per_cell_power_sweeps(self, testcase_params):
        # get reference test
        nr_cell_index = testcase_params['endc_combo_config']['lte_cell_count']
        current_band = testcase_params['endc_combo_config']['cell_list'][
            nr_cell_index]['band']
        reference_test = None
        reference_sensitivity = None
        for testcase_name, testcase_data in self.testclass_results.items():
            if testcase_data['testcase_params']['endc_combo_config'][
                    'cell_list'][nr_cell_index]['band'] == current_band:
                reference_test = testcase_name
                reference_sensitivity = testcase_data['sensitivity']
        if reference_test and reference_sensitivity and not self.retry_flag:
            start_atten = reference_sensitivity + self.testclass_params[
                'adjacent_mcs_gap']
            self.log.info(
                "Reference test {} found. Sensitivity {} dBm. Starting at {} dBm"
                .format(reference_test, reference_sensitivity, start_atten))
        else:
            start_atten = self.testclass_params['nr_cell_power_start']
            self.log.info(
                "Reference test not found. Starting at {} dBm".format(
                    start_atten))
        # get current cell power start
        nr_cell_sweep = list(
            numpy.arange(start_atten,
                         self.testclass_params['nr_cell_power_stop'],
                         self.testclass_params['nr_cell_power_step']))
        lte_sweep = [self.testclass_params['lte_cell_power']
                     ] * len(nr_cell_sweep)
        if nr_cell_index == 0:
            cell_power_sweeps = [nr_cell_sweep]
        else:
            cell_power_sweeps = [lte_sweep, nr_cell_sweep]
        return cell_power_sweeps

    def compile_test_params(self, testcase_params):
        """Function that completes all test params based on the test name.

        Args:
            testcase_params: dict containing test-specific parameters
        """
        # Cell power sweep
        # TODO: Make this a function to support single power and sweep modes for each cell
        testcase_params['cell_power_sweep'] = self.get_per_cell_power_sweeps(
            testcase_params)
        return testcase_params

    def generate_test_cases(self, **kwargs):
        test_cases = []
        with open(self.testclass_params['nr_single_cell_configs'],
                  'r') as csvfile:
            test_configs = csv.DictReader(csvfile)
            for test_config in test_configs:
                if int(test_config['skip_test']):
                    continue
                endc_combo_config = cputils.generate_endc_combo_config_from_csv_row(
                    test_config)
                test_name = 'test_fr1_{}'.format(test_config['nr_band'])
                test_params = collections.OrderedDict(
                    endc_combo_config=endc_combo_config,
                    lte_dl_mcs_table='QAM256',
                    lte_dl_mcs=4,
                    lte_ul_mcs_table='QAM256',
                    lte_ul_mcs=4,
                    nr_dl_mcs=4,
                    nr_ul_mcs=4,
                    transform_precoding=0,
                    # schedule_scenario='FULL_TPUT',
                    # schedule_slot_ratio=80
                    **kwargs)
                setattr(self, test_name,
                        partial(self._test_page_decode, test_params))
                test_cases.append(test_name)
        return test_cases
