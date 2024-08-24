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
import numpy
import json
import re
import os
from acts import context
from acts import base_test
from acts.metrics.loggers.blackbox import BlackboxMappedMetricLogger
from acts_contrib.test_utils.cellular.performance import cellular_performance_test_utils as cputils
from acts_contrib.test_utils.cellular.performance.CellularThroughputBaseTest import CellularThroughputBaseTest
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils
from acts_contrib.test_utils.wifi.wifi_performance_test_utils.bokeh_figure import BokehFigure
from functools import partial


class CellularLteFr1EndcRvrTest(CellularThroughputBaseTest):
    """Class to test ENDC sensitivity"""

    def __init__(self, controllers):
        base_test.BaseTestClass.__init__(self, controllers)
        self.testcase_metric_logger = (
            BlackboxMappedMetricLogger.for_test_case())
        self.testclass_metric_logger = (
            BlackboxMappedMetricLogger.for_test_class())
        self.publish_testcase_metrics = True
        self.testclass_params = self.user_params['endc_rvr_test_params']
        self.tests = self.generate_test_cases(lte_dl_mcs_table='QAM256',
                                              lte_ul_mcs_table='QAM256',
                                              lte_ul_mcs=4,
                                              nr_ul_mcs=4,
                                              transform_precoding=0,
                                              schedule_scenario='FULL_TPUT',
                                              schedule_slot_ratio=80,
                                              nr_dl_mcs_table='Q256',
                                              nr_ul_mcs_table='Q64')

    def process_testclass_results(self):
        pass

    def process_testcase_results(self):
        if self.current_test_name not in self.testclass_results:
            return
        testcase_data = self.testclass_results[self.current_test_name]

        average_power_list = []
        cell_throughput_lists = {}
        for current_cell_idx, current_cell in enumerate(testcase_data['testcase_params']['endc_combo_config']['cell_list']):
            cell_throughput_lists[current_cell_idx]=[]

        for result in testcase_data['results']:
            for current_cell_idx, current_cell in enumerate(testcase_data['testcase_params']['endc_combo_config']['cell_list']):
                if current_cell['cell_type'] == 'LTE':
                    cell_throughput_lists[current_cell_idx].append(
                        result['throughput_measurements']['lte_tput_result'][current_cell['cell_number']]
                        ['DL']['average_tput'])
                else:
                    cell_throughput_lists[current_cell_idx].append(
                        result['throughput_measurements']['nr_tput_result'][current_cell['cell_number']]
                        ['DL']['average_tput'])
            if self.power_monitor:
                average_power_list.append(result['average_power'])

        plot = BokehFigure(
            title='ENDC RvR',
            x_label='Cell Power (dBm/SCS)',
            primary_y_label='PHY Rate (Mbps)',
            secondary_y_label='Power Consumption (mW)')

        for cell_idx, cell_throughput_list in cell_throughput_lists.items():
            plot.add_line(
                testcase_data['testcase_params']['cell_power_sweep'][cell_idx],
                cell_throughput_lists[cell_idx],
                'Cell {} - Average Throughput'.format(cell_idx),
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
        output_file_path = os.path.join(self.log_path, '{}.html'.format(self.current_test_name))
        BokehFigure.save_figure(plot, output_file_path)

        results_file_path = os.path.join(
            context.get_current_context().get_full_output_path(),
            '{}.json'.format(self.current_test_name))
        with open(results_file_path, 'w') as results_file:
            json.dump(wputils.serialize_dict(testcase_data),
                      results_file,
                      indent=4)

    def get_per_cell_power_sweeps(self, testcase_params):
        cell_power_sweeps = []
        # Construct test cell sweep
        lte_sweep = list(
            numpy.arange(self.testclass_params['lte_cell_power_start'],
                         self.testclass_params['lte_cell_power_stop'],
                         self.testclass_params['lte_cell_power_step']))
        nr_sweep = list(
            numpy.arange(self.testclass_params['nr_cell_power_start'],
                         self.testclass_params['nr_cell_power_stop'],
                         self.testclass_params['nr_cell_power_step']))
        if len(lte_sweep) > len(nr_sweep):
            nr_sweep_pad = len(lte_sweep) - len(nr_sweep)
            nr_sweep.extend([nr_sweep[-1]]*nr_sweep_pad)
        elif len(lte_sweep) < len(nr_sweep):
            lte_sweep_pad = len(nr_sweep) - len(lte_sweep)
            lte_sweep.extend([lte_sweep[-1]]*lte_sweep_pad)


        for cell_idx, cell_config in enumerate(testcase_params['endc_combo_config']['cell_list']):
            if testcase_params['test_cell_idx'] in [cell_idx, 'all']:
                if cell_config['cell_type'] == 'LTE':
                    cell_power_sweeps.append(lte_sweep)
                elif cell_config['cell_type'] == 'NR5G':
                    cell_power_sweeps.append(nr_sweep)
            elif cell_config['cell_type'] == 'LTE':
                cell_power_sweeps.append([self.testclass_params['lte_cell_power_start']
                             ] * len(nr_sweep))
            elif cell_config['cell_type'] == 'NR5G':
                cell_power_sweeps.append([self.testclass_params['nr_cell_power_start']
                             ] * len(lte_sweep))
        return cell_power_sweeps

    def generate_test_cases(self, lte_dl_mcs_table,
                            lte_ul_mcs_table, lte_ul_mcs,
                            nr_ul_mcs, **kwargs):
        test_cases = []
        with open(self.testclass_params['endc_combo_file'],
                  'r') as endc_combos:
            for endc_combo_str in endc_combos:
                if endc_combo_str[0] == '#':
                    continue
                endc_combo_config = cputils.generate_endc_combo_config_from_string(
                    endc_combo_str)
                special_chars = '+[]=;,\n'
                for char in special_chars:
                    endc_combo_str = endc_combo_str.replace(char, '_')
                endc_combo_str = endc_combo_str.replace('__', '_')
                endc_combo_str = endc_combo_str.strip('_')
                test_cell_list = list(range(len(endc_combo_config['cell_list'])))
                test_cell_list.append('all')
                for cell_idx in test_cell_list:
                    test_name = 'test_rvr_{}_cell_{}'.format(
                        endc_combo_str, cell_idx)
                    test_params = collections.OrderedDict(
                        endc_combo_config=endc_combo_config,
                        test_cell_idx=cell_idx,
                        lte_dl_mcs_table=lte_dl_mcs_table,
                        lte_dl_mcs=self.testclass_params['link_adaptation_config']['LTE'],
                        lte_ul_mcs_table=lte_ul_mcs_table,
                        lte_ul_mcs=lte_ul_mcs,
                        nr_dl_mcs=self.testclass_params['link_adaptation_config']['NR5G'],
                        nr_ul_mcs=nr_ul_mcs,
                        **kwargs)
                    setattr(self, test_name,
                            partial(self._test_throughput_bler, test_params))
                    test_cases.append(test_name)
        return test_cases