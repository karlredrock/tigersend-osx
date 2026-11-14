#!/bin/sh
# run_tests.sh - run the whole test matrix on every Python this machine has.
#
#   sh tests/run_tests.sh              # every interpreter found in PATH
#   sh tests/run_tests.sh /tmp/py23/bin/python2.3 /tmp/py27/bin/python2.7
#
# For each interpreter it runs:
#   tests/check_legacy_syntax.py tigersend.py   (skipped below Python 2.5)
#   tests/test_tigersend.py                     (the suite)
#   tigersend.py --self-test                    (the built-in check)
#
# Exit status is 0 only when every interpreter passed everything.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR" || exit 1

if [ $# -gt 0 ]; then
    CANDIDATES="$*"
else
    CANDIDATES="python2.3 python2.4 python2.5 python2.6 python2.7 python3 python"
fi

# U+2014 and friends: keep the C locale honest about UTF-8 output
LC_ALL=C.UTF-8
export LC_ALL

TOTAL=0
BROKEN=0
SUMMARY=""

have_python() {
    # have_python <name-or-path> -> prints the executable if it exists
    case "$1" in
        */*) [ -x "$1" ] && echo "$1" ;;
        *)   command -v "$1" 2>/dev/null ;;
    esac
}

for candidate in $CANDIDATES; do
    python_bin="$(have_python "$candidate")"
    if [ -z "$python_bin" ]; then
        continue
    fi
    version="$("$python_bin" -c 'import sys;print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
    if [ -z "$version" ]; then
        continue
    fi
    echo ""
    echo "=================================================================="
    echo "  Python $version   ($python_bin)"
    echo "=================================================================="

    TOTAL=$((TOTAL + 1))
    status=0

    echo "-- legacy syntax check"
    # the checker itself uses `except ... as` and `ast`, so it needs 2.6+
    if "$python_bin" -c 'import sys;sys.exit(0 if sys.version_info[:2] >= (2, 6) else 1)' 2>/dev/null; then
        "$python_bin" tests/check_legacy_syntax.py tigersend.py || status=1
    else
        echo "   skip  the checker itself needs Python 2.6+ (the suite still checks the app)"
    fi

    echo "-- test suite"
    suite="$("$python_bin" tests/test_tigersend.py 2>&1 | tail -3)"
    echo "$suite"
    case "$suite" in
        *"0 failed"*) ;;
        *) status=1 ;;
    esac

    echo "-- built-in self test"
    if "$python_bin" tigersend.py --self-test 2>&1 | tail -2 | grep -q "All self tests passed"; then
        echo "   ok"
    else
        echo "   FAILED"
        status=1
    fi

    if [ "$status" -eq 0 ]; then
        SUMMARY="$SUMMARY
  ok      Python $version  ($python_bin)"
    else
        BROKEN=$((BROKEN + 1))
        SUMMARY="$SUMMARY
  FAILED  Python $version  ($python_bin)"
    fi
done

echo ""
echo "=================================================================="
echo "  Summary"
echo "=================================================================="
if [ "$TOTAL" -eq 0 ]; then
    echo "  no Python interpreter found (pass one as an argument)"
    exit 1
fi
echo "$SUMMARY"
echo ""
if [ "$BROKEN" -eq 0 ]; then
    echo "  $TOTAL interpreter(s), everything passed"
    exit 0
fi
echo "  $BROKEN of $TOTAL interpreter(s) failed"
exit 1
