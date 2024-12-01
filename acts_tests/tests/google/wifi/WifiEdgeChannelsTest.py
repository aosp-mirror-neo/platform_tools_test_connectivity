#!/usr/bin/env python3.4
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

from acts.controllers.ap_lib import hostapd_constants
import acts.signals as signals
import acts_contrib.test_utils.wifi.wifi_test_utils as wutils
from acts_contrib.test_utils.wifi.WifiBaseTest import WifiBaseTest


class WifiEdgeChannelsTest(WifiBaseTest):
  """Tests for Wifi Edge Channel Connection.

  Test Bed Requirement:
  * One Android devices and an AP.
  * 2GHz and 5GHz Wi-Fi network visible to the device.
  """

  def setup_class(self):
    super().setup_class()

    self.dut = self.android_devices[0]
    wutils.wifi_test_device_init(self.dut)
    wutils.wifi_toggle_state(self.dut, True)
    req_params = ["wifi6_models",]
    opt_param = ["reference_networks", "pixel_models"]
    self.unpack_userparams(req_param_names=req_params,
                           opt_param_names=opt_param)

  def setup_test(self):
    self.dut.droid.wakeLockAcquireBright()
    self.dut.droid.wakeUpNow()

  def teardown_test(self):
    super().teardown_test()
    self.dut.droid.wakeLockRelease()
    self.dut.droid.goToSleepNow()

  def configure_ap(self, channel_2g=None, channel_5g=None):
    """Configure and bring up AP on required channel.

    Args:
        channel_2g: The channel number to use for 2GHz network.
        channel_5g: The channel number to use for 5GHz network.

    """
    if not channel_2g:
      channel_2g = hostapd_constants.AP_DEFAULT_CHANNEL_2G
    if not channel_5g:
      channel_5g = hostapd_constants.AP_DEFAULT_CHANNEL_5G
    if "OpenWrtAP" in self.user_params:
      self.openwrt = self.access_points[0]
      self.configure_openwrt_ap_and_start(
          wpa_network=True,
          channel_2g=channel_2g,
          channel_5g=channel_5g)

  def verify_wifi_connection(self, channel_2g=None, channel_5g=None):
    """Verify wifi connection on given channel.
    Args:
        channel_2g: The channel number to use for 2GHz network.
        channel_5g: The channel number to use for 5GHz network.
    """
    self.configure_ap(channel_2g=channel_2g, channel_5g=channel_5g)
    if channel_2g:
      network = self.reference_networks[0]["2g"]
    elif channel_5g:
      network = self.reference_networks[0]["5g"]
    else :
      raise signals.TestError("No channel specified")

    wutils.connect_to_wifi_network(self.dut, network)
    wutils.verify_11ax_wifi_connection(self.dut, self.wifi6_models,
                                       "wifi6_ap" in self.user_params)
    self.dut.log.info("Current network = %s" %
                       self.dut.droid.wifiGetConnectionInfo())
    try:
      self.dut.ed.clear_all_events()
      wutils.wait_for_disconnect(self.dut, timeout=180)
    except:
      self.dut.log.info("Disconnection not happened (as expected)")
    else:
      self.dut.log.info("Unexpected disconnection happened")
      raise signals.TestFailure("Unexpected disconnection happened")

  def test_wifi_connect_edge_channel_64(self):
    """Test to connect 5G edge channel 64."""
    self.verify_wifi_connection(channel_5g=64)

  def test_wifi_connect_edge_channel_144(self):
    """Test to connect 5G edge channel 144."""
    self.verify_wifi_connection(channel_5g=144)
