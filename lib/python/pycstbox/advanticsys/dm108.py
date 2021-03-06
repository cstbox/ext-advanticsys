# -*- coding: utf-8 -*-

# This file is part of CSTBox.
#
# CSTBox is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CSTBox is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with CSTBox.  If not, see <http://www.gnu.org/licenses/>.

""" AdvanticSys wireless Modbus gateway.

This modules defines a sub-class of minimalmodbus.Instrument which polls the
parameters of interest.

It also defines the input registers so that more specific needs can be
implemented by sub-classing and overriding, or direct Modbus register read.

Depends on Jonas Berg's minimalmodbus Python library :
    https://pypi.python.org/pypi/MinimalModbus/
    Version in date of writing: 0.4
"""

import struct
from collections import namedtuple
import logging

from pycstbox.modbus import ModbusRegister, RTUModbusHWDevice
from pycstbox.hal import HalError

__author__ = 'Eric PASCUAL - CSTB (eric.pascual@cstb.fr)'


class DM108Instrument(RTUModbusHWDevice):
    """ minimalmodbus.Instrument sub-class modeling the Carlo Gavazzi EM21
    3-phased energy meter.

    The supported model is the RTU RS485 one, the RS485 bus being connected
    via a USB.RS485 interface.
    """

    DEFAULT_BAUDRATE = 19200

    ADDR_BASE = 0

    PULSE_CNT = ModbusRegister(ADDR_BASE + 4096, size=2)

    GROUP_AND_CHANNEL = ModbusRegister(ADDR_BASE + 4224)
    ID_AND_ROLL_NODE = ModbusRegister(ADDR_BASE + 4225)
    UART_CONFIG = ModbusRegister(ADDR_BASE + 4226)
    RADIO_ID = ModbusRegister(ADDR_BASE + 4227)
    ACK_AND_AES = ModbusRegister(ADDR_BASE + 4228)
    RADIO_POWER = ModbusRegister(ADDR_BASE + 4229)
    RETRIES = ModbusRegister(ADDR_BASE + 4230)
    RESERVED = ModbusRegister(ADDR_BASE + 4231)
    TIMEOUT = ModbusRegister(ADDR_BASE + 4232)

    CONFIGURATION_REGISTERS = [
        GROUP_AND_CHANNEL, ID_AND_ROLL_NODE, UART_CONFIG, RADIO_ID, ACK_AND_AES,
        RADIO_POWER, RETRIES, RESERVED, TIMEOUT
    ]
    CONFIGURATION_REGISTER_MAP_SIZE = reduce(
        lambda accum, size: accum + size, [r.size for r in CONFIGURATION_REGISTERS]
    )

    #: the compiled sequence of registers
    ALL_REGS = [PULSE_CNT]

    _TOTAL_REG_SIZE = reduce(lambda accum, size: accum + size, [r.size for r in ALL_REGS])

    class Configuration(object):
        _dbm = {
            3: -2,
            23: 7.5,
            29: 12.5,
            38: 18,
            55: 22,
            80: 25,
            134: 26
        }
        _bauds = (2400, 4800, 9600, 19200)
        _parity = ('N', 'O', 'E')

        def __init__(self, data, logger):
            self.group_id, self.radio_channel, self.modbus_id, roll_node, _, uart_config, \
            self.radio_id, self.act_enabled, self.aes_enabled, radio_power, _, _, \
            self.retries, _, self.timeout = \
                struct.unpack('>BBBBBBHBBBBBBHH', data)
            try:
                self.radio_power = self._dbm[radio_power]
            except KeyError:
                logger.error("unexpected radio power register content (%s)", radio_power)
                self.radio_power = 0
            self.is_coordinator = bool(roll_node)
            self.uart_config = (
                self._bauds[(uart_config & 0xc0) >> 6],
                self._parity[(uart_config & 0x30) >> 4],
                ((uart_config & 0x08) >> 3) + 1,
                ((uart_config & 0x03) >> 2) + 7
            )

        def __str__(self):
            return "Configuration(group_id=%s, radio_channel=%d, modbus_id=%d, uart_config=%s, radio_id=%d, " \
                   "act_enabled=%d, aes_enabled=%d, radio_power=%ddBm, retries=%d, timeout=%d)" % (
                self.group_id, self.radio_channel, self.modbus_id, self.uart_config, self.radio_id,
                self.act_enabled, self.aes_enabled, self.radio_power, self.retries, self.timeout
            )

    #: Definition of the type of the poll() method result
    #: .. warning::
    #:      the field sequence MUST be synchronized with the register sequence as defined in `ALL_REGS`
    OutputValues = namedtuple('OutputValues', ["PULSE_CNT"])

    def __init__(self, port, unit_id, baudrate=DEFAULT_BAUDRATE):
        """
        :param str port: serial port on which the RS485 interface is connected
        :param int unit_id: the address of the device
        :param int baudrate: the serial communication baudrate
        """
        super(DM108Instrument, self).__init__(port=port, unit_id=int(unit_id), baudrate=baudrate, logname='dm108')

        # check that unit id matches
        self._logger.info('getting unit configuration...')
        try:
            self._config = self.Configuration(
                self.read_string(self.CONFIGURATION_REGISTERS[0].addr, self.CONFIGURATION_REGISTER_MAP_SIZE),
                self._logger
            )
            self._logger.info('... %s', self._config)

            if self._config.modbus_id != self.unit_id:
                raise HalError(
                    "Modbus id stored in config regs does not match (expecting '%d', got '%d')" %
                    (self.unit_id, self._config.modbus_id)
                )

            self._logger.info('DM108 id=%s role: %s', self.unit_id, 'coordinator' if self.is_coordinator else 'endpoint')
        except IOError as e:
            raise HalError(e.message)

    def poll(self):
        """ Reads all the measurement registers and the values as a named tuple.

        :rtype: OutputValues
        """
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("polling %s(%d)", self.__class__.__name__, self.unit_id)

        # read all the registers
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("reading registers")

        data = self._read_registers(self.ALL_REGS[0].addr, self._TOTAL_REG_SIZE)
        if not data:
            return None

        raw_values = struct.unpack('>i', data)

        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("... raw: %s", ' '.join(hex(r) for r in raw_values))

        # decode the raw values
        values = self.OutputValues(*[r.decode(v) for v, r in zip(raw_values, self.ALL_REGS)])
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("==> %s", values)
        return values

    @property
    def is_coordinator(self):
        return self._config.is_coordinator

    @property
    def config(self):
        """ Returns the configuration as stored in the device.

        :rtype: :py:class:`DM108Instrument.Configuration`
        """
        return self._config
