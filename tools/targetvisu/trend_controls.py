# SPDX-License-Identifier: GPL-3.0-only
"""Local, read-only Trend viewport controls shared by Cairo drawing and hit testing."""
import math

# Actions are GUI-only. They never become PLC broker writes.
BUTTONS = (
    ('older', '<'), ('time_in', 'X+'), ('time_out', 'X-'), ('newer', '>'),
    ('down', 'v'), ('value_in', 'Y+'), ('value_out', 'Y-'), ('up', '^'),
    ('live', 'LIVE'),
)


def toolbar_boxes(element):
    """Return (action, label, x, y, width, height) in screen coordinates."""
    x, y, width, height = (element[k] for k in ('x', 'y', 'width', 'height'))
    if height < 145 or width < 120:
        return []
    gap, button_height = 2, 19
    boxes = []
    if width >= 210:
        # One row for a standard (320 x 180) Trend; responsive down to 210 px.
        button_width = min(24, (width - 12 - 32 - 8 * gap) / 8)
        lengths = [button_width] * 8 + [32]
        total = sum(lengths) + gap * 8
        start = x + (width - total) / 2
        for (action, label), bw in zip(BUTTONS, lengths):
            boxes.append((action, label, start, y + height - 23, bw, button_height))
            start += bw + gap
    elif height >= 170:
        # Two rows on narrow Trends. Keep the plot and time-axis readable.
        for row, buttons in enumerate((BUTTONS[:4], BUTTONS[4:])):
            widest = 32 if row else 24
            bw = min(24, (width - 12 - widest - gap * (len(buttons) - 1)) /
                     (len(buttons) - 1)) if row else min(24, (width - 12 - gap * 3) / 4)
            lengths = [bw] * len(buttons)
            if row:
                lengths[-1] = 32
            total = sum(lengths) + gap * (len(buttons) - 1)
            start = x + (width - total) / 2
            for (action, label), length in zip(buttons, lengths):
                boxes.append((action, label, start, y + height - (45 if row == 0 else 23),
                              length, button_height))
                start += length + gap
    return boxes


def control_at(element, x, y):
    for action, _, left, top, width, height in toolbar_boxes(element):
        if left <= x < left + width and top <= y < top + height:
            return action
    return None


def y_bounds(element, points):
    """Return automatic visible-data bounds or configured fixed Y limits."""
    trend = element['trend']
    if trend['autoScale']:
        values = [float(value) for row in points for value in row[1:]
                  if type(value) in (int, float) and math.isfinite(value)]
        if values:
            low, high = min(values), max(values)
            margin = max((high - low) * 0.05, abs(high) * 0.001, 0.1)
            return low - margin, high + margin
    low, high = float(element['minimum']), float(element['maximum'])
    if high <= low:
        high = low + 1
    return low, high


def viewport(element, points, now, view=None):
    """Read-only visible time/Y range. A past window remains anchored in time."""
    state = view or {}
    default = element['trend']['durationSec']
    duration = min(max(float(state.get('duration', default)), 10.0), default * 4)
    end = now if state.get('end') is None else min(float(state['end']), now)
    start = end - duration
    visible = [row for row in points if isinstance(row, (list, tuple)) and row
               and type(row[0]) in (int, float) and math.isfinite(row[0])
               and start <= row[0] <= end]
    low, high = state.get('y') or y_bounds(element, visible)
    return start, end, low, high, visible


def apply_control(element, points, now, view, action):
    """Return a new local viewport; never modifies PLC variables or chart setup."""
    state = dict(view or {})
    if action == 'live':
        return {}
    if action not in {item[0] for item in BUTTONS}:
        return state
    start, end, low, high, _ = viewport(element, points, now, state)
    duration = end - start
    default = element['trend']['durationSec']
    if action == 'time_in':
        state['duration'] = max(10.0, duration / 1.5)
    elif action == 'time_out':
        state['duration'] = min(default * 4, duration * 1.5)
    elif action in ('older', 'newer'):
        if action == 'newer':
            next_end = end + duration / 4
            state['end'] = None if next_end >= now else next_end
        else:
            stamps = [row[0] for row in points if isinstance(row, (list, tuple)) and row
                      and type(row[0]) in (int, float) and math.isfinite(row[0])]
            if stamps:
                oldest_end = min(stamps) + duration
                if oldest_end < end:
                    state['end'] = max(oldest_end, end - duration / 4)
    else:
        center = (low + high) / 2
        span = high - low
        if action == 'value_in':
            span *= 0.8
        elif action == 'value_out':
            span *= 1.25
        elif action == 'up':
            center += span * 0.25
        elif action == 'down':
            center -= span * 0.25
        state['y'] = (center - span / 2, center + span / 2)
    return state
