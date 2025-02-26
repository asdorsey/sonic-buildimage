# sfputil.py
#
# Platform-specific SFP transceiver interface for SONiC
#

import time
import os
import sys
import subprocess
from ctypes import create_string_buffer

try:
    from sonic_platform_base.sonic_xcvr.sfp_optoe_base import SfpOptoeBase
    from sonic_platform_base.sonic_sfp.sff8436 import sff8436Dom
    from sonic_platform_base.sonic_sfp.sfputilhelper import SfpUtilHelper
    from .helper import APIHelper
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

# from xcvrd
SFP_STATUS_INSERTED = '1'
SFP_STATUS_REMOVED = '0'

QSFP_CHANNL_RX_LOS_STATUS_OFFSET = 3
QSFP_CHANNL_RX_LOS_STATUS_WIDTH = 1
QSFP_CHANNL_TX_FAULT_STATUS_OFFSET = 4
QSFP_CHANNL_TX_FAULT_STATUS_WIDTH = 1
QSFP_CONTROL_OFFSET = 86
QSFP_CONTROL_WIDTH = 8
QSFP_POWEROVERRIDE_OFFSET = 93


class Sfp(SfpOptoeBase):
    """Platform-specific Sfp class"""

    PORT_START = 1
    PORT_END = 32
    PORTS_IN_BLOCK = 32
    QSFP_PORT_START = 1
    QSFP_PORT_END = 32

    I2C_DEV_PATH = "/sys/bus/i2c/devices/"
    BASE_VAL_PATH = "/sys/class/i2c-adapter/i2c-{0}/{1}-0050/"
    BASE_OOM_PATH = "/sys/bus/i2c/devices/{0}-0050/"
    CPLD_ADDRESS = ['-0062', '-0064']

    # Path to sysfs
    PLATFORM_ROOT_PATH = "/usr/share/sonic/device"
    PMON_HWSKU_PATH = "/usr/share/sonic/hwsku"
    HOST_CHK_CMD = ["which", "systemctl"]
        
    PLATFORM = "x86_64-accton_as6712_64x-r0"
    HWSKU = "Accton-as6712-64X"

    _port_to_is_present = {}
    _port_to_lp_mode = {}

    _port_to_eeprom_mapping = {}
    _port_to_i2c_mapping = {
        1: [1, 2],
        2: [2, 3],
        3: [3, 4],
        4: [4, 5],
        5: [5, 6],
        6: [6, 7],
        7: [7, 8],
        8: [8, 9],
        9: [9, 10],
        10: [10, 11],
        11: [11, 12],
        12: [12, 13],
        13: [13, 14],
        14: [14, 15],
        15: [15, 16],
        16: [16, 17],
        17: [17, 18],
        18: [18, 19],
        19: [19, 20],
        20: [20, 21],
        21: [21, 22],
        22: [22, 23],
        23: [23, 24],
        24: [24, 25],
        25: [25, 26],
        26: [26, 27],
        27: [27, 28],
        28: [28, 29],
        29: [29, 30],
        30: [30, 31],
        31: [31, 32],
        32: [32, 33],
    }

    # @property
    # def port_start(self):
    #     return self.PORT_START

    # @property
    # def port_end(self):
    #     return self.PORT_END

    # @property
    # def qsfp_port_start(self):
    #     return self.QSFP_PORT_START

    # @property
    # def qsfp_port_end(self):
    #     return self.QSFP_PORT_END

    # @property
    # def qsfp_ports(self):
    #     return list(range(self.QSFP_PORT_START, self.PORTS_IN_BLOCK + 1))

    # @property
    # def port_to_eeprom_mapping(self):
    #     return self._port_to_eeprom_mapping

    def __init__(self, sfp_index=0):
        SfpOptoeBase.__init__(self)
        self._api_helper=APIHelper()
        # Init index
        self.index = sfp_index
        self.port_num = self.index + 1
        # Init eeprom path
        eeprom_path = self.BASE_OOM_PATH + "eeprom"
        self.port_to_eeprom_mapping = {}
        for x in range(self.PORT_START, self.PORT_END+1):
            self.port_to_eeprom_mapping[x] = eeprom_path.format(
                self._port_to_i2c_mapping[x][1]
            )

    def get_eeprom_path(self):
        return self.port_to_eeprom_mapping[self.port_num]

    def __is_host(self):
        return subprocess.call(self.HOST_CHK_CMD) == 0

    def __get_path_to_port_config_file(self):
        platform_path = "/".join([self.PLATFORM_ROOT_PATH, self.PLATFORM])
        hwsku_path = "/".join([platform_path, self.HWSKU]
                              ) if self.__is_host() else self.PMON_HWSKU_PATH
        return "/".join([hwsku_path, "port_config.ini"])

    def __read_eeprom_specific_bytes(self, offset, num_bytes):
        sysfsfile_eeprom = None
        eeprom_raw = []
        for i in range(0, num_bytes):
            eeprom_raw.append("0x00")

        sysfs_sfp_i2c_client_eeprom_path = self.port_to_eeprom_mapping[self.port_num]
        try:
            sysfsfile_eeprom = open(
                sysfs_sfp_i2c_client_eeprom_path, mode="rb", buffering=0)
            sysfsfile_eeprom.seek(offset)
            raw = sysfsfile_eeprom.read(num_bytes)
            if sys.version_info[0] >= 3:
                for n in range(0, num_bytes):
                    eeprom_raw[n] = hex(raw[n])[2:].zfill(2)
            else:
                for n in range(0, num_bytes):
                    eeprom_raw[n] = hex(ord(raw[n]))[2:].zfill(2)
        except Exception:
            pass
        finally:
            if sysfsfile_eeprom:
                sysfsfile_eeprom.close()

        return eeprom_raw

    def get_reset_status(self):
        """
        Retrieves the reset status of SFP
        Returns:
            A Boolean, True if reset enabled, False if disabled
        """
        reset_path="{}{}{}".format(self.get_cpld_dev_path() , "module_reset_" , str(self.port_num))
        val = self._api_helper.read_txt_file(reset_path)
        
        if val is not None:
            return int(val, 10) == 1
        else:
            return False

    def get_rx_los(self):
        """
        Retrieves the RX LOS (lost-of-signal) status of SFP
        Returns:
            A Boolean, True if SFP has RX LOS, False if not.
            Note : RX LOS status is latched until a call to get_rx_los or a reset.
        """

        rx_los_list = []
        dom_channel_monitor_raw = self.__read_eeprom_specific_bytes(
                QSFP_CHANNL_RX_LOS_STATUS_OFFSET, QSFP_CHANNL_RX_LOS_STATUS_WIDTH) if self.get_presence() else None
        if dom_channel_monitor_raw is not None:
                rx_los_data = int(dom_channel_monitor_raw[0], 16)
                rx_los_list.append(rx_los_data & 0x01 != 0)
                rx_los_list.append(rx_los_data & 0x02 != 0)
                rx_los_list.append(rx_los_data & 0x04 != 0)
                rx_los_list.append(rx_los_data & 0x08 != 0)
                return rx_los_list
        else:
            return [False]*4


    def get_tx_fault(self):
        """
        Retrieves the TX fault status of SFP
        Returns:
            A Boolean, True if SFP has TX fault, False if not
            Note : TX fault status is lached until a call to get_tx_fault or a reset.
        """
        tx_fault_list = []
        dom_channel_monitor_raw = self.__read_eeprom_specific_bytes(
                QSFP_CHANNL_TX_FAULT_STATUS_OFFSET, QSFP_CHANNL_TX_FAULT_STATUS_WIDTH) if self.get_presence() else None
        if dom_channel_monitor_raw is not None:
            tx_fault_data = int(dom_channel_monitor_raw[0], 16)
            tx_fault_list.append(tx_fault_data & 0x01 != 0)
            tx_fault_list.append(tx_fault_data & 0x02 != 0)
            tx_fault_list.append(tx_fault_data & 0x04 != 0)
            tx_fault_list.append(tx_fault_data & 0x08 != 0)
            return tx_fault_list
        else:
            return [False]*4

    def get_tx_disable(self):
        """
        Retrieves the tx_disable status of this SFP
        Returns:
            A Boolean, True if tx_disable is enabled, False if disabled
        """
        
        tx_disable_list = []
    
        sfpd_obj = sff8436Dom()
        if sfpd_obj is None:
            return False
    
        dom_control_raw = self.__read_eeprom_specific_bytes(
            QSFP_CONTROL_OFFSET, QSFP_CONTROL_WIDTH) if self.get_presence() else None
        if dom_control_raw is not None:
            dom_control_data = sfpd_obj.parse_control_bytes(dom_control_raw, 0)
            tx_disable_list.append(
                'On' == dom_control_data['data']['TX1Disable']['value'])
            tx_disable_list.append(
                'On' == dom_control_data['data']['TX2Disable']['value'])
            tx_disable_list.append(
                'On' == dom_control_data['data']['TX3Disable']['value'])
            tx_disable_list.append(
                'On' == dom_control_data['data']['TX4Disable']['value'])
            return tx_disable_list
        else:
            return [False]*4

    def get_tx_disable_channel(self):
        """
        Retrieves the TX disabled channels in this SFP
        Returns:
            A hex of 4 bits (bit 0 to bit 3 as channel 0 to channel 3) to represent
            TX channels which have been disabled in this SFP.
            As an example, a returned value of 0x5 indicates that channel 0
            and channel 2 have been disabled.
        """
        tx_disable_list = self.get_tx_disable()
        if tx_disable_list is None:
            return 0
        tx_disabled = 0
        for i in range(len(tx_disable_list)):
            if tx_disable_list[i]:
                tx_disabled |= 1 << i
        return tx_disabled

    def get_lpmode(self):
        """
        Retrieves the lpmode (low power mode) status of this SFP
        Returns:
            A Boolean, True if lpmode is enabled, False if disabled
        """

        power_set=self.get_power_set()
        power_override = self.get_power_override()
        return power_set and power_override

    def get_power_set(self):
        power_set = False
        sfpd_obj = sff8436Dom()
        if sfpd_obj is None:
            return False
        dom_control_raw = self.__read_eeprom_specific_bytes(
            QSFP_CONTROL_OFFSET, QSFP_CONTROL_WIDTH) if self.get_presence() else None
        if dom_control_raw is not None:
            dom_control_data = sfpd_obj.parse_control_bytes(dom_control_raw, 0)
            power_set = (
                'On' == dom_control_data['data']['PowerSet']['value'])
    
        return power_set

    def get_power_override(self):
        """
        Retrieves the power-override status of this SFP
        Returns:
            A Boolean, True if power-override is enabled, False if disabled
        """
        power_override = False
        sfpd_obj = sff8436Dom()
        if sfpd_obj is None:
            return False

        dom_control_raw = self.__read_eeprom_specific_bytes(
                QSFP_CONTROL_OFFSET, QSFP_CONTROL_WIDTH) if self.get_presence() else None
        if dom_control_raw is not None:
            dom_control_data = sfpd_obj.parse_control_bytes(dom_control_raw, 0)
            power_override = (
                'On' == dom_control_data['data']['PowerOverride']['value'])

        return power_override

    def reset(self):
        """
        Reset SFP and return all user module settings to their default srate.
        Returns:
            A boolean, True if successful, False if not
        """
        reset_path = "{}{}{}".format(self.get_cpld_dev_path() , 'module_reset_' , self.port_num)
        ret = self._api_helper.write_txt_file(reset_path, 1)
        if ret is not True:
            return ret

        time.sleep(0.01)
        ret = self._api_helper.write_txt_file(reset_path, 0)
        time.sleep(0.2)

        return ret

    def tx_disable(self, tx_disable):
        """
        Disable SFP TX for all channels
        Args:
            tx_disable : A Boolean, True to enable tx_disable mode, False to disable
                         tx_disable mode.
        Returns:
            A boolean, True if tx_disable is set successfully, False if not
        """
        if not self.get_presence():
            return False
        sysfsfile_eeprom = None
        try:
            tx_disable_ctl = 0xf if tx_disable else 0x0
            buffer = create_string_buffer(1)
            if sys.version_info[0] >= 3:
                buffer[0] = tx_disable_ctl
            else:
                buffer[0] = chr(tx_disable_ctl)
            # Write to eeprom
            sysfsfile_eeprom = open(
                self.port_to_eeprom_mapping[self.port_num], "r+b")
            sysfsfile_eeprom.seek(QSFP_CONTROL_OFFSET)
            sysfsfile_eeprom.write(buffer[0])
        except IOError as e:
            print ('Error: unable to open file: ',str(e))
            return False
        finally:
            if sysfsfile_eeprom is not None:
                sysfsfile_eeprom.close()
                time.sleep(0.01)
        
        return True

    def tx_disable_channel(self, channel, disable):
        """
        Sets the tx_disable for specified SFP channels
        Args:
            channel : A hex of 4 bits (bit 0 to bit 3) which represent channel 0 to 3,
                      e.g. 0x5 for channel 0 and channel 2.
            disable : A boolean, True to disable TX channels specified in channel,
                      False to enable
        Returns:
            A boolean, True if successful, False if not
        """        
        if not self.get_presence():
            return False

        sysfsfile_eeprom = None
        try:
            channel_state = self.get_tx_disable_channel()
            for i in range(4):
                channel_mask = (1 << i)
                if not (channel & channel_mask):
                    continue

                if disable:
                    channel_state |= channel_mask
                else:
                    channel_state &= ~channel_mask

            buffer = create_string_buffer(1)
            if sys.version_info[0] >= 3:
                buffer[0] = channel_state
            else:
                buffer[0] = chr(channel_state)
            # Write to eeprom
            sysfsfile_eeprom = open(
                self.port_to_eeprom_mapping[self.port_num], "r+b")
            sysfsfile_eeprom.seek(QSFP_CONTROL_OFFSET)
            sysfsfile_eeprom.write(buffer[0])
        except IOError as e:
            print ('Error: unable to open file: ', str(e))
            return False
        finally:
            if sysfsfile_eeprom is not None:
                sysfsfile_eeprom.close()
                time.sleep(0.01)

        return True

    def set_lpmode(self, lpmode):
        """
        Sets the lpmode (low power mode) of SFP
        Args:
            lpmode: A Boolean, True to enable lpmode, False to disable it
            Note  : lpmode can be overridden by set_power_override
        Returns:
            A boolean, True if lpmode is set successfully, False if not
        """        
        if lpmode:
            self.set_power_override(True, True)
        else:
            self.set_power_override(False, False)
    
        return True
       
    def set_power_override(self, power_override, power_set):
        """
        Sets SFP power level using power_override and power_set
        Args:
            power_override :
                    A Boolean, True to override set_lpmode and use power_set
                    to control SFP power, False to disable SFP power control
                    through power_override/power_set and use set_lpmode
                    to control SFP power.
            power_set :
                    Only valid when power_override is True.
                    A Boolean, True to set SFP to low power mode, False to set
                    SFP to high power mode.
        Returns:
            A boolean, True if power-override and power_set are set successfully,
            False if not
        """
       
        if not self.get_presence():
            return False
        try:
            power_override_bit = (1 << 0) if power_override else 0
            power_set_bit      = (1 << 1) if power_set else (1 << 3)
    
            buffer = create_string_buffer(1)
            if sys.version_info[0] >= 3:
                buffer[0] = (power_override_bit | power_set_bit)
            else:
                buffer[0] = chr(power_override_bit | power_set_bit)
            # Write to eeprom
            with open(self.port_to_eeprom_mapping[self.port_num], "r+b") as fd:
                fd.seek(QSFP_POWEROVERRIDE_OFFSET)
                fd.write(buffer[0])
                time.sleep(0.01)
        except Exception:
            print ('Error: unable to open file: ', str(e))
            return False

        return True

    def get_name(self):
        """
        Retrieves the name of the device
            Returns:
            string: The name of the device
        """
        sfputil_helper = SfpUtilHelper()
        sfputil_helper.read_porttab_mappings(
            self.__get_path_to_port_config_file())
        name = sfputil_helper.logical[self.index] or "Unknown"
        return name

    def get_presence(self):
        """
        Retrieves the presence of the device
        Returns:
            bool: True if device is present, False if not
        """
        present_path = "{}{}{}".format(self.get_cpld_dev_path() , '/module_present_' , self.port_num)
        val=self._api_helper.read_txt_file(present_path)
        if val is not None:
            return int(val, 10)==1
        else:
            return False

    def get_status(self):
        """
        Retrieves the operational status of the device
        Returns:
            A boolean value, True if device is operating properly, False if not
        """
        return self.get_presence()

    def get_position_in_parent(self):
        """
        Retrieves 1-based relative physical position in parent device. If the agent cannot determine the parent-relative position
        for some reason, or if the associated value of entPhysicalContainedIn is '0', then the value '-1' is returned
        Returns:
            integer: The 1-based relative physical position in parent device or -1 if cannot determine the position
        """
        return self.port_num

    def is_replaceable(self):
        """
        Indicate whether this device is replaceable.
        Returns:
            bool: True if it is replaceable.
        """
        return True

    def get_cpld_dev_path(self):
        if self.port_num <= 16:
            cpld_num = 0
        else:
            cpld_num = 1

        # cpld can be at either bus 0 or bus 1.
        cpld_path = self.I2C_DEV_PATH + str(0) + self.CPLD_ADDRESS[cpld_num]
        if not os.path.exists(cpld_path):
            cpld_path = self.I2C_DEV_PATH + str(1) + self.CPLD_ADDRESS[cpld_num]
        return cpld_path
