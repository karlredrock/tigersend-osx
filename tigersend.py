#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  TigerSend 1.7
#  LocalSend protocol v2 client for classic Mac OS X (Tiger 10.4 -> Snow Leopard 10.6)
#
#  - Pure standard library: Tkinter, socket, BaseHTTPServer, httplib, threading...
#  - Compatible with Python 2.3 / 2.4 (Tiger) and Python 2.6 / 2.7 (Snow Leopard).
#      * no "with" statements
#      * no "except Exception as e" (uses sys.exc_info()[1])
#      * no ternary expressions, generator expressions, decorators, sets, sorted()
#      * bundled mini JSON codec for Python < 2.6
#  - LocalSend v2, plain HTTP on port 53317, no TLS (Encryption OFF required on
#    the remote device), UDP multicast discovery on 224.0.0.167:53317.
#

import os
import sys
import socket
import threading
import time
import random
import mimetypes
import tempfile
import platform

import Tkinter
import tkFileDialog
import tkMessageBox

import BaseHTTPServer
import SocketServer
import httplib
import urlparse
import cgi
import Queue

APP_NAME        = 'TigerSend'
APP_VERSION     = '1.7'
PROTO_VERSION   = '2.0'
PORT            = 53317
MULTICAST_GROUP = '224.0.0.167'
CHUNK_SIZE      = 65536
DEFAULT_ALIAS   = 'Redstones-MacBook-Air'
CONFIG_PATH     = os.path.expanduser('~/.tigersend_config.json')

try:
    import cStringIO
    StringIO = cStringIO
except ImportError:
    import StringIO

# ---------------------------------------------------------------------------
#  md5 helper (hashlib is 2.5+, md5 module is the 2.3/2.4 fallback)
# ---------------------------------------------------------------------------
try:
    import hashlib
    def md5hex(s):
        return hashlib.md5(s).hexdigest()
except ImportError:
    import md5
    def md5hex(s):
        return md5.new(s).hexdigest()

# ---------------------------------------------------------------------------
#  Mini JSON codec (the "json" module only exists since Python 2.6)
# ---------------------------------------------------------------------------
def _json_escape(u):
    out = []
    for ch in u:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif code < 0x20 or code > 0x7e:
            out.append('\\u%04x' % code)
        else:
            out.append(str(ch))
    return ''.join(out)

def _mini_dumps(obj):
    if obj is None:
        return 'null'
    if isinstance(obj, bool):
        if obj:
            return 'true'
        return 'false'
    if isinstance(obj, (int, long)):
        return str(obj)
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, str):
        try:
            u = obj.decode('utf-8')
        except Exception:
            u = obj.decode('latin-1')
        return '"' + _json_escape(u) + '"'
    if isinstance(obj, unicode):
        return '"' + _json_escape(obj) + '"'
    if isinstance(obj, (list, tuple)):
        parts = []
        for item in obj:
            parts.append(_mini_dumps(item))
        return '[' + ','.join(parts) + ']'
    if isinstance(obj, dict):
        parts = []
        for key in obj.keys():
            parts.append(_mini_dumps(key) + ':' + _mini_dumps(obj[key]))
        return '{' + ','.join(parts) + '}'
    return _mini_dumps(str(obj))

class _MiniJSONError(Exception):
    pass

class _MiniJSONParser:
    def __init__(self, text):
        if isinstance(text, str):
            try:
                text = text.decode('utf-8')
            except Exception:
                text = text.decode('latin-1')
        self.s = text
        self.i = 0
        self.n = len(text)

    def error(self, msg):
        raise _MiniJSONError('%s at position %d' % (msg, self.i))

    def skip_ws(self):
        while self.i < self.n and self.s[self.i] in u' \t\r\n':
            self.i = self.i + 1

    def parse(self):
        self.skip_ws()
        val = self.parse_value()
        self.skip_ws()
        return val

    def parse_value(self):
        self.skip_ws()
        if self.i >= self.n:
            self.error('unexpected end of input')
        ch = self.s[self.i]
        if ch == u'{':
            return self.parse_object()
        if ch == u'[':
            return self.parse_array()
        if ch == u'"':
            return self.parse_string()
        if self.s[self.i:self.i + 4] == u'true':
            self.i = self.i + 4
            return True
        if self.s[self.i:self.i + 5] == u'false':
            self.i = self.i + 5
            return False
        if self.s[self.i:self.i + 4] == u'null':
            self.i = self.i + 4
            return None
        return self.parse_number()

    def parse_object(self):
        obj = {}
        self.i = self.i + 1  # skip {
        self.skip_ws()
        if self.i < self.n and self.s[self.i] == u'}':
            self.i = self.i + 1
            return obj
        while 1:
            self.skip_ws()
            if self.i >= self.n or self.s[self.i] != u'"':
                self.error('expected string key')
            key = self.parse_string()
            self.skip_ws()
            if self.i >= self.n or self.s[self.i] != u':':
                self.error('expected ":"')
            self.i = self.i + 1
            obj[key] = self.parse_value()
            self.skip_ws()
            if self.i < self.n and self.s[self.i] == u',':
                self.i = self.i + 1
                continue
            if self.i < self.n and self.s[self.i] == u'}':
                self.i = self.i + 1
                return obj
            self.error('expected "," or "}"')

    def parse_array(self):
        arr = []
        self.i = self.i + 1  # skip [
        self.skip_ws()
        if self.i < self.n and self.s[self.i] == u']':
            self.i = self.i + 1
            return arr
        while 1:
            arr.append(self.parse_value())
            self.skip_ws()
            if self.i < self.n and self.s[self.i] == u',':
                self.i = self.i + 1
                continue
            if self.i < self.n and self.s[self.i] == u']':
                self.i = self.i + 1
                return arr
            self.error('expected "," or "]"')

    def parse_string(self):
        self.i = self.i + 1  # skip opening quote
        out = []
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == u'"':
                self.i = self.i + 1
                return u''.join(out)
            if ch == u'\\':
                self.i = self.i + 1
                if self.i >= self.n:
                    self.error('bad escape')
                esc = self.s[self.i]
                if esc == u'n':
                    out.append(u'\n')
                elif esc == u't':
                    out.append(u'\t')
                elif esc == u'r':
                    out.append(u'\r')
                elif esc == u'b':
                    out.append(u'\b')
                elif esc == u'f':
                    out.append(u'\f')
                elif esc == u'u':
                    hexs = self.s[self.i + 1:self.i + 5]
                    try:
                        out.append(unichr(int(hexs, 16)))
                    except Exception:
                        self.error('bad \\u escape')
                    self.i = self.i + 4
                else:
                    out.append(esc)
                self.i = self.i + 1
            else:
                out.append(ch)
                self.i = self.i + 1
        self.error('unterminated string')

    def parse_number(self):
        start = self.i
        while self.i < self.n and self.s[self.i] in u'-+0123456789.eE':
            self.i = self.i + 1
        token = self.s[start:self.i]
        if token == u'':
            self.error('invalid value')
        try:
            if u'.' in token or u'e' in token or u'E' in token:
                return float(token)
            return int(token)
        except Exception:
            self.error('bad number %s' % token)

try:
    import json as _json
    def json_dumps(obj):
        return _json.dumps(obj)
    def json_loads(text):
        return _json.loads(text)
except ImportError:
    def json_dumps(obj):
        return _mini_dumps(obj)
    def json_loads(text):
        return _MiniJSONParser(text).parse()

# ---------------------------------------------------------------------------
#  Translations
# ---------------------------------------------------------------------------
LANG_ORDER = ['en', 'es', 'fr', 'de', 'pt']
LANG_LABELS = {
    'en': u'English',
    'es': u'Español',
    'fr': u'Français',
    'de': u'Deutsch',
    'pt': u'Português',
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
        'col_address':     u'Dirección',
        'announce':        u'Anunciar / Refrescar',
        'scan':            u'Escanear red',
        'clear_log':       u'Limpiar registro',
        'files_to_send':   u'Archivos a enviar',
        'add_file':        u'Añadir archivo...',
        'paste_clip':      u'Pegar portapapeles',
        'remove':          u'Quitar',
        'clear_list':      u'Vaciar lista',
        'send_to':         u'Enviar al equipo',
        'cancel_transfer': u'Cancelar envío',
        'activity':        u'Actividad',
        'ready':           u'Listo',
        'sending':         u'Enviando...',
        'receiving':       u'Recibiendo...',
        'scanning':        u'Escaneando...',
        'devcount':        u'%d equipo(s)',
        'language':        u'Idioma: %s',
        'enc_off':         u'HTTP :%d - Cifrado OFF en el otro equipo',
        'pick_device':     u'Selecciona primero un equipo en la tabla.',
        'pick_files':      u'Añade al menos un archivo a la cola.',
        'no_clip':         u'El portapapeles está vacío o no tiene texto.',
        'choose_dir':      u'Elige la carpeta de descargas',
    },
    'fr': {
        'server_running':  u'Serveur : HTTP simple :%d - actif',
        'server_error':    u'Serveur : ERREUR - port %d occupé',
        'name':            u'Nom :',
        'apply':           u'Appliquer',
        'save_to':         u'Enregistrer dans :',
        'change':          u'Changer...',
        'devices':         u'Appareils sur ce réseau',
        'col_name':        u'Nom',
        'col_model':       u'Modèle',
        'col_address':     u'Adresse',
        'announce':        u'Annoncer / Rafraîchir',
        'scan':            u'Scanner le réseau',
        'clear_log':       u'Effacer le journal',
        'files_to_send':   u'Fichiers à envoyer',
        'add_file':        u'Ajouter fichier...',
        'paste_clip':      u'Coller presse-papiers',
        'remove':          u'Retirer',
        'clear_list':      u'Vider la liste',
        'send_to':         u'Envoyer à l\u2019appareil',
        'cancel_transfer': u'Annuler le transfert',
        'activity':        u'Activité',
        'ready':           u'Prêt',
        'sending':         u'Envoi...',
        'receiving':       u'Réception...',
        'scanning':        u'Analyse...',
        'devcount':        u'%d appareil(s)',
        'language':        u'Langue : %s',
        'enc_off':         u'HTTP :%d - Chiffrement OFF sur l\u2019autre appareil',
        'pick_device':     u'Sélectionnez d\u2019abord un appareil dans la table.',
        'pick_files':      u'Ajoutez au moins un fichier à la file.',
        'no_clip':         u'Le presse-papiers est vide ou sans texte.',
        'choose_dir':      u'Choisir le dossier de téléchargement',
    },
    'de': {
        'server_running':  u'Server: reines HTTP :%d - läuft',
        'server_error':    u'Server: FEHLER - Port %d belegt',
        'name':            u'Name:',
        'apply':           u'Übernehmen',
        'save_to':         u'Speichern in:',
        'change':          u'Ändern...',
        'devices':         u'Geräte in diesem Netzwerk',
        'col_name':        u'Name',
        'col_model':       u'Modell',
        'col_address':     u'Adresse',
        'announce':        u'Ankündigen / Aktualisieren',
        'scan':            u'Netzwerk scannen',
        'clear_log':       u'Protokoll löschen',
        'files_to_send':   u'Zu sendende Dateien',
        'add_file':        u'Datei hinzufügen...',
        'paste_clip':      u'Zwischenablage einfügen',
        'remove':          u'Entfernen',
        'clear_list':      u'Liste leeren',
        'send_to':         u'An Gerät senden',
        'cancel_transfer': u'Übertragung abbrechen',
        'activity':        u'Aktivität',
        'ready':           u'Bereit',
        'sending':         u'Senden...',
        'receiving':       u'Empfangen...',
        'scanning':        u'Suche...',
        'devcount':        u'%d Gerät(e)',
        'language':        u'Sprache: %s',
        'enc_off':         u'HTTP :%d - Verschlüsselung OFF am anderen Gerät',
        'pick_device':     u'Bitte zuerst ein Gerät in der Tabelle wählen.',
        'pick_files':      u'Mindestens eine Datei zur Warteschlange hinzufügen.',
        'no_clip':         u'Zwischenablage ist leer oder enthält keinen Text.',
        'choose_dir':      u'Download-Ordner wählen',
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
        'col_address':     u'Endereço',
        'announce':        u'Anunciar / Atualizar',
        'scan':            u'Varrer a rede',
        'clear_log':       u'Limpar registro',
        'files_to_send':   u'Arquivos a enviar',
        'add_file':        u'Adicionar arquivo...',
        'paste_clip':      u'Colar área de transf.',
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
        'pick_files':      u'Adicione pelo menos um arquivo à fila.',
        'no_clip':         u'A área de transferência está vazia ou sem texto.',
        'choose_dir':      u'Escolher pasta de downloads',
    },
}

# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------
def mac_os_version():
    try:
        ver = platform.mac_ver()[0]
        if ver:
            parts = ver.split('.')
            return '.'.join(parts[:2])
    except Exception:
        pass
    return '10.x'

def local_ip():
    s = None
    try:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except Exception:
            return '127.0.0.1'
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

def random_hex(nbytes):
    out = []
    i = 0
    while i < nbytes:
        out.append('%02x' % random.randrange(0, 256))
        i = i + 1
    return ''.join(out)

def guess_mime(path):
    mt = mimetypes.guess_type(path)[0]
    if mt is None:
        return 'application/octet-stream'
    return mt

def human_size(n):
    try:
        n = float(n)
    except Exception:
        return '?'
    if n >= 1073741824.0:
        return '%.1f GB' % (n / 1073741824.0)
    if n >= 1048576.0:
        return '%.1f MB' % (n / 1048576.0)
    if n >= 1024.0:
        return '%.1f KB' % (n / 1024.0)
    return '%d B' % int(n)

def safe_filename(name):
    name = os.path.basename(name.replace('\\', '/'))
    cleaned = []
    for ch in name:
        if ch in ':\x00':
            cleaned.append('_')
        else:
            cleaned.append(ch)
    name = ''.join(cleaned)
    if name == '' or name == '.' or name == '..':
        name = 'received.bin'
    return name

def load_config():
    fh = None
    try:
        try:
            fh = open(CONFIG_PATH, 'rb')
            cfg = json_loads(fh.read())
            if isinstance(cfg, dict):
                return cfg
        except Exception:
            pass
    finally:
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
    return {}

def save_config(cfg):
    fh = None
    try:
        try:
            fh = open(CONFIG_PATH, 'wb')
            body = json_dumps(cfg)
            if isinstance(body, unicode):
                body = body.encode('utf-8')
            fh.write(body)
        except Exception:
            pass
    finally:
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass

def unique_path(folder, name):
    candidate = os.path.join(folder, name)
    if not os.path.exists(candidate):
        return candidate
    base = name
    ext = ''
    dot = name.rfind('.')
    if dot > 0:
        base = name[:dot]
        ext = name[dot:]
    idx = 1
    while 1:
        candidate = os.path.join(folder, '%s (%d)%s' % (base, idx, ext))
        if not os.path.exists(candidate):
            return candidate
        idx = idx + 1

# ---------------------------------------------------------------------------
#  HTTP server (LocalSend v2 endpoints)
# ---------------------------------------------------------------------------
APP = None  # global reference used by the request handler

class TigerSendHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    allow_reuse_address = 1
    daemon_threads = 1

class TigerSendHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    server_version = 'TigerSend/' + APP_VERSION
    protocol_version = 'HTTP/1.0'

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    def _send_json(self, code, obj):
        body = json_dumps(obj)
        if isinstance(body, unicode):
            body = body.encode('utf-8')
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _maybe_continue(self):
        # Some clients send "Expect: 100-continue" and wait for the interim
        # response before transmitting the body; answer it explicitly.
        expect = (self.headers.getheader('expect') or '').lower()
        if expect.find('100-continue') >= 0:
            try:
                self.wfile.write('HTTP/1.1 100 Continue\r\n\r\n')
                self.wfile.flush()
            except Exception:
                pass

    def _is_chunked(self):
        te = (self.headers.getheader('transfer-encoding') or '').lower()
        return te.find('chunked') >= 0

    def _read_chunked_to(self, out):
        # Decode a "Transfer-Encoding: chunked" request body into `out`
        # (any object with a write() method). That is how iOS LocalSend
        # sends both JSON and file bodies. Returns the byte count.
        total = 0
        while 1:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            semi = line.find(';')
            if semi >= 0:
                line = line[:semi]
            try:
                size = int(line, 16)
            except Exception:
                break
            if size == 0:
                # consume optional trailers up to the blank line
                while 1:
                    trailer = self.rfile.readline()
                    if not trailer or trailer == '\r\n' or trailer == '\n':
                        break
                break
            if APP.cancel_flag.isSet():
                raise IOError('cancelled by user')
            remaining = size
            while remaining > 0:
                chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    return total
                out.write(chunk)
                total = total + len(chunk)
                remaining = remaining - len(chunk)
            self.rfile.read(2)   # trailing CRLF after each chunk
        return total

    def _read_body(self):
        self._maybe_continue()
        if self._is_chunked():
            buf = StringIO.StringIO()
            try:
                self._read_chunked_to(buf)
            except Exception:
                pass
            return buf.getvalue()
        try:
            length = int(self.headers.getheader('content-length') or '0')
        except Exception:
            length = 0
        if length <= 0:
            return ''
        return self.rfile.read(length)

    def do_GET(self):
        parsed = urlparse.urlparse(self.path)
        if parsed[2] in ('/api/localsend/v2/info', '/api/localsend/v1/info'):
            self._send_json(200, APP.device_info(0))
        else:
            self._send_json(404, {'message': 'not found'})

    def do_POST(self):
        parsed = urlparse.urlparse(self.path)
        path = parsed[2]
        query = cgi.parse_qs(parsed[4])

        if path == '/api/localsend/v2/register':
            self._handle_register()
        elif path == '/api/localsend/v2/prepare-upload':
            self._handle_prepare_upload()
        elif path == '/api/localsend/v2/upload':
            self._handle_upload(query)
        elif path == '/api/localsend/v2/cancel':
            self._handle_cancel(query)
        else:
            self._send_json(404, {'message': 'not found'})

    def _handle_register(self):
        body = self._read_body()
        try:
            info = json_loads(body)
        except Exception:
            self._send_json(400, {'message': 'bad json'})
            return
        APP.remember_device(info, self.client_address[0])
        self._send_json(200, APP.device_info(0))

    def _handle_prepare_upload(self):
        body = self._read_body()
        try:
            req = json_loads(body)
        except Exception:
            self._send_json(400, {'message': 'bad json'})
            return
        info = req.get('info', {})
        files = req.get('files', {})
        APP.remember_device(info, self.client_address[0])

        session_id = random_hex(16)
        tokens = {}
        meta = {}
        for fid in files.keys():
            token = random_hex(16)
            tokens[fid] = token
            meta[fid] = {
                'token': token,
                'fileName': files[fid].get('fileName', 'received.bin'),
                'size': files[fid].get('size', 0),
            }
        APP.sessions[session_id] = meta
        alias = info.get('alias', '?')
        APP.post_log(u'<- prepare-upload from %s (%d file(s))'
                     % (alias, len(files)))
        APP.post_status('receiving')
        self._send_json(200, {'sessionId': session_id, 'files': tokens})

    def _handle_upload(self, query):
        session_id = (query.get('sessionId') or [''])[0]
        file_id = (query.get('fileId') or [''])[0]
        token = (query.get('token') or [''])[0]

        session = APP.sessions.get(session_id)
        if session is None or file_id not in session:
            self._send_json(403, {'message': 'invalid session'})
            return
        if session[file_id]['token'] != token:
            self._send_json(403, {'message': 'invalid token'})
            return

        self._maybe_continue()
        chunked = self._is_chunked()
        try:
            length = int(self.headers.getheader('content-length') or '0')
        except Exception:
            length = 0
        if chunked:
            expected = session[file_id]['size']
        else:
            expected = length

        name = safe_filename(session[file_id]['fileName'])
        dest = unique_path(APP.save_dir, name)
        APP.post_log(u'<- receiving "%s" (%s)...'
                     % (name, human_size(expected)))

        fh = None
        received = 0
        try:
            try:
                fh = open(dest, 'wb')
                if chunked:
                    received = self._read_chunked_to(fh)
                else:
                    remaining = length
                    while remaining > 0:
                        if APP.cancel_flag.isSet():
                            raise IOError('cancelled by user')
                        chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        fh.write(chunk)
                        received = received + len(chunk)
                        remaining = remaining - len(chunk)
            except Exception:
                err = sys.exc_info()[1]
                APP.post_log(u'!! receive failed: %s' % str(err))
                self._send_json(500, {'message': 'write error'})
                return
        finally:
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass

        try:
            declared = int(session[file_id]['size'])
        except Exception:
            declared = 0
        if declared and received != declared:
            APP.post_log(u'!! size mismatch for "%s": got %d, expected %d'
                         % (name, received, declared))
        APP.post_log(u'<- saved "%s" (%s) to %s'
                     % (name, human_size(received), APP.save_dir))
        APP.post_status('ready')
        self._send_json(200, {})

    def _handle_cancel(self, query):
        session_id = (query.get('sessionId') or [''])[0]
        if session_id in APP.sessions:
            del APP.sessions[session_id]
            APP.post_log(u'<- transfer cancelled by remote device')
        APP.post_status('ready')
        self._send_json(200, {})

# ---------------------------------------------------------------------------
#  Main application
# ---------------------------------------------------------------------------
class TigerSendApp:

    # ----- construction ----------------------------------------------------
    def __init__(self, root):
        self.root = root

        # --- persisted configuration (~/.tigersend_config.json) ---------
        cfg = load_config()
        self.lang = cfg.get('lang', 'en')
        if self.lang not in LANG_ORDER:
            self.lang = 'en'
        self.alias = cfg.get('alias', DEFAULT_ALIAS) or DEFAULT_ALIAS
        if isinstance(self.alias, unicode):
            try:
                self.alias = self.alias.encode('utf-8')
            except Exception:
                self.alias = DEFAULT_ALIAS
        self.fingerprint = cfg.get('fingerprint', '')
        if not self.fingerprint:
            self.fingerprint = md5hex('%s-%s-%s' % (DEFAULT_ALIAS,
                                                    time.time(),
                                                    random_hex(8)))
        if isinstance(self.fingerprint, unicode):
            self.fingerprint = self.fingerprint.encode('utf-8')
        self.save_dir = cfg.get('save_dir', '')
        if isinstance(self.save_dir, unicode):
            try:
                self.save_dir = self.save_dir.encode('utf-8')
            except Exception:
                self.save_dir = ''
        if not self.save_dir or not os.path.isdir(self.save_dir):
            self.save_dir = os.path.expanduser('~/Downloads')
        if not os.path.isdir(self.save_dir):
            self.save_dir = os.path.expanduser('~')

        self.devices = []        # list of dicts: alias/model/ip/port/fingerprint
        self.files = []          # list of absolute paths
        self.sessions = {}       # incoming sessions
        self.cancel_flag = threading.Event()
        self.running = 1
        self.server_ok = 0
        self.status_key = 'ready'
        self.queue = Queue.Queue()

        self.my_ip = local_ip()
        self.os_version = mac_os_version()

        self._build_gui()
        self._start_server()
        self._start_udp_listener()
        self.retranslate()
        self._save_config()   # persist fingerprint on first launch
        self.log(u'%s %s started on %s (%s)'
                 % (APP_NAME, APP_VERSION, self.my_ip, self.alias))
        self.log(u'Protocol: LocalSend v%s, plain HTTP :%d, encryption OFF'
                 % (PROTO_VERSION, PORT))
        self.announce()
        self.root.after(200, self._poll_queue)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    # ----- GUI building ----------------------------------------------------
    def _build_gui(self):
        root = self.root
        root.title('%s %s' % (APP_NAME, APP_VERSION))
        try:
            root.minsize(680, 640)
        except Exception:
            pass

        self.font_ui    = ('Lucida Grande', 11)
        self.font_bold  = ('Lucida Grande', 11, 'bold')
        self.font_title = ('Lucida Grande', 12, 'bold')
        self.font_mono  = ('Monaco', 10)
        self.font_small = ('Lucida Grande', 10)

        # --- 1. header -------------------------------------------------
        header = Tkinter.Frame(root)
        header.pack(side='top', fill='x', padx=10, pady=(8, 2))

        self.lbl_title = Tkinter.Label(
            header, font=self.font_title, anchor='w',
            text=u'%s   LocalSend protocol v%s - Mac OS X %s %s'
                 % (APP_NAME, PROTO_VERSION, self.os_version, APP_VERSION))
        self.lbl_title.pack(side='left')

        self.lbl_server = Tkinter.Label(header, font=self.font_small,
                                        anchor='e', fg='#006600')
        self.lbl_server.pack(side='right')

        sep1 = Tkinter.Frame(root, height=2, bd=1, relief='sunken')
        sep1.pack(fill='x', padx=10, pady=4)

        # --- 2. identity / paths ----------------------------------------
        ident = Tkinter.Frame(root)
        ident.pack(side='top', fill='x', padx=10)

        row1 = Tkinter.Frame(ident)
        row1.pack(fill='x', pady=2)
        self.lbl_name = Tkinter.Label(row1, font=self.font_ui, width=9,
                                      anchor='w')
        self.lbl_name.pack(side='left')
        self.var_alias = Tkinter.StringVar()
        self.var_alias.set(self.alias)
        self.ent_alias = Tkinter.Entry(row1, textvariable=self.var_alias,
                                       font=self.font_ui)
        self.ent_alias.pack(side='left', fill='x', expand=1, padx=4)
        self.btn_apply = Tkinter.Button(row1, command=self.apply_alias)
        self.btn_apply.pack(side='left', padx=2)

        row2 = Tkinter.Frame(ident)
        row2.pack(fill='x', pady=2)
        self.lbl_saveto = Tkinter.Label(row2, font=self.font_ui, width=9,
                                        anchor='w')
        self.lbl_saveto.pack(side='left')
        self.var_savedir = Tkinter.StringVar()
        self.var_savedir.set(self.save_dir)
        self.ent_savedir = Tkinter.Entry(row2, textvariable=self.var_savedir,
                                         font=self.font_ui,
                                         state='readonly')
        try:
            self.ent_savedir.config(readonlybackground='#eeeeee')
        except Exception:
            pass
        self.ent_savedir.pack(side='left', fill='x', expand=1, padx=4)
        self.btn_change = Tkinter.Button(row2, command=self.change_save_dir)
        self.btn_change.pack(side='left', padx=2)

        # --- 3. devices --------------------------------------------------
        self.lbl_devices = Tkinter.Label(root, font=self.font_bold, anchor='w')
        self.lbl_devices.pack(fill='x', padx=10, pady=(8, 0))

        devframe = Tkinter.Frame(root, bd=1, relief='sunken')
        devframe.pack(fill='both', padx=10, pady=2)

        self.lbl_devhdr = Tkinter.Label(devframe, font=self.font_mono,
                                        anchor='w', bg='#dddddd')
        self.lbl_devhdr.pack(fill='x')

        devinner = Tkinter.Frame(devframe)
        devinner.pack(fill='both', expand=1)
        self.sb_dev = Tkinter.Scrollbar(devinner, orient='vertical')
        self.lst_devices = Tkinter.Listbox(devinner, height=5,
                                           font=self.font_mono,
                                           yscrollcommand=self.sb_dev.set,
                                           exportselection=0)
        self.sb_dev.config(command=self.lst_devices.yview)
        self.sb_dev.pack(side='right', fill='y')
        self.lst_devices.pack(side='left', fill='both', expand=1)

        devbtns = Tkinter.Frame(root)
        devbtns.pack(fill='x', padx=10, pady=(2, 4))
        self.btn_announce = Tkinter.Button(devbtns, command=self.announce)
        self.btn_announce.pack(side='left', padx=2)
        self.btn_scan = Tkinter.Button(devbtns, command=self.scan_network)
        self.btn_scan.pack(side='left', padx=2)
        self.btn_clearlog = Tkinter.Button(devbtns, command=self.clear_log)
        self.btn_clearlog.pack(side='left', padx=2)

        # --- 4. files to send --------------------------------------------
        self.lbl_files = Tkinter.Label(root, font=self.font_bold, anchor='w')
        self.lbl_files.pack(fill='x', padx=10, pady=(6, 0))

        fileframe = Tkinter.Frame(root, bd=1, relief='sunken')
        fileframe.pack(fill='both', padx=10, pady=2)
        self.sb_files = Tkinter.Scrollbar(fileframe, orient='vertical')
        self.lst_files = Tkinter.Listbox(fileframe, height=5,
                                         font=self.font_mono,
                                         yscrollcommand=self.sb_files.set,
                                         exportselection=0)
        self.sb_files.config(command=self.lst_files.yview)
        self.sb_files.pack(side='right', fill='y')
        self.lst_files.pack(side='left', fill='both', expand=1)

        filebtns = Tkinter.Frame(root)
        filebtns.pack(fill='x', padx=10, pady=(2, 4))
        self.btn_addfile = Tkinter.Button(filebtns, command=self.add_file)
        self.btn_addfile.pack(side='left', padx=2)
        self.btn_paste = Tkinter.Button(filebtns, command=self.paste_clipboard)
        self.btn_paste.pack(side='left', padx=2)
        self.btn_remove = Tkinter.Button(filebtns, command=self.remove_file)
        self.btn_remove.pack(side='left', padx=2)
        self.btn_clearlist = Tkinter.Button(filebtns, command=self.clear_files)
        self.btn_clearlist.pack(side='left', padx=2)
        self.btn_send = Tkinter.Button(filebtns, command=self.send_files)
        self.btn_send.pack(side='left', padx=8)
        self.btn_cancel = Tkinter.Button(filebtns, command=self.cancel_transfer)
        self.btn_cancel.pack(side='left', padx=2)

        # --- 5. activity log ----------------------------------------------
        self.lbl_activity = Tkinter.Label(root, font=self.font_bold, anchor='w')
        self.lbl_activity.pack(fill='x', padx=10, pady=(6, 0))

        actframe = Tkinter.Frame(root, bd=1, relief='sunken')
        actframe.pack(fill='both', expand=1, padx=10, pady=2)
        self.sb_act = Tkinter.Scrollbar(actframe, orient='vertical')
        self.txt_activity = Tkinter.Text(actframe, height=8,
                                         font=self.font_mono,
                                         state='disabled', wrap='word',
                                         yscrollcommand=self.sb_act.set)
        self.sb_act.config(command=self.txt_activity.yview)
        self.sb_act.pack(side='right', fill='y')
        self.txt_activity.pack(side='left', fill='both', expand=1)

        # --- 6. language bar + status bar ----------------------------------
        langbar = Tkinter.Frame(root)
        langbar.pack(fill='x', padx=10, pady=(4, 0))
        self.var_lang = Tkinter.StringVar()
        self.var_lang.set(self.lang)
        self.radio_langs = []
        for code in LANG_ORDER:
            rb = Tkinter.Radiobutton(langbar, text=LANG_LABELS[code],
                                     variable=self.var_lang, value=code,
                                     font=self.font_small,
                                     command=self.on_language)
            rb.pack(side='left', padx=2)
            self.radio_langs.append(rb)

        statusbar = Tkinter.Frame(root, bd=1, relief='sunken')
        statusbar.pack(side='bottom', fill='x')
        self.lbl_status = Tkinter.Label(statusbar, font=self.font_small,
                                        anchor='w')
        self.lbl_status.pack(side='left', padx=6)
        self.lbl_enc = Tkinter.Label(statusbar, font=self.font_small,
                                     anchor='e', fg='#555555')
        self.lbl_enc.pack(side='right', padx=6)

    # ----- translations -----------------------------------------------------
    def tr(self, key):
        table = TR.get(self.lang, TR['en'])
        return table.get(key, TR['en'].get(key, key))

    def retranslate(self):
        t = self.tr
        self.lbl_name.config(text=t('name'))
        self.btn_apply.config(text=t('apply'))
        self.lbl_saveto.config(text=t('save_to'))
        self.btn_change.config(text=t('change'))
        self.lbl_devices.config(text=t('devices'))
        self.lbl_devhdr.config(text='%-26s %-22s %s'
                               % (t('col_name'), t('col_model'),
                                  t('col_address')))
        self.btn_announce.config(text=t('announce'))
        self.btn_scan.config(text=t('scan'))
        self.btn_clearlog.config(text=t('clear_log'))
        self.btn_addfile.config(text=t('add_file'))
        self.btn_paste.config(text=t('paste_clip'))
        self.btn_remove.config(text=t('remove'))
        self.btn_clearlist.config(text=t('clear_list'))
        self.btn_send.config(text=t('send_to'))
        self.btn_cancel.config(text=t('cancel_transfer'))
        self.lbl_activity.config(text=t('activity'))
        if self.server_ok:
            self.lbl_server.config(text=t('server_running') % PORT,
                                   fg='#006600')
        else:
            self.lbl_server.config(text=t('server_error') % PORT,
                                   fg='#aa0000')
        self.lbl_enc.config(text=t('enc_off') % PORT)
        self.update_files_header()
        self.update_status()

    def on_language(self):
        self.lang = self.var_lang.get()
        self.retranslate()
        self._save_config()
        self.log(u'Language switched to %s' % LANG_LABELS[self.lang])

    def _save_config(self):
        save_config({'alias': self.alias,
                     'lang': self.lang,
                     'save_dir': self.save_dir,
                     'fingerprint': self.fingerprint})

    # ----- status bar -------------------------------------------------------
    def update_status(self):
        t = self.tr
        self.lbl_status.config(
            text=u'%s | %s | %s'
                 % (t(self.status_key),
                    t('devcount') % len(self.devices),
                    t('language') % LANG_LABELS[self.lang]))

    def set_status(self, key):
        self.status_key = key
        self.update_status()

    def update_files_header(self):
        self.lbl_files.config(text=u'%s  [ %d ]'
                              % (self.tr('files_to_send'), len(self.files)))

    # ----- activity log -------------------------------------------------------
    def log(self, msg):
        stamp = time.strftime('%H:%M:%S')
        self.txt_activity.config(state='normal')
        self.txt_activity.insert('end', u'[%s] %s\n' % (stamp, msg))
        self.txt_activity.see('end')
        self.txt_activity.config(state='disabled')

    def clear_log(self):
        self.txt_activity.config(state='normal')
        self.txt_activity.delete('1.0', 'end')
        self.txt_activity.config(state='disabled')

    # ----- thread -> GUI queue --------------------------------------------------
    def post_log(self, msg):
        self.queue.put(('log', msg))

    def post_status(self, key):
        self.queue.put(('status', key))

    def post_devices(self):
        self.queue.put(('devices', None))

    def _poll_queue(self):
        try:
            while 1:
                try:
                    kind, payload = self.queue.get_nowait()
                except Queue.Empty:
                    break
                if kind == 'log':
                    self.log(payload)
                elif kind == 'status':
                    self.set_status(payload)
                elif kind == 'devices':
                    self.refresh_device_list()
        except Exception:
            pass
        if self.running:
            self.root.after(200, self._poll_queue)

    # ----- LocalSend protocol: identity ----------------------------------------
    def device_info(self, announce):
        info = {
            'alias': self.alias,
            'version': PROTO_VERSION,
            'deviceModel': 'Mac OS X %s' % self.os_version,
            'deviceType': 'desktop',
            'fingerprint': self.fingerprint,
            'port': PORT,
            'protocol': 'http',
            'download': False,
        }
        if announce:
            info['announce'] = True
        else:
            info['announce'] = False
        return info

    def remember_device(self, info, ip):
        try:
            fp = info.get('fingerprint', '')
        except Exception:
            return
        if not fp or fp == self.fingerprint:
            return
        alias = info.get('alias', '?')
        model = info.get('deviceModel') or info.get('deviceType') or '?'
        try:
            port = int(info.get('port', PORT))
        except Exception:
            port = PORT
        found = 0
        for dev in self.devices:
            if dev['fingerprint'] == fp:
                dev['alias'] = alias
                dev['model'] = model
                dev['ip'] = ip
                dev['port'] = port
                found = 1
                break
        if not found:
            self.devices.append({'fingerprint': fp, 'alias': alias,
                                 'model': model, 'ip': ip, 'port': port})
            self.post_log(u'++ discovered: %s (%s) at %s:%d'
                          % (alias, model, ip, port))
        self.post_devices()

    def refresh_device_list(self):
        self.lst_devices.delete(0, 'end')
        for dev in self.devices:
            self.lst_devices.insert(
                'end', '%-26s %-22s %s:%d'
                % (dev['alias'][:25], str(dev['model'])[:21],
                   dev['ip'], dev['port']))
        self.update_status()

    # ----- server + discovery threads ------------------------------------------
    def _start_server(self):
        try:
            self.httpd = TigerSendHTTPServer(('0.0.0.0', PORT),
                                            TigerSendHandler)
            self.server_ok = 1
        except Exception:
            err = sys.exc_info()[1]
            self.httpd = None
            self.server_ok = 0
            self.log(u'!! HTTP server error: %s' % str(err))
            return
        th = threading.Thread(target=self.httpd.serve_forever)
        th.setDaemon(1)
        th.start()

    def _start_udp_listener(self):
        th = threading.Thread(target=self._udp_loop)
        th.setDaemon(1)
        th.start()

    def _udp_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
            sock.bind(('', PORT))
            mreq = socket.inet_aton(MULTICAST_GROUP) + \
                   socket.inet_aton('0.0.0.0')
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
        except Exception:
            err = sys.exc_info()[1]
            self.post_log(u'!! UDP listener error: %s' % str(err))
            return
        self.post_log(u'UDP multicast listener on %s:%d'
                      % (MULTICAST_GROUP, PORT))
        while self.running:
            try:
                data, addr = sock.recvfrom(65536)
            except socket.timeout:
                continue
            except socket.error:
                continue
            try:
                msg = json_loads(data)
            except Exception:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get('fingerprint', '') == self.fingerprint:
                continue
            self.remember_device(msg, addr[0])
            if msg.get('announce'):
                # answer the announcement: HTTP register, UDP fallback
                th = threading.Thread(target=self._register_back,
                                      args=(addr[0], msg))
                th.setDaemon(1)
                th.start()

    def _register_back(self, ip, msg):
        try:
            port = int(msg.get('port', PORT))
        except Exception:
            port = PORT
        ok = 0
        try:
            conn = httplib.HTTPConnection(ip, port)
            body = json_dumps(self.device_info(0))
            conn.request('POST', '/api/localsend/v2/register', body,
                         {'Content-Type': 'application/json'})
            resp = conn.getresponse()
            resp.read()
            conn.close()
            if resp.status == 200:
                ok = 1
        except Exception:
            ok = 0
        if not ok:
            # UDP response fallback
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(json_dumps(self.device_info(0)), (ip, PORT))
                s.close()
            except Exception:
                pass

    # ----- discovery actions ------------------------------------------------------
    def announce(self):
        th = threading.Thread(target=self._announce_worker)
        th.setDaemon(1)
        th.start()

    def _announce_worker(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                              socket.IPPROTO_UDP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            # macOS/BSD quirk: route multicast out of the real interface,
            # otherwise sendto() can fail with [Errno 49].
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                             socket.inet_aton(self.my_ip))
            except Exception:
                pass
            payload = json_dumps(self.device_info(1))
            i = 0
            while i < 3:
                s.sendto(payload, (MULTICAST_GROUP, PORT))
                time.sleep(0.3)
                i = i + 1
            s.close()
            self.post_log(u'-> announce sent to %s:%d (x3)'
                          % (MULTICAST_GROUP, PORT))
        except Exception:
            err = sys.exc_info()[1]
            self.post_log(u'!! announce failed: %s' % str(err))

    def scan_network(self):
        self.set_status('scanning')
        self.log(u'Scanning subnet of %s on TCP :%d ...' % (self.my_ip, PORT))
        th = threading.Thread(target=self._scan_worker)
        th.setDaemon(1)
        th.start()

    def _scan_worker(self):
        base = self.my_ip
        dot = base.rfind('.')
        if dot < 0:
            self.post_log(u'!! cannot determine local subnet')
            self.post_status('ready')
            return
        prefix = base[:dot + 1]
        targets = Queue.Queue()
        i = 1
        while i < 255:
            ip = '%s%d' % (prefix, i)
            if ip != self.my_ip:
                targets.put(ip)
            i = i + 1

        workers = []
        w = 0
        while w < 16:
            th = threading.Thread(target=self._scan_one_queue,
                                  args=(targets,))
            th.setDaemon(1)
            th.start()
            workers.append(th)
            w = w + 1
        for th in workers:
            th.join()
        self.post_log(u'Scan finished: %d device(s) known'
                      % len(self.devices))
        self.post_status('ready')

    def _scan_one_queue(self, targets):
        while 1:
            try:
                ip = targets.get_nowait()
            except Queue.Empty:
                return
            self._probe(ip)

    def _probe(self, ip):
        s = None
        try:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.6)
                s.connect((ip, PORT))
                s.sendall('GET /api/localsend/v2/info HTTP/1.0\r\n'
                          'Host: %s\r\nConnection: close\r\n\r\n' % ip)
                buf = ''
                while 1:
                    data = s.recv(4096)
                    if not data:
                        break
                    buf = buf + data
                    if len(buf) > 262144:
                        break
                pos = buf.find('\r\n\r\n')
                if pos < 0:
                    return
                body = buf[pos + 4:]
                info = json_loads(body)
                if isinstance(info, dict):
                    self.remember_device(info, ip)
            except Exception:
                pass
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    # ----- identity / path actions ---------------------------------------------------
    def apply_alias(self):
        new_alias = self.var_alias.get().strip()
        if not new_alias:
            self.var_alias.set(self.alias)
            return
        self.alias = new_alias
        self._save_config()
        self.log(u'Alias changed to "%s" - re-announcing' % self.alias)
        self.announce()

    def change_save_dir(self):
        folder = tkFileDialog.askdirectory(title=self.tr('choose_dir'),
                                           initialdir=self.save_dir)
        if folder:
            if isinstance(folder, unicode):
                try:
                    folder = folder.encode('utf-8')
                except Exception:
                    pass
            self.save_dir = folder
            self.var_savedir.set(folder)
            self._save_config()
            self.log(u'Download folder: %s' % folder)

    # ----- file queue actions ------------------------------------------------------
    def add_file(self):
        paths = None
        try:
            paths = tkFileDialog.askopenfilenames(title='Add files')
            if paths and not isinstance(paths, (list, tuple)):
                paths = self.root.tk.splitlist(paths)
        except Exception:
            paths = None
        if not paths:
            one = tkFileDialog.askopenfilename(title='Add file')
            if one:
                paths = [one]
        if not paths:
            return
        for p in paths:
            if p and os.path.isfile(p) and p not in self.files:
                self.files.append(p)
                self.lst_files.insert(
                    'end', '%s  (%s)' % (os.path.basename(p),
                                         human_size(os.path.getsize(p))))
                self.log(u'Queued: %s' % p)
        self.update_files_header()

    def paste_clipboard(self):
        text = None
        try:
            text = self.root.clipboard_get()
        except Exception:
            text = None
        if not text:
            tkMessageBox.showinfo(APP_NAME, self.tr('no_clip'))
            return
        stamp = time.strftime('%Y%m%d-%H%M%S')
        path = os.path.join(tempfile.gettempdir(),
                            'tigersend-clipboard-%s.txt' % stamp)
        fh = None
        try:
            try:
                fh = open(path, 'wb')
                if isinstance(text, unicode):
                    fh.write(text.encode('utf-8'))
                else:
                    fh.write(text)
            except Exception:
                err = sys.exc_info()[1]
                self.log(u'!! clipboard error: %s' % str(err))
                return
        finally:
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass
        self.files.append(path)
        self.lst_files.insert('end', '%s  (%s)'
                              % (os.path.basename(path),
                                 human_size(os.path.getsize(path))))
        self.log(u'Clipboard text queued as %s' % os.path.basename(path))
        self.update_files_header()

    def remove_file(self):
        sel = self.lst_files.curselection()
        if not sel:
            return
        idx = int(sel[0])
        removed = self.files[idx]
        del self.files[idx]
        self.lst_files.delete(idx)
        self.log(u'Removed from queue: %s' % os.path.basename(removed))
        self.update_files_header()

    def clear_files(self):
        self.files = []
        self.lst_files.delete(0, 'end')
        self.update_files_header()

    # ----- sending -------------------------------------------------------------
    def send_files(self):
        sel = self.lst_devices.curselection()
        if not sel:
            tkMessageBox.showwarning(APP_NAME, self.tr('pick_device'))
            return
        if not self.files:
            tkMessageBox.showwarning(APP_NAME, self.tr('pick_files'))
            return
        dev = self.devices[int(sel[0])]
        files = self.files[:]
        self.cancel_flag.clear()
        self.set_status('sending')
        th = threading.Thread(target=self._send_worker, args=(dev, files))
        th.setDaemon(1)
        th.start()

    def _send_worker(self, dev, files):
        ip = dev['ip']
        port = dev['port']
        self.post_log(u'-> prepare-upload to %s (%s:%d), %d file(s)'
                      % (dev['alias'], ip, port, len(files)))

        file_meta = {}
        idx = 0
        for path in files:
            idx = idx + 1
            fid = 'f%d_%s' % (idx, md5hex(path)[:8])
            try:
                size = os.path.getsize(path)
            except Exception:
                size = 0
            file_meta[fid] = {
                'id': fid,
                'fileName': os.path.basename(path),
                'size': size,
                'fileType': guess_mime(path),
                '_path': path,     # local only, stripped before sending
            }

        wire_files = {}
        for fid in file_meta.keys():
            wire_files[fid] = {
                'id': file_meta[fid]['id'],
                'fileName': file_meta[fid]['fileName'],
                'size': file_meta[fid]['size'],
                'fileType': file_meta[fid]['fileType'],
            }

        payload = json_dumps({'info': self.device_info(0),
                              'files': wire_files})
        try:
            conn = httplib.HTTPConnection(ip, port)
            conn.request('POST', '/api/localsend/v2/prepare-upload', payload,
                         {'Content-Type': 'application/json'})
            resp = conn.getresponse()
            body = resp.read()
            status = resp.status
            conn.close()
        except Exception:
            err = sys.exc_info()[1]
            self.post_log(u'!! prepare-upload failed: %s' % str(err))
            self.post_status('ready')
            return

        if status == 204 or not body:
            self.post_log(u'-- remote device accepted nothing (204)')
            self.post_status('ready')
            return
        if status == 403:
            self.post_log(u'!! transfer rejected by %s' % dev['alias'])
            self.post_status('ready')
            return
        if status != 200:
            self.post_log(u'!! prepare-upload: HTTP %d %s'
                          % (status, body[:120]))
            self.post_status('ready')
            return

        try:
            answer = json_loads(body)
            session_id = answer['sessionId']
            tokens = answer['files']
        except Exception:
            self.post_log(u'!! bad prepare-upload answer: %s' % body[:120])
            self.post_status('ready')
            return

        sent = 0
        for fid in tokens.keys():
            if self.cancel_flag.isSet():
                break
            meta = file_meta.get(fid)
            if meta is None:
                continue
            ok = self._upload_one(ip, port, session_id, fid,
                                  tokens[fid], meta)
            if ok:
                sent = sent + 1
            else:
                break

        if self.cancel_flag.isSet():
            try:
                conn = httplib.HTTPConnection(ip, port)
                conn.request('POST',
                             '/api/localsend/v2/cancel?sessionId=%s'
                             % session_id, '',
                             {'Content-Type': 'application/json'})
                conn.getresponse().read()
                conn.close()
            except Exception:
                pass
            self.post_log(u'xx transfer cancelled (%d/%d sent)'
                          % (sent, len(files)))
        else:
            self.post_log(u'== done: %d/%d file(s) sent to %s'
                          % (sent, len(files), dev['alias']))
        self.post_status('ready')

    def _upload_one(self, ip, port, session_id, fid, token, meta):
        path = meta['_path']
        name = meta['fileName']
        size = meta['size']
        self.post_log(u'-> uploading "%s" (%s)...' % (name, human_size(size)))
        fh = None
        conn = None
        try:
            try:
                fh = open(path, 'rb')
                conn = httplib.HTTPConnection(ip, port)
                url = ('/api/localsend/v2/upload?sessionId=%s&fileId=%s'
                       '&token=%s') % (session_id, fid, token)
                conn.putrequest('POST', url)
                conn.putheader('Content-Type', 'application/octet-stream')
                conn.putheader('Content-Length', str(size))
                conn.endheaders()
                while 1:
                    if self.cancel_flag.isSet():
                        raise IOError('cancelled by user')
                    chunk = fh.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    conn.send(chunk)
                resp = conn.getresponse()
                resp.read()
                if resp.status != 200:
                    self.post_log(u'!! upload "%s": HTTP %d'
                                  % (name, resp.status))
                    return 0
                self.post_log(u'ok "%s" uploaded' % name)
                return 1
            except Exception:
                err = sys.exc_info()[1]
                self.post_log(u'!! upload "%s" failed: %s' % (name, str(err)))
                return 0
        finally:
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def cancel_transfer(self):
        self.cancel_flag.set()
        self.log(u'Cancel requested...')

    # ----- shutdown -----------------------------------------------------------
    def on_close(self):
        self.running = 0
        self.cancel_flag.set()
        try:
            if self.httpd is not None:
                # shutdown() exists since 2.6; fall back to closing the socket
                try:
                    self.httpd.shutdown()
                except Exception:
                    pass
                try:
                    self.httpd.socket.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

# ---------------------------------------------------------------------------
def main():
    random.seed()
    root = Tkinter.Tk()
    app = TigerSendApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
