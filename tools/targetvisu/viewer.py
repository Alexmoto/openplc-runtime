# SPDX-License-Identifier: GPL-3.0-only
"""GTK 3 / Cairo X11 viewer; all broker I/O runs on a worker thread."""
import os
import queue
import threading
import time
from .service import Client
from .render import draw, geometry, hit
from .keypad import show as show_numeric_keypad


def run(model, broker_path, fullscreen=False, demo=False):
    os.environ.setdefault('GDK_BACKEND', 'x11')
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Gtk, Gdk, GLib
    if not Gtk.init_check()[0]:
        raise RuntimeError('Cannot open X11 display; connect with ssh -Y and check DISPLAY')
    window = Gtk.Window(title='OpenPLC TargetVisu' + (' — DEMO' if demo else ''))
    initial = next(s for s in model.doc['screens'] if s['id'] == model.doc['startScreen'])
    window.set_default_size(initial['width'], initial['height'])
    canvas = Gtk.DrawingArea()
    canvas.set_can_focus(True)
    canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                      Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
    window.add(canvas)
    state = dict(screen=initial, values={}, online=False, pressed=None, trends={})
    commands = queue.Queue(maxsize=32)
    closed = threading.Event()
    disconnect = threading.Event()

    def publish(reply=None, error=None):
        if closed.is_set():
            return False
        if error:
            state.update(online=False, values={}, pressed=None)
        else:
            state.update(online=reply['online'], values=reply['values'])
        canvas.queue_draw()
        return False

    def publish_trends(reply, screen_id):
        if not closed.is_set() and state['screen']['id'] == screen_id:
            state['trends'] = reply['history']
            canvas.queue_draw()
        return False

    def enqueue(request):
        try:
            commands.put_nowait((time.monotonic(), request))
        except queue.Full:
            # Closing the session makes the broker release any held targets.
            disconnect.set()
            state['online'] = False
            state['pressed'] = None

    def worker():
        client = None
        last_history_at, last_history_screen = 0.0, None
        try:
            while not closed.is_set():
                try:
                    if disconnect.is_set():
                        disconnect.clear()
                        raise ConnectionError('Command queue full; session reset')
                    if client is None:
                        client = Client(broker_path)
                    reply = client.request(dict(op='poll'))
                    if reply['md5'] != model.md5:
                        raise ValueError('Viewer / broker debug-map mismatch')
                    GLib.idle_add(publish, reply)
                    active_screen = state['screen']
                    screen_id = active_screen['id']
                    if (any(e['kind'] == 'trend' for e in active_screen['elements']) and
                            (screen_id != last_history_screen or time.monotonic() - last_history_at >= 1.0)):
                        snapshot = client.request(dict(op='trends', screen=screen_id))
                        GLib.idle_add(publish_trends, snapshot, screen_id)
                        last_history_at, last_history_screen = time.monotonic(), screen_id
                    try:
                        created, request = commands.get(timeout=model.doc['refreshMs'] / 1000)
                    except queue.Empty:
                        continue
                    if time.monotonic() - created <= 1.0 or request['op'] == 'release':
                        result = client.request(request)
                        if 'screen' in result:
                            GLib.idle_add(changed, result['screen'])
                except (OSError, ValueError, ConnectionError) as exc:
                    GLib.idle_add(publish, None, str(exc))
                    if client:
                        client.close(); client = None
                    # Never replay commands collected before a disconnect.
                    while not commands.empty():
                        try:
                            commands.get_nowait()
                        except queue.Empty:
                            break
                    closed.wait(0.5)
        finally:
            if client:
                # Disconnect itself releases leases, even if this message fails.
                try:
                    client.request(dict(op='release'))
                except (OSError, ValueError, ConnectionError):
                    pass
                client.close()

    def release(*_):
        if state['pressed']:
            state['pressed'] = None
            enqueue(dict(op='release'))
            canvas.queue_draw()
        return False

    def changed(screen_id):
        if closed.is_set():
            return False
        release()
        state['screen'] = next(s for s in model.doc['screens'] if s['id'] == screen_id)
        state['trends'] = {}
        canvas.queue_draw()
        return False

    def clicked(widget, event):
        if event.button != 1 or not state['online']:
            return False
        scale, ox, oy = geometry(state['screen'], canvas.get_allocated_width(), canvas.get_allocated_height())
        element = hit(model, state['screen'], state['values'], (event.x - ox) / scale, (event.y - oy) / scale)
        if not element:
            return False
        action = element['action']
        request = dict(op='action', id=element['id'])
        if action['kind'] == 'write':
            current = state['values'].get(action['target'].lower())
            value = show_numeric_keypad(window, element, model, current)
            if value is None:
                return True
            # The broker still verifies online status, permissions, range and type.
            request['value'] = value
        if action['kind'] == 'momentary':
            state['pressed'] = element['id']; request['pressed'] = True
        enqueue(request)
        canvas.queue_draw()
        return True

    def motion(widget, event):
        if state['pressed']:
            scale, ox, oy = geometry(state['screen'], canvas.get_allocated_width(), canvas.get_allocated_height())
            e = hit(model, state['screen'], state['values'], (event.x - ox) / scale, (event.y - oy) / scale)
            if e is None or e['id'] != state['pressed']:
                release()
        return False

    def paint(widget, ctx):
        draw(ctx, model, state['screen'], state['values'], state['online'],
             canvas.get_allocated_width(), canvas.get_allocated_height(), state['pressed'], state['trends'])
        return False

    def destroy(*_):
        closed.set()
        Gtk.main_quit()
    def hide_cursor(widget):
        # Apply after realization, when the native X11 window exists.
        native_window = widget.get_window()
        if native_window is not None:
            native_window.set_cursor(
                Gdk.Cursor.new_for_display(widget.get_display(), Gdk.CursorType.BLANK_CURSOR)
            )

    window.connect('realize', hide_cursor)
    canvas.connect('realize', hide_cursor)
    canvas.connect('draw', paint)
    canvas.connect('button-press-event', clicked)
    canvas.connect('button-release-event', release)
    canvas.connect('leave-notify-event', release)
    canvas.connect('motion-notify-event', motion)
    window.connect('focus-out-event', release)
    window.connect('destroy', destroy)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    window.show_all()
    if fullscreen:
        window.fullscreen()
    Gtk.main()
    closed.set()
    thread.join(timeout=3)
