# SPDX-License-Identifier: GPL-3.0-only
"""Run under X11 (Xvfb is sufficient). Exercises the actual GTK viewer.
The broker adapter is an in-memory Engine/Demo; no PLC or Unix socket required.
"""
import sys
from pathlib import Path
from unittest.mock import patch
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
from targetvisu.model import Model, load_json
from targetvisu.backend import Demo
from targetvisu.service import Engine
from targetvisu.render import draw, geometry
from targetvisu.viewer import run

root = Path(__file__).parents[1]
model = Model(load_json(root/'example.targetvisu.json'), load_json(root/'example.debug-map.json'))
backend = Demo(model)
engine = Engine(model, backend)
engine.tick()

class LocalClient:
    def __init__(self, _):
        pass
    def request(self, request):
        engine.tick()
        return engine.request(request, 1)
    def close(self):
        engine.release(1)


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)

stage, attempts, errors = 0, 0, []

def drive():
    global stage, attempts
    attempts += 1
    try:
        windows = [w for w in Gtk.Window.list_toplevels() if w.get_visible()]
        window = next((w for w in windows if w.get_title().startswith('OpenPLC TargetVisu')), None)
        if attempts > 50:
            raise AssertionError('GTK workflow timed out')
        if window is None:
            return True
        canvas = next(w for w in descendants(window) if isinstance(w, Gtk.DrawingArea))
        def click(element):
            scale, ox, oy = geometry(model.doc['screens'][0], canvas.get_allocated_width(), canvas.get_allocated_height())
            event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
            event.button = 1
            event.x, event.y = ox+(element['x']+element['width']/2)*scale, oy+(element['y']+element['height']/2)*scale
            canvas.emit('button-press-event', event)
        if stage == 0:
            if not any(isinstance(w, Gtk.Label) and w.get_text() == 'DEMO — RUN' for w in descendants(window)):
                return True
            stage = 1
            click(next(e for e in model.elements.values() if e['action']['kind']=='set' and e['action']['value'] is True))
        elif stage == 1:
            if not backend.values['pump1.startrequest']:
                return True
            stage = 2
            click(next(e for e in model.elements.values() if e['action']['kind']=='set' and e['action']['value'] is False))
        elif stage == 2:
            if backend.values['pump1.startrequest']:
                return True
            stage = 3
            # Schedule separately because Gtk.Dialog.run enters a nested main loop.
            GLib.idle_add(lambda: (click(next(e for e in model.elements.values() if e['action']['kind']=='write')), False)[1])
        elif stage == 3:
            dialog = next((w for w in windows if isinstance(w, Gtk.Dialog)), None)
            if dialog is None:
                return True
            entry = next(w for w in descendants(dialog) if isinstance(w, Gtk.Entry))
            entry.set_text('23.5')
            stage = 4
            dialog.response(Gtk.ResponseType.OK)
        elif stage == 4:
            if backend.values['pump1.setpoint'] != 23.5:
                return True
            engine.tick()
            assert engine.values['pump1.pressure'] == 23.5
            # Capture the renderer through its actual Pango/Cairo code path.
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 480)
            draw(cairo.Context(surface), model, model.doc['screens'][0], engine.values, True, 800, 480)
            surface.write_to_png(sys.argv[1] if len(sys.argv)>1 else '/tmp/targetvisu-runtime.png')
            window.destroy()
            return False
    except BaseException as exc:
        errors.append(exc)
        for window in Gtk.Window.list_toplevels():
            window.destroy()
        return False
    return True

GLib.timeout_add(150, drive)
with patch('targetvisu.viewer.Client', LocalClient):
    run(model, '/unused', demo=True)
if errors:
    raise errors[0]
assert stage == 4
print('GTK X11: Start / Stop / numeric dialog / Cairo rendering PASS')
