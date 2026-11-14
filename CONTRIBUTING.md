# Contributing to TigerSend

Thank you for caring. This is a small project with a very concrete goal:
**a Mac running Mac OS X 10.4 Tiger (or anything newer, on PowerPC or on
Intel) should be able to exchange files with devices that speak LocalSend
v2**.

That goal is what makes the rules below non-negotiable. A pull request that
adds a dependency, a Python-2.6-only feature or a Tk 8.5 widget is a pull
request that makes the app stop working on the machines it exists for.

## The rules

1. **Runs on Python 2.3.5** (the `/usr/bin/python` of Tiger), and on 2.4,
   2.5, 2.6, 2.7 and 3.x without changes.
   - no `pip`, `requests`, `flask`, `PyInstaller`, `py2app` — standard
     library only;
   - no syntax newer than 2.3: no `with`, no `except X as e`, no
     `a if b else c`, no generator expressions, no decorators, no set/dict
     comprehensions, no `b'…'` literals, no keyword-only arguments, and
     never `except` **and** `finally` in the same `try`;
   - no `sorted()`, `set()`, `any()`, `all()`, `bytes()`, `bytearray`,
     `str.format()`, `os.urandom`, `os.path.relpath`, `subprocess`, `uuid`,
     `socket.create_connection`, `threading.Event`, `Thread.daemon`;
   - imports that moved between Python 2 and 3 (`Tkinter`, `BaseHTTPServer`,
     `Queue`, `StringIO`…) stay inside the single compatibility block at the
     top of `tigersend.py`.
2. **The bundle stays architecture neutral.** `/bin/sh` launcher plus Python
   source, no compiled code, `LSMinimumSystemVersion=10.4`, no
   `LSRequiresNativeExecution`. `build_app.sh` verifies this.
3. **The protocol stays HTTP on port 53317** with encryption off, and the
   endpoints keep answering what the official app expects.
4. **No copied code.** Everything here is original. In particular, no code
   from GPL/LGPL projects (for example LocalSend clients for iOS), because it
   would change the license of the whole project.
5. **Keep the MIT license** and the copyright notice in copies.

## Before sending a change

```sh
sh tests/run_tests.sh                           # matrix on every Python found
python3 tests/check_legacy_syntax.py tigersend.py   # syntax + stdlib audit for 2.3
python3 tests/test_tigersend.py                 # full suite (fast)
./build_app.sh --check                          # bundle + self test
```

And, ideally, the same suite on the old interpreters. On a modern Linux or
macOS box a real CPython 2.3.5 is two commands away (see README §9); the
expected results are:

```
Python 2.3.5   223 checks passed, 0 failed
Python 2.5.6   223 checks passed, 0 failed
Python 2.7.18  229 checks passed, 0 failed
Python 3.11    231 checks passed, 0 failed
```

The suite needs no display and no peer: it starts engines on loopback and
uses `tests/fake_tk.py` for the window.

## How to report a bug

Please attach:

- the version of TigerSend (first line of the log),
- the first ten lines of `~/Library/Logs/TigerSend.log` — they contain the
  system version, the architecture, the Python in use and the port,
- **the complete log from the launch to the failure**. It is what helps most:
  it includes the file names, the HTTP status, the response body when a
  response was not JSON, and the exact step that failed,
- the other device: model, system, and its LocalSend version and encryption
  setting,
- if it is a network problem: does multicast work on your network? Does the
  same thing happen with *Scan network*?

## Ideas for later

- An accept/reject dialog for incoming transfers.
- Sending text and whole folders (the protocol supports it).
- Verifying SHA-256 when the peer offers it (only on Python 2.5+, where
  `hashlib` exists).
- The download API (`download: true`), so the phone can pull files from the
  old Mac.
- More translations: copy a table in `TR` and the test suite will tell you if
  you missed a key.
