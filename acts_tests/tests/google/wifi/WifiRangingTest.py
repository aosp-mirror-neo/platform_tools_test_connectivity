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
import time
from acts import asserts
from acts import base_test
from acts import context
from acts import utils
from acts.metrics.loggers.blackbox import BlackboxMappedMetricLogger
from acts_contrib.test_utils.wifi import delay_line
from acts_contrib.test_utils.wifi import phase_shifter
from acts_contrib.test_utils.wifi import wifi_performance_test_utils as wputils
from acts_contrib.test_utils.wifi import wifi_retail_ap as retail_ap
from acts_contrib.test_utils.wifi import wifi_test_utils as wutils
from functools import partial
from matplotlib import pyplot


class WifiRangingTest(base_test.BaseTestClass):
    """Class to test Wifi ranging.

    This class implements Wifi ranging in a conducted setup with programmable
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
        #self.tests = self.generate_test_cases()

    def setup_class(self):
        """Initializes common test hardware and parameters.

        This function initializes hardware and compiles parameters that are
        common to all tests in this class.
        """
        self.duts = self.android_devices
        req_params = [
            'DelayLineInstruments', 'testbed_params', 'ranging_test_params'
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
        for dev in self.android_devices:
            if self.testclass_params.get('airplane_mode', 0):
                self.log.info('Turning on airplane mode.')
                asserts.assert_true(utils.force_airplane_mode(dev, True),
                                    'Can not turn on airplane mode.')
            wutils.reset_wifi(dev)
            wutils.wifi_toggle_state(dev, True)
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
    def _test_ranging(self, testcase_params):
        testcase_params = self.compile_test_params(testcase_params)
        ranging_link = wputils.brcm_utils.RangingLink(self.duts[0], self.duts[1])

        ranging_link.setup_ranging_link(testcase_params['channel'],
                                        testcase_params['bandwidth'],
                                        self.testclass_params['associate_initiator'],
                                        testcase_params['ranging_method'])
        if testcase_params['channel'] in wutils.WifiEnums.channel_5G_to_freq:
            testcase_params['swept_path']['phase_shifter'].set_frequency(
                wutils.WifiEnums.channel_5G_to_freq[testcase_params['channel']])
        else:
            testcase_params['swept_path']['phase_shifter'].set_frequency(4000)
        for path in self.paths:
            if path == testcase_params['swept_path']:
                continue
            if not isinstance(path['delay_intrument'], delay_line.FixedDelayLine):
                path['delay_intrument'].set_delay(self.testclass_params['fixed_path_delay'])
            path['attenuator'].set_atten(self.testclass_params['fixed_path_attenuation'])

        looped_phase = (self.testclass_params['swept_path_phase']['stop'] == -1)
        if looped_phase:
            testcase_params['swept_path']['phase_shifter'].start_phase_loop(
                self.testclass_params['swept_path_phase']['step'],
                self.testclass_params['swept_path_phase']['dwell_time'])
        ranging_sweep_results = collections.OrderedDict()

        for attenuation in testcase_params['attenuation_sweep']:
            self.log.info(testcase_params['attenuation_sweep'])
            self.log.info(testcase_params['delay_sweep'])
            ranging_sweep_results[attenuation] = collections.OrderedDict()
            for delay in testcase_params['delay_sweep']:
                ranging_sweep_results[attenuation][delay] = collections.OrderedDict()
                phase_sweep = [1] if looped_phase else testcase_params['phase_sweep']
                for phase in phase_sweep:
                    self.log.info('Swept Path Config: {}ns, {}dB, {}deg'.format(delay, attenuation, phase))
                    testcase_params['swept_path']['delay_intrument'].set_delay(delay)
                    testcase_params['swept_path']['attenuator'].set_atten(attenuation)
                    testcase_params['swept_path']['phase_shifter'].set_phase(phase)
                    result = ranging_link.measure_range(self.testclass_params['ranging_measurements'],
                                                        testcase_params['channel'],
                                                        testcase_params['bandwidth'],
                                                        no_meas_frames=self.testclass_params['ftm_exchanges'],
                                                        ranging_method=testcase_params['ranging_method'])
                    self.log.info(result['summary'])
                    ranging_sweep_results[attenuation][delay][phase] = result

        if looped_phase:
            testcase_params['swept_path']['phase_shifter'].stop_phase_loop()

        ranging_link.teardown_ranging_link()
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
            compiled_sweep_results['rtt'].append([])
            compiled_sweep_results['std_dev_rtt'].append([])
            compiled_sweep_results['rssi'].append([])
            compiled_sweep_results['std_dev_rssi'].append([])
            for current_delay, delay_results in attenuation_results.items():
                distance = numpy.mean([val['summary']['avg_distance'] for key, val in delay_results.items()])
                std_dev_distance = numpy.mean([val['summary']['std_dev_distance'] for key, val in delay_results.items()])
                rtt = numpy.mean([val['summary']['avg_rtt'] for key, val in delay_results.items()])
                rssi = numpy.mean([val['summary']['avg_rssi'] for key, val in delay_results.items()])
                std_dev_rtt = numpy.mean([val['summary']['std_dev_rtt'] for key, val in delay_results.items()])
                std_dev_rssi = numpy.mean([val['summary']['std_dev_rssi'] for key, val in delay_results.items()])
                compiled_sweep_results['distance'][-1].append(distance)
                compiled_sweep_results['std_dev_distance'][-1].append(std_dev_distance)
                compiled_sweep_results['rtt'][-1].append(rtt)
                compiled_sweep_results['std_dev_rtt'][-1].append(std_dev_rtt)
                compiled_sweep_results['rssi'][-1].append(rssi)
                compiled_sweep_results['std_dev_rssi'][-1].append(std_dev_rssi)


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
        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['rtt'],
            'rtt')
        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['std_dev_rtt'],
            'std_dev_rtt')
        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['rssi'],
            'rssi')
        self.plot_attenuation_delay_sweep_results(
            test_result['testcase_params']['attenuation_sweep'],
            test_result['testcase_params']['delay_sweep'],
            compiled_sweep_results['std_dev_rssi'],
            'std_dev_rssi')

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

    def compile_test_params(self, testcase_params):
        # tests to support are
        #   * single path attenuation, delay sweep
        #   * two path delay sweep (relative sweep)

        # Pick first configurable-delay path as swept path
        #for path in self.paths:
        #    if not isinstance(path['delay_intrument'], delay_line.FixedDelayLine):
        #        testcase_params['swept_path'] = path
        #        break
        testcase_params['swept_path'] = self.paths[testcase_params['swept_path_index']]
        num_atten_steps = int(
            (self.testclass_params['swept_path_attenuation']['stop'] - self.testclass_params['swept_path_attenuation']['start']) /
            self.testclass_params['swept_path_attenuation']['step'])
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


    def generate_test_cases(self, num_paths = 2, ranging_method = '11mc'):
        """Function that auto-generates test cases for a test class."""
        test_cases = []
        test_configs = [{'channel': 6, 'bandwidth': 20},
                        {'channel': 36, 'bandwidth': 20},
                        {'channel': 36, 'bandwidth': 40},
                        {'channel': 36, 'bandwidth': 80},
                        {'channel': 36, 'bandwidth': 160},
                        {'channel': 149, 'bandwidth': 20},
                        {'channel': 149, 'bandwidth': 40},
                        {'channel': 149, 'bandwidth': 80}]

        for swept_path_index, test_config in itertools.product(range(num_paths), test_configs):
            test_name = 'test_{}_path_ranging_swept_path_{}_ch{}_{}'.format(
                num_paths, swept_path_index, test_config['channel'], test_config['bandwidth'])
            test_params = collections.OrderedDict(
                num_paths = num_paths,
                swept_path_index = swept_path_index,
                channel=test_config['channel'],
                bandwidth=test_config['bandwidth'],
                ranging_method = ranging_method
            )
            setattr(self, test_name, partial(self._test_ranging, test_params))
            test_cases.append(test_name)
        return test_cases


class WifiRanging_11mc_Test(WifiRangingTest):
    def __init__(self, controllers):
        super().__init__(controllers)
        self.tests = self.generate_test_cases(ranging_method = '11mc')

class WifiRanging_OneSidedRtt_Test(WifiRangingTest):
    def __init__(self, controllers):
        super().__init__(controllers)
        self.tests = self.generate_test_cases(ranging_method = '11mc_one_sided')

class WifiRanging_11az_Test(WifiRangingTest):
    def __init__(self, controllers):
        super().__init__(controllers)
        self.tests = self.generate_test_cases(ranging_method = '11az')