import base64
import copy
import io
import struct
import sys
import unittest
import zlib
from unittest.mock import patch
from targetvisu.graphics import PNG_PREFIX, png_bytes, validate_graphic, placement, draw_graphic, _surface
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
