# SPDX-License-Identifier: GPL-3.0-only
"""Touch-friendly Number input, deliberately separate from broker writes.

The GTK dialog uses this module, but all value checks remain independent of GTK
and the Runtime broker revalidates the write against the compiled PLC symbol.
"""
import math
import re

MAX_DIGITS = 24
INTEGER_TYPES = {'SINT', 'USINT', 'BYTE', 'INT', 'UINT', 'WORD', 'DINT',
                 'UDINT', 'DWORD', 'LINT', 'ULINT', 'LWORD'}
FLOAT_TYPES = {'REAL', 'LREAL'}


def press(text, key, floating):
    """Return an updated numeric string after one on-screen key press."""
    if key == 'C':
        return '0'
    if key == '⌫':
        result = text[:-1]
        return '0' if result in ('', '-') else result
    if key == '±':
        return text[1:] if text.startswith('-') else '-' + text
    if key == '.':
        if not floating or '.' in text:
            return text
        return (text or '0') + '.'
    if key not in '0123456789' or len(key) != 1:
        return text
    if len(text.replace('-', '').replace('.', '')) >= MAX_DIGITS:
        return text
    if text == '0':
        return key
    if text == '-0':
        return '-' + key
    return text + key


def parse(text, datatype, minimum, maximum, encode):
    """Parse and check an entered number before it is queued for the broker.

    encode(value) is the authoritative IEC width/range validation from Model.
    """
    if datatype in INTEGER_TYPES:
        if not re.fullmatch(r'-?\d+', text):
            raise ValueError('Введите целое число')
        value = int(text, 10)
    elif datatype in FLOAT_TYPES:
        if not re.fullmatch(r'-?\d+(?:\.\d*)?', text):
            raise ValueError('Введите число')
        value = float(text)
        if not math.isfinite(value):
            raise ValueError('Число не является конечным')
    else:
        raise ValueError('Недопустимый тип числовой переменной')
    if not minimum <= value <= maximum:
        raise ValueError('Значение вне диапазона Number: {} … {}'.format(minimum, maximum))
    encode(value)
    return value


def initial_text(value, datatype, decimals):
    if type(value) is bool or type(value) not in (int, float):
        return '0'
    if isinstance(value, float) and not math.isfinite(value):
        return '0'
    if datatype in FLOAT_TYPES and isinstance(value, float):
        return format(value, '.{}f'.format(decimals))
    return str(value)


def show(window, element, model, current):
    """Display a modal GTK touch keypad; return a value or None on cancel."""
    from gi.repository import Gtk

    target = element['action']['target']
    datatype = model.leaf(target)['type']
    floating = datatype in FLOAT_TYPES
    dialog = Gtk.Dialog(title='Ввод: ' + element['name'], transient_for=window, modal=True)
    dialog.set_default_size(440, 510)
    dialog.set_resizable(False)
    dialog.add_buttons('Отмена', Gtk.ResponseType.CANCEL, 'Записать', Gtk.ResponseType.OK)
    area = dialog.get_content_area()
    area.set_spacing(10)
    area.set_border_width(12)

    caption = Gtk.Label(label='{}  [{} … {}]'.format(target, element['minimum'], element['maximum']))
    caption.set_line_wrap(True)
    area.pack_start(caption, False, False, 0)

    display = Gtk.Entry()
    display.set_editable(False)
    display.set_alignment(1.0)
    display.set_width_chars(16)
    display.set_text(initial_text(current, datatype, element['decimals']))
    area.pack_start(display, False, False, 0)

    error = Gtk.Label()
    error.set_line_wrap(True)
    area.pack_start(error, False, False, 0)

    grid = Gtk.Grid()
    grid.set_column_spacing(8)
    grid.set_row_spacing(8)
    keys = [['7', '8', '9', '⌫'],
            ['4', '5', '6', 'C'],
            ['1', '2', '3', '±'],
            ['0', '.']]

    def on_key(widget, key):
        display.set_text(press(display.get_text(), key, floating))
        error.set_text('')

    for row, keys_row in enumerate(keys):
        for col, key in enumerate(keys_row):
            button = Gtk.Button(label=key)
            button.set_size_request(78, 65)
            if key == '.' and not floating:
                button.set_sensitive(False)
            button.connect('clicked', on_key, key)
            grid.attach(button, col, row, 1, 1)
    area.pack_start(grid, True, True, 0)

    try:
        dialog.show_all()
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                return None
            try:
                return parse(display.get_text(), datatype, element['minimum'], element['maximum'],
                             lambda value: model.encode(target, value))
            except (ValueError, OverflowError) as exc:
                error.set_text(str(exc))
    finally:
        dialog.destroy()
