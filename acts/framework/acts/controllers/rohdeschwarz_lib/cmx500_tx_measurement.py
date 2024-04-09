#!/usr/bin/env python3
#
#   Copyright 2024 - The Android Open Source Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#           http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""Provides classes for managing uplink power sessions on CMX500 callboxes."""

import time
import logging

logger = logging.getLogger('Xlapi_cmx500')

DEFAULT_SAMPLE_COUNT = 20


def delete_all_multievals():
    """ Removes all current multieval sessions open on the CMX. """
    from xlapi import meas
    meas.delete_all_lte_rf_meas()
    meas.delete_all_nr_fr1_rf_meas()
    meas.delete_all_nr_fr2_rf_meas()


def create_measurement(cell):
    """ Gets or creates a new measurement for an individual cell.

    Args:
        cell the to base the measurement on.

    Returns:
        meas: the Cmx500TxMeasurementBase object for the cell.
    """
    from xlapi import LteCell, NrCell
    if isinstance(cell, LteCell):
        return Cmx500LteTxMeasurement(cell)

    # Nr measurements need to either be FR1 or FR2 so initialization of
    # measurement should take place after cell configuration to avoid
    # changing after-the-fact which will cause an error.
    elif isinstance(cell, NrCell):
        if cell.get_band().is_fr1():
            return Cmx500NrFr1Measurement(cell)
        elif cell.get_band().is_fr2():
            raise ValueError("Fr2 measurements are currently unsupported")
        else:
            raise ValueError("Unsupported frequency band: %s", cell.get_band())
    else:
        raise ValueError("Unsupported cell type: %s", cell)


class Cmx500TxMeasurementBase(object):
    """ Class for performing uplink power measurements for a single cell. """

    @property
    def sample_count(self):
        """ Gets the number of samples to use when running the test. """
        raise NotImplementedError()

    @sample_count.setter
    def sample_count(self, sample_count):
        """ Sets the number of samples to use when running the test. """
        raise NotImplementedError()

    @property
    def tx_average(self):
        """ Gets the measured average Tx power (in dBm). """
        raise NotImplementedError()

    @property
    def tx_min(self):
        """ Gets the measured minimum Tx power (in dBm). """
        raise NotImplementedError()

    @property
    def tx_max(self):
        """ Gets the measured maximum Tx power (in dBm). """
        raise NotImplementedError()

    @property
    def tx_stdev(self):
        """ Gets the measured Tx power standard deviation (in dBm). """
        raise NotImplementedError()

    @property
    def result(self):
        """ Gets the current result for the evaluation. """
        eval = self.get_multi_evaluation()
        return eval.result

    def get_measurement(self):
        """ Gets the underlying CMX500 measurement manager object. """
        raise NotImplementedError()

    def get_multi_evaluation(self):
        """ Gets the CMX500 multieval object. """
        return self.get_measurement().multi_evaluation

    def run_measurement(self):
        """ Runs a single Tx multievaluation measurement to completion. """
        eval = self.get_multi_evaluation()
        self.stop_measurement()
        eval.start_single_shot()

        # Measurements may take some time to initialize the first time they
        # run. In this case wait_for_complete will return immediately so we
        # should ensure eval is started before waiting for completion.
        timeout = time.time() + eval.guard_time.in_s()
        while not eval.is_running:
            if time.time() >= timeout:
                # Just warn, since it's technically possible that we missed
                # is_running due to a race condition.
                logger.warn("Unable to verify that measurement was started")
                break
        eval.wait_for_complete()

    def stop_measurement(self):
        """ Stops any on-going measurements. """
        eval = self.get_multi_evaluation()
        if eval.is_running:
            eval.stop()

    def abort_measurement(self):
        """ Aborts the measurement and releases any resources held open. """
        self.get_measurement().delete()


class Cmx500LteTxMeasurement(Cmx500TxMeasurementBase):
    """ Class for performing Lte uplink power measurements. """

    def __init__(self, cell):
        """ Initialize a new LTE TX measurement.

        Args:
            cell: the CMX500 XLAPI cell to measure.
        """
        from xlapi import meas
        self._meas = meas.get_or_create_lte_rf_meas(cell)
        self.sample_count = DEFAULT_SAMPLE_COUNT

        # Enable only tx power measurement.
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        meas_config.disable_all()
        meas_config.power.monitor_enabled = True

    def get_measurement(self):
        """ Gets the CMX500 measurement manager object. """
        return self._meas

    @property
    def sample_count(self):
        """ Gets the number of samples to use when running the test. """
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        return meas_config.power.statistic_count

    @sample_count.setter
    def sample_count(self, sample_count):
        """ Sets the number of samples to use when running the test. """
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        meas_config.power.statistic_count = sample_count

    @property
    def tx_average(self):
        """ Gets the measured average Tx power (in dBm). """
        result = self.result
        return result.power.monitor.total.avg.value.in_dBm()

    @property
    def tx_min(self):
        """ Gets the measured minimum Tx power (in dBm). """
        result = self.result
        return result.power.monitor.total.min.value.in_dBm()

    @property
    def tx_max(self):
        """ Gets the measured maximum Tx power (in dBm). """
        result = self.result
        return result.power.monitor.total.max.value.in_dBm()

    @property
    def tx_stdev(self):
        """ Gets the measured Tx power standard deviation (in dBm). """
        result = self.result
        return result.power.monitor.total.std_dev.value.in_dBm()


class Cmx500NrFr1Measurement(Cmx500TxMeasurementBase):
    """ Class for performing NR FR1 uplink power measurements. """

    def __init__(self, cell):
        """ Initialize a new 5G FR1 TX measurement.

        Args:
            cell: the CMX500 XLAPI cell to measure.
        """
        from xlapi import meas
        self._meas = meas.get_or_create_nr_fr1_rf_meas(cell)
        self.sample_count = DEFAULT_SAMPLE_COUNT

        # Enable only tx power measurement.
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        meas_config.disable_all()
        meas_config.tx_power.enabled = True

    def get_measurement(self):
        """ Gets the CMX500 measurement manager object. """
        return self._meas

    @property
    def sample_count(self):
        """ Gets the number of samples to use when running the test. """
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        return meas_config.tx_power.statistic_count

    @sample_count.setter
    def sample_count(self, sample_count):
        """ Sets the number of samples to use when running the test. """
        eval = self.get_multi_evaluation()
        meas_config = eval.meas_config
        meas_config.tx_power.statistic_count = sample_count

    @property
    def tx_average(self):
        """ Gets the measured average Tx power (in dBm). """
        result = self.result
        return result.tx_power.total.avg.value.in_dBm()

    @property
    def tx_min(self):
        """ Gets the measured minimum Tx power (in dBm). """
        result = self.result
        return result.tx_power.total.min.value.in_dBm()

    @property
    def tx_max(self):
        """ Gets the measured maximum Tx power (in dBm). """
        result = self.result
        return result.tx_power.total.max.value.in_dBm()

    @property
    def tx_stdev(self):
        """ Gets the measured Tx power standard deviation (in dBm). """
        result = self.result
        return result.tx_power.total.std_dev.value.in_dBm()
