#!/bin/sh
# build_app.sh - Empaqueta SnowSend.app para Mac OS X 10.6 Snow Leopard
# Uso:  ./build_app.sh
# Requisitos en el Mac: /bin/sh, /usr/bin/python (2.6/2.7), sips/iconutil (opcionales)
# En Linux (sandbox) el paquete tambien se genera; sips/iconutil se omiten
# y se crea un icono placeholder en Python puro, para que el build nunca falle.
set -e

# Directorio donde esta este script (y snowsend.py)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="SnowSend.app"
APP_DIR="$SCRIPT_DIR/$APP_NAME"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "==> Construyendo $APP_NAME en $SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/snowsend.py" ]; then
    echo "ERROR: no se encontro snowsend.py en $SCRIPT_DIR" >&2
    exit 1
fi

# Limpiar build anterior
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# Codigo principal
cp "$SCRIPT_DIR/snowsend.py" "$RESOURCES_DIR/snowsend.py"
chmod 644 "$RESOURCES_DIR/snowsend.py"

# Licencia y creditos dentro del paquete (requisito de distribucion)
if [ -f "$SCRIPT_DIR/LICENSE" ]; then
    cp "$SCRIPT_DIR/LICENSE" "$RESOURCES_DIR/LICENSE.txt"
    chmod 644 "$RESOURCES_DIR/LICENSE.txt"
fi

# --- Info.plist (10.6) -------------------------------------------------------
cat > "$CONTENTS_DIR/Info.plist" <<'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleIdentifier</key>
	<string>org.snowsend.SnowSend</string>
	<key>CFBundleName</key>
	<string>SnowSend</string>
	<key>CFBundleDisplayName</key>
	<string>SnowSend</string>
	<key>CFBundleExecutable</key>
	<string>launcher</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleSignature</key>
	<string>????</string>
	<key>CFBundleVersion</key>
	<string>1.7</string>
	<key>CFBundleShortVersionString</key>
	<string>2.0.7-10.6</string>
	<key>LSMinimumSystemVersion</key>
	<string>10.6</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>LSRequiresNativeExecution</key>
	<true/>
</dict>
</plist>
PLISTEOF

# PkgInfo clasico
printf 'APPL????' > "$CONTENTS_DIR/PkgInfo"

# --- launcher ---------------------------------------------------------------
# Resuelve su propia ruta con dirname "$0", redirige stdout/stderr a
# ~/Library/Logs/SnowSend.log (sin abrir Terminal al hacer doble clic)
# y lanza /usr/bin/python con el script de Resources.
cat > "$MACOS_DIR/launcher" <<'LAUNCHEREOF'
#!/bin/sh
# SnowSend - launcher
# Resuelve la ruta de este script (Contents/MacOS) de forma relativa.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$SCRIPT_DIR/../Resources"
mkdir -p "$HOME/Library/Logs"
exec /usr/bin/python "$RESOURCES_DIR/snowsend.py" >>"$HOME/Library/Logs/SnowSend.log" 2>&1
LAUNCHEREOF
chmod +x "$MACOS_DIR/launcher"

# --- Icono ------------------------------------------------------------------
# Si existe icon.png y estan sips/iconutil (Mac), convertir a AppIcon.icns
# (maximo 512x512 para compatibilidad con 10.6). Si no, generar un
# placeholder automatico en Python puro para que el paquete nunca falle.
ICON_SRC=""
for candidate in "$SCRIPT_DIR/icon.png" "$SCRIPT_DIR/AppIcon.png" "$SCRIPT_DIR/icon.jpg" "$SCRIPT_DIR/icon.jpeg"; do
    if [ -f "$candidate" ]; then
        ICON_SRC="$candidate"
        break
    fi
done

ICON_OK=0
if [ -n "$ICON_SRC" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    echo "==> Convirtiendo icono $ICON_SRC con sips/iconutil..."
    TMP_ICONSET="$(mktemp -d 2>/dev/null || echo /tmp/ls_iconset_$$)"
    ICONSET_DIR="$TMP_ICONSET/AppIcon.iconset"
    mkdir -p "$ICONSET_DIR"
    # sips -z alto ancho (maximo 512 para 10.6)
    sips -z 16 16   "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1 || true
    sips -z 32 32   "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1 || true
    sips -z 32 32   "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1 || true
    sips -z 64 64   "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1 || true
    sips -z 128 128 "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1 || true
    sips -z 256 256 "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1 || true
    sips -z 256 256 "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1 || true
    sips -z 512 512 "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1 || true
    sips -z 512 512 "$ICON_SRC" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1 || true
    if iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns" 2>/dev/null; then
        ICON_OK=1
        echo "    Icono generado con iconutil."
    else
        echo "    iconutil fallo, se usara el placeholder."
    fi
    rm -rf "$TMP_ICONSET"
fi

if [ "$ICON_OK" -ne 1 ]; then
    echo "==> Generando icono placeholder (AppIcon.icns)..."
    # Detectar un python disponible (python3 en Linux, /usr/bin/python en Mac)
    PYTHON_BIN=""
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    elif [ -x /usr/bin/python ]; then
        PYTHON_BIN="/usr/bin/python"
    fi
    if [ -n "$PYTHON_BIN" ]; then
        # Generador PNG/icns en Python puro (sin PIL), compatible Py2/Py3.
        # Si hay un icon.png PNG valido, lo incrusta como entrada de 512px;
        # si no, dibuja un placeholder azul con circulo blanco.
        ICON_SRC="$ICON_SRC" ICNS_OUT="$RESOURCES_DIR/AppIcon.icns" "$PYTHON_BIN" <<'PYEOF' || true
import os, sys, struct, zlib

def chunk(typ, data):
    c = struct.pack(">I", len(data)) + typ + data
    crc = zlib.crc32(typ + data) & 0xffffffff
    return c + struct.pack(">I", crc)

def make_png(size):
    raw = bytearray()
    border = max(1, size // 32)
    cx = size // 2
    cy = size // 2
    rad = (size * 3) // 10
    for y in range(size):
        raw.append(0)
        for x in range(size):
            if x < border or y < border or x >= size - border or y >= size - border:
                r, g, b = 255, 255, 255
            else:
                dx = x - cx
                dy = y - cy
                if dx * dx + dy * dy <= rad * rad:
                    r, g, b = 255, 255, 255
                else:
                    r, g, b = 30, 120, 215
            raw.extend((r, g, b))
    if sys.version_info[0] >= 3:
        raw_bytes = bytes(raw)
    else:
        raw_bytes = str(raw)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw_bytes, 9)) + chunk(b"IEND", b""))

icon_src = os.environ.get("ICON_SRC") or ""
png_by_size = {}
# Si el icono fuente es un PNG, usarlo tal cual para 512px.
if icon_src and os.path.isfile(icon_src):
    try:
        f = open(icon_src, "rb")
        try:
            data = f.read()
        finally:
            f.close()
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            png_by_size[512] = data
    except Exception:
        pass

for sz in (16, 32, 64, 128, 256, 512):
    if sz not in png_by_size:
        png_by_size[sz] = make_png(sz)

entries = [
    (b"icp4", png_by_size[16]),
    (b"icp5", png_by_size[32]),
    (b"ic07", png_by_size[128]),
    (b"ic08", png_by_size[256]),
    (b"ic09", png_by_size[512]),
    (b"ic11", png_by_size[32]),
    (b"ic12", png_by_size[64]),
    (b"ic13", png_by_size[256]),
]
body = b""
for typ, png in entries:
    body += typ + struct.pack(">I", len(png) + 8) + png
icns = b"icns" + struct.pack(">I", len(body) + 8) + body
out = os.environ.get("ICNS_OUT") or "AppIcon.icns"
f = open(out, "wb")
try:
    f.write(icns)
finally:
    f.close()
print("placeholder icns escrito: %s (%d bytes)" % (out, len(icns)))
PYEOF
    fi
    # Ultimo recurso si Python no estaba: cabecera icns minima valida.
    if [ ! -s "$RESOURCES_DIR/AppIcon.icns" ]; then
        printf 'icns\000\000\000\010' > "$RESOURCES_DIR/AppIcon.icns"
        echo "    (icono minimo creado)"
    fi
fi

echo "==> Verificacion del paquete:"
ls -l "$CONTENTS_DIR/Info.plist" "$MACOS_DIR/launcher" "$RESOURCES_DIR/snowsend.py" "$RESOURCES_DIR/AppIcon.icns"
echo ""
echo "Listo: $APP_DIR"
echo "En el Mac con Snow Leopard: doble clic en SnowSend.app"
echo "Registro (si algo falla): ~/Library/Logs/SnowSend.log"
