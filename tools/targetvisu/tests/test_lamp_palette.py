# SPDX-License-Identifier: GPL-3.0-only
"""The uploaded lamp sprite must render the same 12 states on GTK/Cairo."""
import struct
import sys
import unittest
from unittest.mock import patch

from targetvisu.graphics import png_bytes, _surface
from targetvisu.lamp_palette import SPRITE_URL, CELL_SIZE, lamp_state


class LampPaletteTests(unittest.TestCase):
    def test_embedded_sprite_has_twelve_33x33_states(self):
        raw = png_bytes(SPRITE_URL)
        width, height = struct.unpack('>II', raw[16:24])
        self.assertEqual((width, height), (CELL_SIZE * 12, CELL_SIZE))
        self.assertEqual([lamp_state(v) for v in (0, -1, 13, None, True, False, 1.5, '1')],
                         [0] * 8)
        self.assertEqual([lamp_state(i) for i in range(1, 13)], list(range(1, 13)))

    def test_cairo_renders_twelve_distinct_lamps_and_zero_is_invisible(self):
        try:
            import cairo
        except ImportError:
            try:
                import cairocffi as cairo
            except ImportError:
                self.skipTest('Cairo unavailable')
        from targetvisu.render import draw_indicator_lamp
        element = {'x': 5, 'y': 5, 'width': 66, 'height': 66}
        observed = []
        with patch.dict(sys.modules, {'cairo': cairo}):
            _surface.cache_clear()
            for state in range(13):
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 80, 80)
                ctx = cairo.Context(surface)
                ctx.set_source_rgb(0, 0, 0)
                ctx.paint()
                draw_indicator_lamp(ctx, element, state)
                surface.flush()
                data = surface.get_data()
                offset = 38 * surface.get_stride() + 38 * 4
                center = bytes(data[offset:offset + 4])
                if state == 0:
                    self.assertEqual(center, b'\x00\x00\x00\xff')
                else:
                    self.assertNotEqual(center, b'\x00\x00\x00\xff')
                    observed.append(center)
                if state == 12:
                    # The lamp scales uniformly and its corners remain transparent.
                    pixel = bytes(data[5 * surface.get_stride() + 5 * 4:
                                       5 * surface.get_stride() + 5 * 4 + 4])
                    self.assertEqual(pixel, b'\x00\x00\x00\xff')
            self.assertEqual(len(set(observed)), 12)
            _surface.cache_clear()
