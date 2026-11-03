# SPDX-License-Identifier: GPL-3.0-only
"""Bounded embedded PNG graphics; no file paths or network resources."""
import base64
import binascii
from functools import lru_cache
import io
import logging
import struct

PNG_PREFIX = 'data:image/png;base64,'
MAX_BYTES = 1024 * 1024
MAX_SIDE = 1024


def png_bytes(data):
    if not isinstance(data, str) or not data.startswith(PNG_PREFIX) or len(data) > len(PNG_PREFIX) + 4 * ((MAX_BYTES + 2) // 3):
        raise ValueError('Expected embedded PNG up to 1 MiB')
    try:
        raw = base64.b64decode(data[len(PNG_PREFIX):], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('Invalid PNG base64') from exc
    if len(raw) < 33 or len(raw) > MAX_BYTES or raw[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
        raise ValueError('Invalid PNG header')
    width, height = struct.unpack('>II', raw[16:24])
    if not 1 <= width <= MAX_SIDE or not 1 <= height <= MAX_SIDE:
        raise ValueError('PNG dimensions exceed 1024 x 1024')
    return raw


def validate_graphic(graphic):
    if not isinstance(graphic, dict) or not {'data', 'fit'} <= set(graphic) or not set(graphic) <= {'data', 'fit', 'variants'}:
        raise ValueError('Invalid graphic properties')
    if graphic['fit'] not in ('contain', 'cover', 'stretch'):
        raise ValueError('Invalid graphic scaling mode')
    default = graphic['data']
    if not isinstance(default, str):
        raise ValueError('Invalid default image')
    if default:
        png_bytes(default)
    variants = graphic.get('variants', [])
    if not isinstance(variants, list) or len(variants) > 16:
        raise ValueError('Invalid image states')
    used = set()
    for variant in variants:
        if not isinstance(variant, dict) or set(variant) != {'value', 'data'}:
            raise ValueError('Invalid image state')
        value = variant['value']
        if type(value) is not int or not -2147483648 <= value <= 4294967295 or value in used:
            raise ValueError('Duplicate or invalid image state value')
        used.add(value)
        png_bytes(variant['data'])
    if not default and not variants:
        raise ValueError('Graphic image is missing')


def select_graphic_data(graphic, selector=None, has_binding=False):
    """Use an exact BOOL/integer state, otherwise the optional fallback PNG."""
    if not has_binding:
        return graphic['data'] or next((v['data'] for v in graphic.get('variants', [])), '')
    if type(selector) is bool:
        selector = int(selector)
    if type(selector) is int:
        for variant in graphic.get('variants', []):
            if variant['value'] == selector:
                return variant['data']
    return graphic['data']


def placement(iw, ih, w, h, fit):
    if fit == 'stretch':
        return 0, 0, w / iw, h / ih
    scale = (max if fit == 'cover' else min)(w / iw, h / ih)
    return (w - iw * scale) / 2, (h - ih * scale) / 2, scale, scale


@lru_cache(maxsize=4)
def _surface(data):
    import cairo
    try:
        return cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes(data)))
    except (cairo.Error, ValueError, OSError) as exc:
        logging.getLogger(__name__).warning('Cannot decode TargetVisu PNG: %s', exc)
        return None


def draw_graphic(ctx, element, selector=None, has_binding=False):
    graphic = element['graphic']
    data = select_graphic_data(graphic, selector, has_binding)
    surface = _surface(data) if data else None
    x, y, w, h = (element[k] for k in ('x', 'y', 'width', 'height'))
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    if surface is None:
        ctx.set_source_rgb(0.8, 0.8, 0.8)
        ctx.paint()
    else:
        dx, dy, sx, sy = placement(surface.get_width(), surface.get_height(), w, h, graphic['fit'])
        ctx.translate(x + dx, y + dy)
        ctx.scale(sx, sy)
        ctx.rectangle(0, 0, surface.get_width(), surface.get_height())
        ctx.clip()
        ctx.set_source_surface(surface, 0, 0)
        ctx.paint()
    ctx.restore()
