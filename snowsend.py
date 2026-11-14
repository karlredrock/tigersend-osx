#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SnowSend - Cliente LocalSend (Protocolo v2) para Mac OS X 10.6 Snow Leopard
=================================================================================
- Python 2.6 / 2.7 ( /usr/bin/python en Snow Leopard ) y Python 3 (para pruebas
  en un Mac moderno). Solo libreria estandar: Tkinter, socket, struct, json,
  threading, BaseHTTPServer, urllib2, hashlib, uuid, mimetypes, os, sys.
- HTTP plano (sin TLS) en el puerto 53317. Snow Leopard no soporta TLS 1.2/1.3
  moderno de forma fiable, por eso en el dispositivo moderno hay que desactivar
  Encryption (ver README.md).
- SnowSend es un proyecto independiente, escrito desde cero en Python, que
  implementa el protocolo LocalSend v2.2 para interoperar con las apps
  oficiales. No esta afiliado ni respaldado por el proyecto LocalSend.
  Licencia MIT (ver LICENSE).
- Descubrimiento multicast UDP 224.0.0.167:53317.
- Servidor: GET /info, POST /register, POST /prepare-upload, POST /upload,
  POST /cancel  (ruta base /api/localsend/v2/...)
- Cliente: secuencia prepare-upload -> upload.
- GUI Tkinter (Aqua/X11 en 10.6).

Uso:
  python snowsend.py                  # GUI
  python snowsend.py --headless       # sin GUI (servidor + descubrimiento)
  python snowsend.py --headless --alias MiMac --port 53317 \
             --download-dir ~/Downloads

Referencia del protocolo: https://github.com/localsend/protocol (v2.2)
"""

from __future__ import print_function, with_statement

import gzip
import hashlib
import json
import mimetypes
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import uuid
import zlib

# ---------------------------------------------------------------------------
# Compatibilidad Python 2 / Python 3
# ---------------------------------------------------------------------------

try:
    unicode
except NameError:
    unicode = str

try:
    import Queue as queue_module
except ImportError:
    import queue as queue_module

try:
    import Tkinter as tk
    import tkFileDialog as filedialog
    import tkMessageBox as messagebox
    HAS_TKINTER = True
except ImportError:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        HAS_TKINTER = True
    except ImportError:
        HAS_TKINTER = False
        tk = None
        filedialog = None
        messagebox = None

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn

try:
    import urllib2
    from urlparse import urlparse, parse_qs
    from urllib import quote as url_quote
except ImportError:
    import urllib.request as urllib2
    import urllib.error
    from urllib.parse import urlparse, parse_qs, quote as url_quote

try:
    import httplib
except ImportError:
    import http.client as httplib

try:
    from StringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

# ---------------------------------------------------------------------------
# Constantes del protocolo
# ---------------------------------------------------------------------------

MULTICAST_IP = "224.0.0.167"
PORT = 53317
PROTOCOL_VERSION = "2.0"
DEVICE_MODEL = "Mac OS X 10.6"
DEVICE_TYPE = "desktop"
PROTOCOL = "http"
API_BASE = "/api/localsend/v2"

# Version del programa
VERSION = "1.7"
APP_VERSION = "2.0.7-10.6"



# ---------------------------------------------------------------------------
# Idiomas / Languages: English, Espanol, Francais, Deutsch, Portugues
# ---------------------------------------------------------------------------
# Todas las cadenas visibles pasan por T("clave"). Las traducciones mantienen
# el MISMO orden de marcadores %s que el original para no romper el formato.
# Se usa unicode en Python 2 para que Tk 8.5 muestre bien los acentos.

LANGUAGES = [
    ("en", "English"),
    ("es", u"Espa\u00f1ol"),
    ("fr", u"Fran\u00e7ais"),
    ("de", "Deutsch"),
    ("pt", u"Portugu\u00eas"),
]
LANGUAGE_CODES = [code for code, _name in LANGUAGES]

STRINGS = {
    # ------------------------------------------------------- cola de envio
    "label.queue": {
        "en": u"Files to send",
        "es": u"Archivos para enviar",
        "fr": u"Fichiers \u00e0 envoyer",
        "de": u"Zu sendende Dateien",
        "pt": u"Arquivos para enviar",
    },
    "btn.add_file": {
        "en": u"Add File\u2026",
        "es": u"A\u00f1adir archivo\u2026",
        "fr": u"Ajouter un fichier\u2026",
        "de": u"Datei hinzuf\u00fcgen\u2026",
        "pt": u"Adicionar arquivo\u2026",
    },
    "btn.paste": {
        "en": u"Paste Clipboard",
        "es": u"Pegar portapapeles",
        "fr": u"Coller le presse-papiers",
        "de": u"Zwischenablage einf\u00fcgen",
        "pt": u"Colar \u00e1rea de transfer\u00eancia",
    },
    "btn.remove": {
        "en": u"Remove",
        "es": u"Quitar",
        "fr": u"Retirer",
        "de": u"Entfernen",
        "pt": u"Remover",
    },
    "btn.clear_queue": {
        "en": u"Clear List",
        "es": u"Vaciar lista",
        "fr": u"Vider la liste",
        "de": u"Liste leeren",
        "pt": u"Limpar lista",
    },
    "btn.cancel_transfer": {
        "en": u"Cancel Transfer",
        "es": u"Cancelar env\u00edo",
        "fr": u"Annuler l'envoi",
        "de": u"Senden abbrechen",
        "pt": u"Cancelar envio",
    },
    "warn.no_files": {
        "en": u"Add at least one file to send.",
        "es": u"A\u00f1ade al menos un archivo para enviar.",
        "fr": u"Ajoutez au moins un fichier \u00e0 envoyer.",
        "de": u"F\u00fcge mindestens eine Datei zum Senden hinzu.",
        "pt": u"Adicione pelo menos um arquivo para enviar.",
    },
    "warn.clipboard_empty": {
        "en": u"The clipboard is empty or contains no text.",
        "es": u"El portapapeles est\u00e1 vac\u00edo o no contiene texto.",
        "fr": u"Le presse-papiers est vide ou ne contient pas de texte.",
        "de": u"Die Zwischenablage ist leer oder enth\u00e4lt keinen Text.",
        "pt": u"A \u00e1rea de transfer\u00eancia est\u00e1 vazia ou n\u00e3o cont\u00e9m texto.",
    },
    "warn.transfer_running": {
        "en": u"A transfer is already in progress.",
        "es": u"Ya hay una transferencia en curso.",
        "fr": u"Un envoi est d\u00e9j\u00e0 en cours.",
        "de": u"Es l\u00e4uft bereits eine \u00dcbertragung.",
        "pt": u"J\u00e1 existe uma transfer\u00eancia em andamento.",
    },
    "gui.files_added": {
        "en": u"Added %s file(s) - %s in the list",
        "es": u"A\u00f1adidos %s archivo(s) - %s en la lista",
        "fr": u"%s fichier(s) ajout\u00e9(s) - %s dans la liste",
        "de": u"%s Datei(en) hinzugef\u00fcgt - %s in der Liste",
        "pt": u"%s arquivo(s) adicionado(s) - %s na lista",
    },
    "gui.file_removed": {
        "en": u"Removed from the list: %s",
        "es": u"Quitado de la lista: %s",
        "fr": u"Retir\u00e9 de la liste : %s",
        "de": u"Aus der Liste entfernt: %s",
        "pt": u"Removido da lista: %s",
    },
    "gui.queue_cleared": {
        "en": u"File list cleared.",
        "es": u"Lista de archivos vaciada.",
        "fr": u"Liste de fichiers vid\u00e9e.",
        "de": u"Dateiliste geleert.",
        "pt": u"Lista de arquivos limpa.",
    },
    "gui.clipboard_added": {
        "en": u"Clipboard text added as %s (%s bytes)",
        "es": u"Texto del portapapeles a\u00f1adido como %s (%s bytes)",
        "fr": u"Texte du presse-papiers ajout\u00e9 comme %s (%s octets)",
        "de": u"Text aus der Zwischenablage hinzugef\u00fcgt als %s (%s Bytes)",
        "pt": u"Texto da \u00e1rea de transfer\u00eancia adicionado como %s (%s bytes)",
    },
    "send.cancelled": {
        "en": u"Transfer cancelled by the user.",
        "es": u"Env\u00edo cancelado por el usuario.",
        "fr": u"Envoi annul\u00e9 par l'utilisateur.",
        "de": u"Übertragung vom Benutzer abgebrochen.",
        "pt": u"Envio cancelado pelo usu\u00e1rio.",
    },
    "send.cancel_sent": {
        "en": u"Cancel request sent to the receiver.",
        "es": u"Solicitud de cancelaci\u00f3n enviada al receptor.",
        "fr": u"Demande d'annulation envoy\u00e9e au r\u00e9cepteur.",
        "de": u"Abbruchanfrage an den Empf\u00e4nger gesendet.",
        "pt": u"Pedido de cancelamento enviado ao receptor.",
    },
    # ---------------------------------------------------------------- ventana
    "app.title": {
        "en": u"SnowSend",
        "es": u"SnowSend",
        "fr": u"SnowSend",
        "de": u"SnowSend",
        "pt": u"SnowSend",
    },
    "app.subtitle": {
        "en": u"LocalSend protocol v2 - Mac OS X 10.6",
        "es": u"Protocolo LocalSend v2 - Mac OS X 10.6",
        "fr": u"Protocole LocalSend v2 - Mac OS X 10.6",
        "de": u"LocalSend-Protokoll v2 - Mac OS X 10.6",
        "pt": u"Protocolo LocalSend v2 - Mac OS X 10.6",
    },
    # ---------------------------------------------------------------- menu
    # ---------------------------------------------------------------- toolbar
    "label.alias": {
        "en": u"Name:",
        "es": u"Nombre:",
        "fr": u"Nom :",
        "de": u"Name:",
        "pt": u"Nome:",
    },
    "btn.apply": {
        "en": u"Apply",
        "es": u"Aplicar",
        "fr": u"Appliquer",
        "de": u"\u00dcbernehmen",
        "pt": u"Aplicar",
    },
    "status.server": {
        "en": u"Server: plain HTTP :%s - running",
        "es": u"Servidor: HTTP plano :%s - activo",
        "fr": u"Serveur : HTTP simple :%s - actif",
        "de": u"Server: reines HTTP :%s - aktiv",
        "pt": u"Servidor: HTTP simples :%s - ativo",
    },
    "label.download_dir": {
        "en": u"Save to:",
        "es": u"Guardar en:",
        "fr": u"Enregistrer dans :",
        "de": u"Speichern in:",
        "pt": u"Salvar em:",
    },
    "btn.change": {
        "en": u"Change\u2026",
        "es": u"Cambiar\u2026",
        "fr": u"Changer\u2026",
        "de": u"\u00c4ndern\u2026",
        "pt": u"Alterar\u2026",
    },
    "label.devices": {
        "en": u"Devices on this network",
        "es": u"Dispositivos en esta red",
        "fr": u"Appareils sur ce r\u00e9seau",
        "de": u"Ger\u00e4te in diesem Netzwerk",
        "pt": u"Dispositivos nesta rede",
    },
    "btn.announce": {
        "en": u"Announce / Refresh",
        "es": u"Anunciar / Refrescar",
        "fr": u"Annoncer / Actualiser",
        "de": u"Ank\u00fcndigen / Aktualisieren",
        "pt": u"Anunciar / Atualizar",
    },
    "btn.scan": {
        "en": u"Scan network",
        "es": u"Escanear red",
        "fr": u"Analyser le r\u00e9seau",
        "de": u"Netzwerk scannen",
        "pt": u"Verificar rede",
    },
    "btn.send": {
        "en": u"Send to Device",
        "es": u"Enviar al dispositivo",
        "fr": u"Envoyer \u00e0 l'appareil",
        "de": u"An Ger\u00e4t senden",
        "pt": u"Enviar ao dispositivo",
    },
    "btn.clear_log": {
        "en": u"Clear log",
        "es": u"Limpiar registro",
        "fr": u"Effacer le journal",
        "de": u"Protokoll leeren",
        "pt": u"Limpar registro",
    },
    "label.log": {
        "en": u"Activity",
        "es": u"Actividad",
        "fr": u"Activit\u00e9",
        "de": u"Aktivit\u00e4t",
        "pt": u"Atividade",
    },
    "footer.hint": {
        "en": u"HTTP :%s - Encryption OFF on the other device",
        "es": u"HTTP :%s - Encryption OFF en el otro dispositivo",
        "fr": u"HTTP :%s - Encryption OFF sur l'autre appareil",
        "de": u"HTTP :%s - Encryption OFF auf dem anderen Ger\u00e4t",
        "pt": u"HTTP :%s - Encryption OFF no outro dispositivo",
    },
    "gui.fitted": {
        "en": u"Window fitted to the screen: %sx%s",
        "es": u"Ventana ajustada a la pantalla: %sx%s",
        "fr": u"Fen\u00eatre ajust\u00e9e \u00e0 l'\u00e9cran : %sx%s",
        "de": u"Fenster an den Bildschirm angepasst: %sx%s",
        "pt": u"Janela ajustada \u00e0 tela: %sx%s",
    },
    # ---------------------------------------------------------------- columnas
    "col.name": {
        "en": u"Name",
        "es": u"Nombre",
        "fr": u"Nom",
        "de": u"Name",
        "pt": u"Nome",
    },
    "col.model": {
        "en": u"Model",
        "es": u"Modelo",
        "fr": u"Mod\u00e8le",
        "de": u"Modell",
        "pt": u"Modelo",
    },
    "col.address": {
        "en": u"Address",
        "es": u"Direcci\u00f3n",
        "fr": u"Adresse",
        "de": u"Adresse",
        "pt": u"Endere\u00e7o",
    },
    # ---------------------------------------------------------------- estado
    "status.ready": {
        "en": u"Ready",
        "es": u"Listo",
        "fr": u"Pr\u00eat",
        "de": u"Bereit",
        "pt": u"Pronto",
    },
    "status.devices": {
        "en": u"%s device(s)",
        "es": u"%s dispositivo(s)",
        "fr": u"%s appareil(s)",
        "de": u"%s Ger\u00e4t(e)",
        "pt": u"%s dispositivo(s)",
    },
    "status.language": {
        "en": u"Language: %s",
        "es": u"Idioma: %s",
        "fr": u"Langue : %s",
        "de": u"Sprache: %s",
        "pt": u"Idioma: %s",
    },
    "type.desktop": {
        "en": u"computer",
        "es": u"ordenador",
        "fr": u"ordinateur",
        "de": u"Computer",
        "pt": u"computador",
    },
    "type.mobile": {
        "en": u"mobile",
        "es": u"m\u00f3vil",
        "fr": u"mobile",
        "de": u"Mobilger\u00e4t",
        "pt": u"celular",
    },
    "type.web": {
        "en": u"browser",
        "es": u"navegador",
        "fr": u"navigateur",
        "de": u"Browser",
        "pt": u"navegador",
    },
    "type.headless": {
        "en": u"headless",
        "es": u"sin pantalla",
        "fr": u"sans \u00e9cran",
        "de": u"ohne Anzeige",
        "pt": u"sem tela",
    },
    "type.server": {
        "en": u"server",
        "es": u"servidor",
        "fr": u"serveur",
        "de": u"Server",
        "pt": u"servidor",
    },
    # ---------------------------------------------------------------- dialogos
    "warn.no_device": {
        "en": u"Select a device from the list first.",
        "es": u"Selecciona primero un dispositivo de la lista.",
        "fr": u"S\u00e9lectionnez d'abord un appareil dans la liste.",
        "de": u"W\u00e4hle zuerst ein Ger\u00e4t aus der Liste.",
        "pt": u"Selecione primeiro um dispositivo da lista.",
    },
    "dialog.change_folder": {
        "en": u"Choose the download folder",
        "es": u"Carpeta de descarga",
        "fr": u"Dossier de t\u00e9l\u00e9chargement",
        "de": u"Download-Ordner w\u00e4hlen",
        "pt": u"Pasta de download",
    },
    "dialog.pick_files": {
        "en": u"Choose files to add",
        "es": u"Elige archivos para a\u00f1adir",
        "fr": u"Choisir des fichiers \u00e0 ajouter",
        "de": u"Dateien zum Hinzuf\u00fcgen w\u00e4hlen",
        "pt": u"Escolha arquivos para adicionar",
    },
    "prefs.language": {
        "en": u"Language:",
        "es": u"Idioma:",
        "fr": u"Langue :",
        "de": u"Sprache:",
        "pt": u"Idioma:",
    },
    # ---------------------------------------------------------------- registro
    "log.device_found": {
        "en": u"Device found: %s (%s) %s://%s:%s",
        "es": u"Dispositivo detectado: %s (%s) %s://%s:%s",
        "fr": u"Appareil d\u00e9tect\u00e9 : %s (%s) %s://%s:%s",
        "de": u"Ger\u00e4t gefunden: %s (%s) %s://%s:%s",
        "pt": u"Dispositivo encontrado: %s (%s) %s://%s:%s",
    },
    "log.unknown_device": {
        "en": u"Unknown",
        "es": u"Desconocido",
        "fr": u"Inconnu",
        "de": u"Unbekannt",
        "pt": u"Desconhecido",
    },
    "log.mc_error_fallback": {
        "en": u"Error sending multicast announcement (fallback): %s",
        "es": u"Error enviando anuncio multicast (respaldo): %s",
        "fr": u"Erreur lors de l'envoi de l'annonce multicast (secours) : %s",
        "de": u"Fehler beim Senden der Multicast-Ank\u00fcndigung (Ersatzweg): %s",
        "pt": u"Erro ao enviar an\u00fancio multicast (alternativo): %s",
    },
    "log.mc_sent_temp": {
        "en": u"Multicast announcement sent (via temporary socket, local IP %s)",
        "es": u"Anuncio multicast enviado (via socket temporal, IP local %s)",
        "fr": u"Annonce multicast envoy\u00e9e (socket temporaire, IP locale %s)",
        "de": u"Multicast-Ank\u00fcndigung gesendet (tempor\u00e4rer Socket, lokale IP %s)",
        "pt": u"An\u00fancio multicast enviado (socket tempor\u00e1rio, IP local %s)",
    },
    "log.mc_error": {
        "en": u"Error sending multicast announcement: %s",
        "es": u"Error enviando anuncio multicast: %s",
        "fr": u"Erreur lors de l'envoi de l'annonce multicast : %s",
        "de": u"Fehler beim Senden der Multicast-Ank\u00fcndigung: %s",
        "pt": u"Erro ao enviar an\u00fancio multicast: %s",
    },
    "log.register_failed": {
        "en": u"Could not register with %s (%s): %s",
        "es": u"No se pudo registrar en %s (%s): %s",
        "fr": u"Impossible de s'enregistrer aupr\u00e8s de %s (%s) : %s",
        "de": u"Registrierung bei %s (%s) fehlgeschlagen: %s",
        "pt": u"N\u00e3o foi poss\u00edvel registrar em %s (%s): %s",
    },
    "log.udp_bind_warn": {
        "en": u"Warning: could not bind UDP :%s (%s). Announcement only.",
        "es": u"Aviso: no se pudo enlazar UDP :%s (%s). Se intentar\u00e1 solo con anuncio.",
        "fr": u"Attention : impossible de lier UDP :%s (%s). Annonce uniquement.",
        "de": u"Warnung: UDP :%s konnte nicht gebunden werden (%s). Nur Ank\u00fcndigung.",
        "pt": u"Aviso: n\u00e3o foi poss\u00edvel vincular UDP :%s (%s). Somente an\u00fancio.",
    },
    "log.discovery_active": {
        "en": u"Multicast discovery active on %s:%s (local IP %s)",
        "es": u"Descubrimiento multicast activo en %s:%s (IP local %s)",
        "fr": u"D\u00e9couverte multicast active sur %s:%s (IP locale %s)",
        "de": u"Multicast-Erkennung aktiv auf %s:%s (lokale IP %s)",
        "pt": u"Descoberta multicast ativa em %s:%s (IP local %s)",
    },
    "log.no_local_ip": {
        "en": u"Could not determine the local IP address for scanning.",
        "es": u"No se pudo determinar la IP local para escanear.",
        "fr": u"Impossible de d\u00e9terminer l'IP locale pour l'analyse.",
        "de": u"Lokale IP f\u00fcr den Scan konnte nicht ermittelt werden.",
        "pt": u"N\u00e3o foi poss\u00edvel determinar o IP local para verificar.",
    },
    "log.bad_local_ip": {
        "en": u"Invalid local IP: %s",
        "es": u"IP local inv\u00e1lida: %s",
        "fr": u"IP locale non valide : %s",
        "de": u"Ung\u00fcltige lokale IP: %s",
        "pt": u"IP local inv\u00e1lido: %s",
    },
    "log.scanning": {
        "en": u"Scanning %s0/24 (local IP %s) for LocalSend devices...",
        "es": u"Escaneando %s0/24 (IP local %s) en busca de dispositivos LocalSend...",
        "fr": u"Analyse de %s0/24 (IP locale %s) \u00e0 la recherche d'appareils LocalSend\u2026",
        "de": u"Suche in %s0/24 (lokale IP %s) nach LocalSend-Ger\u00e4ten...",
        "pt": u"Verificando %s0/24 (IP local %s) em busca de dispositivos LocalSend...",
    },
    "log.scan_found": {
        "en": u"Scan: found %s at %s",
        "es": u"Escaneo: encontrado %s en %s",
        "fr": u"Analyse : %s trouv\u00e9 sur %s",
        "de": u"Scan: %s gefunden unter %s",
        "pt": u"Verifica\u00e7\u00e3o: %s encontrado em %s",
    },
    "log.scan_done": {
        "en": u"Network scan finished.",
        "es": u"Escaneo de red completado.",
        "fr": u"Analyse du r\u00e9seau termin\u00e9e.",
        "de": u"Netzwerkscan abgeschlossen.",
        "pt": u"Verifica\u00e7\u00e3o da rede conclu\u00edda.",
    },
    "log.http_access": {
        "en": u"HTTP %s - %s",
        "es": u"HTTP %s - %s",
        "fr": u"HTTP %s - %s",
        "de": u"HTTP %s - %s",
        "pt": u"HTTP %s - %s",
    },
    "log.prepare_bad_json": {
        "en": u"prepare-upload: invalid JSON: %s",
        "es": u"prepare-upload: JSON inv\u00e1lido: %s",
        "fr": u"prepare-upload : JSON invalide : %s",
        "de": u"prepare-upload: ung\u00fcltiges JSON: %s",
        "pt": u"prepare-upload: JSON inv\u00e1lido: %s",
    },
    "log.incoming_request": {
        "en": u"Request from %s: %s file(s) - accepted automatically",
        "es": u"Solicitud de %s: %s archivo(s) - aceptado autom\u00e1ticamente",
        "fr": u"Demande de %s : %s fichier(s) - accept\u00e9e automatiquement",
        "de": u"Anfrage von %s: %s Datei(en) - automatisch angenommen",
        "pt": u"Solicita\u00e7\u00e3o de %s: %s arquivo(s) - aceita automaticamente",
    },
    "log.incoming_file": {
        "en": u"  - %s (%s bytes)",
        "es": u"  - %s (%s bytes)",
        "fr": u"  - %s (%s octets)",
        "de": u"  - %s (%s Bytes)",
        "pt": u"  - %s (%s bytes)",
    },
    "log.upload_session_missing": {
        "en": u"upload: session or file not found (session=%s file=%s)",
        "es": u"upload: sesi\u00f3n o archivo no encontrado (session=%s file=%s)",
        "fr": u"upload : session ou fichier introuvable (session=%s file=%s)",
        "de": u"upload: Sitzung oder Datei nicht gefunden (session=%s file=%s)",
        "pt": u"upload: sess\u00e3o ou arquivo n\u00e3o encontrado (session=%s file=%s)",
    },
    "log.upload_bad_token": {
        "en": u"upload: invalid token for %s",
        "es": u"upload: token inv\u00e1lido para %s",
        "fr": u"upload : jeton non valide pour %s",
        "de": u"upload: ung\u00fcltiges Token f\u00fcr %s",
        "pt": u"upload: token inv\u00e1lido para %s",
    },
    "log.upload_info": {
        "en": u"upload: %s Content-Length=%s Transfer-Encoding=%s",
        "es": u"upload: %s Content-Length=%s Transfer-Encoding=%s",
        "fr": u"upload : %s Content-Length=%s Transfer-Encoding=%s",
        "de": u"upload: %s Content-Length=%s Transfer-Encoding=%s",
        "pt": u"upload: %s Content-Length=%s Transfer-Encoding=%s",
    },
    "log.mkdir_fail": {
        "en": u"Could not create the download folder: %s",
        "es": u"No se pudo crear la carpeta de descarga: %s",
        "fr": u"Impossible de cr\u00e9er le dossier de t\u00e9l\u00e9chargement : %s",
        "de": u"Download-Ordner konnte nicht erstellt werden: %s",
        "pt": u"N\u00e3o foi poss\u00edvel criar a pasta de download: %s",
    },
    "log.save_error": {
        "en": u"Error saving %s: %s",
        "es": u"Error guardando %s: %s",
        "fr": u"Erreur lors de l'enregistrement de %s : %s",
        "de": u"Fehler beim Speichern von %s: %s",
        "pt": u"Erro ao salvar %s: %s",
    },
    "log.checksum_error": {
        "en": u"ERROR: SHA256 checksum mismatch for %s (received %s bytes, expected %s)",
        "es": u"ERROR: checksum SHA256 no coincide para %s (recibidos %s bytes, esperados %s)",
        "fr": u"ERREUR : somme SHA256 incorrecte pour %s (%s octets re\u00e7us, %s attendus)",
        "de": u"FEHLER: SHA256-Pr\u00fcfsumme stimmt nicht f\u00fcr %s (%s Bytes erhalten, %s erwartet)",
        "pt": u"ERRO: checksum SHA256 n\u00e3o confere para %s (%s bytes recebidos, %s esperados)",
    },
    "log.file_received": {
        "en": u"File received: %s (%s bytes) -> %s",
        "es": u"Archivo recibido: %s (%s bytes) -> %s",
        "fr": u"Fichier re\u00e7u : %s (%s octets) -> %s",
        "de": u"Datei empfangen: %s (%s Bytes) -> %s",
        "pt": u"Arquivo recebido: %s (%s bytes) -> %s",
    },
    "log.session_cancelled": {
        "en": u"Session cancelled by the sender",
        "es": u"Sesi\u00f3n cancelada por el remitente",
        "fr": u"Session annul\u00e9e par l'exp\u00e9diteur",
        "de": u"Sitzung vom Absender abgebrochen",
        "pt": u"Sess\u00e3o cancelada pelo remetente",
    },
    "err.not_json": {
        "en": u"Response is not JSON (status %s, url %s, headers %s, body=%s)",
        "es": u"Respuesta no JSON (status %s, url %s, headers %s, body=%s)",
        "fr": u"R\u00e9ponse non JSON (status %s, url %s, en-t\u00eates %s, corps=%s)",
        "de": u"Antwort ist kein JSON (Status %s, URL %s, Header %s, Body=%s)",
        "pt": u"Resposta n\u00e3o JSON (status %s, url %s, cabe\u00e7alhos %s, corpo=%s)",
    },
    "err.http_get": {
        "en": u"HTTP %s on GET %s: %s",
        "es": u"HTTP %s en GET %s: %s",
        "fr": u"HTTP %s sur GET %s : %s",
        "de": u"HTTP %s bei GET %s: %s",
        "pt": u"HTTP %s em GET %s: %s",
    },
    "err.http_post": {
        "en": u"HTTP %s on POST %s: %s",
        "es": u"HTTP %s en POST %s: %s",
        "fr": u"HTTP %s sur POST %s : %s",
        "de": u"HTTP %s bei POST %s: %s",
        "pt": u"HTTP %s em POST %s: %s",
    },
    "err.http_upload": {
        "en": u"HTTP %s on upload %s: %s",
        "es": u"HTTP %s en upload %s: %s",
        "fr": u"HTTP %s sur l'envoi %s : %s",
        "de": u"HTTP %s beim Upload %s: %s",
        "pt": u"HTTP %s no upload %s: %s",
    },
    "log.server_started": {
        "en": u"HTTP server started on port %s",
        "es": u"Servidor HTTP iniciado en el puerto %s",
        "fr": u"Serveur HTTP d\u00e9marr\u00e9 sur le port %s",
        "de": u"HTTP-Server auf Port %s gestartet",
        "pt": u"Servidor HTTP iniciado na porta %s",
    },
    # ---------------------------------------------------------------- diagnostico
    "hint.no_plain_http": {
        "en": u"  >>> The device does NOT accept plain HTTP on port %s.",
        "es": u"  >>> El dispositivo NO acepta HTTP plano por el puerto %s.",
        "fr": u"  >>> L'appareil n'accepte PAS le HTTP simple sur le port %s.",
        "de": u"  >>> Das Ger\u00e4t akzeptiert KEIN reines HTTP auf Port %s.",
        "pt": u"  >>> O dispositivo N\u00c3O aceita HTTP simples na porta %s.",
    },
    "hint.encryption_off": {
        "en": u"  >>> On the iPhone open LocalSend > Settings (gear) and set Encryption to OFF,",
        "es": u"  >>> En el iPhone abre LocalSend > Ajustes (engranaje) y pon Encryption en OFF,",
        "fr": u"  >>> Sur l'iPhone, ouvrez LocalSend > R\u00e9glages (engrenage) et mettez Encryption sur OFF,",
        "de": u"  >>> \u00d6ffne auf dem iPhone LocalSend > Einstellungen (Zahnrad) und setze Encryption auf OFF,",
        "pt": u"  >>> No iPhone abra LocalSend > Ajustes (engrenagem) e defina Encryption como OFF,",
    },
    "hint.reannounce": {
        "en": u"  >>> close and reopen LocalSend, then press 'Announce / Refresh' here.",
        "es": u"  >>> cierra y vuelve a abrir LocalSend, luego pulsa 'Anunciar / Refrescar' aqu\u00ed.",
        "fr": u"  >>> fermez et rouvrez LocalSend, puis appuyez sur \u00ab Annoncer / Actualiser \u00bb ici.",
        "de": u"  >>> schlie\u00dfe LocalSend und \u00f6ffne es erneut, dann klicke hier auf 'Ank\u00fcndigen / Aktualisieren'.",
        "pt": u"  >>> feche e reabra o LocalSend, depois toque em 'Anunciar / Atualizar' aqui.",
    },
    "diag.no_plain_http": {
        "en": u"  Diagnosis: %s does not answer on plain HTTP (%s)",
        "es": u"  Diagn\u00f3stico: %s no responde a HTTP plano (%s)",
        "fr": u"  Diagnostic : %s ne r\u00e9pond pas en HTTP simple (%s)",
        "de": u"  Diagnose: %s antwortet nicht auf reines HTTP (%s)",
        "pt": u"  Diagn\u00f3stico: %s n\u00e3o responde a HTTP simples (%s)",
    },
    "diag.accept_prompt": {
        "en": u"  If the transfer prompt does not appear on the iPhone, restart LocalSend there.",
        "es": u"  Si el aviso de transferencia no aparece en el iPhone, reinicia LocalSend all\u00ed.",
        "fr": u"  Si l'invite de transfert n'appara\u00eet pas sur l'iPhone, red\u00e9marrez LocalSend.",
        "de": u"  Erscheint die \u00dcbertragungsabfrage nicht auf dem iPhone, starte LocalSend dort neu.",
        "pt": u"  Se o aviso de transfer\u00eancia n\u00e3o aparecer no iPhone, reinicie o LocalSend nele.",
    },
    "diag.ok_http": {
        "en": u"  Diagnosis: %s does answer /info over HTTP (alias=%s, protocol=%s).",
        "es": u"  Diagn\u00f3stico: %s s\u00ed responde /info por HTTP (alias=%s, protocol=%s).",
        "fr": u"  Diagnostic : %s r\u00e9pond bien \u00e0 /info en HTTP (alias=%s, protocol=%s).",
        "de": u"  Diagnose: %s antwortet auf /info per HTTP (Alias=%s, Protokoll=%s).",
        "pt": u"  Diagn\u00f3stico: %s responde /info via HTTP (alias=%s, protocol=%s).",
    },
    "diag.restart_hint": {
        "en": u"  Try restarting LocalSend on the iPhone and accept the transfer prompt.",
        "es": u"  Prueba a reiniciar LocalSend en el iPhone y a aceptar el aviso de transferencia.",
        "fr": u"  Essayez de red\u00e9marrer LocalSend sur l'iPhone et d'accepter l'invite de transfert.",
        "de": u"  Starte LocalSend auf dem iPhone neu und akzeptiere die \u00dcbertragungsabfrage.",
        "pt": u"  Tente reiniciar o LocalSend no iPhone e aceitar o aviso de transfer\u00eancia.",
    },
    "diag.unexpected": {
        "en": u"  Diagnosis: /info returned unexpected data: %s",
        "es": u"  Diagn\u00f3stico: /info devolvi\u00f3 datos inesperados: %s",
        "fr": u"  Diagnostic : /info a renvoy\u00e9 des donn\u00e9es inattendues : %s",
        "de": u"  Diagnose: /info lieferte unerwartete Daten: %s",
        "pt": u"  Diagn\u00f3stico: /info retornou dados inesperados: %s",
    },
    # ---------------------------------------------------------------- envio
    "send.preparing": {
        "en": u"Preparing to send to %s (http://%s:%s) - %s file(s)",
        "es": u"Preparando env\u00edo a %s (http://%s:%s) - %s archivo(s)",
        "fr": u"Pr\u00e9paration de l'envoi vers %s (http://%s:%s) - %s fichier(s)",
        "de": u"Senden an %s wird vorbereitet (http://%s:%s) - %s Datei(en)",
        "pt": u"Preparando envio para %s (http://%s:%s) - %s arquivo(s)",
    },
    "send.skipped": {
        "en": u"  Skipped (does not exist): %s",
        "es": u"  Omitido (no existe): %s",
        "fr": u"  Ignor\u00e9 (inexistant) : %s",
        "de": u"  \u00dcbersprungen (existiert nicht): %s",
        "pt": u"  Ignorado (n\u00e3o existe): %s",
    },
    "send.hashing": {
        "en": u"  Computing SHA256: %s (%s bytes)",
        "es": u"  Calculando SHA256: %s (%s bytes)",
        "fr": u"  Calcul du SHA256 : %s (%s octets)",
        "de": u"  SHA256 wird berechnet: %s (%s Bytes)",
        "pt": u"  Calculando SHA256: %s (%s bytes)",
    },
    "send.hash_fail": {
        "en": u"  Could not compute SHA256 of %s: %s",
        "es": u"  No se pudo calcular SHA256 de %s: %s",
        "fr": u"  Impossible de calculer le SHA256 de %s : %s",
        "de": u"  SHA256 von %s konnte nicht berechnet werden: %s",
        "pt": u"  N\u00e3o foi poss\u00edvel calcular SHA256 de %s: %s",
    },
    "send.no_files": {
        "en": u"No valid files to send.",
        "es": u"No hay archivos v\u00e1lidos para enviar.",
        "fr": u"Aucun fichier valide \u00e0 envoyer.",
        "de": u"Keine g\u00fcltigen Dateien zum Senden.",
        "pt": u"N\u00e3o h\u00e1 arquivos v\u00e1lidos para enviar.",
    },
    "send.waiting_accept": {
        "en": u"  Waiting for acceptance on %s... (accept the prompt on the other device)",
        "es": u"  Esperando aceptaci\u00f3n en %s... (acepta el aviso en el otro dispositivo)",
        "fr": u"  En attente d'acceptation sur %s\u2026 (acceptez l'invite sur l'autre appareil)",
        "de": u"  Warte auf Best\u00e4tigung auf %s... (best\u00e4tige die Abfrage am anderen Ger\u00e4t)",
        "pt": u"  Aguardando aceita\u00e7\u00e3o em %s... (aceite o aviso no outro dispositivo)",
    },
    "send.prepare_fail_proto": {
        "en": u"  prepare-upload with %s failed: %s",
        "es": u"  prepare-upload con %s fall\u00f3: %s",
        "fr": u"  prepare-upload avec %s a \u00e9chou\u00e9 : %s",
        "de": u"  prepare-upload mit %s fehlgeschlagen: %s",
        "pt": u"  prepare-upload com %s falhou: %s",
    },
    "send.prepare_error": {
        "en": u"Error in prepare-upload: %s",
        "es": u"Error en prepare-upload: %s",
        "fr": u"Erreur dans prepare-upload : %s",
        "de": u"Fehler bei prepare-upload: %s",
        "pt": u"Erro em prepare-upload: %s",
    },
    "send.no_session": {
        "en": u"Unexpected prepare-upload response (no sessionId): %s",
        "es": u"Respuesta inesperada de prepare-upload (sin sessionId): %s",
        "fr": u"R\u00e9ponse inattendue de prepare-upload (pas de sessionId) : %s",
        "de": u"Unerwartete prepare-upload-Antwort (keine sessionId): %s",
        "pt": u"Resposta inesperada de prepare-upload (sem sessionId): %s",
    },
    "send.empty_response": {
        "en": u"  The receiver returned an empty response.",
        "es": u"  El receptor devolvi\u00f3 una respuesta vac\u00eda.",
        "fr": u"  Le r\u00e9cepteur a renvoy\u00e9 une r\u00e9ponse vide.",
        "de": u"  Der Empf\u00e4nger hat eine leere Antwort gesendet.",
        "pt": u"  O receptor retornou uma resposta vazia.",
    },
    "send.session_ok": {
        "en": u"Session accepted: %s",
        "es": u"Sesi\u00f3n aceptada: %s",
        "fr": u"Session accept\u00e9e : %s",
        "de": u"Sitzung angenommen: %s",
        "pt": u"Sess\u00e3o aceita: %s",
    },
    "send.not_authorized": {
        "en": u"  %s: not authorized by the receiver",
        "es": u"  %s: no autorizado por el receptor",
        "fr": u"  %s : non autoris\u00e9 par le r\u00e9cepteur",
        "de": u"  %s: vom Empf\u00e4nger nicht erlaubt",
        "pt": u"  %s: n\u00e3o autorizado pelo receptor",
    },
    "send.rejected": {
        "en": u"  %s: rejected by the receiver",
        "es": u"  %s: rechazado por el receptor",
        "fr": u"  %s : refus\u00e9 par le r\u00e9cepteur",
        "de": u"  %s: vom Empf\u00e4nger abgelehnt",
        "pt": u"  %s: recusado pelo receptor",
    },
    "send.sending": {
        "en": u"  Sending: %s",
        "es": u"  Enviando: %s",
        "fr": u"  Envoi : %s",
        "de": u"  Sende: %s",
        "pt": u"  Enviando: %s",
    },
    "send.file_ok": {
        "en": u"  Done: %s",
        "es": u"  OK: %s",
        "fr": u"  OK : %s",
        "de": u"  Fertig: %s",
        "pt": u"  OK: %s",
    },
    "send.file_error": {
        "en": u"  Error sending %s: %s",
        "es": u"  Error enviando %s: %s",
        "fr": u"  Erreur lors de l'envoi de %s : %s",
        "de": u"  Fehler beim Senden von %s: %s",
        "pt": u"  Erro ao enviar %s: %s",
    },
    "send.finished": {
        "en": u"Transfer finished: %s/%s file(s) to %s",
        "es": u"Env\u00edo finalizado: %s/%s archivo(s) a %s",
        "fr": u"Envoi termin\u00e9 : %s/%s fichier(s) vers %s",
        "de": u"Senden beendet: %s/%s Datei(en) an %s",
        "pt": u"Envio conclu\u00eddo: %s/%s arquivo(s) para %s",
    },
    # ---------------------------------------------------------------- GUI / app
    "gui.alias_changed": {
        "en": u"Name changed to: %s",
        "es": u"Nombre cambiado a: %s",
        "fr": u"Nom modifi\u00e9 en : %s",
        "de": u"Name ge\u00e4ndert in: %s",
        "pt": u"Nome alterado para: %s",
    },
    "gui.announcing": {
        "en": u"Announcing presence on the network (multicast %s:%s)...",
        "es": u"Anunciando presencia en la red (multicast %s:%s)...",
        "fr": u"Annonce de pr\u00e9sence sur le r\u00e9seau (multicast %s:%s)\u2026",
        "de": u"Pr\u00e4senz im Netzwerk wird angek\u00fcndigt (Multicast %s:%s)...",
        "pt": u"Anunciando presen\u00e7a na rede (multicast %s:%s)...",
    },
    "gui.download_dir": {
        "en": u"Download folder: %s",
        "es": u"Carpeta de descarga: %s",
        "fr": u"Dossier de t\u00e9l\u00e9chargement : %s",
        "de": u"Download-Ordner: %s",
        "pt": u"Pasta de download: %s",
    },
    "gui.send_started": {
        "en": u"Sending to %s (%s file(s))",
        "es": u"Env\u00edo iniciado a %s (%s archivo(s))",
        "fr": u"Envoi vers %s (%s fichier(s))",
        "de": u"Senden an %s (%s Datei(en))",
        "pt": u"Envio iniciado para %s (%s arquivo(s))",
    },
    "gui.language_changed": {
        "en": u"Language changed to %s",
        "es": u"Idioma cambiado a %s",
        "fr": u"Langue chang\u00e9e en %s",
        "de": u"Sprache ge\u00e4ndert auf %s",
        "pt": u"Idioma alterado para %s",
    },
    "gui.device_count": {
        "en": u"Devices in list: %s",
        "es": u"Dispositivos en lista: %s",
        "fr": u"Appareils dans la liste : %s",
        "de": u"Ger\u00e4te in der Liste: %s",
        "pt": u"Dispositivos na lista: %s",
    },
    "headless.active": {
        "en": u"Headless mode active. Alias: %s",
        "es": u"Modo headless activo. Nombre: %s",
        "fr": u"Mode sans interface actif. Alias : %s",
        "de": u"Headless-Modus aktiv. Alias: %s",
        "pt": u"Modo headless ativo. Alias: %s",
    },
    "headless.quit_hint": {
        "en": u"Press Ctrl+C to quit.",
        "es": u"Pulsa Ctrl+C para salir.",
        "fr": u"Appuyez sur Ctrl+C pour quitter.",
        "de": u"Zum Beenden Ctrl+C dr\u00fccken.",
        "pt": u"Pressione Ctrl+C para sair.",
    },
    "headless.interrupted": {
        "en": u"Interrupted by the user.",
        "es": u"Interrumpido por el usuario.",
        "fr": u"Interrompu par l'utilisateur.",
        "de": u"Vom Benutzer abgebrochen.",
        "pt": u"Interrompido pelo usu\u00e1rio.",
    },
    "app.started": {
        "en": u"SnowSend started - name: %s",
        "es": u"SnowSend iniciado - nombre: %s",
        "fr": u"SnowSend d\u00e9marr\u00e9 - nom : %s",
        "de": u"SnowSend gestartet - Name: %s",
        "pt": u"SnowSend iniciado - nome: %s",
    },
    "app.discovery": {
        "en": u"Multicast discovery: %s:%s",
        "es": u"Descubrimiento multicast: %s:%s",
        "fr": u"D\u00e9couverte multicast : %s:%s",
        "de": u"Multicast-Erkennung: %s:%s",
        "pt": u"Descoberta multicast: %s:%s",
    },
    "app.plain_http_hint": {
        "en": u"Plain HTTP on :%s - turn Encryption OFF on the other device.",
        "es": u"HTTP plano en :%s - desactiva Encryption en el otro dispositivo.",
        "fr": u"HTTP simple sur :%s - d\u00e9sactivez Encryption sur l'autre appareil.",
        "de": u"Reines HTTP auf :%s - schalte Encryption am anderen Ger\u00e4t aus.",
        "pt": u"HTTP simples em :%s - desative Encryption no outro dispositivo.",
    },
    "app.tk_missing": {
        "en": u"Tkinter not available, using headless mode.",
        "es": u"Tkinter no disponible, usando modo headless.",
        "fr": u"Tkinter indisponible, mode sans interface.",
        "de": u"Tkinter nicht verf\u00fcgbar, Headless-Modus wird verwendet.",
        "pt": u"Tkinter indispon\u00edvel, usando modo headless.",
    },
}

_current_language = "en"


def available_languages():
    return list(LANGUAGES)


def set_language(code):
    """Fija el idioma activo. Devuelve el codigo realmente aplicado."""
    global _current_language
    if not code:
        return _current_language
    code = str(code).lower()[:2]
    if code in LANGUAGE_CODES:
        _current_language = code
    return _current_language


def current_language():
    return _current_language


def language_name(code=None):
    code = code or _current_language
    for c, name in LANGUAGES:
        if c == code:
            return name
    return code


def detect_language():
    """Idioma del sistema: AppleLocale en Snow Leopard, LANG/LC_ALL en UNIX."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "AppleLocale", "AppleLanguages"):
        try:
            value = os.environ.get(var)
        except Exception:
            value = None
        if not value:
            continue
        value = value.strip()
        # AppleLanguages viene como "(es-MX, en-US)"
        value = value.replace("(", "").replace(")", "").replace('"', "")
        value = value.split(",")[0].strip()
        code = value[:2].lower()
        if code in LANGUAGE_CODES:
            return code
    return "en"


def T(key, *args):
    """Traduce una clave. Acepta argumentos posicionales para los %s."""
    entry = STRINGS.get(key)
    if not entry:
        text = key
    else:
        text = entry.get(_current_language) or entry.get("en") or key
    # Python 2: asegurar unicode para que Tk muestre bien los acentos
    if not isinstance(text, unicode):
        try:
            text = text.decode("utf-8")
        except Exception:
            text = unicode(text)
    if args:
        try:
            return text % args
        except Exception:
            pass
    return text


# ---------------------------------------------------------------------------
# Configuracion persistente (~/.snowsend_config.json)
# ---------------------------------------------------------------------------

def config_path():
    return os.path.join(os.path.expanduser("~"), ".snowsend_config.json")


def load_config():
    data = {}
    for path in (config_path(), os.path.join(os.path.expanduser("~"), ".localsend_10_6_config.json")):
        try:
            f = open(path, "r")
            try:
                raw = f.read()
            finally:
                f.close()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
                break
        except Exception:
            continue
    cfg = {}
    alias = data.get("alias")
    if isinstance(alias, unicode) or isinstance(alias, str):
        if alias.strip():
            cfg["alias"] = alias.strip()
    lang = data.get("lang")
    if isinstance(lang, str) or isinstance(lang, unicode):
        if str(lang)[:2].lower() in LANGUAGE_CODES:
            cfg["lang"] = str(lang)[:2].lower()
    folder = data.get("download_dir")
    if isinstance(folder, (str, unicode)) and folder.strip():
        cfg["download_dir"] = os.path.expanduser(folder.strip())
    return cfg


def save_config(alias=None, lang=None, download_dir=None):
    data = {}
    try:
        f = open(config_path(), "r")
        try:
            parsed = json.loads(f.read())
            if isinstance(parsed, dict):
                data = parsed
        finally:
            f.close()
    except Exception:
        data = {}
    if alias:
        data["alias"] = alias
    if lang:
        data["lang"] = lang
    if download_dir:
        data["download_dir"] = download_dir
    try:
        f = open(config_path(), "w")
        try:
            f.write(json.dumps(data, indent=2))
        finally:
            f.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Utilidades de bytes / texto (Py2: str es bytes, Py3: bytes != str)
# ---------------------------------------------------------------------------

def to_bytes(s):
    if isinstance(s, bytes):
        return s
    return s.encode("utf-8")


def to_text(b):
    if isinstance(b, unicode):
        return b
    try:
        return b.decode("utf-8")
    except Exception:
        try:
            return b.decode("utf-8", "ignore")
        except Exception:
            return str(b)


def sha256_of_file(path):
    h = hashlib.sha256()
    f = open(path, "rb")
    try:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    finally:
        f.close()
    return h.hexdigest()


def sanitize_filename(name):
    name = str(name).replace("\\", "/")
    name = name.split("/")[-1]
    name = name.strip()
    if not name or name == "." or name == "..":
        name = "archivo_recibido"
    return name


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = "%s (%d)%s" % (base, i, ext)
        if not os.path.exists(candidate):
            return candidate
        i += 1


def default_alias():
    try:
        name = socket.gethostname()
    except Exception:
        name = "SnowLeopard"
    if not name:
        name = "SnowLeopard"
    name = name.split(".")[0]
    return name or "SnowLeopard"


def load_or_create_fingerprint():
    """Fingerprint persistente (en modo HTTP es una cadena aleatoria, segun
    la especificacion: SHA-256 del certificado si hay HTTPS, si no, aleatorio).
    Se guarda en ~/.snowsend_fingerprint para no auto-descubrirnos.
    (Si existe el archivo antiguo ~/.localsend_10_6_fingerprint se reutiliza
    su valor, para seguir siendo el mismo dispositivo tras el renombrado.)"""
    home = os.path.expanduser("~")
    path = os.path.join(home, ".snowsend_fingerprint")
    legacy_path = os.path.join(home, ".localsend_10_6_fingerprint")
    if not os.path.exists(path) and os.path.exists(legacy_path):
        try:
            lf = open(legacy_path, "r")
            try:
                legacy_fp = lf.read().strip()
            finally:
                lf.close()
            if legacy_fp:
                wf = open(path, "w")
                try:
                    wf.write(legacy_fp)
                finally:
                    wf.close()
        except Exception:
            pass
    try:
        f = open(path, "r")
        try:
            fp = f.read().strip()
        finally:
            f.close()
        if fp:
            return fp
    except Exception:
        pass
    raw = uuid.uuid4().hex + str(time.time()) + default_alias()
    fp = hashlib.sha256(to_bytes(raw)).hexdigest()
    try:
        f = open(path, "w")
        try:
            f.write(fp)
        finally:
            f.close()
    except Exception:
        pass
    return fp


# ---------------------------------------------------------------------------
# Estado global de la aplicacion
# ---------------------------------------------------------------------------

class AppState(object):
    def __init__(self, alias, download_dir):
        self.alias = alias
        self.download_dir = download_dir
        self.port = PORT
        self.fingerprint = load_or_create_fingerprint()
        self.devices = {}          # fingerprint -> dict(dispositivo)
        self.devices_lock = threading.Lock()
        self.sessions = {}         # sessionId -> dict(sesion)
        self.sessions_lock = threading.Lock()
        self.log_queue = queue_module.Queue()
        self.device_queue = queue_module.Queue()
        self.stop_event = threading.Event()
        self.discovery_sock = None
        self._last_device_count = -1

    def log(self, msg):
        try:
            ts = time.strftime("%H:%M:%S")
        except Exception:
            ts = ""
        line = "[%s] %s" % (ts, msg)
        try:
            print(line)
        except Exception:
            pass
        try:
            self.log_queue.put(line)
        except Exception:
            pass

    def add_device(self, info, ip):
        if not info or not isinstance(info, dict):
            return
        fp = info.get("fingerprint") or (str(info.get("alias") or T("log.unknown_device")) + "@" + str(ip))
        if fp == self.fingerprint:
            return
        alias = info.get("alias") or T("log.unknown_device")
        try:
            port = int(info.get("port") or PORT)
        except Exception:
            port = PORT
        protocol = info.get("protocol") or "http"
        device = {
            "alias": alias,
            "version": info.get("version") or PROTOCOL_VERSION,
            "deviceModel": info.get("deviceModel") or "",
            "deviceType": info.get("deviceType") or "",
            "fingerprint": fp,
            "port": port,
            "protocol": protocol,
            "download": info.get("download", False),
            "ip": ip,
            "last_seen": time.time(),
        }
        is_new = False
        with self.devices_lock:
            if fp not in self.devices:
                is_new = True
            self.devices[fp] = device
        if is_new:
            self.log(T("log.device_found") % (
                alias, device.get("deviceModel") or device.get("deviceType") or "",
                protocol, ip, port))
        try:
            self.device_queue.put(device)
        except Exception:
            pass


def build_info(state):
    return {
        "alias": state.alias,
        "version": PROTOCOL_VERSION,
        "deviceModel": DEVICE_MODEL,
        "deviceType": DEVICE_TYPE,
        "fingerprint": state.fingerprint,
        "port": getattr(state, "port", PORT) or PORT,
        "protocol": PROTOCOL,
        "download": False,
    }


class TransferCancelled(Exception):
    """El usuario pulso 'Cancelar envio'."""
    pass


# ---------------------------------------------------------------------------
# Cliente HTTP (httplib/http.client directo, con urllib2 como respaldo)
# ---------------------------------------------------------------------------
# El iPhone (Swift/Network.framework) puede responder con
# Transfer-Encoding: chunked, gzip o sin Content-Length, y el
# urllib2/httplib de Python 2.6 de Snow Leopard a veces devuelve el
# cuerpo con el framing chunked sin decodificar, gzip sin descomprimir
# o un cuerpo vacio en 204, lo que provocaba el error:
#   "No JSON object could be decoded"
# Por eso se usa httplib directamente, se registra status/headers/
# cuerpo crudo en caso de error y se intenta decodificar de varias
# formas (gzip/deflate, chunked manual, BOM, extraccion {..}).

def _try_decompress(body, encoding):
    if not body:
        return body
    enc = (encoding or "").lower()
    is_gzip = body[:2] == b"\x1f\x8b"
    if enc == "gzip" or is_gzip:
        try:
            f = gzip.GzipFile(fileobj=BytesIO(body))
            try:
                return f.read()
            finally:
                f.close()
        except Exception:
            pass
    if enc == "deflate":
        try:
            return zlib.decompress(body)
        except Exception:
            try:
                return zlib.decompress(body, -15)
            except Exception:
                pass
    return body


def _try_chunked_decode(body):
    """Decodifica framing chunked a mano si el cuerpo lo trae crudo
    (p. ej. b"a3\\r\\n{...}\\r\\n0\\r\\n\\r\\n"). Devuelve None si no
    parece chunked."""
    if not body or b"\r\n" not in body:
        return None
    # La primera linea debe ser un tamano hex (opcionalmente ;ext)
    first_line = body.split(b"\r\n", 1)[0].strip()
    try:
        int(first_line.split(b";")[0].strip(), 16)
    except Exception:
        return None
    out = b""
    pos = 0
    data = body
    while True:
        eol = data.find(b"\r\n", pos)
        if eol < 0:
            return None
        size_line = data[pos:eol].strip().split(b";")[0].strip()
        try:
            size = int(size_line, 16)
        except Exception:
            return None
        pos = eol + 2
        if size == 0:
            break
        if pos + size > len(data):
            return None
        out += data[pos:pos + size]
        pos += size
        # CRLF tras cada chunk
        if data[pos:pos + 2] == b"\r\n":
            pos += 2
        elif data[pos:pos + 1] == b"\n":
            pos += 1
    return out


def _parse_json_body(body, status, headers, url):
    if body is None:
        body = b""
    if not body or not body.strip():
        return {}
    encoding = headers.get("content-encoding") or headers.get("Content-Encoding") or ""
    body = _try_decompress(body, encoding)
    text = to_text(body)
    # BOM UTF-8
    if text.startswith("\ufeff"):
        text = text[1:]
    text_stripped = text.strip()
    if not text_stripped:
        return {}
    try:
        return json.loads(text_stripped)
    except Exception:
        pass
    # Chunked crudo sin decodificar por httplib (Python 2.6)
    decoded = _try_chunked_decode(body)
    if decoded is not None:
        try:
            return json.loads(to_text(_try_decompress(decoded, encoding)).strip())
        except Exception:
            pass
    # Extraer el primer objeto JSON {..} del cuerpo (por si viene
    # envuelto en HTML, framing u otro texto)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    # Fallo: incluir el cuerpo crudo para diagnosticar en el registro
    raw_repr = repr(body[:1000])
    raise ValueError(T("err.not_json") % (
        status, url, headers, raw_repr))


def _http_request(method, url, body_bytes, headers, timeout):
    parsed = urlparse(url)
    scheme = (parsed.scheme or "http").lower()
    host = parsed.hostname
    if not host:
        raise ValueError("URL sin host: %s" % url)
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = path + "?" + parsed.query
    conn = None
    if scheme == "https":
        try:
            import ssl
            if hasattr(ssl, "_create_unverified_context"):
                context = ssl._create_unverified_context()
                conn = httplib.HTTPSConnection(host, port, timeout=timeout, context=context)
        except Exception:
            conn = None
        if conn is None:
            conn = httplib.HTTPSConnection(host, port, timeout=timeout)
    else:
        conn = httplib.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(method, path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {}
        try:
            for k, v in resp.getheaders():
                resp_headers[k.lower()] = v
        except Exception:
            pass
        raw_body = b""
        try:
            raw_body = resp.read()
        except Exception as e:
            # httplib.IncompleteRead trae .partial con lo recibido
            partial = getattr(e, "partial", None)
            if partial is not None:
                raw_body = partial
            else:
                raise
        return status, resp_headers, raw_body
    finally:
        try:
            conn.close()
        except Exception:
            pass


def http_get_json(url, timeout=5):
    status, headers, body = _http_request("GET", url, None, {"Accept": "application/json"}, timeout)
    if status == 204:
        return {}
    if status >= 400:
        raise Exception(T("err.http_get") % (status, url, repr(body[:500])))
    return _parse_json_body(body, status, headers, url)


def http_post_json(url, body_dict, timeout=10):
    data = to_bytes(json.dumps(body_dict))
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    status, resp_headers, body = _http_request("POST", url, data, headers, timeout)
    if status == 204:
        return {}
    if status >= 400:
        raise Exception(T("err.http_post") % (status, url, repr(body[:1000])))
    return _parse_json_body(body, status, resp_headers, url)


def http_post_file(url, filepath, timeout=120, cancel_event=None):
    """Envia el archivo en tramos de 256 KB leyendolo del disco, para que
    se pueda cancelar a mitad de la transferencia (cerrando el socket el
    receptor descarta el archivo incompleto, y ademas se le manda /cancel)."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "http").lower()
    host = parsed.hostname
    if not host:
        raise ValueError("URL sin host: %s" % url)
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = path + "?" + parsed.query
    size = os.path.getsize(filepath)
    if scheme == "https":
        try:
            import ssl
            context = None
            if hasattr(ssl, "_create_unverified_context"):
                context = ssl._create_unverified_context()
            conn = httplib.HTTPSConnection(host, port, timeout=timeout, context=context)
        except Exception:
            conn = httplib.HTTPSConnection(host, port, timeout=timeout)
    else:
        conn = httplib.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.putrequest("POST", path)
        conn.putheader("Host", host)
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Accept", "application/json")
        conn.putheader("Content-Length", str(size))
        conn.endheaders()
        f = open(filepath, "rb")
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise TransferCancelled()
                chunk = f.read(262144)
                if not chunk:
                    break
                conn.send(chunk)
        finally:
            f.close()
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {}
        try:
            for k, v in resp.getheaders():
                resp_headers[k.lower()] = v
        except Exception:
            pass
        body = b""
        try:
            body = resp.read()
        except Exception:
            pass
        if status >= 400:
            raise Exception(T("err.http_upload") % (status, url, repr(body[:1000])))
        return body
    finally:
        try:
            conn.close()
        except Exception:
            pass


def post_cancel(state, ip, port, session_id, timeout=5):
    """Avisa al receptor de que la sesion se cancela (POST /cancel)."""
    if not session_id:
        return False
    url = "http://%s:%s%s/cancel" % (ip, port, API_BASE)
    try:
        http_post_json(url, {"sessionId": session_id}, timeout=timeout)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Descubrimiento multicast UDP
# ---------------------------------------------------------------------------
# NOTA macOS/BSD (Snow Leopard): enlazar el socket a la direccion multicast
# 224.0.0.167 o a 127.0.0.1 hace que sendto() falle con
# "[Errno 49] Can't assign requested address" (EADDRNOTAVAIL), aunque en
# Linux parezca funcionar. Hay que enlazar a INADDR_ANY / a la IP local
# real (p. ej. 192.168.1.x), fijar IP_MULTICAST_IF con esa IP y unirse
# al grupo con (multicast_ip, local_ip). Ver StackOverflow 19798254.

def get_local_ip():
    """IP local que usaria la ruta hacia el grupo multicast (sin enviar
    ningun paquete: un connect() UDP solo fija la ruta)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((MULTICAST_IP, PORT))
            ip = s.getsockname()[0]
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "0.0.0.0"


def _setup_multicast_socket(sock, local_ip):
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        reuseport = getattr(socket, "SO_REUSEPORT", None)
        if reuseport is not None:
            sock.setsockopt(socket.SOL_SOCKET, reuseport, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    except Exception:
        pass
    # Interfaz de salida multicast = IP local real (clave en macOS).
    try:
        mc_if = getattr(socket, "IP_MULTICAST_IF", None)
        if mc_if is not None and local_ip and local_ip != "0.0.0.0":
            sock.setsockopt(socket.IPPROTO_IP, mc_if, socket.inet_aton(local_ip))
    except Exception:
        pass
    try:
        iface = local_ip if (local_ip and local_ip != "0.0.0.0") else "0.0.0.0"
        mreq = struct.pack("4s4s", socket.inet_aton(MULTICAST_IP), socket.inet_aton(iface))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except Exception:
        pass


def _send_via_temp_socket(state, payload):
    """Envio de respaldo con un socket temporal enlazado a la IP local.
    En macOS el socket de recepcion a veces no puede enviar si quedo
    enlazado de otra forma; este camino suele funcionar."""
    local_ip = get_local_ip()
    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _setup_multicast_socket(tmp, local_ip)
        try:
            tmp.bind((local_ip, 0))
        except Exception:
            try:
                tmp.bind(("", 0))
            except Exception:
                pass
        tmp.sendto(payload, (MULTICAST_IP, PORT))
        return True
    except Exception as e:
        state.log(T("log.mc_error_fallback") % e)
        return False
    finally:
        try:
            tmp.close()
        except Exception:
            pass


def _send_announcement(state, sock):
    info = build_info(state)
    info["announce"] = True
    payload = to_bytes(json.dumps(info))
    # La implementacion oficial anuncia 3 veces; enviamos 3 paquetes.
    for _i in range(3):
        try:
            sock.sendto(payload, (MULTICAST_IP, PORT))
        except Exception as e:
            # Errno 49 en macOS si el socket no esta bien enlazado:
            # reintentar una vez con socket temporal y no spamear el log.
            if _send_via_temp_socket(state, payload):
                state.log(T("log.mc_sent_temp") % get_local_ip())
            else:
                state.log(T("log.mc_error") % e)
            return
        time.sleep(0.1)


def announce_once(state):
    sock = getattr(state, "discovery_sock", None)
    if sock is not None:
        _send_announcement(state, sock)
        return
    local_ip = get_local_ip()
    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _setup_multicast_socket(tmp, local_ip)
        try:
            tmp.bind((local_ip, 0))
        except Exception:
            try:
                tmp.bind(("", 0))
            except Exception:
                pass
        _send_announcement(state, tmp)
    finally:
        try:
            tmp.close()
        except Exception:
            pass


def register_callback(state, info, ip):
    """Cuando recibimos un anuncio con announce=true, respondemos con
    POST /api/localsend/v2/register al remitente (segun la especificacion).
    El iPhone puede anunciar protocol=https aunque el usuario haya
    desactivado el cifrado; si el handshake TLS falla con
    "unknown protocol" (el peer en realidad habla HTTP plano),
    reintentamos con http y actualizamos el protocolo del dispositivo."""
    try:
        port = int(info.get("port") or PORT)
    except Exception:
        port = PORT
    protocol = info.get("protocol") or "http"
    # Snow Leopard no puede hacer TLS moderno: probar http primero
    # siempre (el iPhone anuncia https aunque el cifrado este off).
    protocols_to_try = []
    for p in ("http", protocol, "https"):
        if p not in protocols_to_try:
            protocols_to_try.append(p)
    last_error = None
    for proto in protocols_to_try:
        url = "%s://%s:%s%s/register" % (proto, ip, port, API_BASE)
        try:
            resp = http_post_json(url, build_info(state), timeout=5)
            if isinstance(resp, dict) and resp.get("fingerprint") and resp.get("fingerprint") != state.fingerprint:
                state.add_device(resp, ip)
            elif isinstance(resp, dict):
                if proto != protocol:
                    info = dict(info)
                    info["protocol"] = proto
                state.add_device(info, ip)
            return
        except Exception as e:
            last_error = e
            continue
    state.log(T("log.register_failed") % (info.get("alias") or ip, ip, last_error))


def discovery_loop(state):
    local_ip = get_local_ip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _setup_multicast_socket(sock, local_ip)
    # En macOS/BSD NO hay que enlazar a 224.0.0.167 (Errno 49 al enviar).
    # Se enlaza a INADDR_ANY ("") para recibir el grupo y poder enviar
    # desde la IP local real; si eso fallara, se prueba la IP local.
    bound = False
    bind_error = None
    for bind_addr in ("", local_ip):
        if not bind_addr and local_ip == "0.0.0.0":
            pass
        try:
            sock.bind((bind_addr, PORT))
            bound = True
            break
        except Exception as e:
            bind_error = e
            continue
    if not bound:
        state.log(T("log.udp_bind_warn") % (PORT, bind_error))
        state.discovery_sock = sock
        try:
            _send_announcement(state, sock)
        except Exception:
            pass
        return
    state.discovery_sock = sock
    sock.settimeout(1.0)
    _send_announcement(state, sock)
    state.log(T("log.discovery_active") % (MULTICAST_IP, PORT, local_ip))
    last_announce = time.time()
    while not state.stop_event.is_set():
        # Re-anuncio periodico cada 15 segundos (mantiene visible el equipo).
        if time.time() - last_announce > 15:
            try:
                _send_announcement(state, sock)
            except Exception:
                pass
            last_announce = time.time()
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except Exception:
            continue
        ip = addr[0] if addr else "?"
        try:
            info = json.loads(to_text(data))
        except Exception:
            continue
        if not isinstance(info, dict):
            continue
        if info.get("fingerprint") == state.fingerprint:
            continue
        state.add_device(info, ip)
        if info.get("announce"):
            t = threading.Thread(target=register_callback, args=(state, info, ip))
            t.daemon = True
            t.start()
    try:
        sock.close()
    except Exception:
        pass


def scan_subnet(state):
    """Respaldo cuando el multicast esta bloqueado: pregunta GET /info a
    cada IP del /24 local. Util en redes con aislamiento multicast."""
    local_ip = get_local_ip()
    if not local_ip or local_ip == "0.0.0.0":
        state.log(T("log.no_local_ip"))
        return
    parts = local_ip.split(".")
    if len(parts) != 4:
        state.log(T("log.bad_local_ip") % local_ip)
        return
    prefix = ".".join(parts[:3]) + "."
    state.log(T("log.scanning") % (prefix, local_ip))
    work_q = queue_module.Queue()
    for i in range(1, 255):
        ip = "%s%d" % (prefix, i)
        if ip != local_ip:
            work_q.put(ip)

    def worker():
        while True:
            try:
                ip = work_q.get_nowait()
            except queue_module.Empty:
                return
            url = "http://%s:%d%s/info" % (ip, PORT, API_BASE)
            try:
                info = http_get_json(url, timeout=1)
                if isinstance(info, dict) and info.get("fingerprint") and info.get("fingerprint") != state.fingerprint:
                    state.add_device(info, ip)
                    state.log(T("log.scan_found") % (info.get("alias") or "?", ip))
            except Exception:
                pass

    threads = []
    for _i in range(20):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    state.log(T("log.scan_done"))


# ---------------------------------------------------------------------------
# Servidor HTTP (recepcion)
# ---------------------------------------------------------------------------

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class SnowSendHandler(BaseHTTPRequestHandler):
    server_version = "SnowSend/1.3"
    sys_version = ""
    # HTTP/1.1 es necesario para que BaseHTTPRequestHandler responda
    # "100 Continue" ante "Expect: 100-continue" (iOS/Dart lo envia en
    # subidas grandes). Con el valor por defecto HTTP/1.0 la condicion
    # protocol_version >= "HTTP/1.1" falla, no se llama a
    # handle_expect_100() y cliente/servidor quedan en deadlock hasta
    # timeout, con el cuerpo vacio y SHA-256 incorrecto.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        try:
            state = self.server.state
            state.log(T("log.http_access") % (self.client_address[0] if self.client_address else "?", fmt % args))
        except Exception:
            pass

    def handle_expect_100(self):
        # iOS/Dart y curl envian "Expect: 100-continue" en subidas.
        # Hay que responder 100 explicitamente o el cliente espera.
        try:
            self.send_response_only(100)
        except Exception:
            try:
                self.send_response(100)
            except Exception:
                pass
        try:
            self.end_headers()
        except Exception:
            pass
        return True

    def _is_chunked(self):
        te = self.headers.get("Transfer-Encoding") or ""
        return "chunked" in te.lower()

    def _read_chunk_size(self):
        line = self.rfile.readline(65536)
        if not line:
            return None
        line = line.strip()
        if line == b"":
            return self._read_chunk_size()
        size_str = line.split(b";")[0].strip()
        try:
            return int(size_str, 16)
        except Exception:
            return None

    def _read_chunked_bytes(self):
        chunks = []
        while True:
            size = self._read_chunk_size()
            if size is None:
                break
            if size == 0:
                # trailers hasta linea vacia
                while True:
                    trailer = self.rfile.readline(65536)
                    if not trailer or trailer.strip() == b"":
                        break
                break
            remaining = size
            data = b""
            while remaining > 0:
                piece = self.rfile.read(remaining)
                if not piece:
                    break
                data += piece
                remaining -= len(piece)
            chunks.append(data)
            self.rfile.read(2)  # CRLF tras cada chunk
        return b"".join(chunks)

    def _stream_body_to_file(self, out, hasher):
        """Escribe el cuerpo HTTP a `out` calculando SHA-256 al vuelo.
        Soporta Content-Length y Transfer-Encoding: chunked (iOS).
        Devuelve el numero total de bytes recibidos."""
        total = 0
        if self._is_chunked():
            while True:
                size = self._read_chunk_size()
                if size is None:
                    break
                if size == 0:
                    while True:
                        trailer = self.rfile.readline(65536)
                        if not trailer or trailer.strip() == b"":
                            break
                    break
                remaining = size
                while remaining > 0:
                    to_read = remaining if remaining < 8192 else 8192
                    piece = self.rfile.read(to_read)
                    if not piece:
                        break
                    out.write(piece)
                    hasher.update(piece)
                    total += len(piece)
                    remaining -= len(piece)
                self.rfile.read(2)  # CRLF tras cada chunk
            return total
        length_str = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_str)
        except Exception:
            length = 0
        remaining = length
        while remaining > 0:
            to_read = remaining if remaining < 8192 else 8192
            piece = self.rfile.read(to_read)
            if not piece:
                break
            out.write(piece)
            hasher.update(piece)
            total += len(piece)
            remaining -= len(piece)
        return total

    def _send_json(self, code, obj):
        body = to_bytes(json.dumps(obj))
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_body(self):
        # iOS LocalSend envia prepare-upload/upload con
        # Transfer-Encoding: chunked y SIN Content-Length. Si solo se
        # lee Content-Length, el cuerpo llega como 0 bytes, el JSON
        # falla / el archivo queda vacio y el SHA-256 no coincide (422).
        if self._is_chunked():
            return self._read_chunked_bytes()
        length_str = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_str)
        except Exception:
            length = 0
        if length <= 0:
            return b""
        # read(n) en el socket bufferizado puede devolver menos de n;
        # leer en bucle hasta completar.
        body = b""
        remaining = length
        while remaining > 0:
            piece = self.rfile.read(remaining)
            if not piece:
                break
            body += piece
            remaining -= len(piece)
        return body

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        state = self.server.state
        if path == API_BASE + "/info":
            self._send_json(200, build_info(state))
        elif path == "/" or path == API_BASE + "/ping":
            body = to_bytes("SnowSend - %s\n" % state.alias)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == API_BASE + "/download":
            # Transferencia inversa (download API) no implementada.
            self._send_empty(403)
        else:
            self._send_empty(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        state = self.server.state
        client_ip = self.client_address[0] if self.client_address else "?"

        if path == API_BASE + "/register":
            body = self._read_body()
            try:
                info = json.loads(to_text(body)) if body else {}
            except Exception:
                info = {}
            if isinstance(info, dict) and info.get("fingerprint") != state.fingerprint:
                state.add_device(info, client_ip)
            self._send_json(200, build_info(state))
            return

        if path == API_BASE + "/prepare-upload":
            body = self._read_body()
            try:
                payload = json.loads(to_text(body))
            except Exception as e:
                state.log(T("log.prepare_bad_json") % e)
                self._send_empty(400)
                return
            sender_info = payload.get("info") or {}
            if sender_info:
                state.add_device(sender_info, client_ip)
            files_raw = payload.get("files") or {}
            files_list = []
            if isinstance(files_raw, dict):
                for fid, fmeta in files_raw.items():
                    if isinstance(fmeta, dict):
                        if "id" not in fmeta:
                            fmeta["id"] = fid
                        files_list.append(fmeta)
                    else:
                        files_list.append({"id": fid, "fileName": str(fid)})
            elif isinstance(files_raw, list):
                files_list = files_raw
            else:
                files_list = []
            if not files_list:
                self._send_empty(204)
                return
            session_id = uuid.uuid4().hex
            tokens = {}
            session_files = {}
            for fmeta in files_list:
                fid = fmeta.get("id") or uuid.uuid4().hex
                token = uuid.uuid4().hex
                tokens[fid] = token
                session_files[fid] = {
                    "fileName": fmeta.get("fileName") or fid,
                    "size": fmeta.get("size") or 0,
                    "fileType": fmeta.get("fileType") or "application/octet-stream",
                    "sha256": fmeta.get("sha256"),
                    "token": token,
                }
            with state.sessions_lock:
                state.sessions[session_id] = {
                    "files": session_files,
                    "sender": sender_info,
                    "ip": client_ip,
                }
            state.log(T("log.incoming_request") % (
                sender_info.get("alias") or client_ip, len(files_list)))
            for fmeta in files_list:
                state.log(T("log.incoming_file") % (fmeta.get("fileName"), fmeta.get("size")))
            self._send_json(200, {"sessionId": session_id, "files": tokens})
            return

        if path == API_BASE + "/upload":
            qs = parse_qs(parsed.query)

            def qget(name):
                v = qs.get(name)
                if isinstance(v, list) and v:
                    return v[0]
                return v

            session_id = qget("sessionId")
            file_id = qget("fileId")
            token = qget("token")
            session = None
            with state.sessions_lock:
                if session_id:
                    session = state.sessions.get(session_id)
            if not session or file_id not in session.get("files", {}):
                state.log(T("log.upload_session_missing") % (session_id, file_id))
                self._send_empty(400)
                return
            fmeta = session["files"][file_id]
            if token and token != fmeta.get("token"):
                state.log(T("log.upload_bad_token") % fmeta.get("fileName"))
                self._send_empty(403)
                return
            state.log(T("log.upload_info") % (
                fmeta.get("fileName"),
                self.headers.get("Content-Length") or "-",
                self.headers.get("Transfer-Encoding") or "-"))
            try:
                if not os.path.isdir(state.download_dir):
                    os.makedirs(state.download_dir)
            except Exception as e:
                state.log(T("log.mkdir_fail") % e)
                self._send_empty(500)
                return
            safe_name = sanitize_filename(fmeta.get("fileName") or file_id)
            dest = unique_path(os.path.join(state.download_dir, safe_name))
            hasher = hashlib.sha256()
            out = None
            received = 0
            try:
                out = open(dest, "wb")
                received = self._stream_body_to_file(out, hasher)
            except Exception as e:
                state.log(T("log.save_error") % (safe_name, e))
                try:
                    if out is not None:
                        out.close()
                except Exception:
                    pass
                self._send_empty(500)
                return
            try:
                if out is not None:
                    out.close()
            except Exception:
                pass
            expected = fmeta.get("sha256")
            if expected:
                actual = hasher.hexdigest()
                if actual.lower() != str(expected).lower():
                    state.log(T("log.checksum_error") % (
                        safe_name, received, fmeta.get("size")))
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                    self._send_empty(422)
                    return
            state.log(T("log.file_received") % (safe_name, received, dest))
            self._send_empty(200)
            return

        if path == API_BASE + "/cancel":
            try:
                self._read_body()
            except Exception:
                pass
            qs = parse_qs(parsed.query)
            session_id = None
            if qs.get("sessionId"):
                session_id = qs.get("sessionId")[0]
            if session_id:
                with state.sessions_lock:
                    if session_id in state.sessions:
                        del state.sessions[session_id]
            state.log(T("log.session_cancelled"))
            self._send_empty(200)
            return

        try:
            self._read_body()
        except Exception:
            pass
        self._send_empty(404)


def start_http_server(state, port):
    server = ThreadedHTTPServer(("", port), SnowSendHandler)
    server.state = state
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    state.log(T("log.server_started") % port)
    return server


# ---------------------------------------------------------------------------
# Envio de archivos (cliente)
# ---------------------------------------------------------------------------

def sanitize_log(text, limit=200):
    """Evita volcar bytes binarios/control (p. ej. una alerta TLS del
    iPhone) al registro de la GUI."""
    try:
        text = to_text(text)
    except Exception:
        text = repr(text)
    out = []
    for ch in text:
        o = ord(ch)
        if o < 32 or o == 127:
            out.append("\\x%02x" % o)
        else:
            out.append(ch)
    s = "".join(out)
    if len(s) > limit:
        s = s[:limit] + "..."
    return s


def _encryption_hint(state, port):
    state.log(T("hint.no_plain_http") % port)
    state.log(T("hint.encryption_off"))
    state.log(T("hint.reannounce"))


def diagnose_peer(state, ip, port, alias):
    """Cuando el envio falla, sondea GET /info por HTTP plano para
    distinguir 'el receptor tiene Encryption activado (solo TLS)' de
    otros problemas. Un servidor TLS-only responde basura, vacio o
    cierra la conexion a una peticion HTTP plana."""
    url = "http://%s:%s%s/info" % (ip, port, API_BASE)
    try:
        info = http_get_json(url, timeout=8)
    except Exception as e:
        msg = sanitize_log(e, 160)
        state.log(T("diag.no_plain_http") % (alias, msg))
        low = msg.lower()
        binario = ("\\x" in msg) or ("ssl" in low and "wrong version" in low) or ("ssl" in low and "unknown protocol" in low)
        if (binario or "empty" in low or "no json" in low or "badstatusline" in low
                or "reset" in low or "no status" in low or "10054" in low
                or "timed out" in low):
            _encryption_hint(state, port)
        else:
            state.log(T("diag.accept_prompt"))
        return
    if isinstance(info, dict) and info.get("alias"):
        state.log(T("diag.ok_http") % (
            alias, info.get("alias"), info.get("protocol")))
        state.log(T("diag.restart_hint"))
    else:
        state.log(T("diag.unexpected") % (info,))
        _encryption_hint(state, port)


def send_files_to_device(state, device, filepaths, cancel_event=None):
    ip = device.get("ip")
    try:
        port = int(device.get("port") or PORT)
    except Exception:
        port = PORT
    announced_protocol = device.get("protocol") or "http"
    # Snow Leopard solo puede hablar HTTP plano: probar http primero
    # siempre, aunque el peer anuncie https (caso iPhone con cifrado off).
    protocol = "http"
    alias = device.get("alias") or ip
    state.log(T("send.preparing") % (
        alias, ip, port, len(filepaths)))
    files_dict = {}
    paths_by_id = {}
    for fp in filepaths:
        if not os.path.isfile(fp):
            state.log(T("send.skipped") % fp)
            continue
        fid = uuid.uuid4().hex
        size = os.path.getsize(fp)
        state.log(T("send.hashing") % (os.path.basename(fp), size))
        try:
            sha = sha256_of_file(fp)
        except Exception as e:
            state.log(T("send.hash_fail") % (fp, e))
            sha = None
        ftype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        files_dict[fid] = {
            "id": fid,
            "fileName": os.path.basename(fp),
            "size": size,
            "fileType": ftype,
            "sha256": sha,
        }
        paths_by_id[fid] = fp
    if not files_dict:
        state.log(T("send.no_files"))
        return
    if cancel_event is not None and cancel_event.is_set():
        state.log(T("send.cancelled"))
        return
    prepare_body = {"info": build_info(state), "files": files_dict}
    # 60 s de timeout: en el iPhone hay que tocar T("btn.ok") y eso
    # puede tardar mas que los 15 s anteriores.
    state.log(T("send.waiting_accept") % alias)
    resp = None
    protocols_to_try = []
    for p in ("http", announced_protocol, "https"):
        if p not in protocols_to_try:
            protocols_to_try.append(p)
    last_error = None
    first_error = None
    for proto in protocols_to_try:
        if cancel_event is not None and cancel_event.is_set():
            state.log(T("send.cancelled"))
            return
        protocol = proto
        prepare_url = "%s://%s:%s%s/prepare-upload" % (proto, ip, port, API_BASE)
        try:
            resp = http_post_json(prepare_url, prepare_body, timeout=60)
            break
        except Exception as e:
            last_error = e
            if first_error is None:
                first_error = e
            state.log(T("send.prepare_fail_proto") % (proto, sanitize_log(e, 200)))
            resp = None
            continue
    if resp is None:
        state.log(T("send.prepare_error") % sanitize_log(first_error, 200))
        diagnose_peer(state, ip, port, alias)
        return
    if not resp or "sessionId" not in resp:
        state.log(T("send.no_session") % (resp,))
        if not resp:
            state.log(T("send.empty_response"))
        diagnose_peer(state, ip, port, alias)
        return
    # Recordar el protocolo que funciono para la proxima vez
    try:
        fp_dev = device.get("fingerprint")
        if fp_dev:
            with state.devices_lock:
                if fp_dev in state.devices:
                    state.devices[fp_dev]["protocol"] = protocol
    except Exception:
        pass
    session_id = resp.get("sessionId")
    tokens_raw = resp.get("files") or {}
    tokens = {}
    if isinstance(tokens_raw, dict):
        tokens = tokens_raw
    elif isinstance(tokens_raw, list):
        for item in tokens_raw:
            if isinstance(item, dict):
                fid = item.get("id")
                tokens[fid] = item.get("token") or item.get("status") or "success"
            else:
                tokens[item] = "success"
    state.log(T("send.session_ok") % session_id)
    success_count = 0
    cancelled = False
    for fid, fp in paths_by_id.items():
        token = tokens.get(fid)
        if token is None:
            state.log(T("send.not_authorized") % os.path.basename(fp))
            continue
        if isinstance(token, dict):
            token = token.get("token") or token.get("status")
        if token == "rejected":
            state.log(T("send.rejected") % os.path.basename(fp))
            continue
        upload_url = "%s://%s:%s%s/upload?sessionId=%s&fileId=%s&token=%s" % (
            protocol, ip, port, API_BASE,
            url_quote(str(session_id)), url_quote(str(fid)), url_quote(str(token)))
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        state.log(T("send.sending") % os.path.basename(fp))
        try:
            http_post_file(upload_url, fp, timeout=120, cancel_event=cancel_event)
            state.log(T("send.file_ok") % os.path.basename(fp))
            success_count += 1
        except TransferCancelled:
            cancelled = True
            state.log(T("send.cancelled"))
            break
        except Exception as e:
            state.log(T("send.file_error") % (os.path.basename(fp), sanitize_log(e, 200)))
    if cancelled:
        if post_cancel(state, ip, port, session_id):
            state.log(T("send.cancel_sent"))
    else:
        state.log(T("send.finished") % (success_count, len(paths_by_id), alias))


# ---------------------------------------------------------------------------
# Interfaz grafica (todo dentro de la ventana, sin barra de menus)
# ---------------------------------------------------------------------------
# Nota 10.6: la barra de menus global de Tk 8.5 en Aqua se corrompe al
# reetiquetar entradas (entryconfigure con indices desplazados por el menu de
# aplicacion), lo que producia menus duplicados y entradas basura. Por eso
# TODOS los controles viven en la ventana y el idioma se cambia con botones
# de radio que llaman directamente a change_language().

try:
    import ttk as _ttk_module
    HAS_TTK = True
except ImportError:
    try:
        from tkinter import ttk as _ttk_module
        HAS_TTK = True
    except ImportError:
        _ttk_module = None
        HAS_TTK = False

ttk = _ttk_module


if HAS_TKINTER:
    class SnowSendGUI(object):
        """Ventana principal estilo Mac OS X: identificacion del equipo,
        tabla de dispositivos, registro de actividad, selector de idioma y
        barra de estado. Todo en la ventana, sin menus."""

        def __init__(self, state):
            self.state = state
            self.root = tk.Tk()
            self.root.title(T("app.title"))
            # Tamano provisional; fit_to_screen() lo ajusta a la pantalla real.
            # Un MacBook Air de 11" tiene 1366x768 y con 740 px de alto el pie
            # (idioma y estado) quedaba fuera de la pantalla.
            self.root.geometry("780x620")
            try:
                self.root.minsize(560, 420)
            except Exception:
                pass
            self.device_order = []
            self.queue_files = []          # archivos listos para enviar
            self.cancel_event = None       # threading.Event del envio en curso
            self.send_thread = None
            self.last_dir = os.path.expanduser("~")
            self._static_labels = []       # (widget, clave) -> textos traducibles
            self._column_keys = []         # (columna, clave)
            self.lang_buttons = {}         # codigo -> boton de idioma
            self._lang_var = tk.StringVar()
            self._lang_var.set(current_language())
            self._status_var = tk.StringVar()
            self._server_var = tk.StringVar()
            self._footer_var = tk.StringVar()
            self._version_var = tk.StringVar()
            self._version_var.set("%s %s" % (T("app.subtitle"), VERSION))
            self.build_style()
            self.build_widgets()
            self.retranslate()
            self.update_status()
            self.fit_to_screen()
            try:
                self.root.protocol("WM_DELETE_WINDOW", self.on_quit)
            except Exception:
                pass
            self.poll_queues()

        # ------------------------------------------------------------ estilo
        def build_style(self):
            self.use_ttk = HAS_TTK
            self.style = None
            if not self.use_ttk:
                return
            try:
                self.style = ttk.Style()
                themes = []
                try:
                    themes = self.style.theme_names()
                except Exception:
                    themes = []
                if "aqua" in themes:
                    try:
                        self.style.theme_use("aqua")
                    except Exception:
                        pass
            except Exception:
                self.use_ttk = False
                self.style = None

        def _font(self, name, fallback):
            try:
                import tkFont as tkfont
            except ImportError:
                try:
                    from tkinter import font as tkfont
                except ImportError:
                    return fallback
            try:
                return tkfont.nametofont(name)
            except Exception:
                return fallback

        # ------------------------------------------------------------ widgets
        def build_widgets(self):
            root = self.root
            if self.use_ttk:
                container = ttk.Frame(root, padding=(12, 10, 12, 8))
            else:
                container = tk.Frame(root, padx=12, pady=10)
            container.pack(fill=tk.BOTH, expand=tk.YES)
            self.container = container

            # ---- pie: idioma + estado (se empaqueta con side=BOTTOM) ------
            # Al empaquetarse ANTES que el resto y desde abajo, Tk reserva su
            # espacio: si la ventana es baja, se encoge el registro, nunca el pie.
            footer = self._frame(container)
            footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
            self.footer_frame = footer
            self.status_label = self._label(footer, None, gray=True, size=10,
                                            textvariable=self._status_var)
            self.status_label.pack(side=tk.LEFT)
            self.footer_label = self._label(footer, None, gray=True, size=10,
                                            textvariable=self._footer_var)
            self.footer_label.pack(side=tk.RIGHT)
            self._footer_wrap = 420
            try:
                self.footer_label.config(wraplength=420, justify=tk.RIGHT)
            except Exception:
                pass

            lang_sep = self._separator(container)
            lang_sep.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 6))
            self.lang_sep = lang_sep

            lang_row = self._frame(container)
            lang_row.pack(side=tk.BOTTOM, fill=tk.X)
            self.lang_row = lang_row
            self.lang_label = self._label(lang_row, "prefs.language")
            self.lang_label.pack(side=tk.LEFT, padx=(0, 8))
            for code, name in available_languages():
                button = tk.Radiobutton(lang_row, text=name, value=code,
                                        variable=self._lang_var, indicatoron=0,
                                        command=lambda c=code: self.change_language(c),
                                        padx=6, pady=1, takefocus=0)
                try:
                    button.config(font=self._font("TkSmallSystemFont", ("Helvetica", 11)))
                except Exception:
                    pass
                button.pack(side=tk.LEFT, padx=2)
                self.lang_buttons[code] = button


            # ---- cabecera ------------------------------------------------
            header = self._frame(container)
            header.pack(fill=tk.X)
            title = self._label(header, "app.title", bold=True, size=16)
            title.pack(side=tk.LEFT)
            self.title_label = title
            version = self._label(header, None, gray=True, size=10,
                                  textvariable=self._version_var)
            version.pack(side=tk.LEFT, padx=(8, 0), pady=(4, 0))
            self.server_label = self._label(header, None, gray=True, size=10,
                                            textvariable=self._server_var)
            self.server_label.pack(side=tk.RIGHT)

            self._separator(container).pack(fill=tk.X, pady=(8, 10))

            # ---- identidad del equipo ------------------------------------
            ident = self._frame(container)
            ident.pack(fill=tk.X)

            row1 = self._frame(ident)
            row1.pack(fill=tk.X)
            self._label(row1, "label.alias").pack(side=tk.LEFT)
            self.alias_var = tk.StringVar()
            self.alias_var.set(self.state.alias)
            self.alias_entry = self._entry(row1, textvariable=self.alias_var, width=26)
            self.alias_entry.pack(side=tk.LEFT, padx=(6, 6))
            self.apply_btn = self._button(row1, "btn.apply", self.apply_alias)
            self.apply_btn.pack(side=tk.LEFT)
            try:
                self.alias_entry.bind("<Return>", lambda e: self.apply_alias())
            except Exception:
                pass

            row2 = self._frame(ident)
            row2.pack(fill=tk.X, pady=(8, 0))
            self._label(row2, "label.download_dir").pack(side=tk.LEFT)
            self.download_var = tk.StringVar()
            self.download_var.set(self.state.download_dir)
            self.download_label = self._label(row2, None, gray=True,
                                              textvariable=self.download_var)
            self.download_label.pack(side=tk.LEFT, padx=(6, 6))
            self.change_btn = self._button(row2, "btn.change", self.on_change_download)
            self.change_btn.pack(side=tk.RIGHT)

            # ---- dispositivos --------------------------------------------
            self._separator(container).pack(fill=tk.X, pady=(12, 8))
            dev_header = self._frame(container)
            dev_header.pack(fill=tk.X)
            self.devices_label = self._label(dev_header, "label.devices", bold=True)
            self.devices_label.pack(side=tk.LEFT)

            table = self._frame(container)
            table.pack(fill=tk.BOTH, expand=tk.NO, pady=(6, 0))

            if self.use_ttk:
                self.device_tree = ttk.Treeview(table, columns=("name", "model", "address"),
                                                show="headings", height=5, selectmode="browse")
                self.device_tree.column("name", width=230, anchor=tk.W)
                self.device_tree.column("model", width=190, anchor=tk.W)
                self.device_tree.column("address", width=230, anchor=tk.W)
                self._column_keys = [("name", "col.name"), ("model", "col.model"),
                                     ("address", "col.address")]
                yscroll = self._scrollbar(table, command=self.device_tree.yview)
                self.device_tree.config(yscrollcommand=yscroll.set)
                self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
                yscroll.pack(side=tk.RIGHT, fill=tk.Y)
                try:
                    self.device_tree.bind("<Double-1>", lambda e: self.on_send())
                except Exception:
                    pass
                self.listbox = None
            else:
                self.listbox = tk.Listbox(table, height=5, selectmode=tk.BROWSE)
                yscroll = self._scrollbar(table, command=self.listbox.yview)
                self.listbox.config(yscrollcommand=yscroll.set)
                self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
                yscroll.pack(side=tk.RIGHT, fill=tk.Y)
                try:
                    self.listbox.bind("<Double-1>", lambda e: self.on_send())
                except Exception:
                    pass
                self.device_tree = None

            # ---- acciones -------------------------------------------------
            actions = self._frame(container)
            actions.pack(fill=tk.X, pady=(10, 4))
            self.announce_btn = self._button(actions, "btn.announce", self.on_announce)
            self.announce_btn.pack(side=tk.LEFT)
            self.scan_btn = self._button(actions, "btn.scan", self.on_scan)
            self.scan_btn.pack(side=tk.LEFT, padx=(6, 0))
            self.clear_btn = self._button(actions, "btn.clear_log", self.on_clear_log)
            self.clear_btn.pack(side=tk.RIGHT)

            # ---- cola de archivos para enviar -----------------------------
            self._separator(container).pack(fill=tk.X, pady=(8, 8))
            queue_header = self._frame(container)
            queue_header.pack(fill=tk.X)
            self.queue_label = self._label(queue_header, "label.queue", bold=True)
            self.queue_label.pack(side=tk.LEFT)
            self.queue_count_var = tk.StringVar()
            self.queue_count_var.set("0")
            self.queue_count_label = self._label(queue_header, None, gray=True, size=10,
                                                 textvariable=self.queue_count_var)
            self.queue_count_label.pack(side=tk.LEFT, padx=(8, 0))

            queue_frame = self._frame(container)
            queue_frame.pack(fill=tk.X, pady=(6, 0))
            self.queue_listbox = tk.Listbox(queue_frame, height=4, selectmode=tk.EXTENDED,
                                            relief=tk.SOLID, borderwidth=1)
            try:
                self.queue_listbox.config(font=self._font("TkSmallSystemFont", ("Helvetica", 11)))
            except Exception:
                pass
            queue_scroll = self._scrollbar(queue_frame, command=self.queue_listbox.yview)
            self.queue_listbox.config(yscrollcommand=queue_scroll.set)
            self.queue_listbox.pack(side=tk.LEFT, fill=tk.X, expand=tk.YES)
            queue_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            queue_buttons = self._frame(container)
            queue_buttons.pack(fill=tk.X, pady=(6, 2))
            self.add_file_btn = self._button(queue_buttons, "btn.add_file", self.on_add_files)
            self.add_file_btn.pack(side=tk.LEFT)
            self.paste_btn = self._button(queue_buttons, "btn.paste", self.on_paste_clipboard)
            self.paste_btn.pack(side=tk.LEFT, padx=(6, 0))
            self.remove_btn = self._button(queue_buttons, "btn.remove", self.on_remove_selected)
            self.remove_btn.pack(side=tk.LEFT, padx=(6, 0))
            self.clear_queue_btn = self._button(queue_buttons, "btn.clear_queue", self.on_clear_queue)
            self.clear_queue_btn.pack(side=tk.LEFT, padx=(6, 0))
            self.cancel_btn = self._button(queue_buttons, "btn.cancel_transfer", self.on_cancel_transfer)
            self.cancel_btn.pack(side=tk.RIGHT)
            self.send_queue_btn = self._button(queue_buttons, "btn.send", self.on_send, primary=True)
            self.send_queue_btn.pack(side=tk.RIGHT, padx=(0, 6))

            # ---- registro -------------------------------------------------
            self._separator(container).pack(fill=tk.X, pady=(8, 8))
            log_header = self._frame(container)
            log_header.pack(fill=tk.X)
            self.log_label = self._label(log_header, "label.log", bold=True)
            self.log_label.pack(side=tk.LEFT)

            log_frame = self._frame(container)
            log_frame.pack(fill=tk.BOTH, expand=tk.YES, pady=(6, 0))
            self.log_text = tk.Text(log_frame, height=5, wrap=tk.WORD, relief=tk.SOLID,
                                    borderwidth=1, padx=6, pady=4)
            try:
                self.log_text.config(font=self._font("TkFixedFont", ("Menlo", 11)))
            except Exception:
                pass
            log_scroll = self._scrollbar(log_frame, command=self.log_text.yview)
            self.log_text.config(yscrollcommand=log_scroll.set)
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
            log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self.log_text.config(state="disabled")
            try:
                self.log_text.tag_config("error", foreground="#b00020")
                self.log_text.tag_config("hint", foreground="#8a5a00")
            except Exception:
                pass

        # ---- ajuste a la pantalla real -----------------------------------
        def fit_to_screen(self):
            """Ajusta la ventana a la pantalla (11" = 1366x768).

            Si no cabe, primero encoge el registro de actividad, luego la tabla
            de dispositivos y luego la cola; el pie con los idiomas y el estado
            ya esta empaquetado abajo y siempre se ve.
            """
            root = self.root
            try:
                root.update_idletasks()
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
            except Exception:
                return
            avail_w = max(520, sw - 40)
            avail_h = max(400, sh - 110)   # barra de menus + barra de titulo

            mins = [(self.log_text, "height", 3),
                    (self.device_tree, "height", 3),
                    (self.listbox, "height", 3),
                    (self.queue_listbox, "height", 3)]
            for _ in range(40):
                try:
                    root.update_idletasks()
                    req_h = root.winfo_reqheight()
                except Exception:
                    break
                if req_h <= avail_h:
                    break
                shrunk = False
                for widget, option, floor in mins:
                    if widget is None:
                        continue
                    try:
                        current = int(widget.cget(option))
                        if current > floor:
                            widget.config(**{option: current - 1})
                            shrunk = True
                            break
                    except Exception:
                        continue
                if not shrunk:
                    break

            try:
                root.update_idletasks()
                req_w = root.winfo_reqwidth()
                req_h = root.winfo_reqheight()
            except Exception:
                return
            # ancho minimo comodo: los botones de la cola y los 5 idiomas
            # necesitan sitio, pero nunca mas de lo que hay en pantalla
            wanted_w = max(min(700, avail_w), req_w + 8)
            w = max(520, min(wanted_w, avail_w))
            h = max(400, min(req_h + 8, avail_h))
            # centrada horizontalmente, pegada arriba (como las apps nativas)
            x = max(0, (sw - w) // 2)
            y = max(22, (sh - h) // 3)
            try:
                root.geometry("%dx%d+%d+%d" % (w, h, x, y))
                root.minsize(min(560, w), min(420, h))
            except Exception:
                pass
            # el aviso del pie se reparte con el estado en la misma linea
            try:
                self.footer_label.config(wraplength=max(220, w - 300))
            except Exception:
                pass
            self._avail_h = avail_h
            self.state.log(T("gui.fitted", w, h))

        # ---- constructores de widgets con o sin ttk ----------------------
        def _frame(self, parent, **kw):
            if self.use_ttk:
                return ttk.Frame(parent)
            return tk.Frame(parent, **kw)

        def _separator(self, parent):
            if self.use_ttk:
                return ttk.Separator(parent, orient=tk.HORIZONTAL)
            return tk.Frame(parent, height=1, bd=1, relief=tk.SUNKEN)

        def _scrollbar(self, parent, **kw):
            if self.use_ttk:
                return ttk.Scrollbar(parent, orient=tk.VERTICAL, **kw)
            return tk.Scrollbar(parent, **kw)

        def _label(self, parent, key, bold=False, gray=False, size=None, **kw):
            font = None
            try:
                base = self._font("TkSmallSystemFont" if (size and size <= 10) else "TkDefaultFont",
                                  ("Helvetica", size or 12))
                if hasattr(base, "copy"):
                    font = base.copy()
                    if bold:
                        font.configure(weight="bold")
                    if size:
                        font.configure(size=size)
                elif bold:
                    font = ("Helvetica", size or 12, "bold")
            except Exception:
                font = ("Helvetica", size or 12, "bold") if bold else None
            args = dict(kw)
            if font is not None:
                args["font"] = font
            if gray:
                args["foreground"] = "#6b6b6b"
            if self.use_ttk:
                widget = ttk.Label(parent)
            else:
                widget = tk.Label(parent)
            if args:
                try:
                    widget.config(**args)
                except Exception:
                    pass
            if key:
                try:
                    widget.config(text=T(key))
                except Exception:
                    pass
                self._static_labels.append((widget, key))
            return widget

        def _entry(self, parent, **kw):
            if self.use_ttk:
                return ttk.Entry(parent, **kw)
            return tk.Entry(parent, **kw)

        def _button(self, parent, key, command, primary=False):
            if self.use_ttk:
                widget = ttk.Button(parent, text=T(key), command=command)
                if primary:
                    try:
                        widget.config(default="active")
                    except Exception:
                        pass
            else:
                widget = tk.Button(parent, text=T(key), command=command)
            self._static_labels.append((widget, key))
            return widget

        # ------------------------------------------------------------ idioma
        def change_language(self, code):
            """Aplica el idioma al instante: textos de la ventana, columnas,
            barra de estado, pie y mensajes nuevos del registro."""
            applied = set_language(code)
            try:
                self._lang_var.set(applied)
            except Exception:
                pass
            self.retranslate()
            self.refresh_device_list()
            self.update_status()
            self.state.log(T("gui.language_changed", language_name(applied)))
            try:
                self.fit_to_screen()
            except Exception:
                pass
            save_config(alias=self.state.alias, lang=applied,
                        download_dir=self.state.download_dir)
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            return applied

        def retranslate(self):
            """Reetiqueta todos los textos traducibles que ya existen."""
            try:
                self.root.title(T("app.title"))
            except Exception:
                pass
            for widget, key in self._static_labels:
                try:
                    widget.config(text=T(key))
                except Exception:
                    pass
            if self.device_tree is not None:
                for column, key in self._column_keys:
                    try:
                        self.device_tree.heading(column, text=T(key))
                    except Exception:
                        pass
            try:
                self._server_var.set(T("status.server", str(self.state.port)))
                self._footer_var.set(T("footer.hint", str(self.state.port)))
                self._version_var.set("%s %s" % (T("app.subtitle"), VERSION))
            except Exception:
                pass

        # ------------------------------------------------------------ estado
        def update_status(self):
            try:
                with self.state.devices_lock:
                    count = len(self.state.devices)
            except Exception:
                count = len(self.device_order)
            try:
                self._status_var.set("%s  |  %s  |  %s" % (
                    T("status.ready"), T("status.devices", str(count)),
                    T("status.language", language_name())))
            except Exception:
                pass

        # ------------------------------------------------------------ acciones
        def apply_alias(self):
            new_alias = self.alias_var.get().strip()
            if not new_alias:
                return
            self.state.alias = new_alias
            save_config(alias=new_alias, lang=current_language(),
                        download_dir=self.state.download_dir)
            self.state.log(T("gui.alias_changed", new_alias))
            self.on_announce()

        def on_announce(self):
            self.state.log(T("gui.announcing", MULTICAST_IP, str(PORT)))
            t = threading.Thread(target=announce_once, args=(self.state,))
            t.daemon = True
            t.start()

        def on_scan(self):
            t = threading.Thread(target=scan_subnet, args=(self.state,))
            t.daemon = True
            t.start()

        def on_clear_log(self):
            try:
                self.log_text.config(state="normal")
                self.log_text.delete("1.0", tk.END)
                self.log_text.config(state="disabled")
            except Exception:
                pass

        def on_change_download(self):
            folder = filedialog.askdirectory(title=T("dialog.change_folder"))
            if not folder:
                return
            self.state.download_dir = folder
            self.download_var.set(folder)
            save_config(alias=self.state.alias, lang=current_language(),
                        download_dir=folder)
            self.state.log(T("gui.download_dir", folder))

        def on_quit(self):
            try:
                self.state.stop_event.set()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass

        def selected_fingerprint(self):
            if self.device_tree is not None:
                try:
                    selection = self.device_tree.selection()
                except Exception:
                    selection = ()
                if not selection:
                    return None
                fp = selection[0]
                return fp if fp in self.state.devices else None
            try:
                sel = self.listbox.curselection()
            except Exception:
                sel = ()
            if not sel:
                return None
            idx = int(sel[0])
            if idx < 0 or idx >= len(self.device_order):
                return None
            return self.device_order[idx]

        # ------------------------------------------------ cola de archivos
        def normalize_paths(self, paths):
            """askopenfilenames devuelve tupla, pero en algunas versiones de Tk
            devuelve una sola cadena con los nombres separados por espacios."""
            if not paths:
                return []
            if isinstance(paths, (str, unicode)):
                try:
                    paths = self.root.tk.splitlist(paths)
                except Exception:
                    paths = [paths]
            result = []
            for item in paths:
                item = to_text(item)
                if item and item not in result:
                    result.append(item)
            return result

        def add_files(self, paths):
            added = 0
            for path in self.normalize_paths(paths):
                if not os.path.isfile(path):
                    continue
                if path not in self.queue_files:
                    self.queue_files.append(path)
                    added += 1
            self.refresh_queue()
            if added:
                self.state.log(T("gui.files_added", str(added), str(len(self.queue_files))))
            return added

        def refresh_queue(self):
            try:
                self.queue_listbox.delete(0, tk.END)
                for path in self.queue_files:
                    try:
                        size = os.path.getsize(path)
                    except Exception:
                        size = 0
                    self.queue_listbox.insert(tk.END, "%s  (%s kB)" % (
                        os.path.basename(path), str(max(1, int(size / 1024)))))
            except Exception:
                pass
            try:
                self.queue_count_var.set(str(len(self.queue_files)))
            except Exception:
                pass

        def on_add_files(self):
            paths = filedialog.askopenfilenames(
                title=T("dialog.pick_files"),
                initialdir=self.last_dir)
            paths = self.normalize_paths(paths)
            if not paths:
                return
            try:
                self.last_dir = os.path.dirname(paths[0]) or self.last_dir
            except Exception:
                pass
            self.add_files(paths)

        def on_paste_clipboard(self):
            text = None
            try:
                text = self.root.clipboard_get()
            except Exception:
                text = None
            if text is None or not to_text(text).strip():
                messagebox.showwarning("SnowSend", T("warn.clipboard_empty"))
                return
            name = "clipboard-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(tempfile.gettempdir(), name)
            data = to_bytes(to_text(text))
            try:
                f = open(path, "wb")
                try:
                    f.write(data)
                finally:
                    f.close()
            except Exception as e:
                self.state.log(T("log.save_error") % (name, e))
                return
            self.add_files([path])
            self.state.log(T("gui.clipboard_added", name, str(len(data))))

        def on_remove_selected(self):
            try:
                selection = list(self.queue_listbox.curselection())
            except Exception:
                selection = []
            if not selection:
                return
            removed = []
            for index in sorted([int(i) for i in selection], reverse=True):
                if 0 <= index < len(self.queue_files):
                    removed.append(self.queue_files.pop(index))
            self.refresh_queue()
            for path in removed:
                self.state.log(T("gui.file_removed") % os.path.basename(path))

        def on_clear_queue(self):
            self.queue_files = []
            self.refresh_queue()
            self.state.log(T("gui.queue_cleared"))

        def on_cancel_transfer(self):
            if self.cancel_event is not None:
                self.cancel_event.set()
            elif self.send_thread is not None and self.send_thread.is_alive():
                pass

        def transfer_running(self):
            return self.send_thread is not None and self.send_thread.is_alive()

        def on_send(self):
            fp = self.selected_fingerprint()
            if not fp:
                messagebox.showwarning("SnowSend", T("warn.no_device"))
                return
            if not self.queue_files:
                messagebox.showwarning("SnowSend", T("warn.no_files"))
                return
            if self.transfer_running():
                messagebox.showwarning("SnowSend", T("warn.transfer_running"))
                return
            device_copy = None
            with self.state.devices_lock:
                dev = self.state.devices.get(fp)
                if dev:
                    device_copy = dict(dev)
            if not device_copy:
                return
            filepaths = list(self.queue_files)
            self.state.log(T("gui.send_started", device_copy.get("alias"),
                             str(len(filepaths))))
            self.cancel_event = threading.Event()
            self.send_thread = threading.Thread(
                target=send_files_to_device,
                args=(self.state, device_copy, filepaths, self.cancel_event))
            self.send_thread.daemon = True
            self.send_thread.start()

        # ------------------------------------------------------------ listas
        def device_type_text(self, device):
            model = device.get("deviceModel") or ""
            dtype = (device.get("deviceType") or "").lower()
            if model:
                return model
            if dtype in ("desktop", "mobile", "web", "headless", "server"):
                return T("type." + dtype)
            return ""

        def refresh_device_list(self):
            with self.state.devices_lock:
                devices = list(self.state.devices.values())
            devices.sort(key=lambda d: (d.get("alias") or "").lower())
            self.device_order = [d.get("fingerprint") for d in devices]
            if self.device_tree is not None:
                try:
                    current = ""
                    selection = self.device_tree.selection()
                    if selection:
                        current = selection[0]
                    for item in self.device_tree.get_children():
                        self.device_tree.delete(item)
                    for device in devices:
                        self.device_tree.insert(
                            "", tk.END, iid=device.get("fingerprint"),
                            values=(device.get("alias") or "",
                                    self.device_type_text(device),
                                    "%s://%s:%s" % (device.get("protocol"),
                                                    device.get("ip"),
                                                    device.get("port"))))
                    if current and current in self.state.devices:
                        try:
                            self.device_tree.selection_set(current)
                        except Exception:
                            pass
                except Exception:
                    pass
            else:
                self.listbox.delete(0, tk.END)
                for device in devices:
                    self.listbox.insert(tk.END, "%s  -  %s  (%s://%s:%s)" % (
                        device.get("alias") or "",
                        self.device_type_text(device),
                        device.get("protocol"), device.get("ip"), device.get("port")))
            if len(devices) != self.state._last_device_count:
                self.state._last_device_count = len(devices)
                if devices:
                    self.state.log(T("gui.device_count", str(len(devices))))
            self.update_status()

        def append_log_line(self, line):
            tag = None
            upper = line.upper()
            if ">>>" in line:
                tag = "hint"
            elif "ERROR" in upper or "FEHLER" in upper or "ERREUR" in upper or "ERRO" in upper:
                tag = "error"
            try:
                self.log_text.config(state="normal")
                if tag:
                    self.log_text.insert(tk.END, line + "\n", tag)
                else:
                    self.log_text.insert(tk.END, line + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
            except Exception:
                pass

        def poll_queues(self):
            try:
                while True:
                    line = self.state.log_queue.get_nowait()
                    self.append_log_line(line)
            except queue_module.Empty:
                pass
            need_refresh = False
            try:
                while True:
                    self.state.device_queue.get_nowait()
                    need_refresh = True
            except queue_module.Empty:
                pass
            if need_refresh:
                self.refresh_device_list()
            try:
                self.root.after(400, self.poll_queues)
            except Exception:
                pass

else:
    SnowSendGUI = None


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def run_headless(state, port):
    state.port = port
    server = start_http_server(state, port)
    t = threading.Thread(target=discovery_loop, args=(state,))
    t.daemon = True
    t.start()
    state.log(T("headless.active") % state.alias)
    state.log(T("gui.download_dir") % state.download_dir)
    state.log(T("headless.quit_hint"))
    try:
        while not state.stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        state.log(T("headless.interrupted"))
    finally:
        state.stop_event.set()
        try:
            server.shutdown()
        except Exception:
            pass


def print_usage():
    print("Usage: python snowsend.py [--headless] [--alias NAME] [--port 53317] "
          "[--download-dir PATH] [--lang en|es|fr|de|pt]")


def main():
    config = load_config()
    alias = config.get("alias") or default_alias()
    download_dir = config.get("download_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
    port = PORT
    headless = False
    lang = config.get("lang") or detect_language()
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--headless" or a == "--no-gui":
            headless = True
        elif a == "--alias" and i + 1 < len(args):
            alias = args[i + 1]
            i += 1
        elif a == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except Exception:
                pass
            i += 1
        elif a == "--download-dir" and i + 1 < len(args):
            download_dir = os.path.expanduser(args[i + 1])
            i += 1
        elif a == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
            i += 1
        elif a == "--help" or a == "-h":
            print_usage()
            return
        i += 1

    set_language(lang)
    state = AppState(alias, download_dir)
    state.lang = current_language()

    if headless or not HAS_TKINTER:
        if not HAS_TKINTER and not headless:
            print(T("app.tk_missing"))
        run_headless(state, port)
        return

    state.port = port
    gui = SnowSendGUI(state)
    server = start_http_server(state, port)
    t = threading.Thread(target=discovery_loop, args=(state,))
    t.daemon = True
    t.start()
    state.log(T("app.started") % alias)
    state.log(T("app.discovery") % (MULTICAST_IP, str(PORT)))
    state.log(T("gui.download_dir") % download_dir)
    state.log(T("app.plain_http_hint") % port)

    def on_close():
        state.stop_event.set()
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            gui.root.destroy()
        except Exception:
            pass

    try:
        gui.root.protocol("WM_DELETE_WINDOW", on_close)
    except Exception:
        pass
    gui.root.mainloop()


if __name__ == "__main__":
    main()
