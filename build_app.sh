#!/bin/sh
#
#  build_app.sh - packages TigerSend as a double-clickable Mac OS X .app bundle
#
#  Works on Mac OS X 10.4 Tiger through 10.6 Snow Leopard (and later).
#  Uses only /bin/sh features available on Tiger (backticks, no bashisms).
#
#  Result:
#    TigerSend.app/
#      Contents/
#        Info.plist                    <- LSMinimumSystemVersion 10.4
#        PkgInfo
#        MacOS/launcher                <- shell stub, no Terminal window
#        Resources/tigersend.py        <- the actual program
#        Resources/LICENSE.txt         <- MIT license
#
#  The launcher execs "pythonw", the windowed Python interpreter that Apple
#  ships with every Mac OS X release, and redirects stdout/stderr to
#  ~/Library/Logs/TigerSend.log. Because the Finder starts the bundle
#  executable directly (not through Terminal.app), no Terminal window ever
#  appears; pythonw connects the process to the WindowServer so the Tk GUI
#  comes up in front with a proper Dock icon.
#

APP_NAME="TigerSend"
APP_VERSION="1.7"
BUNDLE_ID="org.tigersend.TigerSend"
MIN_SYSTEM="10.4"          # change to 10.6 if you only target Snow Leopard

HERE=`cd \`dirname "$0"\` && pwd`
SRC="$HERE/tigersend.py"
APP="$HERE/$APP_NAME.app"

if [ ! -f "$SRC" ]; then
    echo "error: tigersend.py not found next to build_app.sh" >&2
    exit 1
fi

echo "* cleaning previous bundle"
rm -rf "$APP"

echo "* creating bundle structure"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"

echo "* copying tigersend.py"
cp "$SRC" "$APP/Contents/Resources/tigersend.py"

if [ -f "$HERE/LICENSE" ]; then
    echo "* copying LICENSE"
    cp "$HERE/LICENSE" "$APP/Contents/Resources/LICENSE.txt"
fi

# ---------------------------------------------------------------------------
#  launcher stub (Contents/MacOS/launcher)
# ---------------------------------------------------------------------------
echo "* writing launcher"
cat > "$APP/Contents/MacOS/launcher" <<'LAUNCHER_EOF'
#!/bin/sh
# TigerSend launcher - started directly by the Finder, so no Terminal window.
DIR=`cd \`dirname "$0"\`/../Resources && pwd`

# Prefer pythonw (GUI-enabled interpreter shipped by Apple on every release).
PY=""
for CAND in /usr/bin/pythonw /usr/local/bin/pythonw \
            /usr/bin/pythonw2.7 /usr/bin/pythonw2.6 \
            /usr/bin/pythonw2.5 /usr/bin/pythonw2.4 /usr/bin/pythonw2.3 \
            /usr/bin/python /usr/local/bin/python
do
    if [ -x "$CAND" ]; then
        PY="$CAND"
        break
    fi
done
if [ -z "$PY" ]; then
    PY=pythonw
fi

# Keep a log so a failed start can be diagnosed without a Terminal.
LOGDIR="$HOME/Library/Logs"
mkdir -p "$LOGDIR" 2>/dev/null
LOG="$LOGDIR/TigerSend.log"

exec "$PY" "$DIR/tigersend.py" >> "$LOG" 2>&1
LAUNCHER_EOF
chmod +x "$APP/Contents/MacOS/launcher"

# ---------------------------------------------------------------------------
#  Info.plist
# ---------------------------------------------------------------------------
echo "* writing Info.plist"
cat > "$APP/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>English</string>
	<key>CFBundleExecutable</key>
	<string>launcher</string>
	<key>CFBundleIdentifier</key>
	<string>$BUNDLE_ID</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$APP_NAME</string>
	<key>CFBundleDisplayName</key>
	<string>$APP_NAME</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleSignature</key>
	<string>TgSd</string>
	<key>CFBundleShortVersionString</key>
	<string>$APP_VERSION</string>
	<key>CFBundleVersion</key>
	<string>$APP_VERSION</string>
	<key>LSMinimumSystemVersion</key>
	<string>$MIN_SYSTEM</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>LSUIElement</key>
	<false/>
	<key>NSHumanReadableCopyright</key>
	<string>TigerSend $APP_VERSION - LocalSend protocol v2 client - MIT License</string>
</dict>
</plist>
PLIST_EOF

# ---------------------------------------------------------------------------
#  PkgInfo (classic Mac OS type/creator stamp)
# ---------------------------------------------------------------------------
echo "* writing PkgInfo"
printf 'APPLTgSd' > "$APP/Contents/PkgInfo"

# Make the Finder notice the fresh bundle (harmless if touch is limited)
touch "$APP" 2>/dev/null

echo ""
echo "Done: $APP"
echo "  - double-click TigerSend.app in the Finder to launch the GUI"
echo "  - no Terminal window will open (launcher + pythonw)"
echo "  - start-up log: ~/Library/Logs/TigerSend.log"
echo "  - minimum system: Mac OS X $MIN_SYSTEM"
