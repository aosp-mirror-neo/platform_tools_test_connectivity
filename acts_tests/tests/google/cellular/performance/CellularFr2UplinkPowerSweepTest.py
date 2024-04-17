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
import itertools
import json
import re
import numpy
import os
from acts import context
from acts import base_test
from acts.metrics.loggers.blackbox import BlackboxMappedMetricLogger
from acts_contrib.test_utils.cellular.performance import cellular_performance_test_utils as cputils
from acts_contrib.test_utils.cellular.performance.CellularThroughputBaseTest import CellularThroughputBaseTest
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils

from functools import partial

LONG_SLEEP = 10
MEDIUM_SLEEP = 2
IPERF_TIMEOUT = 10
SHORT_SLEEP = 1
SUBFRAME_LENGTH = 0.001
STOP_COUNTER_LIMIT = 3


class CellularFr2UplinkPowerSweepTest(CellularThroughputBaseTest):
    """Base class to test cellular FR2 throughput

    This class implements cellular FR2 throughput tests on a callbox setup.
    The class setups up the callbox in the desired configurations, configures
    and connects the phone, and runs traffic/iperf throughput.
    """

    def __init__(self, controllers):
        super().__init__(controllers)
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True

    def process_testcase_results(self):
        """Publish test case metrics and save results"""
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
        testcase_result = testcase_data['results'][0]

    def process_testclass_results(self):
        pass

    def get_per_cell_power_sweeps(self, testcase_params):
        cell_power_sweeps = []
        for cell in testcase_params['endc_combo_config']['cell_list']:
            if cell['cell_type'] == 'LTE':
                sweep = [self.testclass_params['lte_cell_power']]
            else:
                sweep = [self.testclass_params['nr_cell_power']]
            cell_power_sweeps.append(sweep)
        return cell_power_sweeps

    def generate_endc_combo_config(self, test_config):
        """Function to generate ENDC combo config from CSV test config

        Args:
            test_config: dict containing ENDC combo config from CSV
        Returns:
            endc_combo_config: dictionary with all ENDC combo settings
        """
        endc_combo_config = collections.OrderedDict()
        cell_config_list = []

        lte_cell_count = 1
        lte_carriers = [1]
        lte_scc_list = []
        endc_combo_config['lte_pcc'] = 1
        lte_cell = {
            'cell_type': 'LTE',
            'cell_number': 1,
            'pcc': 1,
            'band': self.testclass_params['lte_anchor_band'],
            'dl_bandwidth': self.testclass_params['lte_anchor_bandwidth'],
            'ul_enabled': 1,
            'duplex_mode': self.testclass_params['lte_anchor_duplex_mode'],
            'dl_mimo_config': 'D{nss}U{nss}'.format(nss=1),
            'ul_mimo_config': 'D{nss}U{nss}'.format(nss=1),
            'transmission_mode': 'TM1',
            'num_codewords': 1,
            'num_layers': 1,
            'dl_subframe_allocation': [1] * 10,
        }
        cell_config_list.append(lte_cell)

        nr_cell_count = 0
        nr_dl_carriers = []
        nr_ul_carriers = []
        for nr_cell_idx in range(1, test_config['num_dl_cells'] + 1):
            nr_cell = {
                'cell_type':
                'NR5G',
                'cell_number':
                nr_cell_idx,
                'nr_cell_type':
                'NSA',
                'band':
                test_config['nr_band'],
                'duplex_mode':
                test_config['nr_duplex_mode'],
                'channel':
                test_config['nr_channel'],
                'dl_mimo_config':
                'N{nss}X{nss}'.format(nss=test_config['nr_dl_mimo_config']),
                'dl_bandwidth_class':
                'A',
                'dl_bandwidth':
                test_config['nr_bandwidth'],
                'ul_enabled':
                1 if nr_cell_idx <= test_config['num_ul_cells'] else 0,
                'ul_bandwidth_class':
                'A',
                'ul_mimo_config':
                'N{nss}X{nss}'.format(nss=test_config['nr_ul_mimo_config']),
                'subcarrier_spacing':
                'MU3'
            }
            cell_config_list.append(nr_cell)
            nr_cell_count = nr_cell_count + 1
            nr_dl_carriers.append(nr_cell_idx)
            if nr_cell_idx <= test_config['num_ul_cells']:
                nr_ul_carriers.append(nr_cell_idx)

        endc_combo_config['lte_cell_count'] = lte_cell_count
        endc_combo_config['nr_cell_count'] = nr_cell_count
        endc_combo_config['nr_dl_carriers'] = nr_dl_carriers
        endc_combo_config['nr_ul_carriers'] = nr_ul_carriers
        endc_combo_config['cell_list'] = cell_config_list
        endc_combo_config['lte_scc_list'] = lte_scc_list
        endc_combo_config['lte_dl_carriers'] = lte_carriers
        endc_combo_config['lte_ul_carriers'] = lte_carriers
        return endc_combo_config

    def _test_throughput_bler_sweep_ul_power(self, testcase_params):
        """Test function to run cellular throughput and BLER measurements.

        The function runs BLER/throughput measurement after configuring the
        callbox and DUT. The test supports running PHY or TCP/UDP layer traffic
        in a variety of band/carrier/mcs/etc configurations.

        Args:
            testcase_params: dict containing test-specific parameters
        Returns:
            result: dict containing throughput results and metadata
        """
        # Prepare results dicts
        testcase_params = self.compile_test_params(testcase_params)
        testcase_params['nr_target_power_sweep'] = list(
            numpy.arange(self.testclass_params['nr_target_power_start'],
                         self.testclass_params['nr_target_power_stop'],
                         self.testclass_params['nr_target_power_step']))

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

        # Run throughput test loop
        stop_counter = 0
        if testcase_params['endc_combo_config']['nr_cell_count']:
            self.keysight_test_app.select_display_tab('NR5G', 1, 'BTHR',
                                                      'OTAGRAPH')
        else:
            self.keysight_test_app.select_display_tab('LTE', 1, 'BTHR',
                                                      'OTAGRAPH')
        for power_idx in range(len(testcase_params['nr_target_power_sweep'])):
            result = collections.OrderedDict()
            # Check that cells are still connected
            connected = 1
            for cell in testcase_params['endc_combo_config']['cell_list']:
                if not self.keysight_test_app.wait_for_cell_status(
                        cell['cell_type'], cell['cell_number'],
                    ['ACT', 'CONN'], SHORT_SLEEP, SHORT_SLEEP):
                    connected = 0
            if not connected:
                self.log.info('DUT lost connection to cells. Ending test.')
                break
            # Set DL cell power
            current_target_power = testcase_params['nr_target_power_sweep'][
                power_idx]
            self.log.info(
                'Setting target power to {}dBm'.format(current_target_power))
            for cell_idx, cell in enumerate(
                    testcase_params['endc_combo_config']['cell_list']):
                self.keysight_test_app.set_cell_ul_power_control(
                    cell['cell_type'], cell['cell_number'], 'TARget',
                    current_target_power)
            # Start BLER and throughput measurements
            current_throughput = self.run_single_throughput_measurement(
                testcase_params)
            result['throughput_measurements'] = current_throughput
            result['nr_target_power'] = current_target_power
            self.print_throughput_result(current_throughput)

            tx_power = self.dut_utils.get_fr2_tx_power()

            testcase_results['results'].append(result)
            if (('lte_bler_result' in result['throughput_measurements']
                 and result['throughput_measurements']['lte_bler_result']
                 ['total']['DL']['nack_ratio'] * 100 > 99)
                    or ('nr_bler_result' in result['throughput_measurements']
                        and result['throughput_measurements']['nr_bler_result']
                        ['total']['DL']['nack_ratio'] * 100 > 99)):
                stop_counter = stop_counter + 1
            else:
                stop_counter = 0
            if stop_counter == STOP_COUNTER_LIMIT:
                break

        # Save results
        self.testclass_results[self.current_test_name] = testcase_results

    def generate_test_cases(self, bands, channels, nr_mcs_pair_list,
                            num_dl_cells_list, num_ul_cells_list,
                            orientation_list, dl_mimo_config, ul_mimo_config,
                            **kwargs):
        """Function that auto-generates test cases for a test class."""
        test_cases = []
        for orientation, band, channel, num_ul_cells, num_dl_cells, nr_mcs_pair in itertools.product(
                orientation_list, bands, channels, num_ul_cells_list,
                num_dl_cells_list, nr_mcs_pair_list):
            if num_ul_cells > num_dl_cells:
                continue
            if channel not in cputils.PCC_PRESET_MAPPING[band]:
                continue
            test_config = {
                'nr_band': band,
                'nr_bandwidth': 'BW100',
                'nr_duplex_mode': 'TDD',
                'nr_cell_type': 'NSA',
                'nr_channel': cputils.PCC_PRESET_MAPPING[band][channel],
                'num_dl_cells': num_dl_cells,
                'num_ul_cells': num_ul_cells,
                'nr_dl_mimo_config': dl_mimo_config,
                'nr_ul_mimo_config': ul_mimo_config
            }
            endc_combo_config = self.generate_endc_combo_config(test_config)
            test_name = 'test_fr2_ul_power_sweep_{}_{}_{}_DL_{}CC_mcs{}_{}x{}_UL_{}CC_mcs{}_{}x{}'.format(
                orientation, band, channel, num_dl_cells, nr_mcs_pair[0],
                dl_mimo_config, dl_mimo_config, num_ul_cells, nr_mcs_pair[1],
                ul_mimo_config, ul_mimo_config)
            test_params = collections.OrderedDict(
                endc_combo_config=endc_combo_config,
                nr_dl_mcs=nr_mcs_pair[0],
                nr_ul_mcs=nr_mcs_pair[1],
                orientation=orientation,
                **kwargs)
            setattr(
                self, test_name,
                partial(self._test_throughput_bler_sweep_ul_power,
                        test_params))
            test_cases.append(test_name)
        return test_cases


class CellularFr2CpOfdmUplinkPowerSweepTest(CellularFr2UplinkPowerSweepTest):

    def __init__(self, controllers):
        super().__init__(controllers)
        self.testclass_params = self.user_params[
            'fr2_uplink_power_sweep_test_params']
        self.tests = self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                              ['low', 'mid', 'high'],
                                              [(4, 16), (4, 25), (4, 27),
                                               (4, 28)], [1], [1],
                                              ['A_Plane', 'B_Plane'],
                                              force_contiguous_nr_channel=True,
                                              dl_mimo_config=2,
                                              ul_mimo_config=2,
                                              schedule_scenario="FULL_TPUT",
                                              schedule_slot_ratio=80,
                                              traffic_direction='UL',
                                              transform_precoding=0,
                                              lte_dl_mcs=4,
                                              lte_dl_mcs_table='QAM64',
                                              lte_ul_mcs=4,
                                              lte_ul_mcs_table='QAM64')

        self.tests.extend(
            self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                     ['low', 'mid', 'high'], [(4, 16), (4, 25),
                                                              (4, 27),
                                                              (4, 28)], [2],
                                     [2], ['A_Plane', 'B_Plane'],
                                     force_contiguous_nr_channel=True,
                                     dl_mimo_config=2,
                                     ul_mimo_config=2,
                                     schedule_scenario="FULL_TPUT",
                                     schedule_slot_ratio=80,
                                     traffic_direction='UL',
                                     transform_precoding=0,
                                     lte_dl_mcs=4,
                                     lte_dl_mcs_table='QAM64',
                                     lte_ul_mcs=4,
                                     lte_ul_mcs_table='QAM64'))
        self.tests.extend(
            self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                     ['low', 'mid', 'high'], [(4, 16), (4, 25),
                                                              (4, 27),
                                                              (4, 28)], [4],
                                     [4], ['A_Plane', 'B_Plane'],
                                     force_contiguous_nr_channel=True,
                                     dl_mimo_config=2,
                                     ul_mimo_config=2,
                                     schedule_scenario="FULL_TPUT",
                                     schedule_slot_ratio=80,
                                     traffic_direction='UL',
                                     transform_precoding=0,
                                     lte_dl_mcs=4,
                                     lte_dl_mcs_table='QAM64',
                                     lte_ul_mcs=4,
                                     lte_ul_mcs_table='QAM64'))


class CellularFr2DftsOfdmUplinkPowerSweepTest(CellularFr2UplinkPowerSweepTest):

    def __init__(self, controllers):
        super().__init__(controllers)
        self.testclass_params = self.user_params[
            'fr2_uplink_power_sweep_test_params']
        self.tests = self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                              ['low', 'mid', 'high'],
                                              [(4, 16), (4, 25), (4, 27),
                                               (4, 28)], [1], [1],
                                              ['A_Plane', 'B_Plane'],
                                              force_contiguous_nr_channel=True,
                                              dl_mimo_config=2,
                                              ul_mimo_config=1,
                                              schedule_scenario="FULL_TPUT",
                                              schedule_slot_ratio=80,
                                              traffic_direction='UL',
                                              transform_precoding=1,
                                              lte_dl_mcs=4,
                                              lte_dl_mcs_table='QAM64',
                                              lte_ul_mcs=4,
                                              lte_ul_mcs_table='QAM64')

        self.tests.extend(
            self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                     ['low', 'mid', 'high'], [(4, 16), (4, 25),
                                                              (4, 27),
                                                              (4, 28)], [2],
                                     [2], ['A_Plane', 'B_Plane'],
                                     force_contiguous_nr_channel=True,
                                     dl_mimo_config=2,
                                     ul_mimo_config=2,
                                     schedule_scenario="FULL_TPUT",
                                     schedule_slot_ratio=80,
                                     traffic_direction='UL',
                                     transform_precoding=1,
                                     lte_dl_mcs=4,
                                     lte_dl_mcs_table='QAM64',
                                     lte_ul_mcs=4,
                                     lte_ul_mcs_table='QAM64'))
        self.tests.extend(
            self.generate_test_cases(['N257', 'N258', 'N260', 'N261'],
                                     ['low', 'mid', 'high'], [(4, 16), (4, 25),
                                                              (4, 27),
                                                              (4, 28)], [4],
                                     [4], ['A_Plane', 'B_Plane'],
                                     force_contiguous_nr_channel=True,
                                     dl_mimo_config=2,
                                     ul_mimo_config=2,
                                     schedule_scenario="FULL_TPUT",
                                     schedule_slot_ratio=80,
                                     traffic_direction='UL',
                                     transform_precoding=1,
                                     lte_dl_mcs=4,
                                     lte_dl_mcs_table='QAM64',
                                     lte_ul_mcs=4,
                                     lte_ul_mcs_table='QAM64'))
