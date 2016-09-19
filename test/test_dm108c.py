#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest

from pycstbox.advanticsys.dm108c import DM108CInstrument


class DM108CTestCase(unittest.TestCase):
    def test_01(self):
        reg = DM108CInstrument.PULSE_CNT

        self.assertEquals(reg.decode(''.join((chr(i) for i in xrange(1, 7)))), 605040302.01)

    def test_02(self):
        reg = DM108CInstrument.PULSE_CNT

        self.assertEquals(reg.decode(''.join((chr(i) for i in [0] * 6))), 0)


if __name__ == '__main__':
    unittest.main()
