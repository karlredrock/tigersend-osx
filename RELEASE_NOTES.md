# TigerSend 1.8.1 (2.0.9-10.4)

**LocalSend protocol v2 client for Mac OS X 10.4 Tiger → modern macOS, on
PowerPC and on Intel.** Plain HTTP on port 53317, UDP multicast discovery,
Tkinter GUI, zero dependencies — it runs on the Python (2.3 – 3.x) that ships
with the system.

## What changed in 1.8.1

- **The header no longer claims "port 53317 busy" when the port is free.**
  The server label was painted *before* `engine.start()`, so a freshly opened
  window could show `Server: ERROR - port 53317 busy` in red while the HTTP
  server was in fact listening and receiving files normally — the log already
  said `HTTP server listening on 0.0.0.0:53317`. The label is now repainted
  as soon as the server has bound the port, and it is drawn by a single
  `update_server_label()` helper, so changing the language refreshes it as
  well. Two GUI tests cover it.

Nothing else changed: same protocol, same scripts, same limitations as 1.8
(documented below).

## Install

1. Download **`TigerSend-1.8.1.zip`** below and copy it to the old Mac (USB
   stick, SMB, FTP…). Always carry the ZIP, not the bare `.app` folder.
2. Double-click the ZIP to expand it and drag `TigerSend.app` to
   `/Applications`.
3. Double-click `TigerSend.app`. No Terminal window opens; if nothing
   happens, check `~/Library/Logs/TigerSend.log` and re-apply the executable
   bit once:

   ```sh
   chmod +x /Applications/TigerSend.app/Contents/MacOS/launcher
   ```

> ⚠️ **Before transferring anything**: on the phone / modern computer open
> LocalSend → Settings → **Encryption → OFF**, then restart LocalSend there.
> Tiger/Leopard/Snow Leopard cannot do modern TLS, so TigerSend only speaks
> plain HTTP.

## Checksums

See `SHA256SUMS.txt` attached to this release
(`shasum -a 256 TigerSend-1.8.1.zip`).

---

# TigerSend 1.8 (2.0.8-10.4) — previous release

**LocalSend protocol v2 client for Mac OS X 10.4 Tiger → modern macOS, on
PowerPC and on Intel.** Plain HTTP on port 53317, UDP multicast discovery,
Tkinter GUI, zero dependencies — it runs on the Python (2.3 – 3.x) that ships
with the system.

> ⚠️ **Before transferring anything**: on the phone / modern computer open
> LocalSend → Settings → **Encryption → OFF**, then restart LocalSend there.
> Tiger/Leopard/Snow Leopard cannot do modern TLS, so TigerSend only speaks
> plain HTTP.

## Install

1. Download **`TigerSend-1.8.zip`** below and copy it to the old Mac (USB
   stick, SMB, FTP…). Always carry the ZIP, not the bare `.app` folder.
2. Double-click the ZIP to expand it and drag `TigerSend.app` to
   `/Applications`.
3. Double-click `TigerSend.app`. No Terminal window opens; if nothing
   happens, check `~/Library/Logs/TigerSend.log` and re-apply the executable
   bit once:

   ```sh
   chmod +x /Applications/TigerSend.app/Contents/MacOS/launcher
   ```

Prefer building it yourself? Clone the repo on the old Mac and run
`sh build_app.sh` — it produces the same bundle.

## Highlights of this release

This release is the "make it work on Tiger, on both architectures" release.

- **Actually runs on Tiger's Python 2.3.5.** Version 1.7 claimed 2.3 support
  but could not start on it: `except`+`finally` in one `try`, ternary
  expressions in the hot paths, `HTTPServer.server_address` being empty on
  2.3, `threading.Event.is_set()`, `httplib` without timeouts, and unicode
  formatting that raised `UnicodeDecodeError` on any file name with an
  accent. All of it is gone, and the whole file is now valid Python 2.3
  syntax (checked automatically by `tests/check_legacy_syntax.py`).
- **One bundle for PowerPC and Intel.** The `.app` contains no machine code:
  a POSIX `sh` launcher picks the first interpreter that really has Tkinter
  (`pythonw` … `python3`) and runs the source. `LSMinimumSystemVersion` is
  `10.4` and `LSRequiresNativeExecution` is gone, so the same download runs
  on a G3/G4/G5 and on Intel.
- **Tiger-proof launcher.** Resolves symlinks, sets a sane `PATH` for
  Finder-launched apps, rotates `~/Library/Logs/TigerSend.log` at 1 MB, and
  shows a dialog instead of dying silently when no Python has Tk.
- **New HTTP client on raw sockets.** Timeouts work on 2.3 – 2.5 (where
  `httplib` has none), cancellations really interrupt an upload, and chunked
  / gzip / no-`Content-Length` / `204` / interim `100 Continue` responses are
  understood on every Python.
- **Correct behaviour when a request is refused.** The body is drained before
  answering `403`, so the sender sees the rejection instead of a TCP reset
  (Python 2.3 clients used to lose the answer entirely).
- **Unicode end to end.** UTF-8 names, `\uXXXX` escapes, surrogate pairs
  (emoji), BOM, Latin-1 fallback, narrow-unicode builds; `.part` files are
  renamed only after the size matches, so a cancelled transfer leaves nothing
  behind.
- **Python 3 support.** The same file runs on `python3` (with Tk), which is
  the only way to use it on macOS 12.3+ where Python 2 was removed — and it
  lets the test suite run on a modern machine.
- **Test suite + built-in self test.** `tests/test_tigersend.py` (230 – 238
  checks depending on the interpreter) exercises the protocol over real
  sockets, misbehaving servers, discovery, cancellation and the GUI (through
  a fake Tk). `python tigersend.py --self-test` does the same on the old Mac
  without needing a peer.
- **`--headless`, `--alias`, `--save-dir`, `--port`, `--announce`,
  `--self-test`** command line options. The self test now takes free ports
  from the kernel, so it can run next to a working TigerSend (or twice at
  once) without “port busy” failures.
- Five languages switchable on the fly: English, Español, Français, Deutsch,
  Português.

## Checksums

See `SHA256SUMS.txt` attached to this release (`shasum -a 256 TigerSend-1.8.zip`).

## Known limitations

- Encryption/HTTPS is not supported and cannot be on Tiger/Leopard (no `ssl`
  module). Turn encryption OFF on the other device.
- Incoming transfers are auto-accepted (no accept/reject dialog).
- SHA-256 of received files is not verified (Tiger's Python has no sha256);
  sizes are checked instead.
- The download API (`download: true`) is not implemented.

---

*TigerSend is an independent, unofficial project, not affiliated with or
endorsed by the LocalSend project. MIT license.*
