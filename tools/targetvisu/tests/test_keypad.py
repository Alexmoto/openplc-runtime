# SPDX-License-Identifier: GPL-3.0-only
"""Touch keypad behavior without requiring GTK/X11 on the CI runner."""
import unittest
from targetvisu.keypad import press, parse, initial_text
from targetvisu.tests.test_targetvisu import fixture


class KeypadTests(unittest.TestCase):
    def test_digits_decimal_sign_backspace_and_clear(self):
        s = '0'
        for key in ('2', '5', '.', '5'):
            s = press(s, key, True)
        self.assertEqual(s, '25.5')
        self.assertEqual(press(s, '.', True), s)
        self.assertEqual(press(s, '±', True), '-25.5')
        self.assertEqual(press('-25.5', '⌫', True), '-25.')
        self.assertEqual(press('-25.5', 'C', True), '0')
        self.assertEqual(press('0', '.', False), '0')
        self.assertEqual(press('0', '±', False), '-0')
        self.assertEqual(press('-0', '3', False), '-3')
        self.assertEqual(press('123', '⌫', False), '12')
        self.assertEqual(press('-', '⌫', False), '0')
        self.assertEqual(press('0', 'x', False), '0')
        self.assertEqual(press('9' * 24, '1', False), '9' * 24)

    def test_real_and_integer_range_uses_exact_iec_encoder(self):
        model = fixture()
        real = lambda value: model.encode('Pump1.Setpoint', value)
        self.assertEqual(parse('25.5', 'REAL', 0, 100, real), 25.5)
        self.assertEqual(parse('0', 'REAL', 0, 100, real), 0.0)
        for invalid in ('nan', 'inf', '1e3', '-', '25,5', '', '101', '-1', '3.4.5'):
            with self.assertRaises(ValueError, msg=invalid):
                parse(invalid, 'REAL', 0, 100, real)
        self.assertEqual(initial_text(12.5, 'REAL', 2), '12.50')
        self.assertEqual(initial_text(17, 'DINT', 0), '17')
        self.assertEqual(initial_text(None, 'REAL', 1), '0')
        with self.assertRaises(ValueError):
            parse('2.2', 'DINT', -10, 10, lambda value: model.encode('Pump1.Setpoint', value))
        with self.assertRaises(ValueError):
            parse('1', 'BOOL', 0, 1, lambda value: None)

    def test_wide_integer_precision_and_limits(self):
        model = fixture()
        leaf = model.leaf('Pump1.Setpoint')
        leaf.update(type='LINT', size=8)
        encode = lambda value: model.encode('Pump1.Setpoint', value)
        value = 9223372036854775807
        self.assertEqual(parse(str(value), 'LINT', 0, value, encode), value)
        with self.assertRaises(ValueError):
            parse(str(value+1), 'LINT', 0, value+1, encode)
        self.assertEqual(parse('0', 'LINT', 0, 1, encode), 0)
