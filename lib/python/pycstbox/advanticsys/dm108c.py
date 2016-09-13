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
import binascii

from pycstbox.modbus import ModbusRegister
from dm108 import DM108Instrument

__author__ = 'Eric PASCUAL - CSTB (eric.pascual@cstb.fr)'


class DM108CInstrument(DM108Instrument):
    MODBUS_ID = ModbusRegister(DM108Instrument.ADDR_BASE + 4224)

    CONFIGURATION_REGISTERS = [MODBUS_ID]
    CONFIGURATION_REGISTER_MAP_SIZE = reduce(
        lambda accum, size: accum + size, [r.size for r in CONFIGURATION_REGISTERS]
    )

    class EM24INT32Reg(ModbusRegister):
        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for setting the register size and the signed option.
            """
            return ModbusRegister.__new__(cls, addr, size=2, signed=True, *args, **kwargs)

        def swap_words(self, bytes):
            return bytes[2:] + bytes[:2]

        @property
        def unpack_format(self):
            return '>' + super(DM108CInstrument.EM24INT32Reg, self).unpack_format

    class VoltageRegister(EM24INT32Reg):
        def decode(self, raw):
            return super(DM108CInstrument.VoltageRegister, self).decode(raw) / 10.

    class CurrentRegister(EM24INT32Reg):
        def decode(self, raw):
            return super(DM108CInstrument.CurrentRegister, self).decode(raw) / 1000.

    class PowerRegister(EM24INT32Reg):
        def decode(self, raw):
            return super(DM108CInstrument.PowerRegister, self).decode(raw) / 10.

    # class PatchedPowerRegister(EM24INT32Reg):
    #     def decode(self, raw):
    #         return super(DM108CInstrument.PatchedPowerRegister, self).decode(raw & 0xffff0000) / 10.

    class EM24INT16Register(ModbusRegister):
        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for setting the signed option. """
            return ModbusRegister.__new__(cls, addr, signed=True, *args, **kwargs)

        @property
        def unpack_format(self):
            return '>' + super(DM108CInstrument.EM24INT16Register, self).unpack_format

    class PowerFactorRegister(EM24INT16Register):
        def decode(self, raw):
            return raw / 1000.

    class FrequencyRegister(EM24INT16Register):
        def decode(self, raw):
            return raw / 10.

    class EnergyRegister(EM24INT32Reg):
        def decode(self, raw):
            return super(DM108CInstrument.EnergyRegister, self).decode(raw) / 10.

    class WaterVolumeRegister(ModbusRegister):
        """ AMB8568 version """
        scale = 100.

        def __new__(cls, addr, *args, **kwargs):
            """ Overridden __new__ for setting the size. """
            return ModbusRegister.__new__(cls, addr, size=3, *args, **kwargs)

        def decode(self, raw):
            """
            The three INT16 registers form a BCD number of 12 digits represented in Little Endian.
            i.e , if we have the register readings shown below:
            reg4483 = 0x0102;
            reg4484 = 0x0304;
            reg4485 = 0x0506;
            the raw BCD number (in little endian) is
            0 1 0 2 0 3 0 4 0 5 0 6,
            so in big endian the BCD real number would be:
            0 6 0 5 0 4 0 3 0 2 0 1.
            Converted to decimal, the number is 60504030201

            :param raw: the byte buffer with the concatenated register contents as they are read
            """
            return int(binascii.hexlify(raw[::-1])) / self.scale

        @property
        def unpack_format(self):
            # DM108C counter uses a special BCD format => no unpack
            return None

    V_L1_N = VoltageRegister(DM108Instrument.ADDR_BASE + 4353)
    A_L1 = CurrentRegister(DM108Instrument.ADDR_BASE + 4365)
    W_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4371)
    VA_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4377)
    VAR_L1 = PowerRegister(DM108Instrument.ADDR_BASE + 4383)
    PF_L1 = PowerFactorRegister(DM108Instrument.ADDR_BASE + 4403)
    FREQ = FrequencyRegister(DM108Instrument.ADDR_BASE + 4408)
    KWH = EnergyRegister(DM108Instrument.ADDR_BASE + 4423)
    KVARH = EnergyRegister(DM108Instrument.ADDR_BASE + 4437)

    PULSE_CNT = WaterVolumeRegister(DM108Instrument.ADDR_BASE + 4483)

    #: the compiled sequence of registers
    ALL_REGS = [V_L1_N, A_L1, W_L1, VA_L1, VAR_L1, PF_L1, FREQ, KWH, KVARH, PULSE_CNT]

    OutputValues = namedtuple(
        'OutputValues',
        ["V_L1_N", "A_L1", "W_L1", "VA_L1", "VAR_L1", "PF_L1", "FREQ", "kWh", "kVARh", "PULSE_CNT"]
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

            # reorder words before unpacking, since DM108C regs mix endianess
            # (low endian for words in a 32 bits register, and big endian for bytes inside a word)
            try:
                reg_data = reg.swap_words(reg_data)
            except AttributeError:
                # means that this register does not need this
                pass

            if reg.unpack_format:
                raw = struct.unpack(reg.unpack_format, reg_data)[0]
            else:
                raw = reg_data
            value = reg.decode(raw)
            values.append(value)

            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "... addr=%d data=0x%s raw=%s value=%f",
                    reg.addr, binascii.hexlify(reg_data), hex(raw), value
                )

            # wait a bit before next read
            time.sleep(self.PACE_DELAY)

        # build the final result
        values = self.OutputValues(*values)
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("==> %s", values)
        return values

