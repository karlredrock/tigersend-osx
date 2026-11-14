# TigerSend — LocalSend for Mac OS X 10.4 Tiger and newer

A **LocalSend protocol v2** client that runs on the stock Python of classic
Mac OS X: **10.4 Tiger (PowerPC and Intel)**, Leopard, Snow Leopard, Lion …
and it also still runs today on macOS with Python 3. One small `.app`, no
dependencies, no compilation.

<img width="768" height="697" alt="TigerSend" src="https://github.com/user-attachments/assets/14f00548-6da8-44e2-ba91-ad3d2755b1b7" />


**IMPORTANT NOTE: this project used AI assisted coding as I personally
couldn't manage to get the protocol working, however keep in mind I reviewed
and tested it severely on my computers, as always I strongly suggest you only
use this for personal usage in a secure network, if you have any improvements
or suggestions I'll gladly review them, if you have any issues with AI
projects I suggest you check another thing, however if you just care for
something that just works, check it out**

**TigerSend** is an independent project: it implements the LocalSend protocol
from scratch so a twenty year old Mac can exchange files with modern phones
and computers that run the official app. It is not affiliated with, sponsored
by or endorsed by the LocalSend project.

```
┌──────────────────────────────┐      plain HTTP :53317       ┌──────────────────────────────┐
│  Mac OS X 10.4 – 10.15       │  ◄────────────────────────►  │  Phone / modern computer     │
│  TigerSend.app               │  multicast UDP 224.0.0.167   │  Official LocalSend app      │
│  /usr/bin/python (2.3 – 2.7) │  discovery + file transfer   │  Encryption: OFF             │
│  Tkinter + BaseHTTPServer    │                              │  (see §3, required)          │
└──────────────────────────────┘                              └──────────────────────────────┘
```

> **Why plain HTTP:** Tiger and Leopard have no `ssl` module at all, and
> Snow Leopard cannot reliably negotiate the TLS 1.2/1.3 + self-signed
> certificate with *fingerprint pinning* that LocalSend uses by default
> (HTTPS). TigerSend therefore speaks **unencrypted HTTP on port 53317**.
> Use it only on your own trusted local network.

**Version:** 1.8.1 (`2.0.9-10.4`) · **License:** MIT (see §12) ·
**Status:** personal project, built with AI assistance (§11) ·
**Languages:** English, Español, Français, Deutsch, Português (§5)

---

## 1. What runs where

The same download works everywhere, because the bundle contains **no machine
code at all**: it is a POSIX shell launcher plus a single Python file. The
launcher looks for an interpreter that has Tkinter and runs the app with it.

| System | Architecture | Interpreter used | Status |
|---|---|---|---|
| 10.4 Tiger | PowerPC G3/G4/G5 | `/usr/bin/pythonw` → Python 2.3.5 | supported |
| 10.4 Tiger | Intel | `/usr/bin/pythonw` → Python 2.3.5 | supported |
| 10.5 Leopard | PowerPC / Intel | Python 2.5.1 | supported |
| 10.6 Snow Leopard | Intel | Python 2.6.1 | supported |
| 10.7 – 10.15 | Intel | `/usr/bin/python` (2.7) | supported |
| 11 – 12.2 | Apple silicon / Intel | Python 2.7 | supported |
| 12.3 + | Apple silicon / Intel | `python3` **with Tk** (e.g. `brew install python-tk`) | supported when Tk is present; otherwise headless |

TigerSend itself is written in a subset of Python that is valid on **2.3,
2.4, 2.5, 2.6, 2.7 and 3.x** at the same time:

| Missing on Tiger (2.3) | What TigerSend does |
|---|---|
| `json` (2.6+) | ships its own small JSON encoder/parser (handles `\uXXXX`, surrogate pairs, BOM) |
| `hashlib` (2.5+) | uses `hashlib` when present, otherwise the old `md5` module |
| `uuid`, `os.urandom` | ids/fingerprint from `md5(time, pid, random)` |
| `ssl` (2.6+) | plain HTTP by design; encryption must be off on the other device |
| `bytearray`, `b''` literals, `with`, ternary `a if b else c`, generator expressions, `set()`, `sorted()`, `except … as e`, `except`+`finally` in one `try` | not used anywhere; the file is checked automatically (§9) |
| `ttk` / Treeview (Tk 8.5+) | plain `Tkinter` widgets: monospaced `Listbox` as the device table |
| `httplib` timeouts (2.6+), chunked responses | a small HTTP/1.1 client written on raw sockets |

That last point matters: the built-in HTTP client gives every Python version
the same behaviour — timeouts, cancellation in the middle of an upload, and
servers that answer with `Transfer-Encoding: chunked`, `Content-Encoding:
gzip`, no `Content-Length`, `204 No Content`, or a `100 Continue` handshake.

---

## 2. What's in this project

| File | Purpose |
|---|---|
| `tigersend.py` | Complete source: Tkinter GUI + HTTP server + multicast discovery + send client + 5-language UI + built-in self test. Runs on Python 2.3 … 3.x. |
| `build_app.sh` | Builds `TigerSend.app` and `TigerSend-1.8.1.zip` (Info.plist, launcher, PkgInfo, icon, bundled license). |
| `tests/test_tigersend.py` | Test suite: real sockets, real protocol round trips, scripted misbehaving servers, fake-Tk GUI tests. Runs unchanged on 2.3, 2.5, 2.7 and 3.x. |
| `tests/check_legacy_syntax.py` | Static checker: refuses syntax and stdlib calls that Tiger's Python 2.3 cannot parse or run. |
| `tests/run_tests.sh` | Runs the checker, the suite and the self test on every Python installed on the machine. |
| `tests/fake_tk.py` | A stand-in for Tkinter, so the GUI code can be tested with no display. |
| `snowsend.py` | The original SnowSend 1.3 source (Snow Leopard only). Kept for reference; not used or packaged. |
| `LICENSE` | MIT license. Also copied inside the bundle as `Contents/Resources/LICENSE.txt`. |

The bundle layout is the classic Mac OS X one:

```
TigerSend.app/
└── Contents/
    ├── Info.plist          CFBundleExecutable=launcher, LSMinimumSystemVersion=10.4
    ├── PkgInfo             APPLTgSd
    ├── MacOS/
    │   └── launcher        /bin/sh script (chmod 755)
    └── Resources/
        ├── tigersend.py
        ├── LICENSE.txt
        └── AppIcon.icns
```

The `launcher`:

1. resolves its own path with `cd -P`, so the app keeps working when it is
   moved to `/Applications`, renamed or reached through a symlink;
2. appends `/usr/local/bin` and `/opt/homebrew/bin` to `PATH` (Finder starts
   apps with almost nothing);
3. rotates and appends to `~/Library/Logs/TigerSend.log`;
4. walks a candidate list — `/usr/bin/pythonw`, `pythonw2.7`, `pythonw2.6`,
   `pythonw2.5`, `pythonw2.3`, `/usr/bin/python`, framework builds,
   `python3` — and picks the first one where `import Tkinter`/`import
   tkinter` works;
5. `exec`s the app. If no Python with Tk exists it starts headless instead
   of failing, and says so in a dialog.

Double-clicking therefore opens no Terminal window, and
`~/Library/Logs/TigerSend.log` has the full story when something goes wrong.

---

## 3. Getting `TigerSend.app` onto the old Mac

`TigerSend.app` is really a **folder** (a Finder bundle). Some copy methods
flatten it or drop the executable bit on the `launcher`. The safe way is to
carry it as a **ZIP**.

### Option A — ZIP on a USB drive (recommended)

1. Build the ZIP yourself: `./build_app.sh` (it produces `TigerSend-1.8.1.zip`),
   or download it from the Releases page.
2. Copy it to the Mac running Tiger / Leopard / Snow Leopard.
3. Double-click the ZIP to expand it, then drag `TigerSend.app` to
   `/Applications`.
4. If the app refuses to open, fix the permissions once from Terminal:

   ```sh
   chmod +x /Applications/TigerSend.app/Contents/MacOS/launcher
   ```

### Option B — Local network (SMB / FTP / SSH)

The other machine can serve the ZIP (macOS File Sharing, `python -m
SimpleHTTPServer` in the folder, etc.). Always transfer the **ZIP**, not the
bare folder or `.app`.

### Option C — You are already on the old Mac

```sh
git clone https://github.com/karlredrock/tigersend-osx.git
cd tigersend-osx
chmod +x build_app.sh && ./build_app.sh
```

On 10.5+ the first launch may show the “downloaded from the Internet”
warning; right-click → **Open** once.

---

## 4. ⚠️ Required on the phone / modern computer: turn encryption off

The official LocalSend app encrypts by default (HTTPS with TLS 1.2+ and a
self-signed certificate). **Tiger, Leopard and Snow Leopard cannot do that**
(Tiger's Python has no `ssl` module at all), so the other device must talk
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

If you skip this step, transfers fail and TigerSend's Activity log says so
explicitly:

```
!! prepare-upload: HTTP … | The other device must have Encryption OFF (plain HTTP)
!! iPhone de Ana announces "https": turn Encryption OFF there (this Mac can only do plain HTTP)
```

---

## 5. Daily use

### The window

```
┌───────────────────────────────────────────────────────────────────────┐
│ TigerSend 1.8.1   LocalSend v2.0 - Mac OS X 10.4.11                     │
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
│ │ tigersend-clipboard-20261114-1227.txt  (48 B)                     │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ [Add File...] [Paste Clipboard] [Remove] [Clear List]                 │
│                                  [Send to Device] [Cancel Transfer]   │
├───────────────────────────────────────────────────────────────────────┤
│ Activity                                                              │
│ [12:27:19] ++ discovered: Ana's iPhone (iPhone 13) at 192.168.1.76    │
│ [12:27:20] -> prepare-upload to Ana's iPhone, 3 file(s)               │
├───────────────────────────────────────────────────────────────────────┤
│ (•English)( Español)( Français)( Deutsch)( Português)                 │
│ Ready | 1 device(s) | Language: English | 25%        PowerPC - Python 2.3.5 │
└───────────────────────────────────────────────────────────────────────┘
```

Everything lives inside the window — there is **no menu bar**, as it is a
plain Tkinter app. The left of the status bar shows what is happening
(`Ready`, `Scanning`, `Sending`, `Receiving`) plus the transfer percentage;
the right shows the architecture and the exact Python in use, which is the
first thing to look at in a bug report.

### Receiving files

Nothing to do: the HTTP server listens on **53317** and **accepts incoming
requests automatically** (this lightweight version has no accept/reject
dialog). Every file is written to the download folder:

* the data goes to `name.part` and is **renamed to `name` only when the size
  matches**, so a cancelled transfer never leaves a broken file in the way;
* name clashes become `name (1).ext`, `name (2).ext`…;
* non-ASCII names (`ñ`, `日本語`, emoji) are decoded from the JSON as UTF-8 and
  written with the filesystem encoding — this used to crash on Tiger.

> SHA-256 is **not** verified: Tiger's Python has no `sha256` at all. Sizes
> are checked, plus TCP's own integrity, which is what you get on 2005
> hardware.

### Sending files

TigerSend works like the official app: **you build a list of files first,
and it stays there until you remove it.**

1. Press **Add File...** (multiple selection where the installed Tk supports
   it, single-file fallback) or **Paste Clipboard**. Nothing is sent yet.
2. Repeat as many times as you want, either to send everything to one device
   later or to send the same batch to several devices one after another.
3. Select the target device in the table and press **Send to Device**.
4. Accept the prompt on the other device (watch the Activity pane).
5. Changed your mind mid-transfer? **Cancel Transfer** stops sending, closes
   the connection (the receiver discards the incomplete file) and sends
   `POST /api/localsend/v2/cancel?sessionId=…` so the session is cleaned up
   on the other side.
6. The list is **not** cleared after sending — send it to another device, or
   use **Remove** / **Clear List** when you are done.

Notes:

* **Paste Clipboard** takes the text on the clipboard and adds it as
  `tigersend-clipboard-YYYYMMDD-HHMMSS.txt` (UTF-8), exactly like the text
  feature of the official app. Images are not supported yet.
* Files are read from disk in **64 KB chunks**, so cancelling works even in
  the middle of a large file and huge files are never loaded into memory. The
  log shows 25/50/75/100 % progress.
* The queue lives only while the app is open; it is not saved to disk.

### Headless mode (no window)

```sh
python tigersend.py --headless                 # receive files, log to stdout
python tigersend.py --headless --alias MacG4 --save-dir ~/Desktop
python tigersend.py --announce                 # just announce, then exit
python tigersend.py --self-test                # verify this Python works
```

`--self-test` is the first thing to run on a Mac that misbehaves: it starts
two small engines on loopback and pushes a real `register` →
`prepare-upload` → `upload` (both `Content-Length` and chunked) → `cancel`
sequence through them, plus the JSON codec and the unicode handling.

### Quitting

Close the window. If the app fails to start, check:

```
~/Library/Logs/TigerSend.log
```

---

## 6. Languages

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
  window**. The whole interface switches immediately, and the choice is
  remembered in `~/.tigersend_config.json`.
- Translations live in a single `TR` dictionary near the top of
  `tigersend.py`, one table per language, English as the fallback for any
  missing key. The test suite fails if a language is missing a key.
- Every translation is a `u"…"` unicode literal written with `\uXXXX`
  escapes, so the file stays pure ASCII and cannot be mangled by an editor on
  any of these systems.

---

## 7. Implemented protocol (LocalSend v2)

Reference: <https://github.com/localsend/protocol>

| Element | Implementation |
|---|---|
| Multicast discovery | UDP `224.0.0.167:53317`, announcement JSON with `alias`, `version`, `deviceModel`, `deviceType`, `fingerprint`, `port`, `protocol`, `download`, `announce`; re-announced every 20 s and on demand |
| `POST /api/localsend/v2/register` | Answers announcements over HTTP first, with a unicast UDP response as fallback |
| `POST /api/localsend/v2/prepare-upload` | Receives `{info, files:{id:{fileName,size,fileType}}}`, answers `{sessionId, files:{id:token}}`, or `204` when nothing is requested |
| `POST /api/localsend/v2/upload?sessionId&fileId&token` | Streams the body to disk (chunked or `Content-Length`); validates the token; `200` / `403` / `500` |
| `POST /api/localsend/v2/cancel` | Cancels a session; accepts the id in the query string *and* in a JSON body |
| `GET /api/localsend/v2/info` | Returns this device's info (`/v1/info` answered too, for old clients) |
| `GET /` | Tiny text status page, handy to check the server from a browser |
| HTTP fallback discovery | **Scan network** probes every address of the local `/24` with 12 worker threads |

Robustness details that matter in the real world, all covered by tests:

- **`Transfer-Encoding: chunked`** request bodies are decoded chunk by chunk
  (that is how iOS sends them), including chunk extensions and trailers.
- **`Expect: 100-continue`** is answered explicitly. Python 2.4+ does it
  through `handle_expect_100`; Python 2.3 has no such hook, so TigerSend
  writes the interim response itself.
- **HTTP/1.1 responses** always carry `Content-Length` and
  `Connection: close`, and `204` answers carry no body, as RFC 7230 requires.
- **A refused request is drained first**, so the sender actually receives the
  `403` instead of a TCP reset (that reset is what Python 2.3 clients used to
  see).
- **macOS/BSD multicast quirk:** the UDP socket binds to `INADDR_ANY` and
  sets `IP_MULTICAST_IF` to the real local IP; binding to the multicast
  address fails with `[Errno 49]` on macOS, and Tiger's `HTTPServer` does not
  fill in `server_address`, so the port is read from the socket instead.
- The device **fingerprint is persisted** in `~/.tigersend_config.json`, so
  the Mac stays the same device in the phone's list across launches.
- All I/O runs in daemon threads; the Tkinter GUI is fed through a `Queue`
  polled with `after()` (Tk is not thread-safe).

Not implemented on purpose: HTTPS/TLS, the download API (`download: false`),
checksum verification (`sha256` is ignored when a sender offers it), and the
accept/reject dialog (incoming transfers are always accepted).

One cosmetic limitation of this design: because the launcher `exec`s the
system Python instead of being a compiled Cocoa stub, the **Dock shows the
generic Python icon** while the app runs (the TigerSend icon is the one in
Finder, Get Info and the window title). Replacing the launcher with a
compiled stub would mean shipping a PowerPC **and** an Intel binary — exactly
what this release avoids.

---

## 8. Troubleshooting

Everything interesting is in `~/Library/Logs/TigerSend.log`. The first lines
tell you the system, the architecture, the Python in use and the port.

| Symptom | What to check |
|---|---|
| App does not open at all | Log file. `launcher: command not found`? `chmod +x …/Contents/MacOS/launcher`. “no Python interpreter found”? The system Python is missing or broken. |
| Window never appears, no error | Look for `!! the window could not be created` in the log: it usually means Tkinter is missing (then the app runs headless). |
| The old Mac doesn't appear on the phone | Encryption OFF on the phone (§4)? Same Wi-Fi? Port 53317 free? Press *Announce / Refresh*. |
| The phone doesn't appear on the old Mac | Encryption OFF? Some routers/APs block multicast: use **Scan network**. |
| `!! prepare-upload: HTTP …` when sending | The destination is probably still on HTTPS. Turn Encryption off there and retry; both logs will say so. |
| Stuck while sending | You must tap **Accept** on the other device. If no prompt appears, encryption is on or the devices are on different networks. |
| `Server: ERROR - port 53317 busy` in the header | Quit other LocalSend/TigerSend copies using the port, then relaunch. |
| `!! UDP discovery disabled: …` | Multicast is unavailable (VPN, firewall, weird Wi-Fi). Discovery still works through HTTP register and **Scan network**. |
| Size mismatch note in the log | The sender aborted or the connection dropped; the `.part` file is removed, just resend. |
| Files arrive with garbled names | The log shows the name as received. Please open an issue with those two lines; the code decodes UTF-8 with a Latin-1 fallback. |
| Firewall | On the modern device allow LocalSend through the firewall; on the old Mac, *System Preferences → Sharing → Firewall* must allow incoming connections for `python`. |

---

## 9. For developers

### The legacy ground rules

Tiger ships **Python 2.3.5**, which cannot even *parse* syntax added later,
so the source keeps to these rules (they are enforced automatically):

- no `with`, no `except X as e`, no ternary `a if b else c`, no generator
  expressions, no decorators, no set literals/comprehensions, no dict
  comprehensions, no `b'…'` literals, no keyword-only arguments, no
  annotations;
- never `except` **and** `finally` in the same `try` (that is Python 2.5+):
  nest a `try`/`except` inside a `try`/`finally`;
- no `sorted()`, `set()`, `any()`, `all()`, `bytes()`, `bytearray`,
  `str.format()`, `os.urandom`, `os.path.relpath`, `subprocess`, `uuid`,
  `socket.create_connection`, `threading.Event`, `Thread.daemon`;
- `json` → bundled codec, `hashlib` → `md5` fallback, `Tkinter`/`tkinter`,
  `BaseHTTPServer`/`http.server` … every import that moved between Python 2
  and 3 is behind one compatibility block at the top of the file;
- bytes vs unicode: go through `to_bytes()` / `to_text()`, and format log
  lines with `log_text()` (`u'%s' % 'caf\xc3\xa9'` raises `UnicodeDecodeError`
  on Tiger).

### Running the tests

The suite runs unchanged on every Python from 2.3 to 3.x:

```sh
sh tests/run_tests.sh                     # the whole matrix on every Python found
python  tests/test_tigersend.py           # just the suite (2.3, 2.5, 2.7 or 3.x)
python3 tests/check_legacy_syntax.py tigersend.py     # static 2.3 check
python  tigersend.py --self-test          # quick built-in check
./build_app.sh --check                    # bundle + self test
```

`tests/run_tests.sh` takes interpreter paths as arguments too, which is how
the matrix below was produced:

```sh
sh tests/run_tests.sh /tmp/py23/bin/python2.3 /tmp/py2.5/bin/python2.5 \
                      /tmp/py27/bin/python2.7 python3
```

Expected output on each interpreter:

```
Python 2.3.5 (Tiger)   230 checks passed, 0 failed
Python 2.5.6 (Leopard) 230 checks passed, 0 failed
Python 2.7.18          236 checks passed, 0 failed
Python 3.11            238 checks passed, 0 failed
```

The difference is only a few tests that need a newer `ast` module.

`check_legacy_syntax.py` is the safety net: on a modern machine it catches
what would otherwise show up as “the app does not start” on Tiger. It parses
the file with `ast`, inspects the import/name/attribute usage, and scans the
token stream for `b'…'` and f-strings.

### Testing against a real 2.3 interpreter on a modern machine

You do not need a PowerPC Mac to validate the Tiger path — CPython 2.3.5
builds on Linux and the whole suite runs there:

```sh
curl -L -o py2.3.5.tar.gz \
  https://codeload.github.com/python/cpython/tar.gz/refs/tags/v2.3.5
tar xzf py2.3.5.tar.gz && cd cpython-2.3.5
CFLAGS="-fcommon -fno-strict-aliasing -O1 -Wno-error \
        -Wno-implicit-function-declaration -Wno-implicit-int \
        -Wno-incompatible-pointer-types -std=gnu89" \
  ./configure --prefix=/tmp/py23 --without-cxx
make -j2 && make install
cd - && /tmp/py23/bin/python2.3 tests/test_tigersend.py
```

(Tkinter is not needed for the tests: `tests/fake_tk.py` stands in for it.)

### Rebuilding the bundle

```sh
chmod +x build_app.sh
./build_app.sh              # TigerSend.app + TigerSend-1.8.1.zip
./build_app.sh --no-zip     # just the .app
./build_app.sh --check      # build and self test
```

The build checks the result: `Info.plist` has `CFBundleName=TigerSend` and
`LSMinimumSystemVersion=10.4`, `Contents/MacOS/launcher` is executable and
syntactically valid sh, `Contents/Resources/` has `tigersend.py`,
`LICENSE.txt` and `AppIcon.icns`, **`LSRequiresNativeExecution` is absent**
and there is no compiled file in the bundle (that is what keeps one download
working on PowerPC and Intel).

---

## 10. What has been tested (and what has not)

Being precise about this is more useful than a green check mark:

| Area | How it was verified |
|---|---|
| Python 2.3.5 (Tiger's interpreter) | full suite + `--self-test`, on a real CPython 2.3.5 built from source |
| Python 2.5.6, 2.7.18, 3.11 | full suite |
| Protocol | real sockets, two engines talking `register` → `prepare-upload` → `upload` → `cancel`, chunked and `Content-Length`, name clashes, unicode names, truncated uploads, bad tokens |
| Weird servers | scripted server answers with chunked, gzip, no `Content-Length`, `204`, `403`, interim `100 Continue`, and a peer that never answers (timeout path) |
| GUI logic | `tests/fake_tk.py` drives every button, dialog, language switch, file queue and the send/receive callbacks |
| Icon / bundle | generated icns parsed back and validated; bundle structure verified by the build script |
| **Real Tiger hardware (PPC G4/G5, Intel), Aqua rendering, real iPhone/Android peers** | **not available in the build environment — please report anything that only shows up there.** The logging is deliberately verbose for exactly that reason. |

---

## 11. Project built with AI assistance

This project was developed **in collaboration with an AI assistant**
(Arena.ai agent), in an iterative loop of writing, testing and fixing: the
code, the packaging and this documentation were produced and reviewed with
that help, starting from the author's instructions, tests on real hardware
and the author's corrections.

What that means in practice:

- **Review the code before trusting it.** It has been tested, but no
  software is bug-free and this one has had no formal security audit.
- **It is provided “as is”, without warranty** (see the license, §12).
- **It does not replace the official app.** TigerSend exists because the
  official app no longer runs on these systems; it is not meant as a
  replacement on modern machines.
- Design decisions, the license choice and responsibility for what is
  published belong to the project author.

---

## 12. License and legal notes

### License: MIT

This project is released under the **MIT license** ([`LICENSE`](LICENSE),
also bundled as `TigerSend.app/Contents/Resources/LICENSE.txt`).

### Not affiliated with LocalSend

TigerSend is an independent, unofficial implementation of the publicly
documented LocalSend v2 protocol. It is not affiliated with, sponsored by or
endorsed by the LocalSend project. “LocalSend” is used only to say which
protocol this client speaks.

### Security

- This client speaks **unencrypted HTTP** out of necessity on 10.4–10.6. Use
  it **only on your own trusted LAN**.
- It accepts files automatically: check your download folder periodically and
  never run it on a network you don't trust.
- Without TLS there is no sender authentication: any machine on your network
  could send you a file. This is the same trust model the official LocalSend
  uses with encryption off.
- No telemetry, no external servers: only UDP 53317 (discovery) and TCP
  53317 (HTTP) on your local network.
