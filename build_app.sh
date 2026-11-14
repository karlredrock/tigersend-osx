#!/bin/sh
# build_app.sh - build TigerSend.app
#
# Produces a classic Mac OS X application bundle that runs on
# Mac OS X 10.4 Tiger and every later release, on PowerPC and on Intel:
#
#   TigerSend.app/Contents/Info.plist
#   TigerSend.app/Contents/PkgInfo
#   TigerSend.app/Contents/MacOS/launcher        (a /bin/sh script)
#   TigerSend.app/Contents/Resources/tigersend.py
#   TigerSend.app/Contents/Resources/LICENSE.txt
#   TigerSend.app/Contents/Resources/AppIcon.icns
#
# There is no compiled code at all: the bundle is a shell script plus the
# Python source, so the very same .app is PowerPC and Intel native, and it
# keeps working after a Python update. The launcher picks the best
# interpreter the machine has (/usr/bin/pythonw on Tiger ... Snow Leopard,
# python3 with Tk on macOS 12.3+, where Python 2 was removed).
#
# Usage:
#   ./build_app.sh              build TigerSend.app and TigerSend-<ver>.zip
#   ./build_app.sh --no-zip     build the .app only
#   ./build_app.sh --check      build, then run the self test on this machine
#
# It runs on the old Mac itself (/bin/sh + Python 2.3) and on a modern
# machine; nothing outside the system is required.

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

APP_NAME="TigerSend"
APP_VERSION="1.8"
APP_BUILD="2.0.8-10.4"
BUNDLE_ID="org.tigersend.TigerSend"
BUNDLE_SIGNATURE="TgSd"
APP_FILE="$APP_NAME.app"
ZIP_FILE="$APP_NAME-$APP_VERSION.zip"
MAKE_ZIP=1
RUN_CHECK=0

for option in "$@"; do
    case "$option" in
        --no-zip)  MAKE_ZIP=0 ;;
        --zip)     MAKE_ZIP=1 ;;
        --check)   RUN_CHECK=1 ;;
        --help|-h)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $option (try --help)" >&2
            exit 1
            ;;
    esac
done

CONTENTS_DIR="$APP_FILE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "==> TigerSend $APP_VERSION ($APP_BUILD)"
echo "    bundle: $SCRIPT_DIR/$APP_FILE"

# ---------------------------------------------------------------------------
#  0. Sanity checks
# ---------------------------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/tigersend.py" ]; then
    echo "ERROR: tigersend.py not found in $SCRIPT_DIR" >&2
    exit 1
fi
if [ ! -f "$SCRIPT_DIR/LICENSE" ]; then
    echo "WARNING: LICENSE not found; the bundle will not carry the license" >&2
fi

# ---------------------------------------------------------------------------
#  1. Clean the previous build
# ---------------------------------------------------------------------------
rm -rf "$APP_FILE"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# ---------------------------------------------------------------------------
#  2. Payload
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/tigersend.py" "$RESOURCES_DIR/tigersend.py"
chmod 644 "$RESOURCES_DIR/tigersend.py"

if [ -f "$SCRIPT_DIR/LICENSE" ]; then
    cp "$SCRIPT_DIR/LICENSE" "$RESOURCES_DIR/LICENSE.txt"
    chmod 644 "$RESOURCES_DIR/LICENSE.txt"
fi

# ---------------------------------------------------------------------------
#  3. Info.plist
#
#  LSMinimumSystemVersion is 10.4: Tiger. There is deliberately no
#  LSRequiresNativeExecution and no architecture key, because the bundle
#  holds no machine code: it is architecture neutral by construction.
# ---------------------------------------------------------------------------
cat > "$CONTENTS_DIR/Info.plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleDisplayName</key>
	<string>$APP_NAME</string>
	<key>CFBundleExecutable</key>
	<string>launcher</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>CFBundleIdentifier</key>
	<string>$BUNDLE_ID</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$APP_NAME</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>$APP_BUILD</string>
	<key>CFBundleSignature</key>
	<string>$BUNDLE_SIGNATURE</string>
	<key>CFBundleVersion</key>
	<string>$APP_VERSION</string>
	<key>LSMinimumSystemVersion</key>
	<string>10.4</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSHumanReadableCopyright</key>
	<string>MIT License - an independent LocalSend v2 client, not affiliated with the LocalSend project.</string>
</dict>
</plist>
PLISTEOF

# Classic PkgInfo: APPL + 4 character signature
printf 'APPL%s' "$BUNDLE_SIGNATURE" > "$CONTENTS_DIR/PkgInfo"

# ---------------------------------------------------------------------------
#  4. launcher
#
#  POSIX sh only: Tiger ships /bin/sh and nothing else is guaranteed.
#  It finds a Python with working Tkinter, so the same bundle works with the
#  system Python 2.3.5 (Tiger), 2.5 (Leopard), 2.6 (Snow Leopard), 2.7
#  (Lion ... Big Sur), and python3 on macOS 12.3+ where Python 2 was removed.
# ---------------------------------------------------------------------------
cat > "$MACOS_DIR/launcher" <<'LAUNCHEREOF'
#!/bin/sh
# TigerSend launcher - resolves the bundle, picks a Python with Tkinter,
# logs to ~/Library/Logs/TigerSend.log and starts the app.

# --- where are we? (also works when the .app is moved or symlinked) --------
SELF="$0"
if [ -L "$SELF" ] && command -v readlink >/dev/null 2>&1; then
    TARGET=$(readlink "$SELF" 2>/dev/null) || TARGET=""
    if [ -n "$TARGET" ]; then
        case "$TARGET" in
            /*) SELF="$TARGET" ;;
            *)  SELF="$(dirname "$SELF")/$TARGET" ;;
        esac
    fi
fi
MACOS_DIR=$(cd -P "$(dirname "$SELF")" 2>/dev/null && pwd) || \
    MACOS_DIR=$(dirname "$SELF")
RESOURCES_DIR="$MACOS_DIR/../Resources"
SCRIPT="$RESOURCES_DIR/tigersend.py"

# Finder starts applications with a nearly empty PATH
PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:$PATH"
export PATH

LOG_DIR="$HOME/Library/Logs"
LOG_FILE="$LOG_DIR/TigerSend.log"
mkdir -p "$LOG_DIR" 2>/dev/null

# Keep the log small: one rotation at 1 MB (old Macs have small disks)
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null | tr -d ' ')
    case "$LOG_SIZE" in
        ''|*[!0-9]*) LOG_SIZE=0 ;;
    esac
    if [ "$LOG_SIZE" -gt 1048576 ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null
    fi
fi

{
    echo ""
    echo "==== $(date) ===="
    echo "launcher: $SELF"
    echo "bundle:   $MACOS_DIR"
    echo "system:   $(uname -sr) / $(uname -m)"
} >> "$LOG_FILE" 2>&1

# --- pick an interpreter that actually has Tkinter ------------------------
CANDIDATES="/usr/bin/pythonw
/usr/bin/pythonw2.7
/usr/bin/pythonw2.6
/usr/bin/pythonw2.5
/usr/bin/pythonw2.3
/usr/bin/python
/Library/Frameworks/Python.framework/Versions/Current/bin/pythonw
/Library/Frameworks/Python.framework/Versions/Current/bin/python3
/usr/local/bin/pythonw
/usr/local/bin/python3
/opt/homebrew/bin/python3
/usr/bin/python3
/opt/local/bin/python3"

PYTHON=""
HAVE_TK=0
for candidate in $CANDIDATES; do
    if [ -x "$candidate" ]; then
        if "$candidate" -c "import Tkinter" >/dev/null 2>&1; then
            PYTHON="$candidate"
            HAVE_TK=1
            break
        fi
        if "$candidate" -c "import tkinter" >/dev/null 2>&1; then
            PYTHON="$candidate"
            HAVE_TK=1
            break
        fi
    fi
done

# No Tk anywhere: run headless rather than not starting at all (receiving
# files from a Terminal still works), and tell the user what happened.
if [ -z "$PYTHON" ]; then
    for candidate in /usr/bin/python /usr/bin/python3 \
                     /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$candidate" ]; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    {
        echo "ERROR: no Python interpreter found."
        echo "TigerSend needs the Python that ships with Mac OS X"
        echo "(/usr/bin/python on 10.4 - 12.2) or python3 with Tk."
    } >> "$LOG_FILE" 2>&1
    /usr/bin/osascript -e 'display dialog "TigerSend could not find a Python interpreter on this Mac.\n\nSee ~/Library/Logs/TigerSend.log" buttons {"OK"} default button 1 with icon caution' >/dev/null 2>&1
    exit 1
fi

echo "python:   $PYTHON ($("$PYTHON" -V 2>&1 | head -1))" >> "$LOG_FILE" 2>&1

# --- Finder or Terminal? ---------------------------------------------------
# Double clicking gives the app no usable stdout, so everything goes to the
# log. Started from a Terminal with an informative option, the user expects
# to see the output there instead.
INTERACTIVE=0
case " $* " in
    *" --help "*|*" -h "*)        INTERACTIVE=1 ;;
    *" --version "*|*" -V "*)     INTERACTIVE=1 ;;
    *" --self-test "*)            INTERACTIVE=1 ;;
    *" --announce "*)             INTERACTIVE=1 ;;
esac

if [ "$HAVE_TK" -eq 0 ]; then
    echo "WARNING: this Python has no Tkinter; starting in headless mode" >> "$LOG_FILE" 2>&1
    if [ "$INTERACTIVE" -eq 0 ]; then
        /usr/bin/osascript -e 'display dialog "This Mac has no Tkinter (the Tk binding for Python), so TigerSend cannot open its window.\n\nIt will keep running in the background so other devices can still send files to it.\n\nSee ~/Library/Logs/TigerSend.log" buttons {"OK"} default button 1 with icon caution' >/dev/null 2>&1
    fi
    cd "$RESOURCES_DIR" 2>/dev/null
    if [ "$INTERACTIVE" -eq 1 ]; then
        exec "$PYTHON" "$SCRIPT" --headless "$@"
    fi
    exec "$PYTHON" "$SCRIPT" --headless "$@" >> "$LOG_FILE" 2>&1
fi

# --- run ------------------------------------------------------------------
# Arguments Finder adds (-psn_...) are ignored by tigersend.py itself.
cd "$RESOURCES_DIR" 2>/dev/null
if [ "$INTERACTIVE" -eq 1 ]; then
    exec "$PYTHON" "$SCRIPT" "$@"
fi
exec "$PYTHON" "$SCRIPT" "$@" >> "$LOG_FILE" 2>&1
LAUNCHEREOF

chmod 755 "$MACOS_DIR/launcher"

# ---------------------------------------------------------------------------
#  5. Icon
#
#  Uses sips/iconutil when available (10.6+). Otherwise a pure-Python
#  generator writes an .icns with the sizes Tiger understands
#  (icp4 16, icp5 32, ic07 128, ic08 256) plus 512 for newer systems.
# ---------------------------------------------------------------------------
ICON_SRC=""
for candidate in "$SCRIPT_DIR/icon.png" "$SCRIPT_DIR/AppIcon.png" \
                 "$SCRIPT_DIR/icon.jpg" "$SCRIPT_DIR/icon.jpeg"; do
    if [ -f "$candidate" ]; then
        ICON_SRC="$candidate"
        break
    fi
done

ICON_OK=0
if [ -n "$ICON_SRC" ] && command -v sips >/dev/null 2>&1 && \
   command -v iconutil >/dev/null 2>&1; then
    echo "==> icon: converting $ICON_SRC with sips/iconutil"
    ICONSET_DIR="${TMPDIR:-/tmp}/TigerSend.iconset.$$"
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$ICON_SRC" \
            --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null 2>&1 || true
    done
    if iconutil -c icns "$ICONSET_DIR" \
            -o "$RESOURCES_DIR/AppIcon.icns" >/dev/null 2>&1; then
        ICON_OK=1
        echo "    ok"
    else
        echo "    iconutil failed, using the built-in icon"
    fi
    rm -rf "$ICONSET_DIR"
fi

if [ "$ICON_OK" -ne 1 ]; then
    echo "==> icon: generating the built-in icon (no external tools needed)"
    PYTHON_BIN=""
    for candidate in python3 python /usr/bin/python /usr/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
    if [ -n "$PYTHON_BIN" ]; then
        ICON_SRC="$ICON_SRC" ICNS_OUT="$RESOURCES_DIR/AppIcon.icns" \
        "$PYTHON_BIN" - <<'PYEOF' || true
# Pure-stdlib .icns writer. Runs on Python 2.3 (Tiger) and on Python 3:
# no b'...' literals, no bytearray, no ternaries, nothing newer than 2.3.
# zlib is used when the interpreter has it (Apple's Python always does) and a
# stored-block deflate stream is written by hand when it is missing.
import os
import struct
import sys

PY3 = sys.version_info[0] >= 3
PNG_MAGIC = '\x89PNG\r\n\x1a\n'


def raw(text):
    """str -> the byte-string type of this Python."""
    if PY3:
        if isinstance(text, bytes):
            return text
        return text.encode('latin-1')
    return text


def to_raw(values):
    """list of ints -> bytes."""
    if PY3:
        return bytes(values)
    out = []
    for value in values:
        out.append(chr(value))
    return ''.join(out)


def adler32(data):
    first = 1
    second = 0
    for item in data:
        if not isinstance(item, int):
            item = ord(item)
        first = (first + item) % 65521
        second = (second + first) % 65521
    return (second << 16) | first


def stored_deflate(data):
    """A valid zlib stream with no compression at all (needs no zlib)."""
    pieces = [raw('\x78\x01')]
    position = 0
    total = len(data)
    if total == 0:
        return raw('\x78\x01') + struct.pack('<BHH', 1, 0, 65535) + \
            struct.pack('>I', adler32(data))
    while position < total:
        chunk = data[position:position + 65535]
        final = 0
        if position + 65535 >= total:
            final = 1
        pieces.append(struct.pack('<BHH', final, len(chunk),
                                  len(chunk) ^ 0xffff))
        pieces.append(chunk)
        position = position + 65535
    pieces.append(struct.pack('>I', adler32(data)))
    return raw('').join(pieces)


try:
    import zlib

    def compress(data):
        return zlib.compress(data, 9)
except ImportError:
    def compress(data):
        return stored_deflate(data)


def png_chunk(kind, data):
    body = struct.pack('>I', len(data)) + raw(kind) + data
    crc = 0
    try:
        import zlib as _zlib
        crc = _zlib.crc32(raw(kind) + data) & 0xffffffff
    except ImportError:
        crc = crc32_manual(raw(kind) + data)
    return body + struct.pack('>I', crc)


def crc32_manual(data):
    table = []
    for index in range(256):
        value = index
        step = 0
        while step < 8:
            if value & 1:
                value = 0xedb88320 ^ (value >> 1)
            else:
                value = value >> 1
            step = step + 1
        table.append(value)
    crc = 0xffffffff
    for item in data:
        if not isinstance(item, int):
            item = ord(item)
        crc = table[(crc ^ item) & 0xff] ^ (crc >> 8)
    return crc ^ 0xffffffff


def make_png(size):
    """Blue rounded square with a white upload arrow, drawn by hand.

    Geometry only, so the same code produces a clean 16x16 and a clean
    512x512 without any image library.
    """
    border = max(1, size // 14)
    radius = (size * 3) // 10
    centre = (size - 1) / 2.0
    # arrow shaft
    shaft_half = size * 0.085
    shaft_top = size * 0.42
    shaft_bottom = size * 0.76
    # arrow head (triangle)
    head_apex = size * 0.22
    head_base = size * 0.52
    head_half = size * 0.27
    rows = []
    for y in range(size):
        row = [0]                          # PNG filter type: none
        for x in range(size):
            dx = x - centre
            dy = y - centre
            inside = border <= x < size - border and \
                border <= y < size - border
            if not inside or (dx * dx + dy * dy) > (radius * radius):
                row.extend((0, 0, 0, 0))                # transparent
                continue
            white = 0
            if abs(dx) <= shaft_half and shaft_top <= y <= shaft_bottom:
                white = 1                               # shaft
            if head_apex <= y <= head_base:
                # width of the triangle at this height
                limit = head_half * (y - head_apex) / (head_base - head_apex)
                if abs(dx) <= limit:
                    white = 1
            if white:
                row.extend((252, 252, 252, 255))
            else:
                row.extend((28, 118, 210, 255))         # TigerSend blue
        rows.append(to_raw(row))
    pixels = raw('').join(rows)
    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return (raw(PNG_MAGIC) + png_chunk('IHDR', header)
            + png_chunk('IDAT', compress(pixels))
            + png_chunk('IEND', raw('')))


source = os.environ.get('ICON_SRC') or ''
images = {}
if source and os.path.isfile(source):
    try:
        handle = open(source, 'rb')
        try:
            data = handle.read()
        finally:
            handle.close()
        if data[:8] == raw(PNG_MAGIC):
            images[512] = data
    except Exception:
        pass

for dimension in (16, 32, 64, 128, 256, 512):
    if dimension not in images:
        images[dimension] = make_png(dimension)

# icp4/icp5/ic07/ic08 are understood by Tiger, ic09 by 10.5 and later
entries = (('icp4', images[16]), ('icp5', images[32]), ('ic07', images[128]),
           ('ic08', images[256]), ('ic09', images[512]))

pieces = []
for kind, payload in entries:
    pieces.append(raw(kind) + struct.pack('>I', len(payload) + 8) + payload)
body = raw('').join(pieces)
icns = raw('icns') + struct.pack('>I', len(body) + 8) + body

target = os.environ.get('ICNS_OUT') or 'AppIcon.icns'
handle = open(target, 'wb')
try:
    handle.write(icns)
finally:
    handle.close()
print('    %s (%d bytes)' % (target, len(icns)))
PYEOF
    fi
    if [ ! -s "$RESOURCES_DIR/AppIcon.icns" ]; then
        printf 'icns\000\000\000\010' > "$RESOURCES_DIR/AppIcon.icns"
        echo "    (minimal icns written)"
    fi
fi

# ---------------------------------------------------------------------------
#  6. Verify the bundle
# ---------------------------------------------------------------------------
echo "==> verifying"
PROBLEMS=0

for required in "$CONTENTS_DIR/Info.plist" "$CONTENTS_DIR/PkgInfo" \
                "$MACOS_DIR/launcher" "$RESOURCES_DIR/tigersend.py" \
                "$RESOURCES_DIR/AppIcon.icns"; do
    if [ ! -e "$required" ]; then
        echo "    MISSING: $required" >&2
        PROBLEMS=1
    fi
done

if [ ! -x "$MACOS_DIR/launcher" ]; then
    echo "    launcher is not executable" >&2
    PROBLEMS=1
fi

if ! sh -n "$MACOS_DIR/launcher" 2>/dev/null; then
    echo "    launcher has a shell syntax error" >&2
    PROBLEMS=1
fi

if ! grep -q '<string>10.4</string>' "$CONTENTS_DIR/Info.plist"; then
    echo "    LSMinimumSystemVersion is not 10.4" >&2
    PROBLEMS=1
fi
if grep -q 'LSRequiresNativeExecution' "$CONTENTS_DIR/Info.plist"; then
    echo "    LSRequiresNativeExecution must not be set (PPC/Intel neutral)" >&2
    PROBLEMS=1
fi
if command -v plutil >/dev/null 2>&1; then
    if ! plutil -lint "$CONTENTS_DIR/Info.plist" >/dev/null 2>&1; then
        echo "    plutil rejects Info.plist" >&2
        PROBLEMS=1
    fi
fi

# No machine code anywhere: that is what makes one download work on PowerPC
# and on Intel.
BINARY_FILES=$(find "$APP_FILE" -type f -perm -0100 2>/dev/null | \
               grep -v 'MacOS/launcher' || true)
if [ -n "$BINARY_FILES" ]; then
    echo "    unexpected executable files: $BINARY_FILES" >&2
    PROBLEMS=1
fi

if [ "$PROBLEMS" -ne 0 ]; then
    echo "ERROR: the bundle is not complete" >&2
    exit 1
fi
echo "    ok"

# ---------------------------------------------------------------------------
#  7. Optional: run the built-in protocol self test right here
# ---------------------------------------------------------------------------
if [ "$RUN_CHECK" -eq 1 ]; then
    PYTHON_BIN=""
    for candidate in python3 /usr/bin/python python /usr/bin/python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
    if [ -n "$PYTHON_BIN" ]; then
        echo "==> self test with $PYTHON_BIN"
        "$PYTHON_BIN" "$RESOURCES_DIR/tigersend.py" --self-test
    else
        echo "WARNING: no Python found, skipping the self test" >&2
    fi
fi

# ---------------------------------------------------------------------------
#  8. ZIP (the safe way to carry a bundle to an old Mac)
#
#  ditto on macOS keeps permissions and resource forks; plain zip is the
#  fallback when building on Linux.
# ---------------------------------------------------------------------------
if [ "$MAKE_ZIP" -eq 1 ]; then
    echo "==> packaging $ZIP_FILE"
    rm -f "$ZIP_FILE"
    if command -v ditto >/dev/null 2>&1; then
        ditto -c -k --sequesterRsrc --keepParent "$APP_FILE" "$ZIP_FILE"
    else
        zip -qry "$ZIP_FILE" "$APP_FILE"
    fi
    ls -l "$ZIP_FILE"

    # SHA256SUMS.txt, best effort: the old Macs may only have openssl
    rm -f SHA256SUMS.txt
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$ZIP_FILE" > SHA256SUMS.txt 2>/dev/null || rm -f SHA256SUMS.txt
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$ZIP_FILE" > SHA256SUMS.txt 2>/dev/null || rm -f SHA256SUMS.txt
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$ZIP_FILE" 2>/dev/null > SHA256SUMS.txt || rm -f SHA256SUMS.txt
    fi
    if [ -s SHA256SUMS.txt ]; then
        echo "  checksum -> SHA256SUMS.txt"
        cat SHA256SUMS.txt
    fi
fi

echo ""
echo "Done:"
echo "  $SCRIPT_DIR/$APP_FILE"
if [ "$MAKE_ZIP" -eq 1 ]; then
    echo "  $SCRIPT_DIR/$ZIP_FILE"
    if [ -s SHA256SUMS.txt ]; then
        echo "  $SCRIPT_DIR/SHA256SUMS.txt"
    fi
fi
echo ""
echo "Copy the ZIP (not the bare .app) to the old Mac, expand it, drag"
echo "TigerSend.app to /Applications and double click it."
echo "Log: ~/Library/Logs/TigerSend.log"
