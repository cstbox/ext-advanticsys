#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import json
import os
import logging

from pycstbox.advanticsys.dm108 import DM108Instrument


class DM108MedataTestCase(unittest.TestCase):
    PATH = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "../lib/python/pycstbox/devcfg.d/modbus.d/advanticsys.dm108"
    ))

    def test_01(self):
        json.load(file(self.PATH))


class DM108TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dm108 = DM108Instrument('/dev/ttyUSB0', 1)
        cls.dm108.logger.setLevel(logging.DEBUG)
        # cls.dm108.debug = True

    def test_01(self):
        values = self.dm108.poll()
        self.assertEqual(len(values), 1)

    def test_02(self):
        self.assertTrue(self.dm108.is_coordinator)
        self.dm108.logger.info('config: %s', self.dm108.config)

        remote_dm108 = DM108Instrument('/dev/ttyUSB0', 2)
        self.assertFalse(remote_dm108.is_coordinator)
        self.dm108.logger.info('config: %s', remote_dm108.config)

    def test_03(self):
        self.assertTrue(self.dm108.is_coordinator and self.dm108.config.radio_id == 257)


if __name__ == '__main__':
    unittest.main()
