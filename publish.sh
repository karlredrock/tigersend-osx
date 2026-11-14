#!/bin/sh
# publish.sh - Crea el repositorio en GitHub y sube SnowSend.
#
# Uso:
#   ./publish.sh                      # publico, con el nombre de la carpeta
#   ./publish.sh --private            # repositorio privado
#   ./publish.sh --name snowsend-10.6 # otro nombre de repo
#   ./publish.sh --release            # ademas crea un Release con SnowSend.zip
#
# Requiere UNA de estas dos cosas:
#   A) GitHub CLI autenticado:   gh auth login
#   B) Un token con permiso de crear repositorios, en la variable GITHUB_TOKEN:
#      export GITHUB_TOKEN=ghp_xxx   (o un fine-grained token con "Administration: write")
#
# El token nunca se guarda en el repositorio ni en el historial de git.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

REPO_NAME="snowsend"
VISIBILITY="public"
DO_RELEASE=0
DESCRIPTION="Cliente del protocolo LocalSend v2 para Mac OS X 10.6 Snow Leopard (Python 2.6/2.7, sin dependencias)"
HOMEPAGE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --private) VISIBILITY="private"; shift ;;
        --public)  VISIBILITY="public"; shift ;;
        --name)    REPO_NAME="$2"; shift 2 ;;
        --release) DO_RELEASE=1; shift ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Opcion desconocida: $1" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------- utilidades
have() { command -v "$1" >/dev/null 2>&1; }

json_field() {   # json_field <clave>  (lee JSON de stdin)
    python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('$1') or '')" 2>/dev/null \
        || python -c "import json,sys;d=json.load(sys.stdin);print(d.get('$1') or '')"
}

echo "==> SnowSend: preparando publicacion"

# ---------------------------------------------------------------- git inicial
if [ ! -d .git ]; then
    git init -q
    git symbolic-ref HEAD refs/heads/main 2>/dev/null || git checkout -q -b main
    git add -A
    git -c user.name="${GIT_AUTHOR_NAME:-SnowSend}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-snowsend@users.noreply.github.com}" \
        commit -q -m "SnowSend 1.3: cliente LocalSend v2 para Mac OS X 10.6"
    echo "==> Repositorio git local creado con el primer commit"
else
    echo "==> Ya existe un repositorio git local"
fi

# ---------------------------------------------------------------- cuenta
if have gh && gh auth status >/dev/null 2>&1; then
    OWNER="$(gh api user --jq .login)"
    METHOD="gh"
    echo "==> Usando GitHub CLI como $OWNER"
elif [ -n "$GITHUB_TOKEN" ]; then
    OWNER="$(curl -fsS -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" https://api.github.com/user | json_field login)"
    [ -n "$OWNER" ] || { echo "ERROR: el token no es valido" >&2; exit 1; }
    METHOD="token"
    echo "==> Usando token de $OWNER"
else
    cat >&2 <<'MSG'
ERROR: falta autenticacion con GitHub. Elige una opcion:

  A) GitHub CLI (recomendado):
       gh auth login          # una sola vez
       ./publish.sh

  B) Token personal (fine-grained, permiso "Administration: write" en tus repos):
       export GITHUB_TOKEN=xxxxx
       ./publish.sh

  C) A mano, sin token (2 minutos):
       1. https://github.com/new  ->  nombre: snowsend  (sin README, sin .gitignore)
       2. git remote add origin https://github.com/TU_USUARIO/snowsend.git
       3. git push -u origin main
MSG
    exit 1
fi

# ---------------------------------------------------------------- crear repo
if [ "$METHOD" = "gh" ]; then
    if gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
        echo "==> El repositorio $OWNER/$REPO_NAME ya existe, se reutiliza"
    else
        gh repo create "$OWNER/$REPO_NAME" "--$VISIBILITY" \
            --description "$DESCRIPTION" --source . --remote origin 2>/dev/null \
        || gh repo create "$OWNER/$REPO_NAME" "--$VISIBILITY" --description "$DESCRIPTION"
    fi
else
    HTTP_CODE="$(curl -sS -o /tmp/snowsend_create.json -w '%{http_code}' \
        -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        https://api.github.com/user/repos \
        -d "{\"name\":\"$REPO_NAME\",\"description\":\"$DESCRIPTION\",\"private\":$([ "$VISIBILITY" = "private" ] && echo true || echo false),\"has_issues\":true,\"has_wiki\":false}")"
    case "$HTTP_CODE" in
        201) echo "==> Repositorio creado: $OWNER/$REPO_NAME" ;;
        422) echo "==> El repositorio ya existia (HTTP 422), se reutiliza" ;;
        *)   echo "ERROR: GitHub respondio HTTP $HTTP_CODE" >&2
             cat /tmp/snowsend_create.json >&2; echo >&2; exit 1 ;;
    esac
fi

# ---------------------------------------------------------------- remoto + push
REMOTE_URL="https://github.com/$OWNER/$REPO_NAME.git"
if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL"
else
    git remote add origin "$REMOTE_URL"
fi

if [ "$METHOD" = "token" ]; then
    # El token va por cabecera extra de git, no queda guardado en .git/config
    git -c "http.https://github.com/.extraheader=Authorization: Bearer $GITHUB_TOKEN" \
        push -u origin main
else
    git push -u origin main
fi
echo "==> Codigo publicado: $REMOTE_URL"

# ---------------------------------------------------------------- topics
TOPICS="localsend,file-sharing,mac-os-x,snow-leopard,python2,airdrop,offline,multicast"
if [ "$METHOD" = "gh" ]; then
    for t in $(echo "$TOPICS" | tr ',' ' '); do
        gh api -X PUT "repos/$OWNER/$REPO_NAME/topics" -f "names[]=$t" >/dev/null 2>&1 || true
    done
else
    curl -fsS -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$OWNER/$REPO_NAME/topics" \
        -d "{\"names\":[\"localsend\",\"file-sharing\",\"mac-os-x\",\"snow-leopard\",\"python2\",\"airdrop\",\"offline\",\"multicast\"]}" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- release opcional
if [ "$DO_RELEASE" = 1 ]; then
    echo "==> Construyendo SnowSend.app para el Release"
    chmod +x build_app.sh
    ./build_app.sh >/dev/null
    rm -rf SnowSend.app/Contents/Resources/__pycache__
    rm -f SnowSend.zip
    zip -qr SnowSend.zip SnowSend.app
    TAG="v1.3"
    NOTES="SnowSend 1.3 (2.0.3-10.6): recepcion y envio funcionando con iPhone y Android; renombrado a SnowSend; licencia MIT."
    if [ "$METHOD" = "gh" ]; then
        gh release create "$TAG" SnowSend.zip --title "SnowSend 1.3" --notes "$NOTES" 2>/dev/null \
            || echo "==> El Release $TAG ya existia"
    else
        REL_ID="$(curl -fsS -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$OWNER/$REPO_NAME/releases" \
            -d "{\"tag_name\":\"$TAG\",\"name\":\"SnowSend 1.3\",\"body\":\"$NOTES\"}" | json_field id)"
        if [ -n "$REL_ID" ]; then
            curl -fsS -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
                -H "Content-Type: application/zip" \
                --data-binary @"SnowSend.zip" \
                "https://uploads.github.com/repos/$OWNER/$REPO_NAME/releases/$REL_ID/assets?name=SnowSend.zip" >/dev/null
            echo "==> Release v1.3 con SnowSend.zip publicado"
        else
            echo "==> No se pudo crear el Release (quiza ya existe la etiqueta v1.3)"
        fi
    fi
fi

echo
echo "Listo: https://github.com/$OWNER/$REPO_NAME"
