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
TWO_SECOND_SLEEP = 2
MEDIUM_SLEEP = 3
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

    def process_testcase_results(self):
        if self.current_test_name not in self.testclass_results:
            return
        testcase_data = self.testclass_results[self.current_test_name]
        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.json'.format(self.current_test_name))
        with open(results_file_path, 'w') as results_file:
            json.dump(wputils.serialize_dict(testcase_data),
                      results_file,
                      indent=4)

        decode_probability_list = []
        average_power_list = []
        cell_power_list = testcase_data['testcase_params']['cell_power_sweep'][0]
        for result in testcase_data['results']:
            decode_probability_list.append(result['decode_probability'])
            if self.power_monitor:
                average_power_list.append(result['average_power'])
        padding_len = len(cell_power_list) - len(decode_probability_list)
        decode_probability_list.extend([0] * padding_len)

        testcase_data['decode_probability_list'] = decode_probability_list
        testcase_data['cell_power_list'] = cell_power_list

        plot = BokehFigure(
            title='Band {} - Page Decode Probability'.format(testcase_data['testcase_params']['endc_combo_config']['cell_list'][0]['band']),
            x_label='Cell Power (dBm)',
            primary_y_label='Decode Probability',
            secondary_y_label='Power Consumption (mW)'
        )

        plot.add_line(
            testcase_data['cell_power_list'],
            testcase_data['decode_probability_list'],
            'Decode Probability',
            width=1)
        if self.power_monitor:
            plot.add_line(
                testcase_data['testcase_params']['cell_power_sweep'][0],
                average_power_list,
                'Power Consumption (mW)',
                width=1,
                style='dashdot',
                y_axis='secondary')
        plot.generate_figure()
        output_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.html'.format(self.current_test_name))
        BokehFigure.save_figure(plot, output_file_path)

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
        # Put DUT to sleep for power measurements
        self.dut_utils.go_to_sleep()

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
                    0)
            self.log.info('Cell Power: {}'.format(cell_power_array))
            result['cell_power'] = cell_power_array
            # Start BLER and throughput measurements
            if self.power_monitor:
                measurement_wait = LONG_SLEEP if (power_idx == 0) else 0
                average_power_future = self.collect_power_data_nonblocking(
                    min(10, self.testclass_params['num_measurements'])*MEDIUM_SLEEP,
                    measurement_wait,
                    reconnect_usb=0,
                    measurement_tag=power_idx)
            decode_counter = 0
            for idx in range(self.testclass_params['num_measurements']):
                # Page device
                self.keysight_test_app.send_rrc_paging(
                    test_cell['cell_type'], test_cell['cell_number'])
                time.sleep(MEDIUM_SLEEP)
                # Fetch page result
                preamble_report = self.keysight_test_app.fetch_preamble_report(
                    test_cell['cell_type'], test_cell['cell_number'])
                # If rach attempted, increment decode counter.
                if preamble_report:
                    decode_counter = decode_counter + 1
                self.log.info('Decode probability: {}/{}'.format(decode_counter, idx+1))
            result[
                'decode_probability'] = decode_counter / self.testclass_params[
                    'num_measurements']
            if self.power_monitor:
                average_power = average_power_future.result()
                result['average_power'] = average_power

            if self.testclass_params.get('log_rsrp_metrics', 1) and self.dut.is_connected():
                lte_rx_meas = self.dut_utils.get_rx_measurements('LTE')
                nr_rx_meas = self.dut_utils.get_rx_measurements('NR5G')
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

class CellularFr1PageDecodeTest(CellularPageDecodeTest):

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True
        self.testclass_params = self.user_params['page_decode_test_params']
        self.tests = self.generate_test_cases()

    def get_per_cell_power_sweeps(self, testcase_params):
        nr_cell_sweep = list(
            numpy.arange(self.testclass_params['nr_cell_power_start'],
                         self.testclass_params['nr_cell_power_stop'],
                         self.testclass_params['nr_cell_power_step']))
        return [nr_cell_sweep]

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
                    nr_dl_mcs_table='Q256',
                    nr_ul_mcs_table='Q64',
                    **kwargs)
                setattr(self, test_name,
                        partial(self._test_page_decode, test_params))
                test_cases.append(test_name)
        return test_cases


class CellularLtePageDecodeTest(CellularPageDecodeTest):

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True
        self.testclass_params = self.user_params['page_decode_test_params']
        self.tests = self.generate_test_cases()

    def get_per_cell_power_sweeps(self, testcase_params):
        lte_cell_sweep = list(
            numpy.arange(self.testclass_params['lte_cell_power_start'],
                         self.testclass_params['lte_cell_power_stop'],
                         self.testclass_params['lte_cell_power_step']))
        cell_power_sweeps = [lte_cell_sweep]
        return cell_power_sweeps

    def generate_test_cases(self, **kwargs):
        test_cases = []
        with open(self.testclass_params['lte_single_cell_configs'],
                  'r') as csvfile:
            test_configs = csv.DictReader(csvfile)
            for test_config in test_configs:
                if int(test_config['skip_test']):
                    continue
                endc_combo_config = cputils.generate_endc_combo_config_from_csv_row(
                    test_config)
                test_name = 'test_lte_B{}'.format(test_config['lte_band'])
                test_params = collections.OrderedDict(
                    endc_combo_config=endc_combo_config,
                    lte_dl_mcs_table='QAM256',
                    lte_dl_mcs=4,
                    lte_ul_mcs_table='QAM256',
                    lte_ul_mcs=4,
                    nr_dl_mcs=4,
                    nr_ul_mcs=4,
                    transform_precoding=0,
                    **kwargs)
                setattr(self, test_name,
                        partial(self._test_page_decode, test_params))
                test_cases.append(test_name)
        return test_cases
