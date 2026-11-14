# TigerSend — LocalSend for Mac OS X 10.4 Tiger → 10.6 Snow Leopard

A **LocalSend protocol v2** client written in legacy Python (2.3/2.4 on Tiger,
2.6/2.7 on Snow Leopard) using only the system standard library, packaged as a
native, double-clickable **`TigerSend.app`**.

**IMPORTANT NOTE: This project used AI assisted coding as I personally
couldn't manage to get the protocol working, however keep in mind I reviewed
and tested it severely on my computers, as always I strongly suggest you only
use this for personal usage in a secure network, if you have any improvements
or suggestions I'll gladly review them, if you have any issues with AI
projects I suggest you check another thing, however if you just care for
something that just works, check it out**

**TigerSend** is an independent project: it implements the LocalSend protocol
from scratch so a Mac running Tiger, Leopard or Snow Leopard can exchange
files with modern phones and computers that run the official app. It is not
affiliated with, sponsored by or endorsed by the LocalSend project.

```
┌──────────────────────────────┐      plain HTTP :53317       ┌──────────────────────────────┐
│  Mac OS X 10.4 – 10.6        │  ◄────────────────────────►  │  Phone / modern computer     │
│  TigerSend.app               │  multicast UDP 224.0.0.167   │  Official LocalSend app      │
│  /usr/bin/python (2.3 – 2.7) │  discovery + file transfer   │  Encryption: OFF             │
│  Tkinter + BaseHTTPServer    │                              │  (see §3, required)          │
└──────────────────────────────┘                              └──────────────────────────────┘
```

> **Why plain HTTP:** Tiger and Snow Leopard cannot reliably negotiate modern
> TLS 1.2/1.3, nor the self-signed certificate with *fingerprint pinning*
> that LocalSend uses by default (HTTPS). TigerSend therefore speaks
> **unencrypted HTTP on port 53317**. Use it only on your own trusted local
> network.

**Version:** 1.7 (`2.0.7-10.4`) · **License:** MIT (see §11) ·
**Status:** personal project, built with AI assistance (§10) ·
**Languages:** English, Español, Français, Deutsch, Português (§5)

---

## 1. What's in this project

| File | Purpose |
|---|---|
| `tigersend.py` | Complete source (Tkinter GUI + HTTP server + multicast discovery + send client + 5-language UI). Runs on Python 2.3 through 2.7. |
| `build_app.sh` | Builds `TigerSend.app` (Info.plist, launcher, PkgInfo, bundled license). |
| `LICENSE` | MIT license. Also copied inside the bundle as `Contents/Resources/LICENSE.txt`. |

The package layout is the classic Mac OS X one:

```
TigerSend.app/
└── Contents/
    ├── Info.plist          CFBundleExecutable=launcher, LSMinimumSystemVersion=10.4
    ├── PkgInfo             APPLTgSd
    ├── MacOS/
    │   └── launcher        executable /bin/sh script (chmod +x)
    └── Resources/
        ├── tigersend.py
        └── LICENSE.txt     MIT license
```

The `launcher` resolves its own path with `dirname "$0"`, redirects
`stdout`/`stderr` to `~/Library/Logs/TigerSend.log` (so double-clicking does
**not** open a Terminal window) and runs:

```sh
exec pythonw "$RESOURCES_DIR/tigersend.py"
```

It walks a candidate list (`/usr/bin/pythonw`, versioned `pythonw2.x`
binaries, plain `python`) so the same bundle starts on every release from
Tiger to Snow Leopard and later.

No external dependencies: no `pip`, no `requests`, no `flask`, no
`PyInstaller`, no `py2app`. Only `Tkinter`, `socket`, `threading`,
`BaseHTTPServer`, `httplib`, `mimetypes`, `os` and `sys` — all of which ship
with every Mac OS X release since Tiger. Because Python 2.3/2.4 has **no
`json`, no `hashlib`, no `uuid` and no `ttk`**, TigerSend bundles its own
mini JSON encoder/parser, falls back from `hashlib` to the old `md5` module,
generates identifiers with `random`, and draws the device table with a
monospaced-header `Listbox` (Tk 8.4 has no Treeview).

---

## 2. Getting `TigerSend.app` onto the old Mac

`TigerSend.app` is really a **folder** (a Finder bundle). Some copy methods
flatten it or drop the executable bit on the `launcher`. The safe way is to
carry it as a **ZIP**.

### Option A — ZIP on a USB drive (recommended)

1. Build the ZIP yourself: `./build_app.sh && zip -qr TigerSend.zip
   TigerSend.app` (or download it from the Releases page).
2. Copy it to the Mac running Tiger / Leopard / Snow Leopard.
3. Double-click the ZIP to expand it, then drag `TigerSend.app` to
   `/Applications` (or anywhere you like).
4. If you copied the folder without a ZIP and the app refuses to open, fix
   the permissions once from Terminal:

   ```sh
   chmod +x /Applications/TigerSend.app/Contents/MacOS/launcher
   ```

### Option B — Local network (SMB / FTP / SSH)

The other machine can serve the ZIP (macOS File Sharing, `python -m
SimpleHTTPServer` in the folder, etc.). Always transfer the **ZIP**, not the
bare folder or .app, for proper transfer.

### Option C — You are already on the old Mac

```sh
git clone https://github.com/karlredrock/tigersend-osx.git
cd tigersend-osx
chmod +x build_app.sh && ./build_app.sh
```

The first launch may show the usual “downloaded from the Internet” warning;
right-click → **Open** once.

---

## 3. ⚠️ Required on the phone / modern computer or device: turn encryption off

The official LocalSend app encrypts by default (HTTPS with TLS 1.2+ and a
self-signed certificate). **Tiger and Snow Leopard cannot do that** (at least
for proper function and stability on v1.x we don't support encryption,
however we plan on implementing it later), so the other device must talk
plain HTTP:

### On the phone (Android / iPhone)

1. Open **LocalSend**.
2. Tap the **gear / Settings** icon.
3. Set **Encryption → OFF**.
4. Close and reopen LocalSend so the setting takes effect.

### On the modern computer (Windows / macOS / Linux)

1. Open LocalSend → **Settings**.
2. Set **Encryption → OFF**.
3. Restart the app.

If you skip this step, transfers will fail and TigerSend's Activity log will
show the HTTP/TLS errors that tell you exactly that.

---

## 4. Daily use

### The window

```
┌───────────────────────────────────────────────────────────────────────┐
│ TigerSend   LocalSend protocol v2 - Mac OS X 10.4 1.7                 │
│                                  Server: plain HTTP :53317 - running  │
├───────────────────────────────────────────────────────────────────────┤
│ Name:    [ Redstones-MacBook-Air      ] [Apply]                       │
│ Save to: [ /Users/redstone/Downloads  ] [Change...]                   │
├───────────────────────────────────────────────────────────────────────┤
│ Devices on this network                                               │
│ ┌────────────────────────┬──────────────────┬───────────────────────┐ │
│ │ Name                   │ Model            │ Address               │ │
│ │ Ana's iPhone           │ iPhone 13        │ 192.168.1.76:53317    │ │
│ └────────────────────────┴──────────────────┴───────────────────────┘ │
│ [Announce / Refresh] [Scan network] [Clear log]                       │
├───────────────────────────────────────────────────────────────────────┤
│ Files to send  [ 3 ]                                                  │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ photo.jpg  (2.4 MB)                                               │ │
│ │ report.pdf  (310.0 KB)                                            │ │
│ │ tigersend-clipboard-20261114-1227.txt  (48.0 KB)                  │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ [Add File...] [Paste Clipboard] [Remove] [Clear List]                 │
│                                  [Send to Device] [Cancel Transfer]   │
├───────────────────────────────────────────────────────────────────────┤
│ Activity                                                              │
│ [12:27:19] ++ discovered: Ana's iPhone (iPhone 13) at 192.168.1.76    │
├───────────────────────────────────────────────────────────────────────┤
│ (•English)( Español)( Français)( Deutsch)( Português)                 │
│ Ready | 1 device(s) | Language: English    HTTP :53317 - Encryption   │
│                                            OFF on the other device    │
└───────────────────────────────────────────────────────────────────────┘
```

Everything lives inside the window — there is **no menu bar**, as it's a
plain Tkinter app:

- **Language buttons** at the bottom switch the interface language instantly.
- The Mac's name, the language and the download folder are edited right in
  the window and saved to `~/.tigersend_config.json` when you press *Apply*,
  pick a folder or switch language.

### Receiving files

Nothing to do: the HTTP server listens on **53317** and **accepts incoming
requests automatically** (this lightweight version has no accept/reject
dialog). Every file is written to the download folder and its **size is
checked** against what the sender declared; a mismatch is logged. Name
clashes are resolved as `name (1).ext`, `name (2).ext`…

> SHA-256 checksums are **not** verified: Tiger's Python 2.3 has no
> `hashlib`/`sha256` at all. The size check plus TCP's own integrity is what
> you get on 2005 hardware.

### Sending files

TigerSend works like the official app: **you build a list of files first,
and it stays there until you remove it.**

1. Press **Add File...** (multiple selection is used where the installed Tk
   supports it, with a single-file fallback) or **Paste Clipboard**. Every
   file is added to **Files to send**; nothing is sent yet.
2. Repeat as many times as you want, either to send everything to one device
   later or to send the same batch to several devices one after another.
3. Select the target device in the table and press **Send to Device**.
4. Accept the prompt on the other device (watch the Activity pane).
5. Changed your mind mid-transfer? **Cancel Transfer** aborts it: TigerSend
   stops sending, closes the connection (the receiver discards the
   incomplete file) and sends `POST /api/localsend/v2/cancel` so the session
   is cleaned up on the other side.
6. The list is **not** cleared after sending — send it to another device, or
   use **Remove** / **Clear List** when you are done.

Notes:

- **Paste Clipboard** takes the text on the clipboard and adds it as
  `tigersend-clipboard-YYYYMMDD-HHMMSS.txt` (UTF-8) in your temporary
  folder, exactly like the text feature of the official app. Images are not
  supported yet.
- Files are read from disk in **64 KB chunks**, so cancelling works even in
  the middle of a large file, and huge files are never loaded into memory.
- The queue lives only while the app is open; it is not saved to disk.

### Quitting

Close the window. If the app fails to start, check:

```
~/Library/Logs/TigerSend.log
```

---

## 5. Languages

The whole interface — labels, buttons, table headers, dialogs and the status
bar — is translated into five languages:

| Code | Language | Notes |
|---|---|---|
| `en` | English | default fallback |
| `es` | Español | |
| `fr` | Français | |
| `de` | Deutsch | |
| `pt` | Português | |

- Change it on the fly with the **five radio buttons at the bottom of the
  window** (`English | Español | Français | Deutsch | Português`). The whole
  interface switches immediately, and the choice is remembered in
  `~/.tigersend_config.json`.
- Translations live in a single `TR` dictionary at the top of
  `tigersend.py`, one table per language, with English as the fallback for
  any missing key. Adding a language is a matter of copying a table and
  translating it.
- Every translation is a `u"…"` unicode literal, so accents and ellipses
  render correctly on Python 2.x (byte-string `\uXXXX` escapes would show up
  literally — a classic Python 2 trap).

---

## 6. Implemented protocol (LocalSend v2)

Reference: <https://github.com/localsend/protocol> (v2.2)

| Element | Implementation |
|---|---|
| Multicast discovery | UDP `224.0.0.167:53317`, announcement JSON with `alias`, `version`, `deviceModel`, `deviceType`, `fingerprint`, `port`, `protocol`, `download`, `announce` |
| `POST /api/localsend/v2/register` | Answers announcements over HTTP first, with a UDP response as fallback |
| `POST /api/localsend/v2/prepare-upload` | Receives `{info, files:{id:{fileName,size,fileType}}}` → replies `{sessionId, files:{id:token}}` |
| `POST /api/localsend/v2/upload` | Raw binary body streamed to disk; size is checked, replies `200` |
| `POST /api/localsend/v2/cancel` | Cancels a session |
| `GET /api/localsend/v2/info` | Returns this device's info |
| HTTP fallback discovery | **Scan network** probes every address of the local `/24` with 16 worker threads |

Robustness details that matter in the real world:

- **`Transfer-Encoding: chunked`** request bodies are decoded chunk by chunk
  (that is how iOS sends them) and streamed straight to disk.
- **`Expect: 100-continue`** is answered explicitly (`HTTP/1.1 100
  Continue`), otherwise some clients deadlock before sending the body.
- **macOS/BSD multicast quirk:** the UDP socket binds to `INADDR_ANY` and
  sets `IP_MULTICAST_IF` to the real local IP; binding to the multicast
  address fails with `[Errno 49]` on macOS.
- The device **fingerprint is persisted** in `~/.tigersend_config.json`, so
  the Mac stays the same device in the phone's list across launches.
- Everything runs in daemon threads; the Tkinter GUI is fed through a
  `Queue` polled with `after()` (Tk is not thread-safe).

---

## 7. Troubleshooting

| Symptom | What to check |
|---|---|
| The old Mac doesn't appear on the phone | Encryption OFF on the phone (§3)? Same Wi-Fi? Port 53317 free? Press *Announce / Refresh*. |
| The phone doesn't appear on the old Mac | Encryption OFF? Some routers/APs block multicast: use **Scan network**. |
| “prepare-upload failed” when sending | The destination is probably still on HTTPS. Turn Encryption off there and retry; check both logs. |
| Stuck while sending | You must tap **Accept** on the other device. If no prompt appears, encryption is on or the devices are on different networks. |
| App won't open on double-click | Check `~/Library/Logs/TigerSend.log`. If you copied the folder without a ZIP, re-apply `chmod +x …/Contents/MacOS/launcher` (§2). |
| `Server: ERROR - port 53317 busy` in the header | Quit other LocalSend/TigerSend copies using the port, then relaunch. |
| Firewall | On the modern device allow LocalSend through the firewall; on the old Mac, *System Preferences → Security → Firewall* must allow incoming connections for `python`. |
| Size mismatch logged on receive | The sender aborted or the connection dropped; delete the partial file and resend. |

---

## 8. For developers

Check the syntax on a modern machine (the source deliberately avoids both
Python-3-only *and* Python-2-only syntax — exceptions are retrieved with
`sys.exc_info()[1]` instead of `except X, e` — so Python 3's parser can
validate it even though it *runs* on Python 2):

```sh
python3 -c "import ast; ast.parse(open('tigersend.py').read())"
```

On the old Mac itself:

```sh
/usr/bin/python -m py_compile tigersend.py   # 2.6/2.7 (Snow Leopard)
/usr/bin/python tigersend.py                 # just run it (any release)
```

Legacy-compatibility ground rules used throughout the source — keep them if
you contribute:

- no `with`, no `except X as e`, no ternary expressions, no generator
  expressions, no decorators, no `sorted()`, no `set()`, no `os.urandom`,
  no `uuid`, no `subprocess`, no `ttk`;
- `json` → bundled mini codec fallback, `hashlib` → `md5` module fallback;
- 2-space-wide feature detection with `try/except ImportError` everywhere.

Rebuild the bundle:

```sh
chmod +x build_app.sh
./build_app.sh
```

Before publishing, check the bundle is complete: `Info.plist` with
`CFBundleName=TigerSend` and `LSMinimumSystemVersion=10.4`, an executable
`Contents/MacOS/launcher`, and `Contents/Resources/` containing
`tigersend.py` and `LICENSE.txt`.

---

## 9. Security

- This client speaks **unencrypted HTTP** out of necessity on 10.4–10.6. Use
  it **only on your own trusted LAN**.
- It accepts files automatically: check your download folder periodically
  and never run it on a network you don't trust.
- Without TLS there is no sender authentication: any machine on your network
  could send you a file. This is the same trust model the official LocalSend
  uses with encryption off.
- No telemetry, no external servers: only UDP 53317 (discovery) and TCP
  53317 (HTTP) on your local network.

---

## 10. Project built with AI assistance

This project was developed **in collaboration with an AI assistant**
(Arena.ai agent), in an iterative loop of writing, testing and fixing: the
code, the packaging and this documentation were produced and reviewed with
that help, starting from the author's instructions, tests on real hardware
and the author's corrections.

What that means in practice:

- **Review the code before trusting it.** It has been tested, but no
  software is bug-free and this one has had no formal security audit.
- **It is provided “as is”, without warranty** (see the license, §11).
- **It does not replace the official app.** TigerSend exists because the
  official app no longer runs on these systems; it is not meant as a
  replacement on modern machines.
- Design decisions, the license choice and responsibility for what is
  published belong to the project author.

---

## 11. License and legal notes

### License: MIT

This project is released under the **MIT license** ([`LICENSE`](LICENSE),
also bundled as `TigerSend.app/Contents/Resources/LICENSE.txt`).

MIT lets anyone use, copy, modify, merge, publish, distribute, sublicense
and sell the software, with two conditions: keep the copyright notice and
the license in copies or substantial portions of the software, and accept
that it comes with no warranty (“AS IS”).

### Legal points reviewed

1. **No LocalSend code was copied.** All of `tigersend.py` is original code
   written for this project; no Dart code from LocalSend or any third party
   was translated or ported. Therefore it does **not** inherit the official
   app's Apache-2.0 license and can be licensed freely (MIT).
2. **The protocol repository (`localsend/protocol`) declares no license.**
   Its text is not reproduced here: it is used only as a functional
   reference for interoperability, and endpoints, JSON fields and ports were
   rewritten in our own words. Interoperability itself is not restricted by
   copyright.
3. **Trademarks.** “LocalSend”, its logo and the project name belong to
   their authors. That is why this app is called **TigerSend**: it avoids
   any confusion or misuse of the mark. Mentions such as
   “LocalSend-compatible” are descriptive/nominative use, not a claim to the
   mark. **TigerSend is not affiliated with or endorsed by LocalSend.**
4. **Apple.** macOS, Mac OS X, Tiger, Snow Leopard, Aqua and Finder are
   trademarks of Apple Inc. TigerSend is not affiliated with Apple.
5. **Python and Tk.** The bundle **does not redistribute** Python: it uses
   the interpreter that ships with the system. Python is PSF-licensed and
   Tcl/Tk has its own permissive license; since no binaries are included,
   no redistribution obligations are added.
6. **No telemetry, no external network.** TigerSend sends no data to any
   server and collects no user information. Note that plain HTTP transports
   files **unencrypted** over your local network (§9).

> **To change the copyright holder**, edit the line
> `Copyright (c) 2026 TigerSend contributors` in `LICENSE` (and rebuild with
> `./build_app.sh` so `Contents/Resources/LICENSE.txt` is refreshed).

---

## 12. Acknowledgements

Without these projects, TigerSend would not exist. Thanks to:

- **[LocalSend](https://github.com/localsend/localsend)** (Tien Nam Do and
  contributors, Apache-2.0) — the open-source app that inspired all of this
  and that TigerSend is compatible with.
- **[LocalSend Protocol v2.2](https://github.com/localsend/protocol)**
  (LocalSend organisation) — the specification for multicast discovery,
  `register`, `prepare-upload`, `upload`, `cancel` and `info` implemented
  here. Functional reference, no text copied.
- **[hermes-localsend](https://github.com/tylerbrevard/hermes-localsend)**
  (tylerbrevard, MIT) — a stdlib-only Python implementation of protocol
  v2.2; its public notes about iOS using `Transfer-Encoding: chunked` were
  key to file reception from iPhones.
- **[unlocalsend](https://github.com/theanazerka/unlocalsend)** (theanazerka,
  GPL-3.0) — a LocalSend client for old iOS, useful for understanding
  behaviour on the iOS side. Only behavioural ideas were taken; **no code
  was copied**.
- **The Python project** and its standard library (`Tkinter`,
  `BaseHTTPServer`, `httplib`, `socket`, `threading`), maintained by the
  Python Software Foundation and the community.
- **Tcl/Tk** — the toolkit behind the interface, included in Mac OS X.
- **Apple** — for Mac OS X Tiger through Snow Leopard and their preinstalled
  Python interpreters, which keep these Macs useful.
- **The project author**, for testing on real hardware and validating every
  version.
- **Arena.ai's AI assistant** — for writing, debugging and documenting
  alongside the author; see §10.

---

## 13. Changelog

### v1.7 (2.0.7-10.4) — Renamed to TigerSend, Tiger 10.4 support

1. The app is now **`TigerSend.app`** (was `SnowSend.app`): bundle name,
   window title, `CFBundleName`/`CFBundleIdentifier`
   (`org.tigersend.TigerSend`), signature (`TgSd`), log file
   (`~/Library/Logs/TigerSend.log`), config file
   (`~/.tigersend_config.json`) and source file (`tigersend.py`).
2. **Minimum system lowered to Mac OS X 10.4 Tiger**
   (`LSMinimumSystemVersion=10.4`): the source now runs on Python 2.3/2.4 —
   bundled mini JSON codec (no `json` module before 2.6), `hashlib` → `md5`
   fallback, no `uuid`/`os.urandom`/`ttk`/`sorted()`/`set()`, device table
   drawn with a monospaced-header `Listbox` (Tk 8.4 has no Treeview), and no
   Python-2.5+ syntax anywhere (`with`, ternaries, `except … as`).
3. **Settings are persisted** in `~/.tigersend_config.json`: alias,
   language, download folder and the device fingerprint (so the Mac stays
   the same device in the phone's list across launches).
4. **Chunked reception**: `Transfer-Encoding: chunked` bodies (what iOS
   sends) are decoded and streamed to disk, and `Expect: 100-continue` is
   answered explicitly.
5. **Multicast fix for macOS/BSD**: announce socket sets `IP_MULTICAST_IF`
   to the real local IP (avoids `[Errno 49]`), listener binds `INADDR_ANY`.
6. The launcher tries `pythonw` → versioned `pythonw2.x` → `python`, and
   logs start-up errors to `~/Library/Logs/TigerSend.log`.

### Inherited from SnowSend (v1.0 – v1.7, 10.6-only era)

- **v1.7** — window fits 11" screens; footer packed bottom-first; short
  “Encryption OFF” footer text in all 5 languages.
- **v1.6** — file queue instead of immediate sending; *Paste Clipboard*;
  *Cancel Transfer* (mid-file and between files, with `POST /cancel`);
  streamed chunked uploads; unicode translation literals (no more `\u2026`
  garbage on buttons).
- **v1.5** — language switching via five in-window radio buttons; menu bar
  removed (Tk/Aqua re-labelling was unreliable on Snow Leopard).
- **v1.4** — five languages behind a single string catalog; Mac-style
  window with device table, activity pane and status bar.
- **v1.3** — renamed to SnowSend; MIT license; fingerprint preserved across
  launches.
- **v1.2** — Mac → iPhone sending fixed: plain-HTTP-first `prepare-upload`,
  HTTP client rewritten on `httplib`, peer diagnosis via `GET /info`.
- **v1.1** — iPhone reception fixed (chunked bodies), multicast
  `[Errno 49]` fix, HTTPS-announce fallback handling.
- **v1.0** — first working version: protocol v2 client and server, Tkinter
  GUI, multicast discovery, subnet scanning, `.app` bundle and build script.

---

*TigerSend is an independent, unofficial project, not related to LocalSend,
Apple Inc. or the authors of the credited projects. “LocalSend” is a name of
the LocalSend project; “macOS”, “Mac OS X”, “Tiger” and “Snow Leopard” are
trademarks of Apple Inc.*
