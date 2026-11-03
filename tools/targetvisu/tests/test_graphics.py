import base64
import copy
import io
import struct
import sys
import unittest
import zlib
from unittest.mock import patch
from targetvisu.graphics import PNG_PREFIX, png_bytes, validate_graphic, placement, draw_graphic, select_graphic_data, _surface
from targetvisu.model import Model
from targetvisu.tests.test_targetvisu import fixture


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    # Two pixels: opaque red, transparent green.
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,6,0,0,0)) + chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\xff\x00\xff\x00\x00')) + chunk(b'IEND',b'')


def data_url():
    return PNG_PREFIX + base64.b64encode(png()).decode()


class GraphicTests(unittest.TestCase):
    def test_invalid_resources_and_dimensions(self):
        raw = bytearray(png());raw[16:20] = struct.pack('>I', 1025)
        for value in ['file:///tmp/image.png','https://example.com/a.png','data:image/svg+xml,<svg/>',PNG_PREFIX+'!!!!',PNG_PREFIX+base64.b64encode(raw).decode()]:
            with self.assertRaises(ValueError): png_bytes(value)
        self.assertEqual(png_bytes(data_url()),png())
        with self.assertRaises(ValueError):validate_graphic(dict(data=data_url(),fit='invalid'))

    def test_model_and_no_write_permission(self):
        original=fixture();doc=copy.deepcopy(original.doc)
        e=doc['screens'][0]['elements'][0]
        e.update(kind='graphic',graphic=dict(data=data_url(),fit='contain'),bindings=dict(value='',visible='',enabled=''),action=dict(kind='none',target='',value=True))
        model=Model(doc,dict(version=2,md5=original.md5,leaves=list(original.leaves.values())))
        self.assertEqual(model.elements[e['id']]['graphic']['data'],data_url())
        del e['graphic']
        with self.assertRaises(ValueError):Model(doc,dict(version=2,md5=original.md5,leaves=list(original.leaves.values())))

    def test_image_state_selector_and_backwards_compatibility(self):
        default = data_url()
        image = {'data': default, 'fit': 'contain',
                 'variants': [{'value': 0, 'data': default},
                              {'value': 1, 'data': default}]}
        validate_graphic(image)
        self.assertEqual(select_graphic_data(image, 0, True), image['variants'][0]['data'])
        self.assertEqual(select_graphic_data(image, True, True), image['variants'][1]['data'])
        self.assertEqual(select_graphic_data(image, 9, True), default)
        self.assertEqual(select_graphic_data(image, None, True), default)
        no_default = dict(image, data='')
        validate_graphic(no_default)
        self.assertEqual(select_graphic_data(no_default, 9, True), '')
        self.assertEqual(select_graphic_data(no_default, None, False), image['variants'][0]['data'])
        for invalid in [
            dict(image, variants=[image['variants'][0], image['variants'][0]]),
            dict(image, variants=[dict(value=True, data=default)]),
            dict(image, variants=[dict(value=1, data='file:///etc/passwd')]),
            dict(image, variants=[dict(value=4294967296, data=default)]),
            dict(image, variants=[dict(value=1, data=default, url='http://bad')]),
            dict(image, variants=[dict(value=i, data=default) for i in range(17)]),
        ]:
            with self.assertRaises(ValueError):
                validate_graphic(invalid)
        validate_graphic({'data': default, 'fit': 'contain'})  # legacy project

    def test_graphic_selector_binding_validation(self):
        original = fixture()
        data = dict(version=2, md5=original.md5, leaves=list(original.leaves.values()))
        doc = copy.deepcopy(original.doc)
        e = doc['screens'][0]['elements'][0]
        e.update(kind='graphic',
                 graphic={'data': data_url(), 'fit': 'contain',
                          'variants': [{'value': 1, 'data': data_url()}]},
                 bindings={'value': 'Pump1.Running', 'visible': '', 'enabled': ''},
                 action={'kind': 'none', 'target': '', 'value': True})
        Model(doc, data)
        e['bindings']['value'] = 'Pump1.Pressure'
        with self.assertRaisesRegex(ValueError, 'image selector'):
            Model(doc, data)

    def test_screen_background_image_validation_and_rendering(self):
        from targetvisu.render import draw as draw_screen
        original = fixture()
        doc = copy.deepcopy(original.doc)
        debug_map = dict(version=2, md5=original.md5, leaves=list(original.leaves.values()))
        screen = doc['screens'][0]
        # Legacy screens without an image remain valid.
        Model(doc, debug_map)
        screen['backgroundGraphic'] = {'data': data_url(), 'fit': 'stretch'}
        model = Model(doc, debug_map)
        self.assertEqual(model.doc['screens'][0]['backgroundGraphic']['fit'], 'stretch')
        for bad in [
            {'data': 'file:///tmp/bg.png', 'fit': 'cover'},
            {'data': data_url(), 'fit': 'other'},
            {'data': data_url(), 'fit': 'cover', 'variants': []},
            {'data': '', 'fit': 'cover'},
        ]:
            screen['backgroundGraphic'] = bad
            with self.assertRaises(ValueError):
                Model(doc, debug_map)
        screen['backgroundGraphic'] = {'data': data_url(), 'fit': 'stretch'}
        screen['elements'] = []
        try:
            import cairo
        except ImportError:
            try: import cairocffi as cairo
            except ImportError: self.skipTest('Cairo unavailable')
        with patch.dict(sys.modules, {'cairo': cairo}):
            _surface.cache_clear()
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 160, 120)
            ctx = cairo.Context(surface)
            screen['width'], screen['height'] = 160, 120
            screen['background'] = '#0000ff'
            draw_screen(ctx, model, screen, {}, True, 160, 120)
            surface.flush()
            pixels = bytes(surface.get_data())
            stride = surface.get_stride()
            def pixel(x, y):
                i = y * stride + x * 4
                return pixels[i:i+4]  # BGRA on little-endian CI hosts
            red = pixel(20, 60)
            blue = pixel(140, 60)
            self.assertGreater(red[2], 190)   # opaque red PNG on the left
            self.assertLess(red[0], 80)
            self.assertGreater(blue[0], 190)  # transparent PNG on the right keeps blue fill
            _surface.cache_clear()

    def test_transparent_button_keeps_background_visible_and_border_optional(self):
        from targetvisu.render import draw
        original = fixture()
        doc = copy.deepcopy(original.doc)
        screen = doc['screens'][0]
        e = next(e for e in screen['elements'] if e['kind'] == 'button')
        screen['elements'] = [e]
        screen['background'] = '#00ff00'
        e['text'] = ''  # Avoid native Pango dependency when testing Cairo colors.
        e['strokeWidth'] = 8
        e['fillTransparent'] = True
        e['strokeTransparent'] = True
        model = Model(doc, dict(version=2, md5=original.md5, leaves=list(original.leaves.values())))
        try:
            import cairo
        except ImportError:
            try: import cairocffi as cairo
            except ImportError: self.skipTest('Cairo unavailable')
        with patch.dict(sys.modules, {'cairo': cairo}):
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, screen['width'], screen['height'])
            ctx = cairo.Context(surface)
            draw(ctx, model, screen, {}, True, screen['width'], screen['height'])
            surface.flush()
            x, y = e['x'] + 1, e['y'] + e['height'] // 2
            def pixel(image, x, y):
                data = image.get_data()
                pos = y * image.get_stride() + x * 4
                return bytes(data[pos:pos + 4])
            self.assertEqual(pixel(surface, x, y), b'\\x00\\xff\\x00\\xff')
            self.assertEqual(pixel(surface, e['x'] + e['width']//2, y), b'\\x00\\xff\\x00\\xff')
            e['strokeTransparent'] = False
            surface2 = cairo.ImageSurface(cairo.FORMAT_ARGB32, screen['width'], screen['height'])
            draw(cairo.Context(surface2), model, screen, {}, True, screen['width'], screen['height'])
            surface2.flush()
            self.assertNotEqual(pixel(surface2, x, y), b'\\x00\\xff\\x00\\xff')

    def test_placement(self):
        self.assertEqual(placement(200,100,100,100,'contain'),(0,25,0.5,0.5))
        self.assertEqual(placement(200,100,100,100,'cover'),(-50,0,1,1))
        self.assertEqual(placement(200,100,100,100,'stretch'),(0,0,0.5,1))

    def test_cairo_transparency_and_cache(self):
        try:
            import cairo
        except ImportError:
            try: import cairocffi as cairo
            except ImportError: self.skipTest('Cairo unavailable')
        with patch.dict(sys.modules, {'cairo':cairo}):
            _surface.cache_clear()
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
            ctx=cairo.Context(surface);ctx.set_source_rgb(0,0,1);ctx.paint()
            e=dict(x=0,y=0,width=8,height=8,graphic=dict(data=data_url(),fit='contain'))
            draw_graphic(ctx,e);draw_graphic(ctx,e)
            self.assertEqual(_surface.cache_info().misses,1)
            self.assertEqual(_surface.cache_info().hits,1)
            surface.flush();pixels=bytes(surface.get_data());stride=surface.get_stride()
            # Top padding remains blue; image has opaque red pixels and alpha reveals blue.
            self.assertEqual(pixels[:4],b'\xff\x00\x00\xff')
            self.assertGreater(pixels[4*stride+1*4+2],200)
            self.assertGreater(pixels[4*stride+7*4],200)
            _surface.cache_clear()

if __name__=='__main__':unittest.main()
