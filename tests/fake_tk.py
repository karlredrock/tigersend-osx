# -*- coding: utf-8 -*-
"""A tiny stand-in for Tkinter, so the GUI code can be tested headlessly.

It records what the widgets were told to display and lets the test drive the
callbacks (buttons, dialogs, clipboard...). It is intentionally dumb: it only
implements what tigersend.py actually uses, and it works on Python 2.3 too.
"""


class FakeError(Exception):
    pass


class Variable(object):
    def __init__(self, value=''):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class StringVar(Variable):
    pass


class _TkCall(object):
    def __init__(self, root):
        self.root = root

    def call(self, *args):
        self.root.calls.append(args)
        if args[:2] == ('tk', 'appname'):
            return ''
        return ''

    def splitlist(self, value):
        if isinstance(value, (list, tuple)):
            return list(value)
        return str(value).split()


class Widget(object):
    def __init__(self, master=None, **options):
        self.master = master
        self.options = dict(options)
        self.children = []
        self.packed = None
        if master is not None and hasattr(master, 'children'):
            master.children.append(self)

    # geometry: everything succeeds and is remembered
    def pack(self, **options):
        self.packed = options
        return self

    def grid(self, **options):
        self.packed = options
        return self

    def place(self, **options):
        self.packed = options
        return self

    def pack_forget(self):
        self.packed = None

    # configuration
    def config(self, **options):
        self.options.update(options)

    configure = config

    def cget(self, key):
        return self.options.get(key, '')

    def __getitem__(self, key):
        return self.options.get(key, '')

    def bind(self, sequence, function=None):
        self.options['bind:' + sequence] = function

    def destroy(self):
        self.options['destroyed'] = 1

    def winfo_exists(self):
        return not self.options.get('destroyed')

    def update(self):
        pass

    def update_idletasks(self):
        pass


class Frame(Widget):
    pass


class Scrollback(Widget):
    def set(self, *args):
        pass


class Label(Widget):
    def text(self):
        return self.options.get('text', '')


class Button(Widget):
    def invoke(self):
        command = self.options.get('command')
        if command is not None:
            return command()

    def flash(self):
        pass


class Entry(Widget):
    def get(self):
        variable = self.options.get('textvariable')
        if variable is not None:
            return variable.get()
        return self.options.get('text', '')

    def insert(self, index, text):
        variable = self.options.get('textvariable')
        if variable is not None:
            variable.set(variable.get() + text)

    def delete(self, first, last=None):
        variable = self.options.get('textvariable')
        if variable is not None:
            variable.set('')

    def selection_range(self, first, last):
        pass


class Listbox(Widget):
    def __init__(self, master=None, **options):
        Widget.__init__(self, master, **options)
        self.items = []
        self.selection = ()
        self.visible = 0

    def insert(self, index, text):
        if index == 'end':
            self.items.append(text)
        else:
            self.items.insert(int(index), text)

    def delete(self, first, last=None):
        if first == 0 and last == 'end':
            self.items = []
            self.selection = ()
            return
        if last is None:
            index = int(first)
            if 0 <= index < len(self.items):
                del self.items[index]
            if index < len(self.selection):
                self.selection = ()
            return
        start = int(first)
        end = len(self.items)
        if last != 'end':
            end = int(last)
        del self.items[start:end]

    def size(self):
        return len(self.items)

    def get(self, first, last=None):
        if last is None:
            return self.items[int(first)]
        return self.items[int(first):int(last) + 1]

    def curselection(self):
        return self.selection

    def selection_set(self, index):
        self.selection = (str(index),)

    def selection_clear(self, first, last=None):
        self.selection = ()

    def see(self, index):
        pass

    def yview(self, *args):
        return 0.0

    def yview_scroll(self, number, what):
        pass

    def activate(self, index):
        pass

    def nearest(self, y):
        return 0


class Text(Widget):
    def __init__(self, master=None, **options):
        Widget.__init__(self, master, **options)
        self.content = ''
        self.marks = {}

    def insert(self, index, text):
        if index == 'end':
            self.content = self.content + text
        else:
            self.content = text + self.content

    def delete(self, first, last=None):
        if first == '1.0' and last == 'end':
            self.content = ''
            return
        # delete('1.0', '200.0') -> drop the first 199 lines
        try:
            first_line = int(str(first).split('.')[0])
            last_line = int(str(last).split('.')[0])
        except Exception:
            self.content = ''
            return
        lines = self.content.splitlines(True)
        del lines[first_line - 1:last_line - 1]
        self.content = ''.join(lines)

    def get(self, first, last=None):
        return self.content

    def index(self, index):
        if index == 'end-1c' or index == 'end':
            return '%d.0' % (len(self.content.splitlines()) + 1)
        return index

    def see(self, index):
        pass

    def yview(self, *args):
        return 0.0

    def yview_pickplace(self, *args):
        pass


class Radiobutton(Widget):
    def invoke(self):
        variable = self.options.get('variable')
        if variable is not None:
            variable.set(self.options.get('value'))
        command = self.options.get('command')
        if command is not None:
            return command()

    def select(self):
        self.invoke()


class Tk(Widget):
    def __init__(self):
        Widget.__init__(self, None)
        self.calls = []
        self.tk = _TkCall(self)
        self.after_calls = []
        self.protocols = {}
        self.clipboard = ''
        self.destroyed = 0
        self.mainloop_called = 0

    def after(self, delay, function=None, *args):
        self.after_calls.append((delay, function, args))
        return len(self.after_calls)

    def after_idle(self, function=None, *args):
        return self.after(0, function, *args)

    def protocol(self, name, function=None):
        if function is None:
            return self.protocols.get(name)
        self.protocols[name] = function

    def title(self, text=None):
        if text is not None:
            self.options['title'] = text
        return self.options.get('title', '')

    def minsize(self, width=None, height=None):
        self.options['minsize'] = (width, height)

    def maxsize(self, width=None, height=None):
        pass

    def geometry(self, spec=None):
        if spec is not None:
            self.options['geometry'] = spec
        return self.options.get('geometry', '')

    def lift(self):
        self.options['lifted'] = 1

    def focus_force(self):
        pass

    def clipboard_get(self, **options):
        if self.clipboard is None:
            raise FakeError('no clipboard')
        return self.clipboard

    def clipboard_clear(self):
        self.clipboard = ''

    def clipboard_append(self, text):
        self.clipboard = self.clipboard + text

    def destroy(self):
        self.destroyed = 1
        self.options['destroyed'] = 1

    def mainloop(self, count=0):
        self.mainloop_called = self.mainloop_called + 1

    def quit(self):
        pass

    def update(self):
        pass

    def wait_window(self, window=None):
        pass

    def bell(self):
        pass


# ---------------------------------------------------------------------------
#  Dialog modules
# ---------------------------------------------------------------------------
class _FileDialog(object):
    def __init__(self):
        self.next_open_names = []
        self.next_open_name = None
        self.next_directory = None
        self.calls = []

    def askopenfilenames(self, **options):
        self.calls.append(('askopenfilenames', options))
        return tuple(self.next_open_names)

    def askopenfilename(self, **options):
        self.calls.append(('askopenfilename', options))
        return self.next_open_name or ''

    def askdirectory(self, **options):
        self.calls.append(('askdirectory', options))
        return self.next_directory or ''

    def asksaveasfilename(self, **options):
        return ''


class _MessageBox(object):
    def __init__(self):
        self.messages = []

    def showinfo(self, title, message, **options):
        self.messages.append(('info', title, message))

    def showwarning(self, title, message, **options):
        self.messages.append(('warning', title, message))

    def showerror(self, title, message, **options):
        self.messages.append(('error', title, message))

    def askyesno(self, title, message, **options):
        self.messages.append(('askyesno', title, message))
        return True

    def askokcancel(self, title, message, **options):
        return True


tkFileDialog = _FileDialog()
tkMessageBox = _MessageBox()


class _TkinterModule(object):
    """Mimics `import Tkinter` / `import tkinter as Tkinter`."""

    Frame = Frame
    Label = Label
    Button = Button
    Entry = Entry
    Listbox = Listbox
    Text = Text
    Scrollbar = Scrollback
    Radiobutton = Radiobutton
    Checkbutton = Radiobutton
    Canvas = Widget
    Menu = Widget
    Toplevel = Tk
    Tk = Tk
    StringVar = StringVar
    IntVar = StringVar
    BooleanVar = StringVar
    TclError = FakeError


Tkinter = _TkinterModule()
