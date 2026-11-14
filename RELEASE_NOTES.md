# TigerSend 1.7 (2.0.7-10.4)

**LocalSend protocol v2 client for Mac OS X 10.4 Tiger → 10.6 Snow Leopard.**
Plain HTTP on port 53317, UDP multicast discovery, Tkinter GUI, zero
dependencies — it runs on the Python (2.3–2.7) that ships with the system.

> ⚠️ **Before transferring anything**: on the phone / modern computer open
> LocalSend → Settings → **Encryption → OFF**, then restart LocalSend there.
> Old Mac OS X cannot do modern TLS, so TigerSend only speaks plain HTTP.

## Install

1. Download **`TigerSend-1.7.zip`** below and copy it to the old Mac
   (USB stick, SMB, FTP…). Always carry the ZIP, not the bare `.app` folder.
2. Double-click the ZIP to expand it and drag `TigerSend.app` to
   `/Applications`.
3. Double-click `TigerSend.app`. No Terminal window opens; if nothing
   happens, check `~/Library/Logs/TigerSend.log` and re-apply the executable
   bit once:

   ```sh
   chmod +x /Applications/TigerSend.app/Contents/MacOS/launcher
   ```

Prefer building it yourself? Clone the repo on the old Mac and run
`sh build_app.sh` — it produces the exact same bundle.

## Highlights of this release

- **Renamed to TigerSend** (was SnowSend) and **minimum system lowered to
  Mac OS X 10.4 Tiger**: Python 2.3/2.4 compatible — bundled mini JSON
  codec (no `json` module before 2.6), `hashlib` → `md5` fallback, device
  table drawn with a monospaced `Listbox` (Tk 8.4 has no Treeview), no
  Python-2.5+ syntax anywhere.
- **Settings persist** in `~/.tigersend_config.json`: alias, language,
  download folder and the device fingerprint (the Mac stays the same device
  in the phone's list across launches).
- **Chunked reception** (`Transfer-Encoding: chunked`, what iOS sends) with
  streaming to disk, plus explicit `Expect: 100-continue` handling.
- **macOS/BSD multicast fix**: `IP_MULTICAST_IF` on announce, `INADDR_ANY`
  listener (avoids `[Errno 49]`).
- Five languages switchable on the fly: English, Español, Français,
  Deutsch, Português.
- File queue, Paste Clipboard, mid-transfer Cancel with `POST /cancel`,
  activity log, subnet scanner — see the README for the full tour.

## Checksums

See `SHA256SUMS.txt` attached to this release.

## Known limitations

- Encryption/HTTPS is not supported (planned for a later major version).
- Incoming transfers are auto-accepted (no accept/reject dialog).
- SHA-256 of received files is not verified (Tiger's Python has no sha256);
  sizes are checked instead.

---

*TigerSend is an independent, unofficial project, not affiliated with or
endorsed by LocalSend or Apple Inc. Use it only on your own trusted local
network. MIT licensed.*
