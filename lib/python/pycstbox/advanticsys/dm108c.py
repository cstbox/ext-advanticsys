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

""" DM108C (Collector version) Modbus gateway.

This version is an extension of the standard DM108 developed by ADV for
the WISDOM project. It collects (hence the suffix) the registers of interest
from a Carlo Gavazzi EM24 energy meter and a wireless pulse counter, and
presents them as an extension of its own register map.
"""

import struct
from collections import namedtuple
import logging
import time

from pycstbox.modbus import ModbusRegister
from dm108 import DM108Instrument

__author__ = 'Eric PASCUAL - CSTB (eric.pascual@cstb.fr)'


class DM108CInstrument(DM108Instrument):
    MODBUS_ID = ModbusRegister(DM108Instrument.ADDR_BASE + 4224)

    class EM24_INT32Reg(ModbusRegister):
        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for fixing the register size and
            forcing unsigned values since 2's complement is used here.
            """
            return ModbusRegister.__new__(cls, addr, size=2, signed=False, *args, **kwargs)

        @staticmethod
        def decode(raw):
            # swap the words and apply the 2's complement if negative value
            # BTW discard the signed since negative values have no real meaning
            raw = ((raw >> 16) & 0xffff) | ((raw & 0xffff) << 16)
            return abs(raw - 0x100000000) if raw & 0x80000000 else raw

    class VoltageRegister(EM24_INT32Reg):
        @staticmethod
        def decode(raw):
            return DM108CInstrument.EM24_INT32Reg.decode(raw) / 10.

    class CurrentRegister(EM24_INT32Reg):
        @staticmethod
        def decode(raw):
            return DM108CInstrument.EM24_INT32Reg.decode(raw) / 1000.

    class PowerRegister(EM24_INT32Reg):
        @staticmethod
        def decode(raw):
            return DM108CInstrument.EM24_INT32Reg.decode(raw) / 10.

    class PowerFactorRegister(ModbusRegister):
        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for fixing the register size. """
            return ModbusRegister.__new__(cls, addr, *args, **kwargs)

        @staticmethod
        def decode(raw):
            return raw / 1000.

    class FrequencyRegister(ModbusRegister):
        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for fixing the register size. """
            return ModbusRegister.__new__(cls, addr, *args, **kwargs)

        @staticmethod
        def decode(raw):
            return raw / 10.    # TODO to be checked since it was wrong for EM21

    class EnergyRegister(EM24_INT32Reg):
        @staticmethod
        def decode(raw):
            return DM108CInstrument.EM24_INT32Reg.decode(raw) / 10.

    V_L1_N = VoltageRegister(DM108Instrument.ADDR_BASE + 4353)
    A_L1 = CurrentRegister(DM108Instrument.ADDR_BASE + 4365)
    W_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4371)
    VA_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4377)
    VAR_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4383)
    PF_L1 = PowerFactorRegister(DM108Instrument.ADDR_BASE + 4403)
    FREQ = FrequencyRegister(DM108Instrument.ADDR_BASE + 4408)
    KWH = EnergyRegister(DM108Instrument.ADDR_BASE + 4423)
    KVARH = EnergyRegister(DM108Instrument.ADDR_BASE + 4437)

    PULSE_CNT = ModbusRegister(DM108Instrument.ADDR_BASE + 4466, size=2)

    #: the compiled sequence of registers
    ALL_REGS = [V_L1_N, A_L1, W_L1, VA_L1, VAR_L1, PF_L1, FREQ, KWH, KVARH, PULSE_CNT]

    OutputValues = namedtuple(
        'OutputValues',
        ["V_L1_N", "A_L1", "W_L1", "VA_L1", "VAR_L1", "PF_L1", "FREQ", "KWH", "KVARH", "PULSE_CNT"]
    )

    class Configuration(object):
        is_coordinator = True

        def __init__(self, data, logger):
            _, self.modbus_id = struct.unpack('>BB', data)

        def __str__(self):
            return "Configuration(modbus_id=%d)" % self.modbus_id

    #: delay between two successive register readings
    PACE_DELAY = 1

    def poll(self):
        """ Reads all the measurement registers and the values as a named tuple.

        Since the registers are spread over the map, we cannot read them by packet
        and have to issue one request per register. This will have severe impacts
        on performances.

        :rtype: OutputValues
        """
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("polling %s(%d)", self.__class__.__name__, self.unit_id)

        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("reading registers")

        values = []
        # read all the registers, one at a time
        for reg in self.ALL_REGS:
            reg_data = self._read_registers(reg.addr, reg.size)
            if not reg_data:
                return None

            raw = struct.unpack(reg.unpack_format, reg_data)[0]
            value = reg.decode(raw)
            values.append(value)

            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug("... addr=%d raw=%s value=%f", reg.addr, hex(raw), value)

            # wait a bit before next read
            time.sleep(self.PACE_DELAY)

        # build the final result
        values = self.OutputValues(*values)
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("==> %s", values)
        return values

