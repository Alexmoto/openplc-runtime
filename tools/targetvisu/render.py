# SPDX-License-Identifier: GPL-3.0-only
"""Cairo renderer; logical coordinates match the Editor SVG preview."""
import math
from .graphics import draw_graphic


def rgb(value):
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def bound_color(model, element, key, values):
    value = model.bound(element, key, values)
    if element['kind'] != 'number' or type(value) is not int:
        return element[key]
    return f'#{value & 0xffffff:06x}'


def rounded_rect(ctx, x, y, w, h, radius):
    radius = max(0, min(radius, w / 2, h / 2))
    if not radius:
        ctx.rectangle(x, y, w, h)
        return
    ctx.new_sub_path()
    ctx.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    ctx.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    ctx.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    ctx.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def geometry(screen, width, height):
    scale = min(width / screen['width'], height / screen['height'])
    return scale, (width - screen['width'] * scale) / 2, (height - screen['height'] * scale) / 2


def hit(model, screen, values, x, y):
    # Topmost visible primitive captures the pointer, including a decorative cover.
    for e in reversed(screen['elements']):
        if model.visible(e, values) and e['x'] <= x <= e['x'] + e['width'] and e['y'] <= y <= e['y'] + e['height']:
            return e if model.enabled(e, values) and e['action']['kind'] != 'none' else None
    return None


def draw(ctx, model, screen, values, online, width, height, pressed=None):
    ctx.set_source_rgb(0.12, 0.14, 0.17)
    ctx.paint()
    scale, ox, oy = geometry(screen, width, height)
    ctx.save()
    ctx.translate(ox, oy)
    ctx.scale(scale, scale)
    ctx.rectangle(0, 0, screen['width'], screen['height'])
    ctx.clip()
    ctx.set_source_rgb(*rgb(screen['background']))
    ctx.paint()
    for e in screen['elements']:
        if not model.visible(e, values):
            continue
        if e['kind'] == 'graphic':
            draw_graphic(ctx, e, model.bound(e, 'value', values), bool(e['bindings'].get('value')))
            continue
        ctx.save()
        ctx.new_path()
        x, y, w, h = (e[k] for k in ('x', 'y', 'width', 'height'))
        value = model.bound(e, 'value', values)
        active = (e['kind'] in ('indicator', 'button') and bool(value)) or e['id'] == pressed
        fill = e['activeFill'] if active else bound_color(model, e, 'fill', values)
        stroke = bound_color(model, e, 'stroke', values)
        text_color = bound_color(model, e, 'textColor', values)
        if e['kind'] == 'line':
            direction = e.get('lineDirection', 'horizontal')
            start, end = {'horizontal': ((x, y + h / 2), (x + w, y + h / 2)),
                          'vertical': ((x + w / 2, y), (x + w / 2, y + h)),
                          'diagonal-down': ((x, y), (x + w, y + h)),
                          'diagonal-up': ((x, y + h), (x + w, y))}[direction]
            ctx.move_to(*start); ctx.line_to(*end)
        elif e['kind'] in ('ellipse', 'indicator'):
            ctx.save(); ctx.translate(x + w / 2, y + h / 2); ctx.scale(w / 2, h / 2)
            ctx.arc(0, 0, 1, 0, 2 * math.pi); ctx.restore()
        elif e['kind'] == 'number':
            rounded_rect(ctx, x, y, w, h, e.get('borderRadius', 0))
        elif e['kind'] != 'text':
            ctx.rectangle(x, y, w, h)
        if e['kind'] != 'text':
            if e['kind'] != 'line':
                ctx.set_source_rgb(*rgb(fill)); ctx.fill_preserve()
            ctx.set_source_rgb(*rgb(stroke)); ctx.set_line_width(e['strokeWidth'])
            if e['strokeWidth']:
                ctx.stroke()
            else:
                ctx.new_path()
        text = e['text']
        if e['kind'] == 'number' or (e['kind'] == 'text' and e['bindings']['value']):
            if value is None:
                text = '—'
            elif isinstance(value, bool):
                text = 'TRUE' if value else 'FALSE'
            elif isinstance(value, int):
                # Retain exact LINT/ULINT digits rather than convert through float.
                text = str(value) + ('.' + '0' * e['decimals'] if e['decimals'] else '')
            elif isinstance(value, float):
                text = f'{value:.{e["decimals"]}f}'
            else:
                text = str(value)
        if text and e['kind'] != 'line':
            ctx.rectangle(x, y, w, h); ctx.clip()
            ctx.set_source_rgb(*rgb(text_color))
            # Pango provides UTF-8/Cyrillic layout and respects the element clip.
            from gi.repository import Pango, PangoCairo
            layout = PangoCairo.create_layout(ctx)
            font = Pango.FontDescription('Sans')
            font.set_absolute_size(e['fontSize'] * Pango.SCALE)
            layout.set_font_description(font)
            layout.set_text(text, -1)
            tw, th = layout.get_pixel_size()
            tx = x if e['kind'] == 'text' else x + (w - tw) / 2
            ctx.move_to(tx, y + (h - th) / 2)
            PangoCairo.show_layout(ctx, layout)
        if e['action']['kind'] != 'none' and (not online or not model.enabled(e, values)):
            ctx.reset_clip(); ctx.rectangle(x, y, w, h)
            ctx.set_source_rgba(0.5, 0.5, 0.5, 0.4); ctx.fill()
        ctx.restore()
    ctx.restore()
