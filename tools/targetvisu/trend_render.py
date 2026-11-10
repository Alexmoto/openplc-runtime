# SPDX-License-Identifier: GPL-3.0-only
"""Cairo chart for bounded TargetVisu trend history (no GTK imports)."""
import math
import time
from .trend_controls import y_bounds, viewport, toolbar_boxes


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def series_segments(points, index, now, duration, sample_ms):
    """Split discontinuities so communication failures do not join across gaps."""
    start = now - duration
    gap = max(1.0, 2.5 * sample_ms / 1000)
    segments, current, previous = [], [], None
    for row in points:
        if not isinstance(row, (list, tuple)) or len(row) <= index + 1:
            continue
        stamp, value = row[0], row[index + 1]
        if (type(stamp) not in (int, float) or not math.isfinite(stamp) or
                type(value) not in (int, float) or not math.isfinite(value) or
                stamp < start or stamp > now + 1):
            continue
        if previous is not None and (stamp <= previous or stamp - previous > gap):
            if current:
                segments.append(current)
            current = []
        current.append((stamp, value))
        previous = stamp
    if current:
        segments.append(current)
    return segments


def draw_trend(ctx, element, points, online, now=None, view=None):
    if now is None:
        now = time.time()
    x, y, w, h = (element[key] for key in ('x', 'y', 'width', 'height'))
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    ctx.set_source_rgb(*_rgb(element['fill']))
    ctx.rectangle(x, y, w, h)
    ctx.fill()
    if element['strokeWidth']:
        ctx.set_source_rgb(*_rgb(element['stroke']))
        ctx.set_line_width(element['strokeWidth'])
        ctx.rectangle(x + 1, y + 1, max(1, w - 2), max(1, h - 2))
        ctx.stroke()

    ctx.set_source_rgb(*_rgb(element['textColor']))
    ctx.select_font_face('Sans')
    ctx.set_font_size(min(14, max(9, h / 12)))
    ctx.move_to(x + 8, y + 18)
    ctx.show_text(element['text'][:32])
    if not online:
        ctx.set_source_rgb(0.75, 0.25, 0.25)
        ctx.move_to(x + max(8, w - 65), y + 18)
        ctx.show_text('OFFLINE')

    if w < 125 or h < 100:
        ctx.restore()
        return

    trend = element['trend']
    controls = toolbar_boxes(element)
    left, right = x + 48, x + w - 12
    top = y + 46
    # Controls are below the time labels, not over the plot.
    rows = 2 if len(controls) > 4 and controls[0][3] != controls[-1][3] else 1 if controls else 0
    bottom = y + h - (73 if rows == 2 else 49 if rows == 1 else 30)
    if bottom - top < 10:
        ctx.restore()
        return
    start, end, low, high, _ = viewport(element, points, now, view)
    span = high - low
    duration = end - start

    ctx.set_font_size(10)
    for tick in range(5):
        value = low + span * (4 - tick) / 4
        yy = top + (bottom - top) * tick / 4
        ctx.set_source_rgba(0.45, 0.52, 0.61, 0.45)
        ctx.set_line_width(0.75)
        ctx.move_to(left, yy)
        ctx.line_to(right, yy)
        ctx.stroke()
        ctx.set_source_rgb(*_rgb(element['textColor']))
        ctx.move_to(x + 4, yy + 3)
        ctx.show_text(f'{value:.4g}'[:9])

    time_format = '%H:%M:%S' if duration <= 180 else '%H:%M'
    for tick in range(3):
        stamp = start + duration * tick / 2
        xx = left + (right - left) * tick / 2
        ctx.set_source_rgba(0.45, 0.52, 0.61, 0.25)
        ctx.set_line_width(0.75)
        ctx.move_to(xx, top)
        ctx.line_to(xx, bottom)
        ctx.stroke()
        timestamp = time.strftime(time_format, time.localtime(stamp))
        ext = ctx.text_extents(timestamp)
        text_x = xx if tick == 0 else xx - ext.width if tick == 2 else xx - ext.width / 2
        ctx.set_source_rgb(*_rgb(element['textColor']))
        ctx.move_to(text_x, bottom + 17)
        ctx.show_text(timestamp)

    ctx.save()
    ctx.rectangle(left, top, right - left, bottom - top)
    ctx.clip()
    for index, series in enumerate(trend['series']):
        ctx.set_source_rgb(*_rgb(series['color']))
        ctx.set_line_width(1.8)
        for segment in series_segments(points, index, end, duration, trend['sampleMs']):
            ctx.new_path()
            for i, (stamp, value) in enumerate(segment):
                xx = left + (stamp - start) / duration * (right - left)
                yy = bottom - (value - low) / span * (bottom - top)
                if i == 0:
                    ctx.move_to(xx, yy)
                else:
                    ctx.line_to(xx, yy)
            if len(segment) == 1:
                ctx.arc(xx, yy, 1.8, 0, math.tau)
                ctx.fill()
            else:
                ctx.stroke()
    ctx.restore()

    ctx.set_font_size(9)
    for index, series in enumerate(trend['series']):
        legend_x = x + 8 + (index % 2) * w / 2
        legend_y = y + 29 + (index // 2) * 12
        ctx.set_source_rgb(*_rgb(series['color']))
        ctx.set_line_width(2.5)
        ctx.move_to(legend_x, legend_y)
        ctx.line_to(legend_x + 12, legend_y)
        ctx.stroke()
        ctx.set_source_rgb(*_rgb(element['textColor']))
        ctx.move_to(legend_x + 16, legend_y + 3)
        ctx.show_text((series['label'] or series['path'].split('.')[-1])[:16])

    # Local view controls; no PLC actions or broker requests are generated.
    ctx.set_font_size(10)
    for action, label, bx, by, bw, bh in controls:
        active = action == 'live' and bool(view)
        ctx.set_source_rgba(0.18, 0.39, 0.58, 0.94) if active else ctx.set_source_rgba(0.18, 0.23, 0.31, 0.9)
        ctx.rectangle(bx, by, bw, bh)
        ctx.fill_preserve()
        ctx.set_source_rgba(0.58, 0.67, 0.77, 0.85)
        ctx.set_line_width(0.75)
        ctx.stroke()
        ext = ctx.text_extents(label)
        ctx.set_source_rgb(1, 1, 1)
        ctx.move_to(bx + (bw - ext.width) / 2 - ext.x_bearing,
                    by + (bh - ext.height) / 2 - ext.y_bearing)
        ctx.show_text(label)
    ctx.restore()
