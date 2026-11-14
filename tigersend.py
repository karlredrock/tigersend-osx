#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  TigerSend 1.8
#  LocalSend protocol v2 client for classic Mac OS X
#  Mac OS X 10.4 Tiger (PowerPC + Intel) and newer: Leopard, Snow Leopard,
#  Lion ... and any macOS that still ships a Python with Tk.
#
#  Design rules (they are the whole point of this file):
#    * runs on the stock /usr/bin/python of Mac OS X 10.4: Python 2.3.5
#    * runs on 2.4 / 2.5 / 2.6 / 2.7 (Leopard, Snow Leopard, Lion ...)
#    * runs on Python 3 too (so it can be tested on a modern machine, and
#      so it keeps working on macOS 12.3+ where /usr/bin/python is gone)
#    * no dependencies: only what ships with the system
#    * no syntax newer than Python 2.3 is used anywhere:
#         - no "with", no "except X as e", no ternary (a if b else c),
#           no generator expressions, no decorators, no set()/sorted(),
#           no dict comprehensions, no b'...' literals, and never "except"
#           and "finally" in the same try (that is Python 2.5+ only; the
#           file always nests:  try: <try/except> finally: <cleanup>)
#    * byte strings vs unicode: everything coming from the network, from a
#      filename or from a socket goes through to_text()/to_bytes()
#
#  Protocol: LocalSend v2 (https://github.com/localsend/protocol), plain
#  HTTP on port 53317, multicast discovery 224.0.0.167:53317.
#  Encryption must be OFF on the other device: Tiger/Leopard/Snow Leopard
#  cannot negotiate modern TLS 1.2/1.3, and Python 2.3/2.4/2.5 have no ssl
#  module at all.
#
#  License: MIT (see LICENSE)
#

import os
import sys
import time
import errno
import socket
import random
import mimetypes
import tempfile
import threading
import platform

APP_NAME        = 'TigerSend'
APP_VERSION     = '1.8'
APP_BUILD       = '2.0.8-10.4'
PROTO_VERSION   = '2.0'          # LocalSend protocol version we announce
API_BASE        = '/api/localsend/v2'
PORT            = 53317
MULTICAST_GROUP = '224.0.0.167'
CHUNK_SIZE      = 65536          # 64 KB: gentle with 2005 hardware
ANNOUNCE_EVERY  = 20.0           # seconds between multicast announcements
CONFIG_NAME     = '.tigersend_config.json'
DEFAULT_ALIAS   = 'TigerSend'
HTTP_USER_AGENT = APP_NAME + '/' + APP_VERSION

# ---------------------------------------------------------------------------
#  Python 2.3 .. 3.x compatibility layer
# ---------------------------------------------------------------------------
PY3 = sys.version_info[0] >= 3

if PY3:
    text_type = str
    binary_type = bytes
    integer_types = (int,)
    long_type = int
    _unichr = chr

    # No b'...' literals anywhere in this file: Python 2.3 cannot even parse
    # them, so the byte primitives are built at run time instead.
    EMPTY      = bytes()
    NL         = '\n'.encode('ascii')
    CRLF       = '\r\n'.encode('ascii')
    SEMI       = ';'.encode('ascii')
    SPACE      = ' '.encode('ascii')
    GZIP_MAGIC = '\x1f\x8b'.encode('latin-1')

    from io import BytesIO

    import queue as Queue
    import socketserver as SocketServer
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import unquote

    def _parse_qs(query):
        from urllib.parse import parse_qs as _parse_qs_impl
        return _parse_qs_impl(query)

    try:
        import tkinter as Tkinter
        import tkinter.filedialog as tkFileDialog
        import tkinter.messagebox as tkMessageBox
        HAVE_TK = 1
    except Exception:
        Tkinter = None
        tkFileDialog = None
        tkMessageBox = None
        HAVE_TK = 0
else:
    text_type = unicode            # noqa: F821  (Python 2 only)
    binary_type = str
    integer_types = (int, long)    # noqa: F821
    long_type = long               # noqa: F821
    _unichr = unichr               # noqa: F821

    EMPTY      = ''
    NL         = '\n'
    CRLF       = '\r\n'
    SEMI       = ';'
    SPACE      = ' '
    GZIP_MAGIC = '\x1f\x8b'

    try:
        from cStringIO import StringIO as BytesIO
    except ImportError:
        from StringIO import StringIO as BytesIO

    import Queue
    import SocketServer
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from urllib import unquote

    def _parse_qs(query):
        import cgi
        return cgi.parse_qs(query, keep_blank_values=1)

    try:
        import Tkinter
        import tkFileDialog
        import tkMessageBox
        HAVE_TK = 1
    except Exception:
        Tkinter = None
        tkFileDialog = None
        tkMessageBox = None
        HAVE_TK = 0


def _from_codepoint(code):
    """unicode character for a code point, on wide *and* narrow builds.

    Python 2.3/2.4 (Tiger, Leopard) are usually narrow builds: unichr() only
    accepts up to 0xffff there, so an emoji coming from a modern phone is
    kept as the UTF-16 surrogate pair instead of crashing the parser.
    """
    try:
        return _unichr(code)
    except Exception:
        pass
    code = code - 0x10000
    return _unichr(0xd800 + (code >> 10)) + _unichr(0xdc00 + (code & 0x3ff))


def _decode_bytes(value):
    """bytes -> unicode, never raises (UTF-8 first, then Latin-1)."""
    try:
        return value.decode('utf-8')
    except Exception:
        pass
    try:
        return value.decode('latin-1')
    except Exception:
        pass
    try:
        return value.decode('utf-8', 'replace')
    except Exception:
        return u''


def to_text(value):
    """Anything -> unicode text. Never raises."""
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        return _decode_bytes(value)
    try:
        return text_type(value)
    except Exception:
        pass
    try:
        return text_type(repr(value))
    except Exception:
        return u''


def to_bytes(value):
    """Anything -> byte string (UTF-8). Never raises."""
    if isinstance(value, binary_type):
        return value
    if not isinstance(value, text_type):
        value = to_text(value)
    try:
        return value.encode('utf-8')
    except Exception:
        pass
    try:
        return value.encode('utf-8', 'replace')
    except Exception:
        return EMPTY


def fsenc(path):
    """Path -> the str type that os.* wants on this Python (bytes on Py2)."""
    if PY3:
        if isinstance(path, str):
            return path
        return to_text(path)
    if isinstance(path, binary_type):
        return path
    encoding = 'utf-8'
    try:
        encoding = sys.getfilesystemencoding() or 'utf-8'
    except Exception:
        encoding = 'utf-8'
    try:
        return path.encode(encoding)
    except Exception:
        pass
    try:
        return path.encode('utf-8', 'replace')
    except Exception:
        return path


def log_text(fmt, *args):
    """u'...%s' % args, but bytes args are decoded instead of blowing up.

    On Tiger ``u'%s' % 'caf\\xc3\\xa9'`` raises UnicodeDecodeError, which used
    to abort transfers of files with non-ASCII names. Everything goes through
    to_text() here.
    """
    if not isinstance(fmt, text_type):
        fmt = to_text(fmt)
    cooked = []
    for arg in args:
        if isinstance(arg, text_type):
            cooked.append(arg)
        elif isinstance(arg, binary_type):
            # u'%s' % 'caf\xc3\xa9' raises UnicodeDecodeError on Tiger
            cooked.append(to_text(arg))
        else:
            # keep numbers, None, objects... so that %d / %f still work
            cooked.append(arg)
    try:
        return fmt % tuple(cooked)
    except Exception:
        return fmt


# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------
def write_out(text):
    """Write a line to stdout as UTF-8, on Python 2 and on Python 3."""
    data = to_bytes(text)
    try:
        stream = getattr(sys.stdout, 'buffer', None)
    except Exception:
        stream = None
    try:
        if stream is not None:
            stream.write(data)
            stream.flush()
        else:
            sys.stdout.write(data)
            sys.stdout.flush()
    except Exception:
        pass


def set_daemon(thread):
    """Make a thread daemon: thread.setDaemon(1) without the 3.10+ warning."""
    if sys.version_info[0] >= 3:
        try:
            setattr(thread, 'daemon', True)
            return
        except Exception:
            pass
    try:
        thread.setDaemon(1)
    except Exception:
        pass


def md5_hex(data):
    """MD5 hex digest using hashlib (2.5+) or the old md5 module (2.3/2.4)."""
    payload = to_bytes(data)
    try:
        import hashlib
        return hashlib.md5(payload).hexdigest()
    except Exception:
        pass
    try:
        import md5
        return md5.new(payload).hexdigest()
    except Exception:
        pass
    return _weak_hex(payload)


def _weak_hex(data):
    """Last-resort non-cryptographic digest (ids and fingerprint only)."""
    value = 2166136261
    for byte in data:
        if not isinstance(byte, int):
            byte = ord(byte)
        value = value ^ byte
        value = (value * 16777619) & 0xffffffff
    return '%08x' % value


_RANDOM = random.Random()


def random_hex(nbytes):
    """Hex id, 2 chars per byte. Tiger has no os.urandom, so mix everything."""
    seed = '%s-%s-%s-%s' % (time.time(), os.getpid(),
                            _RANDOM.randrange(0, 2147483647),
                            _RANDOM.randrange(0, 2147483647))
    digest = md5_hex(seed)
    while len(digest) < nbytes * 2:
        digest = digest + md5_hex(digest + seed)
    return digest[:nbytes * 2]


def human_size(count):
    try:
        size = float(count)
    except Exception:
        return u'?'
    if size >= 1073741824.0:
        return u'%.1f GB' % (size / 1073741824.0)
    if size >= 1048576.0:
        return u'%.1f MB' % (size / 1048576.0)
    if size >= 1024.0:
        return u'%.1f KB' % (size / 1024.0)
    return u'%d B' % int(size)


def timestamp():
    return time.strftime('%H:%M:%S')


def mac_os_version():
    """'10.4.11' style release string, or '' if it cannot be detected."""
    try:
        release = platform.mac_ver()[0]
        if release:
            return release
    except Exception:
        pass
    if sys.platform == 'darwin':
        try:
            return 'Darwin ' + os.uname()[2]
        except Exception:
            pass
    return ''


def os_label():
    """Short human label: 'Mac OS X 10.4.11' / 'Linux' / ..."""
    release = mac_os_version()
    if release[:7] == 'Darwin ':
        return u'Mac OS X %s' % release[7:]
    if release:
        return u'Mac OS X %s' % release
    if sys.platform == 'darwin':
        return u'Mac OS X'
    return to_text(platform.system() or sys.platform)


def arch_label():
    """'PowerPC' or 'Intel' (shown in the UI and announced to peers)."""
    machine = ''
    try:
        machine = platform.machine() or ''
    except Exception:
        machine = ''
    lowered = machine.lower()
    if lowered.find('power') >= 0 or lowered.find('ppc') >= 0:
        return u'PowerPC'
    if lowered in ('x86_64', 'amd64'):
        return u'Intel 64-bit'
    if lowered in ('i386', 'i486', 'i586', 'i686', 'x86'):
        return u'Intel'
    if machine:
        return to_text(machine)
    return u'universal'


def python_label():
    return u'Python %d.%d.%d' % (sys.version_info[0], sys.version_info[1],
                                 sys.version_info[2])


def local_ip():
    """Best guess of the primary IPv4 address, without needing internet."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except Exception:
        return '127.0.0.1'
    try:
        # A UDP connect() sends nothing: it only asks the kernel to pick the
        # outgoing interface. This works even with no internet connection.
        for target in ((MULTICAST_GROUP, PORT), ('8.8.8.8', 80)):
            try:
                sock.connect(target)
                address = sock.getsockname()[0]
                if address and address != '0.0.0.0':
                    return address
            except Exception:
                continue
        try:
            address = socket.gethostbyname(socket.gethostname())
            if address and not address.startswith('127.'):
                return address
        except Exception:
            pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return '127.0.0.1'


def guess_mime(path):
    try:
        guess = mimetypes.guess_type(path)[0]
        if guess:
            return to_text(guess)
    except Exception:
        pass
    return u'application/octet-stream'


def safe_filename(name):
    """Strip directories and control characters from a remote file name."""
    name = to_text(name).replace(u'\\', u'/')
    slash = name.rfind(u'/')
    if slash >= 0:
        name = name[slash + 1:]
    cleaned = []
    for char in name:
        code = ord(char)
        if char in (u':', u'/', u'\\') or code < 32 or code == 127:
            cleaned.append(u'_')
        else:
            cleaned.append(char)
    name = u''.join(cleaned).strip()
    if name in (u'', u'.', u'..'):
        name = u'received.bin'
    if len(name) > 200:
        extension = u''
        dot = name.rfind(u'.')
        if dot > 0 and len(name) - dot <= 12:
            extension = name[dot:]
        name = name[:200 - len(extension)] + extension
    return name


def unique_path(folder, name):
    """`folder/name`, `folder/name (1).ext`, ... returned as unicode."""
    folder = to_text(folder)
    name = to_text(name)
    candidate = os.path.join(folder, name)
    if not os.path.exists(fsenc(candidate)):
        return candidate
    base = name
    extension = u''
    dot = name.rfind(u'.')
    if dot > 0:
        base = name[:dot]
        extension = name[dot:]
    index = 1
    while index < 10000:
        candidate = os.path.join(folder, u'%s (%d)%s'
                                 % (base, index, extension))
        if not os.path.exists(fsenc(candidate)):
            return candidate
        index = index + 1
    return os.path.join(folder, u'%s-%s%s' % (base, random_hex(4), extension))


def ensure_folder(path):
    path = to_text(path)
    if not path:
        return False
    if os.path.isdir(fsenc(path)):
        return True
    try:
        os.makedirs(fsenc(path))
        return True
    except Exception:
        return os.path.isdir(fsenc(path))


def default_save_dir():
    home = os.path.expanduser('~')
    for candidate in ('Downloads', 'Desktop', ''):
        path = home
        if candidate:
            path = os.path.join(home, candidate)
        if os.path.isdir(fsenc(path)):
            return path
    return home


def config_path():
    try:
        return os.path.join(os.path.expanduser('~'), CONFIG_NAME)
    except Exception:
        return CONFIG_NAME


def load_config(path=None):
    if path is None:
        path = config_path()
    handle = None
    try:
        try:
            handle = open(fsenc(path), 'rb')
            raw = handle.read()
        except Exception:
            return {}
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
    try:
        config = json_loads(raw)
    except Exception:
        return {}
    if not isinstance(config, dict):
        return {}
    return config


def save_config(config, path=None):
    if path is None:
        path = config_path()
    data = to_bytes(json_dumps(config))
    handle = None
    temporary = path + '.tmp'
    try:
        try:
            handle = open(fsenc(temporary), 'wb')
            handle.write(data)
            handle.flush()
        except Exception:
            return False
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
    try:
        os.rename(fsenc(temporary), fsenc(path))
        return True
    except Exception:
        try:
            os.remove(fsenc(temporary))
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
#  Mini JSON codec
#
#  Python 2.6+ and Python 3 ship "json"; Tiger's 2.3 and Leopard's 2.4/2.5 do
#  not, so TigerSend always carries a small dependency-free codec and uses it
#  whenever the real module is missing or fails.
# ---------------------------------------------------------------------------
_JSON_SPECIAL = {
    u'"': u'\\"',
    u'\\': u'\\\\',
    u'\n': u'\\n',
    u'\r': u'\\r',
    u'\t': u'\\t',
    u'\b': u'\\b',
    u'\f': u'\\f',
}


def _json_quote(value):
    out = [u'"']
    for char in value:
        special = _JSON_SPECIAL.get(char)
        if special is not None:
            out.append(special)
            continue
        code = ord(char)
        if code < 0x20 or code > 0x7e:
            if code > 0xffff:
                # Non-BMP character: emit the UTF-16 surrogate pair, which is
                # what the json module and LocalSend expect.
                code = code - 0x10000
                out.append(u'\\u%04x\\u%04x'
                           % (0xd800 + (code >> 10), 0xdc00 + (code & 0x3ff)))
            else:
                out.append(u'\\u%04x' % code)
        else:
            out.append(char)
    out.append(u'"')
    return u''.join(out)


def _mini_dumps(value):
    if value is None:
        return u'null'
    if value is True:
        return u'true'
    if value is False:
        return u'false'
    if isinstance(value, integer_types):
        return u'%d' % value
    if isinstance(value, float):
        return u'%r' % value
    if isinstance(value, (text_type, binary_type)):
        return _json_quote(to_text(value))
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.append(_mini_dumps(item))
        return u'[' + u','.join(parts) + u']'
    if isinstance(value, dict):
        parts = []
        for key in value.keys():
            parts.append(_json_quote(to_text(key)) + u':'
                         + _mini_dumps(value[key]))
        return u'{' + u','.join(parts) + u'}'
    return _json_quote(to_text(value))


class JSONError(Exception):
    pass


class _MiniJSONParser(object):
    def __init__(self, text):
        self.text = to_text(text)
        self.pos = 0
        self.length = len(self.text)

    def fail(self, message):
        raise JSONError(u'%s at position %d' % (message, self.pos))

    def skip_space(self):
        while self.pos < self.length and self.text[self.pos] in u' \t\r\n':
            self.pos = self.pos + 1

    def parse(self):
        self.skip_space()
        value = self.parse_value()
        self.skip_space()
        return value

    def parse_value(self):
        self.skip_space()
        if self.pos >= self.length:
            self.fail(u'unexpected end of input')
        char = self.text[self.pos]
        if char == u'{':
            return self.parse_object()
        if char == u'[':
            return self.parse_array()
        if char == u'"':
            return self.parse_string()
        if self.text[self.pos:self.pos + 4] == u'true':
            self.pos = self.pos + 4
            return True
        if self.text[self.pos:self.pos + 5] == u'false':
            self.pos = self.pos + 5
            return False
        if self.text[self.pos:self.pos + 4] == u'null':
            self.pos = self.pos + 4
            return None
        return self.parse_number()

    def parse_object(self):
        result = {}
        self.pos = self.pos + 1
        self.skip_space()
        if self.pos < self.length and self.text[self.pos] == u'}':
            self.pos = self.pos + 1
            return result
        while 1:
            self.skip_space()
            if self.pos >= self.length or self.text[self.pos] != u'"':
                self.fail(u'expected a string key')
            key = self.parse_string()
            self.skip_space()
            if self.pos >= self.length or self.text[self.pos] != u':':
                self.fail(u'expected ":"')
            self.pos = self.pos + 1
            result[key] = self.parse_value()
            self.skip_space()
            if self.pos < self.length and self.text[self.pos] == u',':
                self.pos = self.pos + 1
                continue
            if self.pos < self.length and self.text[self.pos] == u'}':
                self.pos = self.pos + 1
                return result
            self.fail(u'expected "," or "}"')

    def parse_array(self):
        result = []
        self.pos = self.pos + 1
        self.skip_space()
        if self.pos < self.length and self.text[self.pos] == u']':
            self.pos = self.pos + 1
            return result
        while 1:
            result.append(self.parse_value())
            self.skip_space()
            if self.pos < self.length and self.text[self.pos] == u',':
                self.pos = self.pos + 1
                continue
            if self.pos < self.length and self.text[self.pos] == u']':
                self.pos = self.pos + 1
                return result
            self.fail(u'expected "," or "]"')

    def parse_string(self):
        self.pos = self.pos + 1
        out = []
        simple = {u'"': u'"', u'\\': u'\\', u'/': u'/',
                  u'b': u'\b', u'f': u'\f', u'n': u'\n',
                  u'r': u'\r', u't': u'\t'}
        while self.pos < self.length:
            char = self.text[self.pos]
            if char == u'"':
                self.pos = self.pos + 1
                return u''.join(out)
            if char == u'\\':
                self.pos = self.pos + 1
                if self.pos >= self.length:
                    self.fail(u'bad escape')
                escape = self.text[self.pos]
                replacement = simple.get(escape)
                if replacement is not None:
                    out.append(replacement)
                elif escape == u'u':
                    code = self.read_hex4()
                    if 0xd800 <= code <= 0xdbff:
                        # UTF-16 surrogate pair -> one real character
                        if self.text[self.pos + 1:self.pos + 3] == u'\\u':
                            saved = self.pos
                            self.pos = self.pos + 2
                            low = self.read_hex4()
                            if 0xdc00 <= low <= 0xdfff:
                                code = 0x10000 + ((code - 0xd800) << 10) \
                                    + (low - 0xdc00)
                            else:
                                self.pos = saved
                        out.append(_from_codepoint(code))
                    elif 0xdc00 <= code <= 0xdfff:
                        out.append(u'\ufffd')     # lone low surrogate
                    else:
                        out.append(_from_codepoint(code))
                else:
                    out.append(escape)
                self.pos = self.pos + 1
            else:
                out.append(char)
                self.pos = self.pos + 1
        self.fail(u'unterminated string')

    def read_hex4(self):
        digits = self.text[self.pos + 1:self.pos + 5]
        if len(digits) != 4:
            self.fail(u'bad \\u escape')
        try:
            value = int(digits, 16)
        except Exception:
            self.fail(u'bad \\u escape')
        self.pos = self.pos + 4
        return value

    def parse_number(self):
        start = self.pos
        while self.pos < self.length and \
                self.text[self.pos] in u'-+0123456789.eE':
            self.pos = self.pos + 1
        token = self.text[start:self.pos]
        if token == u'':
            self.fail(u'invalid value')
        try:
            if u'.' in token or u'e' in token or u'E' in token:
                return float(token)
            return int(token)
        except Exception:
            self.fail(u'bad number %s' % token)


try:
    import json as _json_module
except ImportError:
    _json_module = None


def json_dumps(value):
    """Serialize to unicode JSON text (ASCII only, safe on every codec)."""
    if _json_module is not None:
        try:
            return to_text(_json_module.dumps(value))
        except Exception:
            pass
    return _mini_dumps(value)


def json_loads(data):
    """Parse JSON from bytes or unicode. Raises JSONError on garbage."""
    text = to_text(data)
    if text[:1] == u'\ufeff':
        text = text[1:]
    text = text.strip()
    if text == u'':
        return {}
    if _json_module is not None:
        try:
            return _json_module.loads(text)
        except Exception:
            pass
    try:
        return _MiniJSONParser(text).parse()
    except JSONError:
        raise
    except Exception:
        raise JSONError(to_text(sys.exc_info()[1]))


# ---------------------------------------------------------------------------
#  Cancellation flag
#
#  threading.Event works on 2.3, but is_set()/isSet() changed across
#  versions; this tiny class behaves the same everywhere.
# ---------------------------------------------------------------------------
class CancelFlag(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.flag = 0

    def set(self):
        try:
            self.lock.acquire()
        except Exception:
            return
        try:
            self.flag = 1
        finally:
            self.lock.release()

    def clear(self):
        try:
            self.lock.acquire()
        except Exception:
            return
        try:
            self.flag = 0
        finally:
            self.lock.release()

    def is_set(self):
        return self.flag != 0

    # Python 2 spelling, used in a couple of places for symmetry with 2.3 code
    def isSet(self):
        return self.flag != 0


# ---------------------------------------------------------------------------
#  Raw-socket HTTP/1.1 client
#
#  httplib in Python 2.3/2.4/2.5 has no timeout argument, leaves chunked
#  bodies undecoded, cannot cancel an upload half way, and its API changed a
#  lot between 2.3 and 3.x. These 250 lines give us one code path everywhere:
#  timeouts, cancellation while streaming, chunked + gzip responses and
#  "100 Continue" interim responses.
# ---------------------------------------------------------------------------
class TransferCancelled(Exception):
    pass


class ConnectionClosed(Exception):
    pass


def send_all(sock, data):
    """sendall() that also behaves with the socket timeouts of 2.3/2.4."""
    total = len(data)
    sent = 0
    while sent < total:
        try:
            count = sock.send(data[sent:])
        except socket.error:
            error = sys.exc_info()[1]
            code = 0
            if error.args:
                code = error.args[0]
            if code in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                time.sleep(0.01)
                continue
            raise
        if count <= 0:
            raise ConnectionClosed(u'send() returned 0')
        sent = sent + count
    return sent


class SocketReader(object):
    """Buffered reader over a socket, with readline()/read(n)/read_all()."""

    def __init__(self, sock):
        self.sock = sock
        self.buffer = EMPTY

    def fill(self, wanted):
        count = 8192
        if wanted > 0:
            count = wanted
        chunk = self.sock.recv(count)
        if not chunk:
            raise ConnectionClosed(u'connection closed by peer')
        self.buffer = self.buffer + chunk

    def readline(self, limit=65536):
        while 1:
            position = self.buffer.find(NL)
            if position >= 0:
                line = self.buffer[:position + 1]
                self.buffer = self.buffer[position + 1:]
                return line
            if len(self.buffer) > limit:
                line = self.buffer
                self.buffer = EMPTY
                return line
            self.fill(8192)

    def read(self, count):
        while len(self.buffer) < count:
            self.fill(min(65536, count - len(self.buffer)))
        data = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return data

    def read_all(self):
        chunks = [self.buffer]
        self.buffer = EMPTY
        while 1:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                break
            except socket.error:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return EMPTY.join(chunks)


def decompress_body(body):
    """Transparently undo Content-Encoding: gzip/deflate when possible."""
    if not body:
        return body
    if body[:2] == GZIP_MAGIC:
        try:
            import gzip
            stream = gzip.GzipFile(fileobj=BytesIO(body))
            try:
                return stream.read()
            finally:
                stream.close()
        except Exception:
            return body
    try:
        import zlib
        try:
            return zlib.decompress(body)
        except Exception:
            pass
        try:
            return zlib.decompress(body, -15)
        except Exception:
            pass
    except ImportError:
        pass
    except Exception:
        pass
    return body


def read_chunked(reader):
    out = []
    while 1:
        line = reader.readline()
        if not line:
            break
        line = line.strip()
        if line == EMPTY:
            continue
        semi = line.find(SEMI)
        if semi >= 0:
            line = line[:semi]
        try:
            size = int(line, 16)
        except Exception:
            raise ConnectionClosed(u'bad chunk size')
        if size == 0:
            while 1:
                trailer = reader.readline()
                if not trailer or trailer.strip() == EMPTY:
                    break
            break
        out.append(reader.read(size))
        reader.read(2)          # CRLF after every chunk
    return EMPTY.join(out)


class HTTPResponse(object):
    def __init__(self, status, reason, headers, body):
        self.status = status
        self.reason = reason
        self.headers = headers
        self.body = body

    def header(self, name, default=''):
        return self.headers.get(name.lower(), default)

    def json(self):
        if not self.body:
            return {}
        return json_loads(self.body)

    def summary(self):
        excerpt = to_text(self.body)[:200].replace(u'\n', u' ')
        excerpt = excerpt.strip()
        if excerpt == u'':
            return u'HTTP %d %s' % (self.status, to_text(self.reason))
        return u'HTTP %d %s: %s' % (self.status, to_text(self.reason), excerpt)


def read_head(reader):
    line = reader.readline()
    while line and line.strip() == EMPTY:
        line = reader.readline()
    if not line:
        raise ConnectionClosed(u'empty response')
    parts = to_text(line.strip()).split(' ', 2)
    if len(parts) < 2 or parts[0][:5] != 'HTTP/':
        raise ConnectionClosed(u'bad status line: %s' % to_text(line.strip()))
    try:
        status = int(parts[1])
    except Exception:
        raise ConnectionClosed(u'bad status code')
    reason = u''
    if len(parts) > 2:
        reason = parts[2]
    headers = {}
    while 1:
        line = reader.readline()
        if not line:
            break
        if line.strip() == EMPTY:
            break
        text = to_text(line.strip())
        semi = text.find(u':')
        if semi < 0:
            continue
        name = text[:semi].strip().lower()
        value = text[semi + 1:].strip()
        if name in headers:
            headers[name] = headers[name] + u', ' + value
        else:
            headers[name] = value
    return status, reason, headers


def http_request(host, port, method, path, body=None, headers=None,
                 timeout=15.0, file_path=None, file_size=None,
                 cancel_flag=None, on_progress=None):
    """One HTTP/1.1 request over a plain socket. Returns an HTTPResponse."""
    if headers is None:
        headers = {}
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        sock.settimeout(timeout)
        sock.connect((host, int(port)))
        return http_exchange(sock, host, port, method, path, body, headers,
                             file_path, file_size, cancel_flag, on_progress)
    finally:
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass


def http_exchange(sock, host, port, method, path, body, headers, file_path,
                  file_size, cancel_flag, on_progress):
    if not path.startswith('/'):
        path = '/' + path
    lines = ['%s %s HTTP/1.1' % (method, path)]
    if port:
        lines.append('Host: %s:%d' % (host, int(port)))
    else:
        lines.append('Host: %s' % host)
    lines.append('User-Agent: ' + HTTP_USER_AGENT)
    lines.append('Accept: application/json')
    lines.append('Connection: close')
    if file_path is not None:
        lines.append('Content-Type: application/octet-stream')
        lines.append('Content-Length: %d' % long_type(file_size or 0))
    elif body is not None:
        lines.append('Content-Length: %d' % len(body))
    for name in headers.keys():
        lines.append('%s: %s' % (name, headers[name]))
    send_all(sock, to_bytes('\r\n'.join(lines) + '\r\n\r\n'))

    if file_path is not None:
        handle = None
        sent = 0
        try:
            try:
                handle = open(fsenc(file_path), 'rb')
            except Exception:
                raise
            while 1:
                if cancel_flag is not None and cancel_flag.is_set():
                    raise TransferCancelled()
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                send_all(sock, chunk)
                sent = sent + len(chunk)
                if on_progress is not None:
                    on_progress(sent, file_size or 0)
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        if file_size is not None and sent < int(file_size):
            raise ConnectionClosed(u'file shrank while sending')
    elif body:
        send_all(sock, body)

    reader = SocketReader(sock)
    while 1:
        status, reason, response_headers = read_head(reader)
        if 100 <= status < 200 and status != 101:
            continue          # interim "100 Continue": wait for the real one
        break

    transfer_encoding = response_headers.get('transfer-encoding', '')
    content_length = response_headers.get('content-length', '')
    if transfer_encoding.lower().find('chunked') >= 0:
        payload = read_chunked(reader)
    elif content_length:
        try:
            length = int(content_length)
        except Exception:
            length = 0
        if length > 0:
            payload = reader.read(length)
        else:
            payload = EMPTY
    elif status in (204, 304):
        payload = EMPTY
    else:
        payload = reader.read_all()

    encoding = response_headers.get('content-encoding', '').lower()
    if encoding in ('gzip', 'deflate') or payload[:2] == GZIP_MAGIC:
        payload = decompress_body(payload)
    return HTTPResponse(status, reason, response_headers, payload)


def http_json(host, port, method, path, payload=None, timeout=15.0,
              cancel_flag=None):
    body = None
    headers = {}
    if payload is not None:
        body = to_bytes(json_dumps(payload))
        headers['Content-Type'] = 'application/json'
    return http_request(host, port, method, path, body=body, headers=headers,
                        timeout=timeout, cancel_flag=cancel_flag)


def url_quote(value):
    """Percent-encode the bytes of `value` (only for query string values)."""
    out = []
    for byte in to_bytes(value):
        if not isinstance(byte, int):
            byte = ord(byte)
        char = chr(byte)
        if char.isalnum() or char in '-_.~':
            out.append(char)
        else:
            out.append('%%%02X' % byte)
    return ''.join(out)

# ---------------------------------------------------------------------------
#  Translations
# ---------------------------------------------------------------------------
LANG_ORDER = ['en', 'es', 'fr', 'de', 'pt']

LANG_LABELS = {
    'en': u'English',
    'es': u'Espa\u00f1ol',
    'fr': u'Fran\u00e7ais',
    'de': u'Deutsch',
    'pt': u'Portugu\u00eas',
}

TR = {
    'en': {
        'server_running':  u'Server: plain HTTP :%d - running',
        'server_error':    u'Server: ERROR - port %d busy',
        'name':            u'Name:',
        'apply':           u'Apply',
        'save_to':         u'Save to:',
        'change':          u'Change...',
        'devices':         u'Devices on this network',
        'col_name':        u'Name',
        'col_model':       u'Model',
        'col_address':     u'Address',
        'announce':        u'Announce / Refresh',
        'scan':            u'Scan network',
        'clear_log':       u'Clear log',
        'files_to_send':   u'Files to send',
        'add_file':        u'Add File...',
        'paste_clip':      u'Paste Clipboard',
        'remove':          u'Remove',
        'clear_list':      u'Clear List',
        'send_to':         u'Send to Device',
        'cancel_transfer': u'Cancel Transfer',
        'activity':        u'Activity',
        'ready':           u'Ready',
        'sending':         u'Sending...',
        'receiving':       u'Receiving...',
        'scanning':        u'Scanning...',
        'devcount':        u'%d device(s)',
        'language':        u'Language: %s',
        'enc_off':         u'HTTP :%d - Encryption OFF on the other device',
        'pick_device':     u'Select a device in the table first.',
        'pick_files':      u'Add at least one file to the queue.',
        'no_clip':         u'Clipboard is empty or has no text.',
        'choose_dir':      u'Choose download folder',
        'add_files_title': u'Add files',
        'add_file_title':  u'Add file',
        'system':          u'%s - %s',
        'progress':        u'%s / %s',
        'ready_hint':      u'Encryption OFF needed on the other device',
        'headless_start':  u'Headless mode: no window. Control-C quits.',
    },
    'es': {
        'server_running':  u'Servidor: HTTP plano :%d - activo',
        'server_error':    u'Servidor: ERROR - puerto %d ocupado',
        'name':            u'Nombre:',
        'apply':           u'Aplicar',
        'save_to':         u'Guardar en:',
        'change':          u'Cambiar...',
        'devices':         u'Dispositivos en esta red',
        'col_name':        u'Nombre',
        'col_model':       u'Modelo',
        'col_address':     u'Direcci\u00f3n',
        'announce':        u'Anunciar / Refrescar',
        'scan':            u'Escanear red',
        'clear_log':       u'Limpiar registro',
        'files_to_send':   u'Archivos a enviar',
        'add_file':        u'A\u00f1adir archivo...',
        'paste_clip':      u'Pegar portapapeles',
        'remove':          u'Quitar',
        'clear_list':      u'Vaciar lista',
        'send_to':         u'Enviar al equipo',
        'cancel_transfer': u'Cancelar env\u00edo',
        'activity':        u'Actividad',
        'ready':           u'Listo',
        'sending':         u'Enviando...',
        'receiving':       u'Recibiendo...',
        'scanning':        u'Escaneando...',
        'devcount':        u'%d equipo(s)',
        'language':        u'Idioma: %s',
        'enc_off':         u'HTTP :%d - Cifrado OFF en el otro equipo',
        'pick_device':     u'Selecciona primero un equipo en la tabla.',
        'pick_files':      u'A\u00f1ade al menos un archivo a la cola.',
        'no_clip':         u'El portapapeles est\u00e1 vac\u00edo o no tiene texto.',
        'choose_dir':      u'Elige la carpeta de descargas',
        'add_files_title': u'A\u00f1adir archivos',
        'add_file_title':  u'A\u00f1adir archivo',
        'system':          u'%s - %s',
        'progress':        u'%s / %s',
        'ready_hint':      u'El otro equipo necesita Cifrado OFF',
        'headless_start':  u'Modo sin ventana. Control-C para salir.',
    },
    'fr': {
        'server_running':  u'Serveur : HTTP simple :%d - actif',
        'server_error':    u'Serveur : ERREUR - port %d occup\u00e9',
        'name':            u'Nom :',
        'apply':           u'Appliquer',
        'save_to':         u'Enregistrer dans :',
        'change':          u'Changer...',
        'devices':         u'Appareils sur ce r\u00e9seau',
        'col_name':        u'Nom',
        'col_model':       u'Mod\u00e8le',
        'col_address':     u'Adresse',
        'announce':        u'Annoncer / Rafra\u00eechir',
        'scan':            u'Scanner le r\u00e9seau',
        'clear_log':       u'Effacer le journal',
        'files_to_send':   u'Fichiers \u00e0 envoyer',
        'add_file':        u'Ajouter fichier...',
        'paste_clip':      u'Coller presse-papiers',
        'remove':          u'Retirer',
        'clear_list':      u'Vider la liste',
        'send_to':         u'Envoyer \u00e0 l\u2019appareil',
        'cancel_transfer': u'Annuler le transfert',
        'activity':        u'Activit\u00e9',
        'ready':           u'Pr\u00eat',
        'sending':         u'Envoi...',
        'receiving':       u'R\u00e9ception...',
        'scanning':        u'Analyse...',
        'devcount':        u'%d appareil(s)',
        'language':        u'Langue : %s',
        'enc_off':         u'HTTP :%d - Chiffrement OFF sur l\u2019autre appareil',
        'pick_device':     u'S\u00e9lectionnez d\u2019abord un appareil dans la table.',
        'pick_files':      u'Ajoutez au moins un fichier \u00e0 la file.',
        'no_clip':         u'Le presse-papiers est vide ou sans texte.',
        'choose_dir':      u'Choisir le dossier de t\u00e9l\u00e9chargement',
        'add_files_title': u'Ajouter des fichiers',
        'add_file_title':  u'Ajouter un fichier',
        'system':          u'%s - %s',
        'progress':        u'%s / %s',
        'ready_hint':      u'Chiffrement OFF requis sur l\u2019autre appareil',
        'headless_start':  u'Mode sans fen\u00eatre. Control-C pour quitter.',
    },
    'de': {
        'server_running':  u'Server: reines HTTP :%d - l\u00e4uft',
        'server_error':    u'Server: FEHLER - Port %d belegt',
        'name':            u'Name:',
        'apply':           u'\u00dcbernehmen',
        'save_to':         u'Speichern in:',
        'change':          u'\u00c4ndern...',
        'devices':         u'Ger\u00e4te in diesem Netzwerk',
        'col_name':        u'Name',
        'col_model':       u'Modell',
        'col_address':     u'Adresse',
        'announce':        u'Ank\u00fcndigen / Aktualisieren',
        'scan':            u'Netzwerk scannen',
        'clear_log':       u'Protokoll l\u00f6schen',
        'files_to_send':   u'Zu sendende Dateien',
        'add_file':        u'Datei hinzuf\u00fcgen...',
        'paste_clip':      u'Zwischenablage einf\u00fcgen',
        'remove':          u'Entfernen',
        'clear_list':      u'Liste leeren',
        'send_to':         u'An Ger\u00e4t senden',
        'cancel_transfer': u'\u00dcbertragung abbrechen',
        'activity':        u'Aktivit\u00e4t',
        'ready':           u'Bereit',
        'sending':         u'Senden...',
        'receiving':       u'Empfangen...',
        'scanning':        u'Suche...',
        'devcount':        u'%d Ger\u00e4t(e)',
        'language':        u'Sprache: %s',
        'enc_off':         u'HTTP :%d - Verschl\u00fcsselung OFF am anderen Ger\u00e4t',
        'pick_device':     u'Bitte zuerst ein Ger\u00e4t in der Tabelle w\u00e4hlen.',
        'pick_files':      u'Mindestens eine Datei zur Warteschlange hinzuf\u00fcgen.',
        'no_clip':         u'Zwischenablage ist leer oder enth\u00e4lt keinen Text.',
        'choose_dir':      u'Download-Ordner w\u00e4hlen',
        'add_files_title': u'Dateien hinzuf\u00fcgen',
        'add_file_title':  u'Datei hinzuf\u00fcgen',
        'system':          u'%s - %s',
        'progress':        u'%s / %s',
        'ready_hint':      u'Verschl\u00fcsselung OFF am anderen Ger\u00e4t n\u00f6tig',
        'headless_start':  u'Modus ohne Fenster. Control-C beendet.',
    },
    'pt': {
        'server_running':  u'Servidor: HTTP simples :%d - ativo',
        'server_error':    u'Servidor: ERRO - porta %d ocupada',
        'name':            u'Nome:',
        'apply':           u'Aplicar',
        'save_to':         u'Salvar em:',
        'change':          u'Mudar...',
        'devices':         u'Dispositivos nesta rede',
        'col_name':        u'Nome',
        'col_model':       u'Modelo',
        'col_address':     u'Endere\u00e7o',
        'announce':        u'Anunciar / Atualizar',
        'scan':            u'Varrer a rede',
        'clear_log':       u'Limpar registro',
        'files_to_send':   u'Arquivos a enviar',
        'add_file':        u'Adicionar arquivo...',
        'paste_clip':      u'Colar \u00e1rea de transf.',
        'remove':          u'Remover',
        'clear_list':      u'Limpar lista',
        'send_to':         u'Enviar ao aparelho',
        'cancel_transfer': u'Cancelar envio',
        'activity':        u'Atividade',
        'ready':           u'Pronto',
        'sending':         u'Enviando...',
        'receiving':       u'Recebendo...',
        'scanning':        u'Varrendo...',
        'devcount':        u'%d aparelho(s)',
        'language':        u'Idioma: %s',
        'enc_off':         u'HTTP :%d - Criptografia OFF no outro aparelho',
        'pick_device':     u'Selecione primeiro um aparelho na tabela.',
        'pick_files':      u'Adicione pelo menos um arquivo \u00e0 fila.',
        'no_clip':         u'A \u00e1rea de transf. est\u00e1 vazia ou sem texto.',
        'choose_dir':      u'Escolher pasta de downloads',
        'add_files_title': u'Adicionar arquivos',
        'add_file_title':  u'Adicionar arquivo',
        'system':          u'%s - %s',
        'progress':        u'%s / %s',
        'ready_hint':      u'Criptografia OFF necess\u00e1ria no outro aparelho',
        'headless_start':  u'Modo sem janela. Control-C para sair.',
    },
}


def translate(lang, key, *args):
    table = TR.get(lang)
    if table is None:
        table = TR['en']
    text = table.get(key)
    if text is None:
        text = TR['en'].get(key, u'')
    if args:
        return log_text(text, *args)
    return text


# ---------------------------------------------------------------------------
#  Transfer engine (no Tkinter in here: this half runs headless, and it is
#  what the test suite exercises under Python 2.3/2.7/3.x)
# ---------------------------------------------------------------------------
class Session(object):
    def __init__(self, session_id, sender_info, sender_ip):
        self.session_id = session_id
        self.sender_info = sender_info
        self.sender_ip = sender_ip
        self.files = {}
        self.created = time.time()
        self.pending = 0

    def add(self, file_id, name, size, mime, token):
        self.files[file_id] = {
            'fileName': name,
            'size': size,
            'fileType': mime,
            'token': token,
            'received': 0,
        }


class TigerSendEngine(object):
    """LocalSend v2 device: HTTP server + multicast discovery + client."""

    def __init__(self, alias=None, save_dir=None, port=PORT, cfg_file=None,
                 echo=0):
        self.port = int(port)
        self.cfg_file = cfg_file
        if self.cfg_file is None:
            self.cfg_file = config_path()
        self.echo = echo

        config = load_config(self.cfg_file)
        lang = to_text(config.get('lang') or 'en')
        if lang not in LANG_ORDER:
            lang = 'en'
        self.lang = lang

        alias = to_text(alias or config.get('alias') or DEFAULT_ALIAS).strip()
        if alias == u'':
            alias = DEFAULT_ALIAS
        self.alias = alias

        fingerprint = to_text(config.get('fingerprint') or '')
        if len(fingerprint) < 16:
            fingerprint = md5_hex('%s-%s-%s' % (self.alias, time.time(),
                                                random_hex(8)))
        self.fingerprint = fingerprint

        save_dir = to_text(save_dir or config.get('save_dir') or '')
        if save_dir:
            # An explicit --save-dir may point at a folder that does not
            # exist yet: create it instead of silently falling back to $HOME.
            ensure_folder(save_dir)
        if save_dir == u'' or not os.path.isdir(fsenc(save_dir)):
            save_dir = default_save_dir()
        self.save_dir = save_dir

        self.os_version = mac_os_version()
        self.arch = arch_label()
        self.my_ip = local_ip()

        self.lock = threading.RLock()
        self.devices = []          # list of dicts
        self.sessions = {}         # sessionId -> Session
        self.files = []            # outbound queue (unicode paths)
        self.running = 0
        self.server = None
        self.server_ok = 0
        self.udp_sock = None
        self.status = 'ready'
        self.cancel_flag = CancelFlag()
        self.transferring = 0
        self.last_announce = 0.0
        self.threads = []
        self.registered = {}       # fingerprint -> last register time

        # callbacks, set by the GUI (all optional)
        self.on_log = None
        self.on_status = None
        self.on_devices = None
        self.on_progress = None

        self.save_config()

    # ----- callbacks used by the GUI and by the tests --------------------
    def log(self, message):
        text = to_text(message)
        if self.on_log is not None:
            try:
                self.on_log(text)
            except Exception:
                pass
        if self.echo:
            self.echo_line(u'[%s] %s' % (timestamp(), text))

    def echo_line(self, text):
        data = to_bytes(to_text(text) + u'\n')
        try:
            stream = getattr(sys.stdout, 'buffer', None)
            if stream is not None:
                stream.write(data)
                stream.flush()
            else:
                sys.stdout.write(data)
                sys.stdout.flush()
        except Exception:
            pass

    def set_status(self, key):
        self.status = key
        if self.on_status is not None:
            try:
                self.on_status(key)
            except Exception:
                pass

    def notify_devices(self):
        if self.on_devices is not None:
            try:
                self.on_devices()
            except Exception:
                pass

    def publish_progress(self, done, total):
        if self.on_progress is not None:
            try:
                self.on_progress(done, total)
            except Exception:
                pass

    # ----- configuration --------------------------------------------------
    def save_config(self):
        save_config({
            'alias': self.alias,
            'lang': self.lang,
            'save_dir': self.save_dir,
            'fingerprint': self.fingerprint,
            'port': self.port,
            'app_version': APP_VERSION,
        }, self.cfg_file)

    def set_alias(self, alias):
        alias = to_text(alias).strip()
        if alias == u'':
            return self.alias
        self.alias = alias
        self.save_config()
        self.log(u'Alias changed to "%s" - re-announcing' % alias)
        self.announce()
        return self.alias

    def set_language(self, lang):
        if lang in LANG_ORDER:
            self.lang = lang
            self.save_config()
        return self.lang

    def set_save_dir(self, path):
        path = to_text(path)
        if path and ensure_folder(path):
            self.save_dir = path
            self.save_config()
            self.log(u'Download folder: %s' % path)
            return True
        return False

    # ----- identity -------------------------------------------------------
    def model_name(self):
        arch = self.arch
        if self.os_version:
            return u'Mac OS X %s (%s)' % (self.os_version, arch)
        return u'Mac (%s)' % arch

    def device_info(self, announce=0):
        return {
            'alias': self.alias,
            'version': PROTO_VERSION,
            'deviceModel': self.model_name(),
            'deviceType': 'desktop',
            'fingerprint': self.fingerprint,
            'port': self.port,
            'protocol': 'http',
            'download': False,
            'announce': bool(announce),
        }

    def remember_device(self, info, ip):
        """Add/update a peer from its info dict. Returns True if it is new."""
        if not isinstance(info, dict):
            return False
        fingerprint = to_text(info.get('fingerprint') or '')
        if fingerprint == u'' or fingerprint == self.fingerprint:
            return False
        alias = to_text(info.get('alias') or u'?')
        model = to_text(info.get('deviceModel') or info.get('deviceType')
                        or u'?')
        try:
            peer_port = int(info.get('port') or self.port)
        except Exception:
            peer_port = self.port
        protocol = to_text(info.get('protocol') or 'http').lower()
        is_new = False
        try:
            self.lock.acquire()
        except Exception:
            self.lock = None
        try:
            for device in self.devices:
                if device['fingerprint'] == fingerprint:
                    device['alias'] = alias
                    device['model'] = model
                    device['ip'] = ip
                    device['port'] = peer_port
                    device['protocol'] = protocol
                    device['last_seen'] = time.time()
                    break
            else:
                self.devices.append({
                    'fingerprint': fingerprint,
                    'alias': alias,
                    'model': model,
                    'ip': ip,
                    'port': peer_port,
                    'protocol': protocol,
                    'last_seen': time.time(),
                })
                is_new = True
        finally:
            if self.lock is not None:
                try:
                    self.lock.release()
                except Exception:
                    pass
        if is_new:
            self.log(u'++ discovered: %s (%s) at %s:%d'
                     % (alias, model, ip, peer_port))
            if protocol not in ('http', ''):
                self.log(u'!! %s announces "%s": turn Encryption OFF there '
                         u'(this Mac can only do plain HTTP)' % (alias,
                                                                 protocol))
        self.notify_devices()
        return isinstance(info, dict)

    def device_count(self):
        return len(self.devices)

    # ----- server lifecycle ----------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = 1
        self.start_server()
        self.start_udp_listener()
        self.start_announcer()

    def stop(self):
        self.running = 0
        self.cancel_flag.set()
        sock = self.udp_sock
        self.udp_sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        server = self.server
        self.server = None
        if server is not None:
            # shutdown() only exists from Python 2.6: on Tiger the listening
            # socket is closed instead and the daemon thread simply ends.
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass

    def start_server(self):
        try:
            server = ThreadedHTTPServer(('', self.port), TigerSendHandler,
                                        self)
        except Exception:
            error = sys.exc_info()[1]
            self.server_ok = 0
            self.log(u'!! HTTP server could not start on port %d: %s'
                     % (self.port, to_text(error)))
            self.log(u'!! Quit other LocalSend/TigerSend copies and relaunch.')
            return 0
        if self.port == 0:
            # Python 2.3 does not update HTTPServer.server_address after
            # binding, so ask the socket itself (server.server_port works
            # on 2.3 as well, but the socket is the ground truth).
            chosen = 0
            try:
                chosen = server.server_port
            except Exception:
                chosen = 0
            if not chosen:
                try:
                    chosen = server.socket.getsockname()[1]
                except Exception:
                    chosen = 0
            if chosen:
                self.port = chosen
        self.server = server
        self.server_ok = 1
        thread = threading.Thread(target=server.serve_forever)
        set_daemon(thread)
        thread.start()
        self.threads.append(thread)
        self.log(u'HTTP server listening on 0.0.0.0:%d (plain HTTP, no TLS)'
                 % self.port)
        return 1

    def start_udp_listener(self):
        thread = threading.Thread(target=self.udp_loop)
        set_daemon(thread)
        thread.start()
        self.threads.append(thread)

    def start_announcer(self):
        thread = threading.Thread(target=self.announce_loop)
        set_daemon(thread)
        thread.start()
        self.threads.append(thread)

    # ----- multicast discovery -------------------------------------------
    def join_multicast(self, sock):
        """Join 224.0.0.167 on every local address we can think of."""
        candidates = []
        if self.my_ip and self.my_ip != '127.0.0.1':
            candidates.append(self.my_ip)
        candidates.append('0.0.0.0')
        for interface in candidates:
            try:
                membership = socket.inet_aton(MULTICAST_GROUP) \
                    + socket.inet_aton(interface)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                membership)
                return interface
            except Exception:
                continue
        return None

    def udp_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, 'SO_REUSEPORT'):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            sock.bind(('', self.port))
            interface = self.join_multicast(sock)
            sock.settimeout(1.0)
        except Exception:
            error = sys.exc_info()[1]
            self.log(u'!! UDP discovery disabled: %s' % to_text(error))
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            return
        self.udp_sock = sock
        if interface:
            self.log(u'Multicast listener on %s:%d (interface %s)'
                     % (MULTICAST_GROUP, self.port, interface))
        else:
            self.log(u'!! Multicast join failed; use "Scan network" instead')
        while self.running:
            try:
                data, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except socket.error:
                if not self.running:
                    break
                continue
            try:
                message = json_loads(data)
            except Exception:
                continue
            if not isinstance(message, dict):
                continue
            if to_text(message.get('fingerprint') or '') == self.fingerprint:
                continue
            sender_ip = address[0]
            if message.get('announce'):
                self.remember_device(message, sender_ip)
                self.register_back(sender_ip, message)
            else:
                self.remember_device(message, sender_ip)
        try:
            sock.close()
        except Exception:
            pass

    def register_back(self, ip, info):
        """Answer an announcement over HTTP so the peer learns about us."""
        fingerprint = to_text(info.get('fingerprint') or '')
        now = time.time()
        last = self.registered.get(fingerprint, 0)
        if now - last < 3.0:
            return
        self.registered[fingerprint] = now
        try:
            peer_port = int(info.get('port') or self.port)
        except Exception:
            peer_port = self.port
        thread = threading.Thread(target=self.register_back_worker,
                                  args=(ip, peer_port))
        set_daemon(thread)
        thread.start()

    def register_back_worker(self, ip, peer_port):
        try:
            response = http_json(ip, peer_port, 'POST',
                                 API_BASE + '/register',
                                 self.device_info(0), timeout=5.0)
        except Exception:
            return
        if response.status == 200:
            try:
                self.remember_device(response.json(), ip)
            except Exception:
                pass

    def announce_loop(self):
        # first announcement right away, then every ANNOUNCE_EVERY seconds
        while self.running:
            try:
                if time.time() - self.last_announce >= ANNOUNCE_EVERY:
                    self.send_announcement(quiet=1)
            except Exception:
                pass
            time.sleep(1.0)

    def announce(self):
        thread = threading.Thread(target=self.send_announcement)
        set_daemon(thread)
        thread.start()

    def send_announcement(self, quiet=0):
        payload = to_bytes(json_dumps(self.device_info(1)))
        sock = None
        try:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                     socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.IPPROTO_IP,
                                    socket.IP_MULTICAST_TTL, 1)
                except Exception:
                    pass
                # macOS/BSD: without IP_MULTICAST_IF, sendto() may fail with
                # [Errno 49] on machines with several interfaces.
                if self.my_ip and self.my_ip != '127.0.0.1':
                    try:
                        sock.setsockopt(socket.IPPROTO_IP,
                                        socket.IP_MULTICAST_IF,
                                        socket.inet_aton(self.my_ip))
                    except Exception:
                        pass
                count = 0
                while count < 3:
                    sock.sendto(payload, (MULTICAST_GROUP, self.port))
                    count = count + 1
                    time.sleep(0.15)
                self.last_announce = time.time()
                if not quiet:
                    self.log(u'-> announce sent to %s:%d (x3)'
                             % (MULTICAST_GROUP, self.port))
            except Exception:
                error = sys.exc_info()[1]
                if not quiet:
                    self.log(u'!! announce failed: %s' % to_text(error))
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def announce_now(self):
        self.send_announcement()

    def scan_network(self):
        self.set_status('scanning')
        thread = threading.Thread(target=self.scan_worker)
        set_daemon(thread)
        thread.start()

    def scan_worker(self):
        base = local_ip()
        dot = base.rfind('.')
        if dot < 0:
            self.log(u'!! cannot determine the local subnet (no IP?)')
            self.set_status('ready')
            return
        self.my_ip = base
        prefix = base[:dot + 1]
        targets = Queue.Queue()
        index = 1
        while index < 255:
            address = '%s%d' % (prefix, index)
            if address != base:
                targets.put(address)
            index = index + 1
        self.log(u'Scanning %s0/24 on TCP :%d ...' % (prefix, self.port))
        workers = []
        worker_index = 0
        while worker_index < 12:
            thread = threading.Thread(target=self.scan_worker_one,
                                      args=(targets,))
            set_daemon(thread)
            thread.start()
            workers.append(thread)
            worker_index = worker_index + 1
        for thread in workers:
            thread.join(30.0)
        self.log(u'Scan finished: %d device(s) known' % self.device_count())
        self.set_status('ready')

    def scan_worker_one(self, targets):
        while 1:
            try:
                address = targets.get_nowait()
            except Queue.Empty:
                return
            self.probe(address)

    def probe(self, ip):
        try:
            response = http_request(ip, self.port, 'GET', API_BASE + '/info',
                                     timeout=0.7)
        except Exception:
            return
        if response.status != 200:
            return
        try:
            info = response.json()
        except Exception:
            return
        self.remember_device(info, ip)

    # ----- receiving ------------------------------------------------------
    def new_session(self, sender_info, sender_ip):
        session_id = random_hex(16)
        session = Session(session_id, sender_info, sender_ip)
        try:
            self.lock.acquire()
        except Exception:
            self.lock = None
        try:
            self.sessions[session_id] = session
        finally:
            if self.lock is not None:
                try:
                    self.lock.release()
                except Exception:
                    pass
        return session

    def get_session(self, session_id):
        if self.lock is not None:
            try:
                self.lock.acquire()
            except Exception:
                pass
        try:
            return self.sessions.get(session_id)
        finally:
            if self.lock is not None:
                try:
                    self.lock.release()
                except Exception:
                    pass

    def drop_session(self, session_id):
        if self.lock is not None:
            try:
                self.lock.acquire()
            except Exception:
                pass
        try:
            if session_id in self.sessions:
                del self.sessions[session_id]
                return True
        finally:
            if self.lock is not None:
                try:
                    self.lock.release()
                except Exception:
                    pass
        return False

    def prune_sessions(self):
        """Forget sessions nobody finished (crashed senders, new transfers)."""
        now = time.time()
        stale = []
        if self.lock is not None:
            try:
                self.lock.acquire()
            except Exception:
                pass
        try:
            for session_id in self.sessions.keys():
                session = self.sessions[session_id]
                if now - session.created > 1800:
                    stale.append(session_id)
            for session_id in stale:
                del self.sessions[session_id]
        finally:
            if self.lock is not None:
                try:
                    self.lock.release()
                except Exception:
                    pass
        return stale

    def receive_upload(self, session, file_id, dest_dir):
        """Open the destination file for one incoming upload."""
        entry = session.files.get(file_id)
        if entry is None:
            return None, None
        if not ensure_folder(dest_dir):
            return None, None
        name = safe_filename(entry.get('fileName') or file_id)
        destination = unique_path(dest_dir, name)
        handle = open(fsenc(destination + u'.part'), 'wb')
        return destination, handle

    # ----- sending --------------------------------------------------------
    def send_files(self, device, paths):
        """Blocking send (the UI runs it in a thread). Returns (ok, total)."""
        self.cancel_flag.clear()
        self.transferring = 1
        self.set_status('sending')
        try:
            return self.send_files_worker(device, paths)
        finally:
            self.transferring = 0
            self.set_status('ready')

    def send_files_worker(self, device, paths):
        ip = device['ip']
        port = device.get('port') or self.port
        alias = device.get('alias') or ip
        paths = [to_text(path) for path in paths]
        self.log(u'-> prepare-upload to %s (%s:%d), %d file(s)'
                 % (alias, ip, port, len(paths)))

        order = []
        metadata = {}
        index = 0
        for path in paths:
            index = index + 1
            file_id = 'f%d_%s' % (index, md5_hex(to_bytes(path))[:8])
            try:
                size = os.path.getsize(fsenc(path))
            except Exception:
                size = 0
            metadata[file_id] = {
                'id': file_id,
                'fileName': to_text(os.path.basename(fsenc(path))),
                'size': size,
                'fileType': guess_mime(path),
                'path': path,
            }
            order.append(file_id)

        wire_files = {}
        for file_id in order:
            wire_files[file_id] = {
                'id': file_id,
                'fileName': metadata[file_id]['fileName'],
                'size': metadata[file_id]['size'],
                'fileType': metadata[file_id]['fileType'],
            }

        try:
            response = http_json(ip, port, 'POST',
                                 API_BASE + '/prepare-upload',
                                 {'info': self.device_info(0),
                                  'files': wire_files}, timeout=20.0)
        except Exception:
            error = sys.exc_info()[1]
            self.log(u'!! prepare-upload failed: %s' % to_text(error))
            self.log(u'!! The other device must have Encryption OFF (plain '
                     u'HTTP). Check that it is the same Wi-Fi network.')
            return 0, len(order)

        if response.status == 204:
            self.log(u'-- %s accepted nothing (204): transfer declined or '
                     u'empty' % alias)
            return 0, len(order)
        if response.status == 403:
            self.log(u'!! transfer rejected by %s' % alias)
            return 0, len(order)
        if response.status != 200:
            self.log(u'!! prepare-upload: %s' % response.summary())
            self.log(u'!! Is Encryption OFF on %s? This Mac can only use '
                     u'plain HTTP.' % alias)
            return 0, len(order)

        try:
            answer = response.json()
            session_id = to_text(answer.get('sessionId') or '')
            tokens = answer.get('files') or {}
        except Exception:
            self.log(u'!! bad prepare-upload answer: %s'
                     % to_text(response.body)[:200])
            return 0, len(order)
        if session_id == u'':
            self.log(u'!! prepare-upload answer has no sessionId')
            return 0, len(order)

        sent = 0
        for file_id in order:
            if self.cancel_flag.is_set():
                break
            token = tokens.get(file_id) or tokens.get(to_bytes(file_id))
            if token is None:
                self.log(u'-- %s did not ask for "%s", skipping'
                         % (alias, metadata[file_id]['fileName']))
                continue
            if self.upload_one(ip, port, session_id, file_id, token,
                               metadata[file_id]):
                sent = sent + 1
            else:
                break

        if self.cancel_flag.is_set():
            self.cancel_remote(ip, port, session_id)
            self.log(u'xx transfer cancelled (%d/%d sent)'
                     % (sent, len(order)))
        else:
            self.log(u'== done: %d/%d file(s) sent to %s'
                     % (sent, len(order), alias))
        return sent, len(order)

    def upload_one(self, ip, port, session_id, file_id, token, metadata):
        path = metadata['path']
        name = metadata['fileName']
        size = metadata['size']
        self.log(u'-> uploading "%s" (%s)...' % (name, human_size(size)))
        reported = [0]

        def progress(done, total):
            percent = 0
            if total:
                percent = int(done * 100 / total)
            if percent >= reported[0] + 25 or done >= total:
                reported[0] = percent
                self.log(u'   %s %d%%' % (name, percent))
            self.publish_progress(done, total)

        url = (API_BASE + '/upload?sessionId=%s&fileId=%s&token=%s'
               % (url_quote(session_id), url_quote(file_id),
                  url_quote(token)))
        try:
            response = http_request(ip, port, 'POST', url,
                                    file_path=path, file_size=size,
                                    timeout=120.0,
                                    cancel_flag=self.cancel_flag,
                                    on_progress=progress)
        except TransferCancelled:
            self.log(u'xx upload of "%s" cancelled' % name)
            return 0
        except Exception:
            error = sys.exc_info()[1]
            self.log(u'!! upload "%s" failed: %s' % (name, to_text(error)))
            return 0
        if response.status != 200:
            self.log(u'!! upload "%s": %s' % (name, response.summary()))
            return 0
        self.log(u'ok "%s" uploaded' % name)
        return 1

    def cancel_remote(self, ip, port, session_id):
        if not session_id:
            return
        try:
            http_json(ip, port, 'POST',
                      API_BASE + '/cancel?sessionId=' + url_quote(session_id),
                      {}, timeout=5.0)
        except Exception:
            pass

    def cancel_transfer(self):
        self.cancel_flag.set()
        self.log(u'Cancel requested...')


# ---------------------------------------------------------------------------
#  HTTP server side (LocalSend v2 endpoints)
# ---------------------------------------------------------------------------
class ThreadedHTTPServer(SocketServer.ThreadingMixIn, HTTPServer):
    allow_reuse_address = 1
    daemon_threads = 1

    def __init__(self, address, handler, engine):
        self.engine = engine
        HTTPServer.__init__(self, address, handler)

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        try:
            client = ''
            if client_address:
                client = client_address[0]
            self.engine.log(u'!! connection from %s dropped: %s'
                            % (client, to_text(error)))
        except Exception:
            pass


def split_path(raw):
    """'/x/y?a=1' -> ('/x/y', 'a=1'). No urlparse dependency needed."""
    question = raw.find('?')
    if question < 0:
        return raw, ''
    return raw[:question], raw[question + 1:]


def query_value(query, name):
    try:
        values = _parse_qs(query)
    except Exception:
        return ''
    value = values.get(name)
    if isinstance(value, (list, tuple)):
        if value:
            return to_text(value[0])
        return ''
    if isinstance(value, (text_type, binary_type)):
        return to_text(value)
    return ''


class TigerSendHandler(BaseHTTPRequestHandler):
    server_version = APP_NAME + '/' + APP_VERSION
    sys_version = ''
    # HTTP/1.1 is required for the stdlib to answer "Expect: 100-continue"
    # on Python 2.4+ (iOS and Dart send it for big uploads).
    protocol_version = 'HTTP/1.1'

    # ----- plumbing -------------------------------------------------------
    def setup(self):
        BaseHTTPRequestHandler.setup(self)
        try:
            self._continue_sent = 0
        except Exception:
            pass
        try:
            # Do not let a vanished phone keep a thread blocked forever.
            self.connection.settimeout(120.0)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        pass                       # the activity log has all the detail

    def header(self, name, default=''):
        value = None
        try:
            value = self.headers.get(name)
        except Exception:
            value = None
        if value is None:
            try:
                value = self.headers.getheader(name)
            except Exception:
                value = None
        if value is None:
            return default
        return to_text(value)

    def engine(self):
        return self.server.engine

    def send_payload(self, code, payload, content_type):
        body = to_bytes(payload)
        try:
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass
        self.close_connection = 1

    def send_json(self, code, payload):
        self.send_payload(code, json_dumps(payload), 'application/json')

    def send_text(self, code, text):
        self.send_payload(code, text, 'text/plain; charset=utf-8')

    def send_empty(self, code):
        try:
            self.send_response(code)
            if code != 204 and code != 304:
                self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
        except Exception:
            pass
        self.close_connection = 1

    def handle_expect_100(self):
        # Python 2.4+ calls this; 2.3 has no such hook and sends it manually
        # from maybe_continue().
        self._continue_sent = 1
        try:
            self.send_response_only(100)
        except Exception:
            try:
                self.send_response(100)
            except Exception:
                return 0
        try:
            self.end_headers()
        except Exception:
            pass
        return 1

    def maybe_continue(self):
        if getattr(self, '_continue_sent', 0):
            return
        if self.header('expect').lower().find('100-continue') < 0:
            return
        self._continue_sent = 1
        try:
            self.wfile.write(to_bytes('HTTP/1.1 100 Continue\r\n\r\n'))
            self.wfile.flush()
        except Exception:
            pass

    def is_chunked(self):
        encoding = self.header('transfer-encoding').lower()
        return encoding.find('chunked') >= 0

    def content_length(self):
        try:
            return long_type(self.header('content-length') or '0')
        except Exception:
            return 0

    def read_body(self, limit=33554432):
        """Read the whole request body (chunked or Content-Length)."""
        self.maybe_continue()
        if self.is_chunked():
            try:
                body = read_chunked(self.rfile)
            except Exception:
                return EMPTY
            if len(body) > limit:
                return EMPTY
            return body
        length = self.content_length()
        if length <= 0:
            return EMPTY
        if length > limit:
            return EMPTY
        pieces = []
        remaining = length
        while remaining > 0:
            try:
                piece = self.rfile.read(min(CHUNK_SIZE, remaining))
            except Exception:
                break
            if not piece:
                break
            pieces.append(piece)
            remaining = remaining - len(piece)
        return EMPTY.join(pieces)

    # ----- endpoints ------------------------------------------------------
    def do_GET(self):
        path, query = split_path(self.path)
        engine = self.engine()
        if path in (API_BASE + '/info', '/api/localsend/v1/info'):
            self.send_json(200, engine.device_info(0))
        elif path in ('/', '/index.html'):
            pending = u''
            try:
                pending = u'\n%d file(s) queued' % len(engine.files)
            except Exception:
                pending = u''
            self.send_text(200, u'%s %s\n%s\nHTTP :%d, plain HTTP, '
                                u'encryption OFF%s\n'
                           % (APP_NAME, APP_VERSION, engine.model_name(),
                              engine.port, pending))
        elif path == API_BASE + '/download':
            self.send_empty(403)      # we do not offer the download API
        else:
            self.send_json(404, {'message': 'not found'})

    def do_POST(self):
        path, query = split_path(self.path)
        if path == API_BASE + '/register':
            self.handle_register()
        elif path == API_BASE + '/prepare-upload':
            self.handle_prepare_upload()
        elif path == API_BASE + '/upload':
            self.handle_upload(query)
        elif path == API_BASE + '/cancel':
            self.handle_cancel(query)
        else:
            try:
                self.read_body(65536)
            except Exception:
                pass
            self.send_json(404, {'message': 'not found'})

    def handle_register(self):
        engine = self.engine()
        body = self.read_body()
        info = {}
        if body:
            try:
                info = json_loads(body)
            except Exception:
                info = {}
        if isinstance(info, dict) and info:
            alias = to_text(info.get('alias') or u'?')
            engine.remember_device(info, self.client_address[0])
            engine.log(u'<- register from %s (%s)'
                       % (alias, self.client_address[0]))
        self.send_json(200, engine.device_info(0))

    def handle_prepare_upload(self):
        engine = self.engine()
        body = self.read_body()
        try:
            payload = json_loads(body)
        except Exception:
            engine.log(u'!! prepare-upload with invalid JSON')
            self.send_empty(400)
            return
        if not isinstance(payload, dict):
            self.send_empty(400)
            return

        info = payload.get('info') or {}
        if isinstance(info, dict) and info:
            engine.remember_device(info, self.client_address[0])
        files = payload.get('files') or {}

        entries = []
        if isinstance(files, dict):
            for file_id in files.keys():
                meta = files[file_id]
                if not isinstance(meta, dict):
                    continue
                if not meta.get('id'):
                    meta['id'] = file_id
                entries.append(meta)
        elif isinstance(files, list):
            for meta in files:
                if isinstance(meta, dict):
                    entries.append(meta)
        if not entries:
            engine.log(u'<- prepare-upload with no files: answering 204')
            self.send_empty(204)
            return

        engine.prune_sessions()
        session = engine.new_session(info, self.client_address[0])
        tokens = {}
        for meta in entries:
            file_id = to_text(meta.get('id') or random_hex(8))
            token = random_hex(16)
            name = to_text(meta.get('fileName') or file_id)
            try:
                size = long_type(meta.get('size') or 0)
            except Exception:
                size = 0
            mime = to_text(meta.get('fileType') or 'application/octet-stream')
            session.add(file_id, name, size, mime, token)
            tokens[file_id] = token
        session.pending = len(tokens)

        alias = u'?'
        if isinstance(info, dict):
            alias = to_text(info.get('alias') or u'?')
        engine.log(u'<- %s (%s) wants to send %d file(s)'
                   % (alias, self.client_address[0], len(tokens)))
        for meta in entries:
            engine.log(u'   "%s" (%s)' % (to_text(meta.get('fileName') or '?'),
                                          human_size(meta.get('size') or 0)))
        engine.set_status('receiving')
        self.send_json(200, {'sessionId': session.session_id,
                             'files': tokens})

    def handle_upload(self, query):
        engine = self.engine()
        session_id = query_value(query, 'sessionId')
        file_id = query_value(query, 'fileId')
        token = query_value(query, 'token')

        session = engine.get_session(session_id)
        if session is None:
            engine.log(u'!! upload for unknown session %s (expired or '
                       u'already finished)' % (session_id or u'-'))
            self.drain_body()
            self.send_empty(403)
            return
        entry = session.files.get(file_id)
        if entry is None:
            engine.log(u'!! upload for unknown fileId %s' % (file_id or u'-'))
            self.drain_body()
            self.send_empty(403)
            return
        if to_text(entry['token']) != token:
            engine.log(u'!! upload with a bad token for "%s"'
                       % entry['fileName'])
            self.drain_body()
            self.send_empty(403)
            return

        self.maybe_continue()
        name = entry['fileName']
        declared = entry['size']
        chunked = self.is_chunked()
        if chunked:
            expected = declared
        else:
            expected = self.content_length()
        kind = u''
        if chunked:
            kind = u' [chunked]'
        engine.log(u'<- receiving "%s" (%s) from %s%s'
                   % (name, human_size(expected), self.client_address[0],
                      kind))

        destination = None
        handle = None
        temporary = None
        try:
            try:
                destination, handle = engine.receive_upload(
                    session, file_id, engine.save_dir)
            except Exception:
                error = sys.exc_info()[1]
                engine.log(u'!! cannot write to %s: %s'
                           % (engine.save_dir, to_text(error)))
                self.send_empty(500)
                return
            temporary = destination + u'.part'
            received = 0
            try:
                if chunked:
                    received = self.stream_chunked_to(handle, engine,
                                                      declared)
                else:
                    received = self.stream_length_to(handle, expected, engine)
            except Exception:
                error = sys.exc_info()[1]
                engine.log(u'!! receive of "%s" failed: %s'
                           % (name, to_text(error)))
                try:
                    handle.close()
                except Exception:
                    pass
                handle = None
                self.discard(temporary)
                self.send_empty(500)
                return
            try:
                handle.close()
            except Exception:
                pass
            handle = None
            if declared and received != declared:
                engine.log(u'   note: got %s of %s'
                           % (human_size(received), human_size(declared)))
            try:
                os.rename(fsenc(temporary), fsenc(destination))
            except Exception:
                error = sys.exc_info()[1]
                engine.log(u'!! cannot finish "%s": %s'
                           % (name, to_text(error)))
                self.discard(temporary)
                self.send_empty(500)
                return
            engine.log(u'<- saved "%s" (%s) in %s'
                       % (name, human_size(received), engine.save_dir))
            session.pending = session.pending - 1
            if session.pending <= 0:
                engine.drop_session(session_id)
                engine.set_status('ready')
                engine.log(u'== all files of this transfer received')
            self.send_json(200, {})
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass

    def drain_body(self, limit=1048576):
        """Read and throw away what is left of the request body.

        Answering 403 without consuming the body makes the kernel send a TCP
        reset when the socket closes, and the sender then never sees the
        rejection (Python 2.3/2.4 clients lose the response entirely). So:
        read a bounded amount first, then answer.
        """
        try:
            self.connection.settimeout(5.0)
        except Exception:
            pass
        try:
            if self.is_chunked():
                remaining = limit
                while remaining > 0:
                    line = self.rfile.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line == EMPTY:
                        continue
                    semi = line.find(SEMI)
                    if semi >= 0:
                        line = line[:semi]
                    try:
                        size = int(line, 16)
                    except Exception:
                        break
                    if size == 0:
                        break
                    piece = self.rfile.read(min(size, remaining))
                    remaining = remaining - len(piece)
                    self.rfile.read(2)
                    if len(piece) < size:
                        break
                return
            length = self.content_length()
            if length <= 0:
                return
            remaining = length
            if remaining > limit:
                remaining = limit
            while remaining > 0:
                piece = self.rfile.read(min(CHUNK_SIZE, remaining))
                if not piece:
                    break
                remaining = remaining - len(piece)
        except Exception:
            pass

    def discard(self, path):
        try:
            os.remove(fsenc(path))
        except Exception:
            pass

    def stream_length_to(self, handle, length, engine):
        total = 0
        remaining = int(length)
        while remaining > 0:
            if engine.cancel_flag.is_set():
                raise TransferCancelled()
            try:
                piece = self.rfile.read(min(CHUNK_SIZE, remaining))
            except Exception:
                raise ConnectionClosed(u'timeout or reset while receiving')
            if not piece:
                raise ConnectionClosed(u'connection closed early')
            handle.write(piece)
            total = total + len(piece)
            remaining = remaining - len(piece)
            engine.publish_progress(total, length)
        return total

    def stream_chunked_to(self, handle, engine, total_hint=0):
        total = 0
        while 1:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            if line == EMPTY:
                continue
            semi = line.find(SEMI)
            if semi >= 0:
                line = line[:semi]
            try:
                size = int(line, 16)
            except Exception:
                raise ConnectionClosed(u'bad chunk size')
            if size == 0:
                while 1:
                    trailer = self.rfile.readline()
                    if not trailer or trailer.strip() == EMPTY:
                        break
                break
            remaining = size
            while remaining > 0:
                if engine.cancel_flag.is_set():
                    raise TransferCancelled()
                try:
                    piece = self.rfile.read(min(CHUNK_SIZE, remaining))
                except Exception:
                    raise ConnectionClosed(u'timeout or reset while receiving')
                if not piece:
                    raise ConnectionClosed(u'connection closed early')
                handle.write(piece)
                total = total + len(piece)
                remaining = remaining - len(piece)
                engine.publish_progress(total, total_hint)
            self.rfile.read(2)      # CRLF after each chunk
        return total

    def handle_cancel(self, query):
        engine = self.engine()
        session_id = query_value(query, 'sessionId')
        if session_id == '':
            body = self.read_body(65536)
            try:
                payload = json_loads(body)
                if isinstance(payload, dict):
                    session_id = to_text(payload.get('sessionId') or '')
            except Exception:
                session_id = ''
        if session_id and engine.drop_session(session_id):
            engine.log(u'<- transfer %s cancelled by the other device'
                       % session_id)
        engine.set_status('ready')
        self.send_json(200, {})

# ---------------------------------------------------------------------------
#  Tkinter GUI (Tk 8.4 on Tiger: no ttk, no Treeview)
# ---------------------------------------------------------------------------
class TigerSendGUI(object):
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.queue = Queue.Queue()
        self.pending_files = engine.files
        self.last_progress = 0.0

        engine.on_log = self.queue_log
        engine.on_status = self.queue_status
        engine.on_devices = self.queue_devices
        engine.on_progress = self.queue_progress

        self.font_ui = ('Lucida Grande', 11)
        self.font_bold = ('Lucida Grande', 11, 'bold')
        self.font_title = ('Lucida Grande', 12, 'bold')
        self.font_mono = ('Monaco', 10)
        self.font_small = ('Lucida Grande', 10)

        try:
            self.root.tk.call('tk', 'appname', APP_NAME)
        except Exception:
            pass
        try:
            self.root.title(u'%s %s' % (APP_NAME, APP_VERSION))
        except Exception:
            pass
        try:
            self.root.minsize(700, 660)
        except Exception:
            pass

        self.build()
        self.retranslate()
        self.engine.start()
        self.log_startup()
        self.root.after(200, self.poll_queue)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        try:
            self.root.lift()
        except Exception:
            pass

    # ----- notifications from worker threads ------------------------------
    def queue_log(self, text):
        self.queue.put(('log', text))

    def queue_status(self, key):
        self.queue.put(('status', key))

    def queue_devices(self):
        self.queue.put(('devices', None))

    def queue_progress(self, done, total):
        self.queue.put(('progress', (done, total)))

    def poll_queue(self):
        try:
            while 1:
                try:
                    kind, payload = self.queue.get_nowait()
                except Queue.Empty:
                    break
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'status':
                    self.set_status_key(payload)
                elif kind == 'devices':
                    self.refresh_devices()
                elif kind == 'progress':
                    self.show_progress(payload[0], payload[1])
        except Exception:
            pass
        if self.engine.running:
            try:
                self.root.after(200, self.poll_queue)
            except Exception:
                pass

    # ----- widgets --------------------------------------------------------
    def build(self):
        root = self.root
        Tkinter = _tk()

        header = Tkinter.Frame(root)
        header.pack(side='top', fill='x', padx=10, pady=(8, 2))
        self.lbl_title = Tkinter.Label(header, font=self.font_title,
                                       anchor='w', text=u'')
        self.lbl_title.pack(side='left')
        self.lbl_server = Tkinter.Label(header, font=self.font_small,
                                        anchor='e', text=u'')
        self.lbl_server.pack(side='right')

        Tkinter.Frame(root, height=2, bd=1, relief='sunken').pack(
            fill='x', padx=10, pady=4)

        identity = Tkinter.Frame(root)
        identity.pack(side='top', fill='x', padx=10)

        row = Tkinter.Frame(identity)
        row.pack(fill='x', pady=2)
        self.lbl_name = Tkinter.Label(row, font=self.font_ui, width=9,
                                      anchor='w', text=u'')
        self.lbl_name.pack(side='left')
        self.var_alias = Tkinter.StringVar()
        self.var_alias.set(self.engine.alias)
        self.ent_alias = Tkinter.Entry(row, textvariable=self.var_alias,
                                       font=self.font_ui)
        self.ent_alias.pack(side='left', fill='x', expand=1, padx=4)
        self.btn_apply = Tkinter.Button(row, command=self.on_apply_alias,
                                        text=u'')
        self.btn_apply.pack(side='left', padx=2)

        row = Tkinter.Frame(identity)
        row.pack(fill='x', pady=2)
        self.lbl_saveto = Tkinter.Label(row, font=self.font_ui, width=9,
                                        anchor='w', text=u'')
        self.lbl_saveto.pack(side='left')
        self.var_savedir = Tkinter.StringVar()
        self.var_savedir.set(self.engine.save_dir)
        self.ent_savedir = Tkinter.Entry(row, textvariable=self.var_savedir,
                                         font=self.font_ui, state='readonly')
        try:
            self.ent_savedir.config(readonlybackground='#eeeeee')
        except Exception:
            pass
        self.ent_savedir.pack(side='left', fill='x', expand=1, padx=4)
        self.btn_change = Tkinter.Button(row, command=self.on_change_dir,
                                         text=u'')
        self.btn_change.pack(side='left', padx=2)

        self.lbl_devices = Tkinter.Label(root, font=self.font_bold, anchor='w',
                                         text=u'')
        self.lbl_devices.pack(fill='x', padx=10, pady=(8, 0))

        device_box = Tkinter.Frame(root, bd=1, relief='sunken')
        device_box.pack(fill='both', padx=10, pady=2)
        self.lbl_devhdr = Tkinter.Label(device_box, font=self.font_mono,
                                        anchor='w', bg='#dddddd', text=u'')
        self.lbl_devhdr.pack(fill='x')
        inner = Tkinter.Frame(device_box)
        inner.pack(fill='both', expand=1)
        self.sb_devices = Tkinter.Scrollbar(inner, orient='vertical')
        self.lst_devices = Tkinter.Listbox(inner, height=5,
                                           font=self.font_mono,
                                           yscrollcommand=self.sb_devices.set,
                                           exportselection=0)
        self.sb_devices.config(command=self.lst_devices.yview)
        self.sb_devices.pack(side='right', fill='y')
        self.lst_devices.pack(side='left', fill='both', expand=1)

        buttons = Tkinter.Frame(root)
        buttons.pack(fill='x', padx=10, pady=(2, 4))
        self.btn_announce = Tkinter.Button(buttons, text=u'',
                                           command=self.on_announce)
        self.btn_announce.pack(side='left', padx=2)
        self.btn_scan = Tkinter.Button(buttons, text=u'',
                                       command=self.on_scan)
        self.btn_scan.pack(side='left', padx=2)
        self.btn_clearlog = Tkinter.Button(buttons, text=u'',
                                           command=self.on_clear_log)
        self.btn_clearlog.pack(side='left', padx=2)

        self.lbl_files = Tkinter.Label(root, font=self.font_bold, anchor='w',
                                       text=u'')
        self.lbl_files.pack(fill='x', padx=10, pady=(6, 0))

        file_box = Tkinter.Frame(root, bd=1, relief='sunken')
        file_box.pack(fill='both', padx=10, pady=2)
        self.sb_files = Tkinter.Scrollbar(file_box, orient='vertical')
        self.lst_files = Tkinter.Listbox(file_box, height=5,
                                         font=self.font_mono,
                                         yscrollcommand=self.sb_files.set,
                                         exportselection=0)
        self.sb_files.config(command=self.lst_files.yview)
        self.sb_files.pack(side='right', fill='y')
        self.lst_files.pack(side='left', fill='both', expand=1)

        buttons = Tkinter.Frame(root)
        buttons.pack(fill='x', padx=10, pady=(2, 4))
        self.btn_addfile = Tkinter.Button(buttons, text=u'',
                                          command=self.on_add_files)
        self.btn_addfile.pack(side='left', padx=2)
        self.btn_paste = Tkinter.Button(buttons, text=u'',
                                        command=self.on_paste_clipboard)
        self.btn_paste.pack(side='left', padx=2)
        self.btn_remove = Tkinter.Button(buttons, text=u'',
                                         command=self.on_remove_file)
        self.btn_remove.pack(side='left', padx=2)
        self.btn_clearlist = Tkinter.Button(buttons, text=u'',
                                            command=self.on_clear_files)
        self.btn_clearlist.pack(side='left', padx=2)
        self.btn_send = Tkinter.Button(buttons, text=u'',
                                       command=self.on_send)
        self.btn_send.pack(side='left', padx=8)
        self.btn_cancel = Tkinter.Button(buttons, text=u'',
                                         command=self.on_cancel)
        self.btn_cancel.pack(side='left', padx=2)

        self.lbl_activity = Tkinter.Label(root, font=self.font_bold,
                                          anchor='w', text=u'')
        self.lbl_activity.pack(fill='x', padx=10, pady=(6, 0))

        activity_box = Tkinter.Frame(root, bd=1, relief='sunken')
        activity_box.pack(fill='both', expand=1, padx=10, pady=2)
        self.sb_activity = Tkinter.Scrollbar(activity_box, orient='vertical')
        self.txt_activity = Tkinter.Text(activity_box, height=8,
                                         font=self.font_mono, state='disabled',
                                         wrap='word',
                                         yscrollcommand=self.sb_activity.set)
        self.sb_activity.config(command=self.txt_activity.yview)
        self.sb_activity.pack(side='right', fill='y')
        self.txt_activity.pack(side='left', fill='both', expand=1)

        language_bar = Tkinter.Frame(root)
        language_bar.pack(fill='x', padx=10, pady=(4, 0))
        self.var_lang = Tkinter.StringVar()
        self.var_lang.set(self.engine.lang)
        self.radio_langs = []
        for code in LANG_ORDER:
            button = Tkinter.Radiobutton(language_bar, text=LANG_LABELS[code],
                                         variable=self.var_lang, value=code,
                                         font=self.font_small,
                                         command=self.on_language)
            button.pack(side='left', padx=2)
            self.radio_langs.append(button)

        status_bar = Tkinter.Frame(root, bd=1, relief='sunken')
        status_bar.pack(side='bottom', fill='x')
        self.lbl_status = Tkinter.Label(status_bar, font=self.font_small,
                                        anchor='w', text=u'')
        self.lbl_status.pack(side='left', padx=6)
        self.lbl_system = Tkinter.Label(status_bar, font=self.font_small,
                                        anchor='e', fg='#555555', text=u'')
        self.lbl_system.pack(side='right', padx=6)

    # ----- translations ---------------------------------------------------
    def tr(self, key, *args):
        return translate(self.engine.lang, key, *args)

    def retranslate(self):
        self.lbl_title.config(
            text=u'%s %s   LocalSend v%s - %s'
                 % (APP_NAME, APP_VERSION, PROTO_VERSION, os_label()))
        self.lbl_name.config(text=self.tr('name'))
        self.btn_apply.config(text=self.tr('apply'))
        self.lbl_saveto.config(text=self.tr('save_to'))
        self.btn_change.config(text=self.tr('change'))
        self.lbl_devices.config(text=self.tr('devices'))
        header = u'%-26s %-22s %s'
        self.lbl_devhdr.config(text=log_text(header, self.tr('col_name'),
                                             self.tr('col_model'),
                                             self.tr('col_address')))
        self.btn_announce.config(text=self.tr('announce'))
        self.btn_scan.config(text=self.tr('scan'))
        self.btn_clearlog.config(text=self.tr('clear_log'))
        self.btn_addfile.config(text=self.tr('add_file'))
        self.btn_paste.config(text=self.tr('paste_clip'))
        self.btn_remove.config(text=self.tr('remove'))
        self.btn_clearlist.config(text=self.tr('clear_list'))
        self.btn_send.config(text=self.tr('send_to'))
        self.btn_cancel.config(text=self.tr('cancel_transfer'))
        self.lbl_activity.config(text=self.tr('activity'))
        if self.engine.server_ok:
            self.lbl_server.config(text=self.tr('server_running')
                                   % self.engine.port, fg='#006600')
        else:
            self.lbl_server.config(text=self.tr('server_error')
                                   % self.engine.port, fg='#aa0000')
        self.lbl_system.config(text=log_text(self.tr('system'),
                                             self.engine.arch,
                                             python_label()))
        self.update_files_header()
        self.update_status()

    def on_language(self):
        lang = self.var_lang.get()
        self.engine.set_language(lang)
        self.retranslate()
        self.engine.log(u'Language switched to %s'
                        % LANG_LABELS.get(self.engine.lang, u'?'))

    def update_status(self, progress=u''):
        text = log_text(u'%s | %s | %s',
                        self.tr(self.engine.status),
                        self.tr('devcount') % self.engine.device_count(),
                        self.tr('language') % LANG_LABELS[self.engine.lang])
        if progress:
            text = text + u' | ' + progress
        self.lbl_status.config(text=text)

    def set_status_key(self, key):
        self.engine.status = key
        self.update_status()

    def update_files_header(self):
        self.lbl_files.config(text=log_text(u'%s  [ %d ]',
                                            self.tr('files_to_send'),
                                            len(self.pending_files)))

    def show_progress(self, done, total):
        if not total:
            return
        self.update_status(self.tr('progress') % (human_size(done),
                                                  human_size(total)))

    # ----- activity log ---------------------------------------------------
    def append_log(self, text):
        line = log_text(u'[%s] %s\n', timestamp(), text)
        try:
            self.txt_activity.config(state='normal')
            self.txt_activity.insert('end', line)
            # Keep the widget small: 2005 machines do not like 100k lines.
            try:
                lines = int(self.txt_activity.index('end-1c').split('.')[0])
                if lines > 900:
                    self.txt_activity.delete('1.0', '200.0')
            except Exception:
                pass
            self.txt_activity.see('end')
            self.txt_activity.config(state='disabled')
        except Exception:
            pass

    def log_startup(self):
        engine = self.engine
        engine.log(u'%s %s (%s) on %s'
                   % (APP_NAME, APP_VERSION, APP_BUILD,
                      os_label() or u'this Mac'))
        engine.log(u'%s, %s' % (python_label(), engine.arch))
        engine.log(u'Protocol: LocalSend v%s - plain HTTP :%d, encrypted '
                   u'HTTPS is not supported' % (PROTO_VERSION, engine.port))
        engine.log(u'Alias: %s   Fingerprint: %s'
                   % (engine.alias, engine.fingerprint[:16]))
        engine.log(u'Save folder: %s' % engine.save_dir)
        engine.log(u'Remember: Encryption must be OFF on the phone/computer.')

    # ----- identity -------------------------------------------------------
    def on_apply_alias(self):
        alias = self.engine.set_alias(self.var_alias.get())
        self.var_alias.set(alias)
        self.engine.announce()

    def on_change_dir(self):
        folder = None
        try:
            folder = tkFileDialog.askdirectory(
                title=self.tr('choose_dir'), initialdir=self.engine.save_dir)
        except Exception:
            folder = None
        if folder:
            if self.engine.set_save_dir(folder):
                self.var_savedir.set(self.engine.save_dir)

    # ----- device table ---------------------------------------------------
    def refresh_devices(self):
        try:
            self.lst_devices.delete(0, 'end')
        except Exception:
            return
        for device in self.engine.devices:
            row = log_text(u'%-26s %-22s %s:%d',
                           device['alias'][:25],
                           to_text(device['model'])[:21],
                           to_text(device['ip']), device['port'])
            try:
                self.lst_devices.insert('end', row)
            except Exception:
                pass
        self.update_status()

    def on_announce(self):
        self.engine.announce()

    def on_scan(self):
        self.engine.scan_network()

    def on_clear_log(self):
        try:
            self.txt_activity.config(state='normal')
            self.txt_activity.delete('1.0', 'end')
            self.txt_activity.config(state='disabled')
        except Exception:
            pass

    # ----- outbound queue -------------------------------------------------
    def add_path(self, path):
        path = to_text(path)
        if path in self.pending_files:
            return
        try:
            size = os.path.getsize(fsenc(path))
        except Exception:
            size = 0
        self.pending_files.append(path)
        try:
            name = to_text(os.path.basename(fsenc(path)))
            self.lst_files.insert('end', log_text(u'%s  (%s)', name,
                                                  human_size(size)))
        except Exception:
            pass
        self.update_files_header()

    def add_paths(self, paths):
        for path in paths:
            if not os.path.isfile(fsenc(path)):
                continue
            self.add_path(path)
            self.engine.log(u'Queued: %s' % to_text(path))

    def on_add_files(self):
        paths = None
        try:
            paths = tkFileDialog.askopenfilenames(
                title=self.tr('add_files_title'))
            if paths and not isinstance(paths, (list, tuple)):
                paths = self.root.tk.splitlist(paths)
        except Exception:
            paths = None
        if not paths:
            try:
                one = tkFileDialog.askopenfilename(
                    title=self.tr('add_file_title'))
            except Exception:
                one = None
            if one:
                paths = [one]
        if not paths:
            return
        self.add_paths(paths)

    def on_paste_clipboard(self):
        text = None
        try:
            text = self.root.clipboard_get()
        except Exception:
            text = None
        if not text:
            self.alert(self.tr('no_clip'))
            return
        name = u'tigersend-clipboard-%s.txt' % time.strftime('%Y%m%d-%H%M%S')
        path = os.path.join(tempfile.gettempdir(), name)
        handle = None
        try:
            try:
                handle = open(fsenc(path), 'wb')
                handle.write(to_bytes(text))
            except Exception:
                error = sys.exc_info()[1]
                self.engine.log(u'!! clipboard error: %s' % to_text(error))
                return
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        self.add_path(path)
        self.engine.log(u'Clipboard text queued as %s' % name)

    def on_remove_file(self):
        selection = self.lst_files.curselection()
        if not selection:
            return
        index = int(selection[0])
        if index < len(self.pending_files):
            path = self.pending_files[index]
            del self.pending_files[index]
            self.lst_files.delete(index)
            self.engine.log(u'Removed from queue: %s'
                            % to_text(os.path.basename(fsenc(path))))
            self.update_files_header()

    def on_clear_files(self):
        del self.pending_files[:]
        try:
            self.lst_files.delete(0, 'end')
        except Exception:
            pass
        self.update_files_header()

    def alert(self, message):
        try:
            tkMessageBox.showwarning(APP_NAME, message)
        except Exception:
            self.engine.log(message)

    # ----- sending --------------------------------------------------------
    def on_send(self):
        selection = self.lst_devices.curselection()
        if not selection:
            self.alert(self.tr('pick_device'))
            return
        if not self.pending_files:
            self.alert(self.tr('pick_files'))
            return
        index = int(selection[0])
        if index >= len(self.engine.devices):
            return
        device = self.engine.devices[index]
        paths = self.pending_files[:]
        thread = threading.Thread(target=self.send_thread,
                                  args=(device, paths))
        set_daemon(thread)
        thread.start()

    def send_thread(self, device, paths):
        try:
            self.engine.send_files(device, paths)
        except Exception:
            error = sys.exc_info()[1]
            self.engine.log(u'!! send failed: %s' % to_text(error))
            self.engine.set_status('ready')

    def on_cancel(self):
        self.engine.cancel_transfer()

    # ----- shutdown -------------------------------------------------------
    def on_close(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def _tk():
    return Tkinter


# ---------------------------------------------------------------------------
#  Command line
# ---------------------------------------------------------------------------
USAGE = u"""%(name)s %(version)s - LocalSend protocol v%(proto)s for Mac OS X
10.4 Tiger and newer (PowerPC and Intel)

Usage:  %(name)s [options]

  (no options)        open the window
  --headless          run the server without a window (Terminal use)
  --alias NAME        set the name shown to other devices
  --save-dir FOLDER   where received files are stored
  --port N            TCP/UDP port (default %(port)d)
  --announce          send a discovery announcement and exit
  --self-test         run the built-in protocol tests and exit
  --version           print the version and exit
  --help              this text

The other device must have Encryption turned OFF: this Mac can only use
plain HTTP (no TLS). Use it on your own trusted local network.
""" % {'name': APP_NAME, 'version': APP_VERSION, 'proto': PROTO_VERSION,
       'port': PORT}


def parse_args(argv):
    options = {
        'headless': 0,
        'alias': None,
        'save_dir': None,
        'port': PORT,
        'self_test': 0,
        'version': 0,
        'help': 0,
        'announce': 0,
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ('-h', '--help'):
            options['help'] = 1
        elif arg in ('-V', '--version'):
            options['version'] = 1
        elif arg == '--headless':
            options['headless'] = 1
        elif arg == '--self-test':
            options['self_test'] = 1
        elif arg == '--announce':
            options['announce'] = 1
        elif arg == '--alias':
            index = index + 1
            if index < len(argv):
                options['alias'] = argv[index]
        elif arg[:8] == '--alias=':
            options['alias'] = arg[8:]
        elif arg in ('--save-dir', '--save_dir'):
            index = index + 1
            if index < len(argv):
                options['save_dir'] = argv[index]
        elif arg[:11] == '--save-dir=':
            options['save_dir'] = arg[11:]
        elif arg == '--port':
            index = index + 1
            if index < len(argv):
                try:
                    options['port'] = int(argv[index])
                except Exception:
                    pass
        elif arg[:7] == '--port=':
            try:
                options['port'] = int(arg[7:])
            except Exception:
                pass
        # Finder on Tiger passes "-psn_0_123456"; ignore unknown options.
        index = index + 1
    return options


def run_headless(engine):
    engine.echo = 1
    engine.start()
    engine.log(translate(engine.lang, 'headless_start'))
    engine.send_announcement()
    try:
        while 1:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    engine.log(u'Shutting down...')
    engine.stop()
    return 0


def run_gui(engine):
    root = Tkinter.Tk()
    TigerSendGUI(root, engine)
    root.mainloop()
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    options = parse_args(argv)

    if options['help']:
        write_out(USAGE)
        return 0
    if options['version']:
        write_out(u'%s %s (%s) %s\n'
                                 % (APP_NAME, APP_VERSION, APP_BUILD,
                                    PROTO_VERSION))
        return 0
    if options['self_test']:
        return run_self_test()

    engine = TigerSendEngine(alias=options['alias'],
                             save_dir=options['save_dir'],
                             port=options['port'])

    if options['announce']:
        engine.echo = 1
        engine.start_server()
        engine.send_announcement()
        engine.stop()
        return 0

    if options['headless'] or not HAVE_TK:
        if not HAVE_TK and not options['headless']:
            engine.echo = 1
            engine.log(u'!! Tkinter is not available in this Python; '
                       u'running headless instead')
        return run_headless(engine)

    try:
        return run_gui(engine)
    except Exception:
        error = sys.exc_info()[1]
        engine.echo = 1
        engine.log(u'!! the window could not be created: %s'
                   % to_text(error))
        engine.log(u'!! Is this a Terminal session without a display? '
                   u'Try --headless.')
        raise


# ---------------------------------------------------------------------------
#  Built-in self test
#
#  Run it on the old Mac with:   python tigersend.py --self-test
#  It needs no network peer: two engines are started on loopback and talk
#  the real LocalSend protocol to each other.
# ---------------------------------------------------------------------------
def run_self_test():
    failures = []

    def check(name, condition, detail=''):
        if condition:
            write_out(u'ok   %s\n' % name)
        else:
            failures.append(name)
            write_out(u'FAIL %s %s\n' % (name, detail))

    write_out(u'%s %s (%s) self test\n'
                             % (APP_NAME, APP_VERSION, APP_BUILD))
    write_out(u'%s, %s, %s\n'
                             % (python_label(), os_label(), arch_label()))

    # --- JSON codec ---------------------------------------------------
    sample = {'a': 1, 'b': [1, 2, 3], 'c': u'caf\u00e9 \u00f1',
              'd': True, 'e': None, 'f': 1.5,
              'g': u'\u00e9\u4e2d' + _from_codepoint(0x1f600)}
    encoded = json_dumps(sample)
    try:
        decoded = json_loads(encoded)
        check(u'json round trip', decoded == sample, repr(decoded))
    except Exception:
        check(u'json round trip', False, to_text(sys.exc_info()[1]))
        decoded = {}
    check(u'json unicode escapes',
          json_loads(u'{"t":"\\u00f1\\u4e2d"}') == {'t': u'\u00f1\u4e2d'})
    check(u'json surrogate pair',
          json_loads(u'{"e":"\\ud83d\\ude00"}') == {'e': _from_codepoint(0x1f600)},
          repr(json_loads(u'{"e":"\\ud83d\\ude00"}')))
    check(u'json numbers',
          json_loads(u'{"n":-12,"f":2.5e3}') == {'n': -12, 'f': 2500.0})
    check(u'json empty body', json_loads(EMPTY) == {})
    try:
        json_loads(u'{broken')
        check(u'json rejects garbage', False)
    except Exception:
        check(u'json rejects garbage', True)

    # --- helpers ------------------------------------------------------
    check(u'human_size', human_size(1536) == u'1.5 KB', human_size(1536))
    check(u'safe_filename', safe_filename(u'../../etc/passwd') == u'passwd',
          safe_filename(u'../../etc/passwd'))
    check(u'safe_filename control chars',
          safe_filename(u'a\x01b:c.txt') == u'a_b_c.txt',
          safe_filename(u'a\x01b:c.txt'))
    check(u'url_quote', url_quote(u'a b&c') == 'a%20b%26c',
          url_quote(u'a b&c'))
    check(u'md5', len(md5_hex(u'abc')) == 32)
    check(u'random_hex', len(random_hex(8)) == 16)
    for code in LANG_ORDER:
        missing = 0
        for key in TR['en'].keys():
            if key not in TR[code]:
                missing = missing + 1
        check(u'translation %s complete' % code, missing == 0,
              u'%d missing' % missing)

    # --- two engines talking real LocalSend v2 on loopback -------------
    work = tempfile.mkdtemp(prefix='tigersend-selftest-')
    inbox = os.path.join(work, 'inbox')
    ensure_folder(inbox)
    source = os.path.join(work, u'caf\u00e9 \u00f1 and space.txt')
    handle = open(fsenc(source), 'wb')
    try:
        handle.write(to_bytes(u'hello LocalSend v2 from Tiger\n' * 100))
    finally:
        handle.close()
    source_size = os.path.getsize(fsenc(source))

    # port 0: let the kernel pick free ports, so that two self tests (or a
    # self test next to a running TigerSend) cannot collide.
    receiver = TigerSendEngine(alias=u'Receiver', save_dir=inbox, port=0,
                               cfg_file=os.path.join(work, 'receiver.json'),
                               echo=0)
    sender = TigerSendEngine(alias=u'Sender', port=0,
                             cfg_file=os.path.join(work, 'sender.json'),
                             echo=0)
    receiver.start_server()
    if not receiver.server_ok or not receiver.port:
        check(u'server starts on a free port', False,
              u'could not bind: %s (temp folder: %s)' % (receiver.port, work))
        return failures
    rport = receiver.port
    sender.log = lambda text: None
    try:
        info = receiver.device_info(0)
        check(u'device info fields',
              info.get('alias') == u'Receiver'
              and info.get('protocol') == 'http'
              and info.get('fingerprint') == receiver.fingerprint
              and info.get('port') == rport, repr(info))

        response = http_request('127.0.0.1', rport, 'GET',
                                API_BASE + '/info', timeout=5.0)
        check(u'GET /info', response.status == 200
              and response.json().get('alias') == u'Receiver',
              response.summary())

        response = http_json('127.0.0.1', rport, 'POST',
                             API_BASE + '/register',
                             sender.device_info(0), timeout=5.0)
        check(u'POST /register', response.status == 200
              and response.json().get('alias') == u'Receiver',
              response.summary())

        response = http_request('127.0.0.1', rport, 'GET', '/nope',
                                timeout=5.0)
        check(u'404 on unknown path', response.status == 404)

        # full round trip: sender -> receiver through the protocol
        device = {'ip': '127.0.0.1', 'port': rport, 'alias': u'Receiver',
                  'fingerprint': receiver.fingerprint, 'model': u'test'}
        sent, total = sender.send_files(device, [source])
        check(u'prepare-upload + upload', sent == 1 and total == 1,
              u'%d/%d' % (sent, total))
        source_name = to_text(os.path.basename(fsenc(source)))
        received = os.path.join(inbox, safe_filename(source_name))
        check(u'file arrived', os.path.exists(fsenc(received)), received)
        if os.path.exists(fsenc(received)):
            check(u'received size',
                  os.path.getsize(fsenc(received)) == source_size)
            handle = open(fsenc(received), 'rb')
            try:
                content = handle.read()
            finally:
                handle.close()
            check(u'received content unchanged',
                  len(content) == source_size)

        # chunked upload (what iOS sends) through the real server
        prepare = http_json('127.0.0.1', rport, 'POST',
                            API_BASE + '/prepare-upload',
                            {'info': sender.device_info(0),
                             'files': {'abc': {'id': 'abc',
                                               'fileName': 'chunked.bin',
                                               'size': 11,
                                               'fileType': 'text/plain'}}},
                            timeout=5.0)
        check(u'prepare-upload answer', prepare.status == 200, prepare.summary())
        answer = {}
        try:
            answer = prepare.json()
        except Exception:
            answer = {}
        session_id = to_text(answer.get('sessionId') or '')
        token = to_text((answer.get('files') or {}).get('abc') or '')
        check(u'session id and token', session_id != u'' and token != u'')
        if session_id and token:
            check(u'chunked upload', chunked_upload(rport, session_id, 'abc',
                                                    token, to_bytes('hello world')))
            chunked_file = os.path.join(inbox, u'chunked.bin')
            check(u'chunked file written', os.path.exists(fsenc(chunked_file)))
            if os.path.exists(fsenc(chunked_file)):
                handle = open(fsenc(chunked_file), 'rb')
                try:
                    payload = handle.read()
                finally:
                    handle.close()
                check(u'chunked payload', to_bytes(payload) == to_bytes('hello world'),
                      repr(payload))

            # cancel must drop the session
            response = http_json('127.0.0.1', rport, 'POST',
                                 API_BASE + '/cancel?sessionId='
                                 + url_quote(session_id), {}, timeout=5.0)
            check(u'POST /cancel', response.status == 200,
                  response.summary())
            check(u'cancelled session forgotten',
                  receiver.get_session(session_id) is None)

        # a rejected/empty prepare-upload must answer 204
        empty = http_json('127.0.0.1', rport, 'POST',
                          API_BASE + '/prepare-upload',
                          {'info': sender.device_info(0), 'files': {}},
                          timeout=5.0)
        check(u'prepare-upload with no files -> 204', empty.status == 204,
              empty.summary())

        # bad token must be refused
        prepare = http_json('127.0.0.1', rport, 'POST',
                            API_BASE + '/prepare-upload',
                            {'info': sender.device_info(0),
                             'files': {'x': {'id': 'x', 'fileName': 'x.bin',
                                             'size': 3}}}, timeout=5.0)
        answer = prepare.json()
        bad = http_request('127.0.0.1', rport, 'POST',
                           API_BASE + '/upload?sessionId=%s&fileId=x&token=nope'
                           % url_quote(to_text(answer.get('sessionId') or '')),
                           body=to_bytes('abc'), timeout=5.0)
        check(u'bad token -> 403', bad.status == 403, bad.summary())

        # discovery bookkeeping
        sender.remember_device(receiver.device_info(0), '127.0.0.1')
        check(u'device remembered', sender.device_count() == 1,
              u'%d' % sender.device_count())
        check(u'own fingerprint ignored',
              not sender.remember_device(sender.device_info(0), '127.0.0.1'))
    except Exception:
        check(u'loopback protocol test', False, to_text(sys.exc_info()[1]))
        try:
            import traceback
            traceback.print_exc()
        except Exception:
            pass
    receiver.stop()
    sender.stop()
    if not failures:
        cleanup_tree(work)

    write_out(u'\n')
    if failures:
        write_out(u'%d test(s) FAILED: %s\n'
                                 % (len(failures), u', '.join(failures)))
        return 1
    write_out(u'All self tests passed.\n')
    return 0


def chunked_upload(port, session_id, file_id, token, payload):
    """Send an upload with Transfer-Encoding: chunked, like iOS does."""
    sock = None
    try:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect(('127.0.0.1', port))
            request = ('POST %s/upload?sessionId=%s&fileId=%s&token=%s '
                       'HTTP/1.1\r\n'
                       'Host: 127.0.0.1\r\n'
                       'Content-Type: application/octet-stream\r\n'
                       'Transfer-Encoding: chunked\r\n'
                       'Connection: close\r\n\r\n'
                       % (API_BASE, url_quote(session_id), url_quote(file_id),
                          url_quote(token)))
            send_all(sock, to_bytes(request))
            data = to_bytes(payload)
            pieces = [data[:5], data[5:]]
            for piece in pieces:
                if not piece:
                    continue
                send_all(sock, to_bytes('%x\r\n' % len(piece)))
                send_all(sock, piece)
                send_all(sock, to_bytes('\r\n'))
            send_all(sock, to_bytes('0\r\n\r\n'))
            reader = SocketReader(sock)
            status, reason, headers = read_head(reader)
            return status == 200
        except Exception:
            return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def cleanup_tree(path):
    """Remove a temporary directory tree (os.walk works on 2.3)."""
    try:
        for root, dirs, files in os.walk(fsenc(path), topdown=0):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except Exception:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except Exception:
                    pass
        os.rmdir(fsenc(path))
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
