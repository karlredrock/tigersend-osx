# -*- coding: utf-8 -*-
"""TigerSend test suite.

Runs unchanged on the three Pythons that matter:

    /usr/bin/python    (2.3.5, Tiger)      <- the one that must not break
    python2.7          (Snow Leopard+)
    python3            (modern machines / CI)

No test framework and no dependencies: on Tiger there is no pip and no
unittest.mock, so this file is plain Python with a tiny runner.

    python tigersend.py --self-test     # quick, built into the app
    python tests/test_tigersend.py      # this, more thorough
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import tigersend as ts

FAILURES = []
PASSED = [0]
SKIPPED = []


def check(name, condition, detail=''):
    if condition:
        PASSED[0] = PASSED[0] + 1
        return True
    FAILURES.append(name)
    write('FAIL  %s  %s' % (name, detail))
    return False


def write(text):
    data = ts.to_bytes(ts.to_text(text) + u'\n')
    stream = getattr(sys.stdout, 'buffer', None)
    if stream is not None:
        stream.write(data)
        stream.flush()
    else:
        sys.stdout.write(data)
        sys.stdout.flush()


def skip(name, why):
    SKIPPED.append(name)
    write('skip  %s (%s)' % (name, why))


def expect_error(name, callable_object, *args, **kwargs):
    try:
        callable_object(*args, **kwargs)
    except Exception:
        return check(name, True)
    return check(name, False, 'no exception raised')


def temp_dir():
    return tempfile.mkdtemp(prefix='tigersend-test-')


def remove_dir(path):
    ts.cleanup_tree(path)


def free_port():
    """Ask the OS for a port, then hand it back."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    finally:
        sock.close()
    return port


def wait_for(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def make_file(folder, name, content):
    path = os.path.join(folder, name)
    handle = open(ts.fsenc(path), 'wb')
    try:
        handle.write(ts.to_bytes(content))
    finally:
        handle.close()
    return path


# ===========================================================================
#  1. JSON codec
# ===========================================================================
JSON_SAMPLES = [
    {},
    {'a': 1},
    {'alias': u'Ana\u2019s iPhone', 'port': 53317, 'download': False},
    {'nested': {'x': [1, 2, 3], 'y': [None, True, False]}},
    {'size': 1234567890123, 'ratio': -0.5, 'exp': 1e-7},
    {'emoji': ts._from_codepoint(0x1f600)},
    {'empty_string': u'', 'spaces': u'   ', 'slash': u'a/b\\c'},
    {'quote': u'he said "hi"', 'tab': u'a\tb', 'nl': u'a\nb'},
    {'accent': u'caf\u00e9 \u00f1and\u00fa \u00e4\u00f6\u00fc'},
    {'cjk': u'\u4e2d\u6587\u30c6\u30b9\u30c8'},
    {'deep': [[[[[1]]]]]},
]


def test_json():
    # the real json module (when present) and the built-in codec must agree
    for index in range(len(JSON_SAMPLES)):
        sample = JSON_SAMPLES[index]
        encoded = ts.json_dumps(sample)
        if not check('json encode is text', isinstance(encoded, ts.text_type),
                     type(encoded)):
            continue
        ascii_only = 1
        for char in encoded:
            if ord(char) > 127:
                ascii_only = 0
        check('json ascii only', ascii_only, repr(encoded[:80]))
        decoded = ts.json_loads(encoded)
        check('json round trip sample %d' % index, decoded == sample,
              repr(decoded)[:120])

    # force the mini codec, even on Python 2.6+/3.x
    saved = ts._json_module
    ts._json_module = None
    try:
        for index in range(len(JSON_SAMPLES)):
            sample = JSON_SAMPLES[index]
            encoded = ts.json_dumps(sample)
            if not check('mini json encode is text',
                         isinstance(encoded, ts.text_type), type(encoded)):
                continue
            decoded = ts.json_loads(encoded)
            check('mini json round trip sample %d' % index,
                  decoded == sample, repr(decoded)[:120])
        check('mini json accepts bytes', ts.json_loads(ts.to_bytes(
            u'{"a":1}')) == {'a': 1})
        check('mini json whitespace', ts.json_loads(
            u'  \r\n\t {"a" : [ 1 , 2 ] }  ') == {'a': [1, 2]})
        check('mini json escapes', ts.json_loads(
            u'{"a":"\\u00e9\\n\\t\\"\\\\\\/"}') == {'a': u'\u00e9\n\t"\\/'})
        check('mini json surrogate pair', ts.json_loads(
            u'{"e":"\\ud83d\\ude00"}') == {'e': ts._from_codepoint(0x1f600)})
        check('mini json lone surrogate is replaced',
              ts.json_loads(u'{"e":"\\udc00"}') == {'e': u'\ufffd'})
        check('mini json bom', ts.json_loads(u'\ufeff{"a":1}') == {'a': 1})
        expect_error('mini json rejects garbage', ts.json_loads, u'{oops')
        expect_error('mini json rejects truncated', ts.json_loads, u'{"a":')
        expect_error('mini json rejects text', ts.json_loads, u'hello')
        # what LocalSend actually sends
        announce = (u'{"alias":"Ana\'s iPhone","version":"2.1",'
                    u'"deviceModel":"iPhone 13","deviceType":"mobile",'
                    u'"fingerprint":"abc123","port":53317,"protocol":"http",'
                    u'"download":false,"announce":true}')
        parsed = ts.json_loads(announce)
        check('localSend announcement', parsed.get('alias') == u"Ana's iPhone"
              and parsed.get('port') == 53317 and parsed.get('announce') is True,
              repr(parsed))
    finally:
        ts._json_module = saved

    # unicode helpers
    check('to_text(bytes)', ts.to_text(ts.to_bytes(u'caf\u00e9'))
          == u'caf\u00e9')
    check('to_bytes(unicode)',
          ts.to_text(ts.to_bytes(u'caf\u00e9')) == u'caf\u00e9')
    check('to_text(latin1 fallback)', ts.to_text('\xe9') == u'\xe9')
    check('log_text with bytes',
          ts.log_text(u'x=%s', ts.to_bytes(u'caf\u00e9')) == u'x=caf\u00e9',
          repr(ts.log_text(u'x=%s', ts.to_bytes(u'caf\u00e9'))))
    check('log_text with unicode', ts.log_text(u'x=%s', u'\u00f1')
          == u'x=\u00f1')
    check('log_text with int', ts.log_text(u'x=%d', 42) == u'x=42')


# ===========================================================================
#  2. Helpers
# ===========================================================================
def test_helpers():
    check('human_size bytes', ts.human_size(999) == u'999 B',
          ts.human_size(999))
    check('human_size KB', ts.human_size(2048) == u'2.0 KB',
          ts.human_size(2048))
    check('human_size GB', ts.human_size(3 * 1073741824) == u'3.0 GB',
          ts.human_size(3 * 1073741824))
    check('human_size long', ts.human_size(ts.long_type(4294967296))
          == u'4.0 GB')
    check('human_size bad input', ts.human_size('abc') == u'?')

    check('safe_filename path', ts.safe_filename('/etc/passwd') == u'passwd')
    check('safe_filename windows path',
          ts.safe_filename(u'C:\\Users\\a\\b.txt') == u'b.txt')
    check('safe_filename dots', ts.safe_filename(u'..') == u'received.bin')
    check('safe_filename empty', ts.safe_filename(u'') == u'received.bin')
    check('safe_filename control', ts.safe_filename(u'a\x00b\x1fc') == u'a_b_c')
    check('safe_filename keeps unicode',
          ts.safe_filename(u'caf\u00e9 \u00f1.txt') == u'caf\u00e9 \u00f1.txt')
    long_name = u'a' * 400 + u'.txt'
    check('safe_filename truncates', len(ts.safe_filename(long_name)) <= 200,
          len(ts.safe_filename(long_name)))

    folder = temp_dir()
    try:
        path = make_file(folder, 'x.txt', 'hello')
        check('unique_path free name',
              ts.unique_path(folder, u'x.txt') == os.path.join(folder,
                                                               u'x (1).txt'))
        check('unique_path new name', ts.unique_path(folder, u'y.txt')
              == os.path.join(folder, u'y.txt'))
        make_file(folder, u'x (1).txt', 'hello')
        check('unique_path second clash', ts.unique_path(folder, u'x.txt')
              == os.path.join(folder, u'x (2).txt'))
        check('unique_path unicode', ts.unique_path(folder, u'caf\u00e9.txt')
              == os.path.join(folder, u'caf\u00e9.txt'))
        check('ensure_folder creates', ts.ensure_folder(os.path.join(folder,
                                                                     'a/b')))
        check('url_quote', ts.url_quote(u'a b&c/d?e=f') == 'a%20b%26c%2Fd%3Fe'
              '%3Df', ts.url_quote(u'a b&c/d?e=f'))
        check('url_quote hex', ts.url_quote('deadbeef') == 'deadbeef')
        check('md5 known value',
              ts.md5_hex(u'abc') == '900150983cd24fb0d6963f7d28e17f72',
              ts.md5_hex(u'abc'))
        check('md5 bytes input', ts.md5_hex(ts.to_bytes(u'abc'))
              == '900150983cd24fb0d6963f7d28e17f72')
        first = ts.random_hex(16)
        second = ts.random_hex(16)
        check('random_hex length', len(first) == 32)
        check('random_hex changes', first != second)
        check('guess_mime', ts.guess_mime(u'photo.jpg') == u'image/jpeg',
              ts.guess_mime(u'photo.jpg'))
        check('guess_mime unknown',
              ts.guess_mime(u'x.nope') == u'application/octet-stream')
        check('split_path', ts.split_path('/a/b?x=1') == ('/a/b', 'x=1'))
        check('split_path plain', ts.split_path('/a/b') == ('/a/b', ''))
        check('query_value', ts.query_value('sessionId=abc&fileId=f1',
                                            'sessionId') == 'abc')
        check('query_value missing', ts.query_value('a=1', 'sessionId') == '')
        check('query_value encoded', ts.query_value('t=a%20b', 't') == 'a b')

        # config round trip
        cfg_path = os.path.join(folder, 'config.json')
        ts.save_config({'alias': u'Caf\u00e9', 'lang': 'es', 'port': 53317},
                       cfg_path)
        loaded = ts.load_config(cfg_path)
        check('config round trip', loaded.get('alias') == u'Caf\u00e9'
              and loaded.get('lang') == 'es', repr(loaded))
        check('config missing file', ts.load_config(os.path.join(folder,
                                                                 'nope')) == {})
        handle = open(cfg_path, 'wb')
        try:
            handle.write(ts.to_bytes('not json at all'))
        finally:
            handle.close()
        check('config garbage', ts.load_config(cfg_path) == {})

        # cancel flag
        flag = ts.CancelFlag()
        check('cancel flag clear', not flag.is_set())
        flag.set()
        check('cancel flag set', flag.is_set() and flag.isSet())
        flag.clear()
        check('cancel flag cleared', not flag.is_set())

        check('arch_label non empty', ts.arch_label() != u'')
        check('python_label', ts.python_label().startswith(u'Python '))
        check('os_label non empty', ts.os_label() != u'')
    finally:
        remove_dir(folder)


# ===========================================================================
#  3. HTTP client against a scripted server
# ===========================================================================
class ScriptedServer(object):
    """A one-shot HTTP server that answers with exactly what the test wants.

    It is written with raw sockets on purpose: BaseHTTPServer would normalise
    the odd responses (no Content-Length, chunked, gzip, "100 Continue") that
    this file exists to test.
    """

    def __init__(self, response_factory, require_continue=False):
        self.response_factory = response_factory
        self.require_continue = require_continue
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.request = None
        self.body = None
        self.error = None
        self.thread = threading.Thread(target=self.serve)
        self.thread.setDaemon(1)
        self.thread.start()

    def read_request(self, connection):
        reader = ts.SocketReader(connection)
        lines = []
        while 1:
            line = reader.readline()
            if not line or line.strip() == ts.EMPTY:
                break
            lines.append(line)
        head = ts.EMPTY.join(lines)
        text = ts.to_text(head)
        headers = {}
        method = ''
        path = ''
        parts = text.split('\r\n')[0].split(' ')
        if len(parts) >= 2:
            method = parts[0]
            path = parts[1]
        for line in text.split('\r\n')[1:]:
            if ':' in line:
                name, value = line.split(':', 1)
                headers[name.strip().lower()] = value.strip()
        body = ts.EMPTY
        if headers.get('transfer-encoding', '').lower() == 'chunked':
            body = ts.read_chunked(reader)
        elif headers.get('content-length'):
            body = reader.read(int(headers['content-length']))
        return method, path, headers, body

    def serve(self):
        connection = None
        try:
            try:
                connection, address = self.sock.accept()
                connection.settimeout(5.0)
                self.request = self.read_request(connection)
                method, path, headers, body = self.request
                self.body = body
                if self.require_continue:
                    ts.send_all(connection, ts.to_bytes(
                        'HTTP/1.1 100 Continue\r\n\r\n'))
                payload = self.response_factory(self.request)
                ts.send_all(connection, payload)
            except Exception:
                self.error = ts.to_text(sys.exc_info()[1])
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            try:
                self.sock.close()
            except Exception:
                pass

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.thread.join(5.0)


def test_http_client():
    # --- plain Content-Length response
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
        'Content-Length: 14\r\nConnection: close\r\n\r\n{"a": "hello"}'))
    try:
        response = ts.http_request('127.0.0.1', server.port, 'GET', '/x',
                                   timeout=5.0)
        check('http status 200', response.status == 200)
        check('http content-length body',
              response.json() == {'a': 'hello'}, response.summary())
        check('http method and path', server.request[0] == 'GET'
              and server.request[1] == '/x', repr(server.request[:2]))
        check('http sends host header',
              'host' in server.request[2], repr(server.request[2]))
    finally:
        server.close()

    # --- chunked response (what iOS/Swift hands back)
    def chunked(request):
        pieces = ['{"sess', 'ion":1', '}']
        body = ''
        for piece in pieces:
            body = body + '%x\r\n%s\r\n' % (len(piece), piece)
        return ts.to_bytes(
            'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
            'Transfer-Encoding: chunked\r\n\r\n' + body + '0\r\n\r\n')
    server = ScriptedServer(chunked)
    try:
        response = ts.http_request('127.0.0.1', server.port, 'POST', '/p',
                                   body=ts.to_bytes('{}'), timeout=5.0)
        check('http chunked body', response.json() == {'session': 1},
              response.summary())
    finally:
        server.close()

    # --- chunked with extensions and trailers
    def chunked_extensions(request):
        return ts.to_bytes(
            'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
            '5;name=value\r\n{"a":\r\n2\r\n1}\r\n0\r\nX-Trailer: 1\r\n\r\n')
    server = ScriptedServer(chunked_extensions)
    try:
        response = ts.http_request('127.0.0.1', server.port, 'GET', '/x',
                                   timeout=5.0)
        check('http chunk extensions/trailers', response.json() == {'a': 1},
              response.summary())
    finally:
        server.close()

    # --- gzip response
    try:
        import gzip
        buffer = ts.BytesIO()
        gzip_file = gzip.GzipFile(fileobj=buffer, mode='wb')
        gzip_file.write(ts.to_bytes('{"gzipped": true}'))
        gzip_file.close()
        compressed = buffer.getvalue()
        server = ScriptedServer(lambda request: (
            ts.to_bytes('HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n'
                        'Content-Length: %d\r\n\r\n' % len(compressed))
            + compressed))
        try:
            response = ts.http_request('127.0.0.1', server.port, 'GET', '/x',
                                       timeout=5.0)
            check('http gzip response', response.json() == {'gzipped': True},
                  response.summary())
        finally:
            server.close()
    except ImportError:
        skip('http gzip response', 'no gzip/zlib in this Python build')

    # --- no Content-Length: body ends when the connection closes
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n'
        '{"closed": true}'))
    try:
        response = ts.http_request('127.0.0.1', server.port, 'GET', '/x',
                                   timeout=5.0)
        check('http close-delimited body',
              response.json() == {'closed': True}, response.summary())
    finally:
        server.close()

    # --- 204 with no body
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'))
    try:
        response = ts.http_request('127.0.0.1', server.port, 'POST', '/p',
                                   body=ts.to_bytes('{}'), timeout=5.0)
        check('http 204', response.status == 204
              and to_bytes_safe(response.body) == ts.EMPTY,
              response.summary())
    finally:
        server.close()

    # --- 403 keeps the body for the activity log
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.1 403 Forbidden\r\nContent-Length: 24\r\n\r\n'
        '{"message": "refused..."}'))
    try:
        response = ts.http_request('127.0.0.1', server.port, 'POST', '/p',
                                   body=ts.to_bytes('{}'), timeout=5.0)
        check('http 403 body kept', response.status == 403
              and response.body != ts.EMPTY, response.summary())
    finally:
        server.close()

    # --- 100-continue interim response must be skipped
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'),
        require_continue=True)
    try:
        response = ts.http_request(
            '127.0.0.1', server.port, 'POST', '/p', body=ts.to_bytes('{}'),
            headers={'Expect': '100-continue'}, timeout=5.0)
        check('http skips 100-continue', response.status == 200
              and response.json() == {}, response.summary())
    finally:
        server.close()

    # --- file upload streams the bytes and the declared length
    folder = temp_dir()
    try:
        payload = 'A' * 200000
        path = make_file(folder, 'upload.bin', payload)
        server = ScriptedServer(lambda request: ts.to_bytes(
            'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'))
        try:
            progress = []
            response = ts.http_request(
                '127.0.0.1', server.port, 'POST', '/upload', file_path=path,
                file_size=len(payload), timeout=5.0,
                on_progress=lambda done, total: progress.append(done))
            check('http upload status', response.status == 200)
            check('http upload content length header',
                  server.request[2].get('content-length') == str(len(payload)),
                  repr(server.request[2].get('content-length')))
            check('http upload body received',
                  len(server.body) == len(payload), len(server.body))
            check('http upload progress reported', len(progress) > 1,
                  repr(progress[:4]))
        finally:
            server.close()

        # --- cancelling during an upload raises TransferCancelled
        flag = ts.CancelFlag()
        server = ScriptedServer(lambda request: ts.to_bytes(
            'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'))
        try:
            thrown = []
            try:
                ts.http_request(
                    '127.0.0.1', server.port, 'POST', '/upload',
                    file_path=path, file_size=len(payload), timeout=5.0,
                    cancel_flag=flag,
                    on_progress=lambda done, total: flag.set())
            except ts.TransferCancelled:
                thrown.append(1)
            except Exception:
                thrown.append(0)
                write('      unexpected: %s' % ts.to_text(sys.exc_info()[1]))
            check('http cancel raises TransferCancelled', thrown == [1])
        finally:
            server.close()

        # --- an unreachable peer must raise quickly (timeout works)
        port = free_port()
        started = time.time()
        expect_error('http connect failure raises', ts.http_request,
                     '127.0.0.1', port, 'GET', '/x', timeout=1.0)
        check('http connect failure is quick', time.time() - started < 3.0,
              time.time() - started)
    finally:
        remove_dir(folder)

    # --- http_json posts JSON with the right header
    server = ScriptedServer(lambda request: ts.to_bytes(
        'HTTP/1.1 200 OK\r\nContent-Length: 12\r\n\r\n{"ok": true}'))
    try:
        response = ts.http_json('127.0.0.1', server.port, 'POST', '/p',
                                {'info': {'alias': u'Caf\u00e9'}}, timeout=5.0)
        check('http_json response', response.json() == {'ok': True})
        check('http_json content type',
              server.request[2].get('content-type')
              == 'application/json', repr(server.request[2].get('content-type')))
        check('http_json body', ts.json_loads(server.body).get('info', {}).get(
            'alias') == u'Caf\u00e9', ts.to_text(server.body))
    finally:
        server.close()


def to_bytes_safe(value):
    return ts.to_bytes(value)


# ===========================================================================
#  4. The LocalSend v2 server
# ===========================================================================
def start_engine(alias=u'Test', folder=None, echo=0):
    folder = folder or temp_dir()
    engine = ts.TigerSendEngine(alias=alias, save_dir=folder, port=0,
                                cfg_file=os.path.join(folder, 'cfg.json'),
                                echo=echo)
    engine.start_server()
    return engine


def stop_engine(engine):
    engine.stop()


def raw_request(port, text, body=None):
    if body is None:
        body = ts.EMPTY
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(10.0)
        sock.connect(('127.0.0.1', port))
        ts.send_all(sock, ts.to_bytes(text))
        if body:
            ts.send_all(sock, ts.to_bytes(body))
        reader = ts.SocketReader(sock)
        status, reason, headers = ts.read_head(reader)
        payload = ts.EMPTY
        if headers.get('transfer-encoding', '').lower().find('chunked') >= 0:
            payload = ts.read_chunked(reader)
        elif headers.get('content-length'):
            payload = reader.read(int(headers['content-length']))
        else:
            payload = reader.read_all()
        return status, headers, payload
    finally:
        try:
            sock.close()
        except Exception:
            pass


def test_server():
    folder = temp_dir()
    engine = start_engine(u'Caf\u00e9 Mac', folder)
    port = engine.port
    try:
        # --- GET /info
        response = ts.http_request('127.0.0.1', port, 'GET',
                                   ts.API_BASE + '/info', timeout=5.0)
        info = response.json()
        check('server info status', response.status == 200, response.summary())
        check('server info alias', info.get('alias') == u'Caf\u00e9 Mac',
              repr(info.get('alias')))
        check('server info protocol', info.get('protocol') == 'http')
        check('server info download flag', info.get('download') is False)
        check('server info port', info.get('port') == port, info.get('port'))
        check('server info fingerprint', info.get('fingerprint')
              == engine.fingerprint)
        check('server info no announce',
              info.get('announce') is False, repr(info.get('announce')))
        check('server info json content type',
              response.header('content-type', '').find('json') >= 0)

        # --- v1 info, for old clients
        response = ts.http_request('127.0.0.1', port, 'GET',
                                   '/api/localsend/v1/info', timeout=5.0)
        check('server v1 info', response.status == 200, response.summary())

        # --- register
        response = ts.http_json('127.0.0.1', port, 'POST',
                                ts.API_BASE + '/register',
                                {'alias': u'Ana iPhone', 'fingerprint': 'fp1',
                                 'deviceModel': 'iPhone 13', 'port': 53317,
                                 'protocol': 'http'}, timeout=5.0)
        check('server register', response.status == 200, response.summary())
        check('server register adds device', engine.device_count() == 1,
              engine.device_count())
        check('server register keeps alias',
              engine.devices[0]['alias'] == u'Ana iPhone',
              repr(engine.devices[0]['alias']))

        # --- register with its own fingerprint must not add itself
        ts.http_json('127.0.0.1', port, 'POST', ts.API_BASE + '/register',
                     engine.device_info(0), timeout=5.0)
        check('server ignores its own register', engine.device_count() == 1,
              engine.device_count())

        # --- prepare-upload + upload (plain Content-Length)
        name = u'caf\u00e9 \u00f1.txt'
        payload = 'hello tiger'
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'alias': u'Ana iPhone',
                                         'fingerprint': 'fp1',
                                         'port': 53317},
                                'files': {'f1': {'id': 'f1',
                                                 'fileName': name,
                                                 'size': len(payload),
                                                 'fileType': 'text/plain'}}},
                               timeout=5.0)
        check('server prepare-upload', prepare.status == 200,
              prepare.summary())
        answer = prepare.json()
        session_id = ts.to_text(answer.get('sessionId') or '')
        token = ts.to_text((answer.get('files') or {}).get('f1') or '')
        check('server prepare returns token', session_id != u''
              and token != u'', repr(answer))

        upload_path = (ts.API_BASE + '/upload?sessionId=%s&fileId=f1&token=%s'
                       % (ts.url_quote(session_id), ts.url_quote(token)))
        response = ts.http_request('127.0.0.1', port, 'POST', upload_path,
                                   body=ts.to_bytes(payload), timeout=5.0)
        check('server upload 200', response.status == 200, response.summary())
        saved = os.path.join(folder, ts.safe_filename(name))
        check('server upload wrote the file', os.path.exists(ts.fsenc(saved)),
              saved)
        if os.path.exists(ts.fsenc(saved)):
            handle = open(ts.fsenc(saved), 'rb')
            try:
                content = ts.to_text(handle.read())
            finally:
                handle.close()
            check('server upload content', content == payload, repr(content))
        check('server session dropped after last file',
              engine.get_session(session_id) is None)

        # --- name clash becomes " (1)"
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1', 'port': 53317},
                                'files': {'f1': {'id': 'f1',
                                                 'fileName': name,
                                                 'size': 3,
                                                 'fileType': 'text/plain'}}},
                               timeout=5.0)
        answer = prepare.json()
        session_id = ts.to_text(answer.get('sessionId') or '')
        token = ts.to_text((answer.get('files') or {}).get('f1') or '')
        response = ts.http_request(
            '127.0.0.1', port, 'POST',
            ts.API_BASE + '/upload?sessionId=%s&fileId=f1&token=%s'
            % (ts.url_quote(session_id), ts.url_quote(token)),
            body=ts.to_bytes('abc'), timeout=5.0)
        base = ts.safe_filename(name)
        stem, extension = os.path.splitext(base)
        clash = os.path.join(folder, stem + u' (1)' + extension)
        check('server name clash resolved', os.path.exists(ts.fsenc(clash)),
              clash)

        # --- chunked upload with an Expect: 100-continue handshake, done by
        #     hand so the interim response is really checked on every Python
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1', 'port': 53317},
                                'files': {'f2': {'id': 'f2',
                                                 'fileName': 'chunky.bin',
                                                 'size': 9,
                                                 'fileType': 'text/plain'}}},
                               timeout=5.0)
        answer = prepare.json()
        session_id = ts.to_text(answer.get('sessionId') or '')
        token = ts.to_text((answer.get('files') or {}).get('f2') or '')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(10.0)
            sock.connect(('127.0.0.1', port))
            head = ('POST %s/upload?sessionId=%s&fileId=f2&token=%s HTTP/1.1\r\n'
                    'Host: 127.0.0.1\r\n'
                    'Transfer-Encoding: chunked\r\n'
                    'Expect: 100-continue\r\n\r\n'
                    % (ts.API_BASE, ts.url_quote(session_id),
                       ts.url_quote(token)))
            ts.send_all(sock, ts.to_bytes(head))
            reader = ts.SocketReader(sock)
            interim_status = None
            try:
                interim_status, interim_reason, interim_headers = \
                    ts.read_head(reader)
            except Exception:
                interim_status = None
            check('server answers 100-continue', interim_status == 100,
                  repr(interim_status))
            ts.send_all(sock, ts.to_bytes('5\r\nhello\r\n'))
            ts.send_all(sock, ts.to_bytes('4\r\n wor\r\n0\r\n\r\n'))
            final_status, final_reason, final_headers = ts.read_head(reader)
            check('server chunked upload 200', final_status == 200,
                  repr(final_status))
            if final_headers.get('content-length'):
                reader.read(int(final_headers['content-length']))
        finally:
            try:
                sock.close()
            except Exception:
                pass
        chunky = os.path.join(folder, u'chunky.bin')
        check('server chunked upload wrote the file',
              os.path.exists(ts.fsenc(chunky)), chunky)
        if os.path.exists(ts.fsenc(chunky)):
            handle = open(ts.fsenc(chunky), 'rb')
            try:
                content = ts.to_text(handle.read())
            finally:
                handle.close()
            check('server chunked upload content', content == 'hello wor',
                  repr(content))

        # --- HTTP/1.0 client (very old senders) with Content-Length
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1', 'port': 53317},
                                'files': {'f3': {'id': 'f3',
                                                 'fileName': 'ancient.txt',
                                                 'size': 4,
                                                 'fileType': 'text/plain'}}},
                               timeout=5.0)
        answer = prepare.json()
        session_id = ts.to_text(answer.get('sessionId') or '')
        token = ts.to_text((answer.get('files') or {}).get('f3') or '')
        status, headers, body = raw_request(
            port,
            'POST %s/upload?sessionId=%s&fileId=f3&token=%s HTTP/1.0\r\n'
            'Content-Length: 4\r\n\r\n'
            % (ts.API_BASE, ts.url_quote(session_id), ts.url_quote(token)),
            body='old!')
        check('server HTTP/1.0 upload', status == 200, repr(status))
        check('server HTTP/1.0 file',
              os.path.exists(ts.fsenc(os.path.join(folder, u'ancient.txt'))))

        # --- bad requests
        status, headers, body = raw_request(
            port, 'POST %s/prepare-upload HTTP/1.1\r\nContent-Length: 5\r\n\r\n'
            % ts.API_BASE, body='{oops')
        check('server bad json -> 400', status == 400, repr(status))

        response = ts.http_request(
            '127.0.0.1', port, 'POST',
            ts.API_BASE + '/upload?sessionId=nope&fileId=f1&token=x',
            body=ts.to_bytes('x'), timeout=5.0)
        check('server unknown session -> 403', response.status == 403,
              response.summary())

        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1'},
                                'files': {'f9': {'id': 'f9',
                                                 'fileName': 'tok.txt',
                                                 'size': 1}}}, timeout=5.0)
        answer = prepare.json()
        session_id = ts.to_text(answer.get('sessionId') or '')
        response = ts.http_request(
            '127.0.0.1', port, 'POST',
            ts.API_BASE + '/upload?sessionId=%s&fileId=f9&token=wrong'
            % ts.url_quote(session_id), body=ts.to_bytes('x'), timeout=5.0)
        check('server bad token -> 403', response.status == 403,
              response.summary())

        response = ts.http_request('127.0.0.1', port, 'GET', '/nope',
                                   timeout=5.0)
        check('server unknown path -> 404', response.status == 404,
              response.summary())
        response = ts.http_request('127.0.0.1', port, 'GET', '/', timeout=5.0)
        check('server index page', response.status == 200
              and ts.to_text(response.body).find('TigerSend') >= 0,
              response.summary())

        # --- empty prepare-upload (the user pressed "decline")
        response = ts.http_json('127.0.0.1', port, 'POST',
                                ts.API_BASE + '/prepare-upload',
                                {'info': {'fingerprint': 'fp1'},
                                 'files': {}}, timeout=5.0)
        check('server empty prepare -> 204', response.status == 204,
              response.summary())

        # --- cancel with a JSON body instead of the query string (SnowSend)
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1'},
                                'files': {'f8': {'id': 'f8',
                                                 'fileName': 'c.txt',
                                                 'size': 1}}}, timeout=5.0)
        session_id = ts.to_text(prepare.json().get('sessionId') or '')
        check('server session exists before cancel',
              engine.get_session(session_id) is not None)
        response = ts.http_json('127.0.0.1', port, 'POST',
                                ts.API_BASE + '/cancel',
                                {'sessionId': session_id}, timeout=5.0)
        check('server cancel with JSON body', response.status == 200,
              response.summary())
        check('server cancel dropped session',
              engine.get_session(session_id) is None)

        # --- a file that never finishes must not stay as a .part file
        prepare = ts.http_json('127.0.0.1', port, 'POST',
                               ts.API_BASE + '/prepare-upload',
                               {'info': {'fingerprint': 'fp1'},
                                'files': {'f7': {'id': 'f7',
                                                 'fileName': 'short.txt',
                                                 'size': 100}}}, timeout=5.0)
        session_id = ts.to_text(prepare.json().get('sessionId') or '')
        token = ts.to_text((prepare.json().get('files') or {}).get('f7') or '')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(10.0)
            sock.connect(('127.0.0.1', port))
            ts.send_all(sock, ts.to_bytes(
                'POST %s/upload?sessionId=%s&fileId=f7&token=%s HTTP/1.1\r\n'
                'Content-Length: 100\r\n\r\nonly-ten!!'
                % (ts.API_BASE, ts.url_quote(session_id), ts.url_quote(token))))
        finally:
            sock.close()
        time.sleep(0.4)
        leftovers = []
        for entry in os.listdir(ts.fsenc(folder)):
            if entry.endswith('.part'):
                leftovers.append(entry)
        check('server removes partial file on short upload',
              leftovers == [], repr(leftovers))
    finally:
        stop_engine(engine)
        remove_dir(folder)


# ===========================================================================
#  5. Discovery
# ===========================================================================
def test_discovery():
    folder = temp_dir()
    engine = ts.TigerSendEngine(alias=u'Discover', save_dir=folder, port=0,
                                cfg_file=os.path.join(folder, 'cfg.json'),
                                echo=0)
    engine.start()
    try:
        peer = {
            'alias': u'iPhone de Ana',
            'version': '2.1',
            'deviceModel': 'iPhone 13',
            'deviceType': 'mobile',
            'fingerprint': 'peer-fingerprint',
            'port': 53317,
            'protocol': 'http',
            'download': False,
            'announce': True,
        }
        # unicast to the multicast port: the listener binds INADDR_ANY
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(ts.to_bytes(ts.json_dumps(peer)),
                        ('127.0.0.1', engine.port))
            sock.sendto(ts.to_bytes(ts.json_dumps(peer)),
                        ('127.0.0.1', engine.port))
        finally:
            sock.close()
        found = wait_for(lambda: engine.device_count() > 0, 5.0)
        check('discovery adds the peer', found, engine.device_count())
        if found:
            check('discovery keeps the alias',
                  engine.devices[0]['alias'] == u'iPhone de Ana',
                  repr(engine.devices[0]['alias']))
            check('discovery keeps the model',
                  engine.devices[0]['model'] == 'iPhone 13',
                  repr(engine.devices[0]['model']))
            check('discovery remembers the address',
                  engine.devices[0]['ip'] == '127.0.0.1',
                  engine.devices[0]['ip'])
            # a second announcement updates instead of duplicating
            peer['alias'] = u'Renamed iPhone'
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(ts.to_bytes(ts.json_dumps(peer)),
                            ('127.0.0.1', engine.port))
            finally:
                sock.close()
            wait_for(lambda: engine.devices[0]['alias'] == u'Renamed iPhone',
                     3.0)
            check('discovery updates in place', engine.device_count() == 1
                  and engine.devices[0]['alias'] == u'Renamed iPhone',
                  engine.device_count())

        # garbage on the wire must not kill the listener
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(ts.to_bytes('not json'), ('127.0.0.1', engine.port))
            sock.sendto(ts.to_bytes('[1,2,3]'), ('127.0.0.1', engine.port))
            sock.sendto(ts.to_bytes('{"fingerprint":"x"}'),
                        ('127.0.0.1', engine.port))
        finally:
            sock.close()
        time.sleep(0.3)
        # 'not json' and '[1,2,3]' are ignored; the minimal but valid packet
        # adds one more (unknown) device
        check('discovery survives garbage', engine.device_count() == 2,
              engine.device_count())

        # announce does not raise even without a working multicast route
        engine.send_announcement(quiet=1)
        check('announce runs', True)
    finally:
        engine.stop()
        remove_dir(folder)


# ===========================================================================
#  6. Sending, end to end, including cancellation
# ===========================================================================
def test_send():
    folder = temp_dir()
    inbox = os.path.join(folder, 'inbox')
    ts.ensure_folder(inbox)
    receiver = ts.TigerSendEngine(alias=u'Receiver', save_dir=inbox, port=0,
                                  cfg_file=os.path.join(folder, 'r.json'),
                                  echo=0)
    receiver.start_server()
    sender = ts.TigerSendEngine(alias=u'Sender', port=0,
                                cfg_file=os.path.join(folder, 's.json'),
                                echo=0)
    try:
        device = {'ip': '127.0.0.1', 'port': receiver.port,
                  'alias': u'Receiver', 'fingerprint': receiver.fingerprint,
                  'model': u'test'}
        big = make_file(folder, u'\u00f1and\u00fa report.txt', 'x' * 300000)
        small = make_file(folder, 'empty.bin', '')
        sent, total = sender.send_files(device, [big, small])
        check('send two files', sent == 2 and total == 2,
              '%d/%d' % (sent, total))
        arrived = os.path.join(inbox, ts.safe_filename(u'\u00f1and\u00fa report'
                                                       u'.txt'))
        check('send unicode file name arrived',
              os.path.exists(ts.fsenc(arrived)), arrived)
        if os.path.exists(ts.fsenc(arrived)):
            check('send unicode file size',
                  os.path.getsize(ts.fsenc(arrived)) == 300000,
                  os.path.getsize(ts.fsenc(arrived)))
        check('send empty file arrived',
              os.path.exists(ts.fsenc(os.path.join(inbox, u'empty.bin'))))

        # a device that is not there: prepare-upload fails, nothing crashes
        dead = {'ip': '127.0.0.1', 'port': free_port(), 'alias': u'ghost'}
        sent, total = sender.send_files(dead, [big])
        check('send to missing device fails cleanly', sent == 0 and total == 1,
              '%d/%d' % (sent, total))

        # cancellation in the middle of the big file
        logs = []
        sender.on_log = lambda text: logs.append(text)
        cancel_once = [0]

        def progress(done, total_bytes):
            if cancel_once[0] == 0 and done > 0:
                cancel_once[0] = 1
                sender.cancel_transfer()
        sender.on_progress = progress
        huge = make_file(folder, 'huge.bin', 'y' * 1000000)
        sent, total = sender.send_files(device, [huge])
        check('cancelled send reports zero', sent == 0,
              '%d/%d' % (sent, total))
        saw_cancel = 0
        for text in logs:
            if text.lower().find('cancel') >= 0:
                saw_cancel = 1
        check('cancelled send logs the cancel', saw_cancel, repr(logs[-3:]))
        time.sleep(0.3)
        cancelled_file = os.path.join(inbox, u'huge.bin')
        check('cancelled transfer leaves no finished file',
              not os.path.exists(ts.fsenc(cancelled_file)))
        parts = [name for name in os.listdir(ts.fsenc(inbox))
                 if name.endswith('.part')]
        check('cancelled transfer leaves no .part file', parts == [],
              repr(parts))
        sender.on_progress = None
        sender.on_log = None
    finally:
        receiver.stop()
        sender.stop()
        remove_dir(folder)


# ===========================================================================
#  7. GUI wiring, with a fake Tkinter
# ===========================================================================
def test_gui():
    import fake_tk

    saved = (ts.Tkinter, ts.tkFileDialog, ts.tkMessageBox, ts.HAVE_TK)
    ts.Tkinter = fake_tk.Tkinter
    ts.tkFileDialog = fake_tk.tkFileDialog
    ts.tkMessageBox = fake_tk.tkMessageBox
    ts.HAVE_TK = 1
    folder = temp_dir()
    engine = None
    try:
        fake_tk.tkMessageBox.messages = []
        fake_tk.tkFileDialog.calls = []
        engine = ts.TigerSendEngine(alias=u'GUI Mac', save_dir=folder,
                                    port=0,
                                    cfg_file=os.path.join(folder, 'cfg.json'))
        root = fake_tk.Tkinter.Tk()
        gui = ts.TigerSendGUI(root, engine)
        check('gui builds', gui is not None)
        check('gui window title', 'TigerSend' in root.title(), root.title())
        check('gui title label', 'LocalSend' in gui.lbl_title.cget('text'),
              gui.lbl_title.cget('text'))
        check('gui language buttons', len(gui.radio_langs) == len(ts.LANG_ORDER))
        check('gui status label',
              'Ready' in gui.lbl_status.cget('text')
              or 'Listo' in gui.lbl_status.cget('text'),
              gui.lbl_status.cget('text'))
        check('gui shows the architecture', 'PowerPC' in gui.lbl_system.cget(
            'text') or 'Intel' in gui.lbl_system.cget('text'),
            gui.lbl_system.cget('text'))

        # every language must translate every widget without exploding
        for code in ts.LANG_ORDER:
            gui.var_lang.set(code)
            gui.on_language()
            check('gui language %s' % code, gui.lbl_name.cget('text')
                  == ts.TR[code]['name'], gui.lbl_name.cget('text'))
        gui.var_lang.set('en')
        gui.on_language()

        # adding files through the dialog
        path = make_file(folder, 'photo.jpg', 'xyz')
        fake_tk.tkFileDialog.next_open_names = [path]
        gui.on_add_files()
        check('gui add file', len(gui.pending_files) == 1,
              len(gui.pending_files))
        check('gui file list shown', len(gui.lst_files.items) == 1,
              gui.lst_files.items)
        check('gui file queue in engine', len(engine.files) == 1)
        gui.on_add_files()      # same file again: no duplicate
        check('gui does not duplicate', len(gui.pending_files) == 1)

        # clipboard
        root.clipboard = u'text from the clipboard \u00f1'
        gui.on_paste_clipboard()
        check('gui paste clipboard', len(gui.pending_files) == 2,
              len(gui.pending_files))
        root.clipboard = ''
        gui.on_paste_clipboard()
        check('gui empty clipboard warns', len(fake_tk.tkMessageBox.messages)
              == 1, fake_tk.tkMessageBox.messages)

        # remove / clear
        gui.lst_files.selection = ('0',)
        gui.on_remove_file()
        check('gui remove file', len(gui.pending_files) == 1,
              len(gui.pending_files))
        gui.on_clear_files()
        check('gui clear list', len(gui.pending_files) == 0
              and len(gui.lst_files.items) == 0)

        # sending without a device or without files warns
        messages_before = len(fake_tk.tkMessageBox.messages)
        gui.on_send()
        check('gui send without device warns',
              len(fake_tk.tkMessageBox.messages) == messages_before + 1,
              fake_tk.tkMessageBox.messages[-1:])

        # buttons
        gui.btn_announce.invoke()
        gui.btn_scan.invoke()
        gui.btn_clearlog.invoke()
        check('gui clear log', gui.txt_activity.content == '')

        # the activity log receives engine output
        engine.log(u'test line with \u00f1')
        gui.poll_queue()
        check('gui activity log', u'test line' in gui.txt_activity.content,
              gui.txt_activity.content[-80:])

        # device table refresh
        engine.remember_device({'alias': u'Ana iPhone',
                                'deviceModel': 'iPhone 13',
                                'fingerprint': 'fp-gui',
                                'port': 53317}, '192.168.1.50')
        gui.refresh_devices()
        check('gui device row', len(gui.lst_devices.items) == 1,
              gui.lst_devices.items)
        check('gui device row content',
              'Ana iPhone' in gui.lst_devices.items[0]
              and '192.168.1.50' in gui.lst_devices.items[0],
              repr(gui.lst_devices.items))

        # selecting a device and sending a queued file, for real
        gui.add_path(make_file(folder, 'send-me.txt', 'payload'))
        gui.lst_devices.selection = ('0',)
        devices = engine.devices
        receiver = ts.TigerSendEngine(alias=u'GUI receiver',
                                      save_dir=os.path.join(folder, 'in'),
                                      port=0,
                                      cfg_file=os.path.join(folder, 'r.json'))
        receiver.start_server()
        try:
            devices[0]['port'] = receiver.port
            devices[0]['ip'] = '127.0.0.1'
            gui.on_send()
            arrived = wait_for(lambda: os.path.exists(ts.fsenc(
                os.path.join(folder, 'in', u'send-me.txt'))), 10.0)
            check('gui sends a queued file', arrived)
        finally:
            receiver.stop()

        # alias change and folder change
        gui.var_alias.set(u'Renamed Mac')
        gui.on_apply_alias()
        check('gui alias applied', engine.alias == u'Renamed Mac',
              engine.alias)
        new_folder = os.path.join(folder, 'downloads')
        ts.ensure_folder(new_folder)
        fake_tk.tkFileDialog.next_directory = new_folder
        gui.on_change_dir()
        check('gui folder changed', engine.save_dir == new_folder,
              engine.save_dir)
        check('gui folder shown', gui.var_savedir.get() == new_folder)

        # status helpers
        gui.set_status_key('receiving')
        check('gui status receiving', 'Receiving' in gui.lbl_status.cget('text'))
        gui.show_progress(50, 100)
        check('gui progress shown', '50 B / 100 B' in gui.lbl_status.cget(
            'text'), gui.lbl_status.cget('text'))

        # closing
        gui.on_close()
        check('gui close stops the engine', not engine.running)
        check('gui close destroys the window', root.destroyed == 1)
    finally:
        try:
            if engine is not None:
                engine.stop()
        except Exception:
            pass
        ts.Tkinter, ts.tkFileDialog, ts.tkMessageBox, ts.HAVE_TK = saved
        remove_dir(folder)


# ===========================================================================
#  8. Command line
# ===========================================================================
def test_command_line():
    options = ts.parse_args([])
    check('cli defaults', options['headless'] == 0
          and options['port'] == ts.PORT and options['self_test'] == 0)
    options = ts.parse_args(['--headless', '--port', '53400',
                             '--alias', u'Mac \u00f1', '--save-dir', '/tmp/x'])
    check('cli parses', options['headless'] == 1 and options['port'] == 53400
          and options['alias'] == u'Mac \u00f1' and options['save_dir']
          == '/tmp/x', repr(options))
    options = ts.parse_args(['--alias=Equals', '--port=53401'])
    check('cli equals syntax', options['alias'] == 'Equals'
          and options['port'] == 53401, repr(options))
    options = ts.parse_args(['-psn_0_123456'])
    check('cli ignores Finder psn argument', options['headless'] == 0
          and options['port'] == ts.PORT)
    check('cli help flag', ts.parse_args(['--help'])['help'] == 1)
    check('cli version flag', ts.parse_args(['--version'])['version'] == 1)
    check('usage mentions Tiger', 'Tiger' in ts.USAGE, ts.USAGE[:40])
    check('main --version returns 0', ts.main(['--version']) == 0)
    check('self test passes', ts.run_self_test() == 0)


# ===========================================================================
#  9. The legacy checker itself
# ===========================================================================
def test_checker():
    if sys.version_info < (2, 5):
        skip('legacy checker', 'the ast module is too old on Python 2.3')
        return
    try:
        import check_legacy_syntax as checker
    except (ImportError, AttributeError, SyntaxError):
        skip('legacy checker', 'needs a newer Python')
        return

    problems = checker.check_source(os.path.join(ROOT, 'tigersend.py'))
    check('tigersend.py passes the Python 2.3 checker', problems == [],
          repr(problems[:5]))

    folder = temp_dir()
    try:
        bad = os.path.join(folder, 'bad.py')
        handle = open(bad, 'w')
        try:
            handle.write(
                "import json\n"
                "value = 1 if True else 2\n"
                "items = sorted([3, 1])\n"
                "try:\n"
                "    pass\n"
                "except Exception:\n"
                "    pass\n"
                "finally:\n"
                "    pass\n"
                "data = b'bytes'\n"
                "with open('x') as handle:\n"
                "    pass\n")
        finally:
            handle.close()
        found = checker.check_source(bad)
        text = '\n'.join(found)
        check('checker finds ternaries', 'ternary' in text, text)
        if sys.version_info[0] >= 3:
            check('checker finds except+finally', 'except+finally' in text,
                  text)
        else:
            # Python 2's ast splits try/except/finally into two nodes, so the
            # combined form is simply a syntax error there, not a style check
            skip('checker finds except+finally', 'Python 2 ast has no Try')
        check('checker finds sorted()', 'sorted()' in text, text)
        check('checker finds b"" literals', 'b"..."' in text, text)
        check('checker finds with', '"with"' in text, text)
        check('checker finds json import', 'import json' in text, text)
    finally:
        remove_dir(folder)


# ===========================================================================
#  Runner
# ===========================================================================
TESTS = [
    ('json', test_json),
    ('helpers', test_helpers),
    ('http_client', test_http_client),
    ('server', test_server),
    ('discovery', test_discovery),
    ('send', test_send),
    ('gui', test_gui),
    ('command_line', test_command_line),
    ('checker', test_checker),
]


def main(argv):
    wanted = argv[1:]
    started = time.time()
    write('TigerSend test suite - %s, %s'
          % (ts.python_label(), ts.os_label() or sys.platform))
    for name, function in TESTS:
        if wanted and name not in wanted:
            continue
        write('-- %s' % name)
        try:
            function()
        except Exception:
            error = ts.to_text(sys.exc_info()[1])
            FAILURES.append(name + ' (crashed)')
            write('CRASH %s: %s' % (name, error))
            import traceback
            traceback.print_exc()
    elapsed = time.time() - started
    write('')
    write('%d checks passed, %d failed, %d skipped in %.1fs'
          % (PASSED[0], len(FAILURES), len(SKIPPED), elapsed))
    if FAILURES:
        write('FAILURES: ' + ', '.join(FAILURES))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
