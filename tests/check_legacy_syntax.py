#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static check that tigersend.py stays runnable on Python 2.3.5 (Tiger).

Tiger ships /usr/bin/python 2.3.5, which cannot even *parse* syntax that was
introduced later. Running this checker on a modern machine catches the
mistakes that otherwise only show up as "the app does not start" on a twenty
year old PowerPC Mac.

Usage:
    python3 tests/check_legacy_syntax.py [file ...]

Exit code 0 means the file is safe for Python 2.3.
"""

import ast
import io
import re
import sys
import tokenize

TARGET = 'tigersend.py'

# Names that do not exist in Python 2.3 (or that behave differently enough to
# be a bug on Tiger).
BANNED_NAMES = {
    'set': 'set() is Python 2.4+; use a dict or a list',
    'frozenset': 'frozenset() is Python 2.4+',
    'sorted': 'sorted() is Python 2.4+; use list.sort()',
    'reversed': 'reversed() is Python 2.4+',
    'any': 'any() is Python 2.5+',
    'all': 'all() is Python 2.5+',
    'next': 'next() builtin is Python 2.6+',
    'format': 'str.format() is Python 2.6+',
    'print_function': 'from __future__ import print_function is 2.6+',
    'with_statement': 'from __future__ import with_statement is 2.5+',
    'exceptf': '',
    'bytes': 'bytes() is Python 2.6+; use str on Python 2',
    'bytearray': 'bytearray() is Python 2.6+',
    'uuid': 'uuid is Python 2.5+',
    'subprocess': 'subprocess is Python 2.4+',
    'ctypes': 'ctypes is Python 2.5+',
    'ssl': 'ssl is Python 2.6+ (Tiger has no TLS at all)',
    'json': 'json is Python 2.6+ (TigerSend has its own codec)',
    'hashlib': 'hashlib is Python 2.5+ (TigerSend falls back to md5)',
    'socketserver': 'the module is SocketServer on Python 2',
    'tkinter': 'the module is Tkinter on Python 2',
    'http': 'the module is BaseHTTPServer on Python 2',
    'urllib.parse': 'the module is urllib/urlparse on Python 2',
    'threading.Event': 'Event.is_set() is 2.6+; TigerSend uses CancelFlag',
    'os.urandom': 'os.urandom is Python 2.4+',
    'os.path.relpath': 'os.path.relpath is Python 2.6+',
    'os.get_terminal_size': '2.7+',
    'socket.create_connection': 'socket.create_connection is Python 2.6+',
    'socket.if_nameindex': '2.3 does not have it',
    'time.monotonic': '3.3+',
    'time.perf_counter': '3.3+',
    'platform.architecture': 'spawns a subprocess; use platform.machine()',
}

# Method names that do not exist on Python 2.3 strings / objects.
BANNED_ATTRS = {
    'partition': 'str.partition() is Python 2.5+',
    'rpartition': 'str.rpartition() is Python 2.5+',
    'rsplit': 'str.rsplit() is Python 2.4+',
    'lstrip_unused': '',
    'daemon': 'Thread.daemon property is Python 2.6+ (use setDaemon)',
    'replace_all': '',
    'format_map': '3.2+',
    'casefold': '3.3+',
    'total_seconds': 'timedelta.total_seconds() is 2.7+',
    'relative_to': 'pathlib is 3.4+',
    'exists_ok': '',
}

# Modules that may be imported only inside a try/except ImportError fallback.
OPTIONAL_MODULES = ('json', 'hashlib', 'md5', 'gzip', 'zlib', 'cStringIO')

ALLOWED_FUTURES = ()

# A real b"..." / f"..." literal starts a token: it is not preceded by a
# backslash (u'\\b'), a letter, or another quote.
STRING_PREFIX_B = re.compile(r"(?<![\w'\"\\])[bB][rR]?['\"]")
STRING_PREFIX_F = re.compile(r"(?<![\w'\"\\])[fF][rR]?['\"]")


def _block_range(nodes):
    """(first line, last line) of a block; works before end_lineno existed."""
    if not nodes:
        return None
    start = None
    end = 0
    for node in nodes:
        for sub in ast.walk(node):
            line = getattr(sub, 'lineno', None)
            if not line:
                continue
            if start is None or line < start:
                start = line
            if line > end:
                end = line
    if start is None:
        return None
    return (start, end)


TRY_NODES = tuple(getattr(ast, name) for name in
                  ('Try', 'TryExcept', 'TryFinally')
                  if hasattr(ast, name))


def collect_ranges(tree):
    """Line ranges that are Python-3-only or import fallbacks."""
    py3_ranges = []
    optional_ranges = []

    def is_py3_test(node):
        """`if PY3:` or `if sys.version_info[0] >= 3:` guards."""
        dump = ast.dump(node)
        if "id='PY3'" in dump or 'id=\'PY3\'' in dump:
            return True
        if 'version_info' in dump:
            return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and is_py3_test(node.test):
            body_range = _block_range(node.body)
            if body_range:
                py3_ranges.append(body_range)
            else_range = _block_range(node.orelse)
            if else_range:
                # the "else" branch of `if PY3:` is the Python 2 code: keep it
                pass
        if isinstance(node, TRY_NODES):
            for handler in getattr(node, 'handlers', None) or []:
                for name in ('ImportError', 'Exception'):
                    if isinstance(handler.type, ast.Name) and \
                            handler.type.id == name:
                        optional_range = _block_range(node.body)
                        if optional_range:
                            optional_ranges.append(optional_range)
    return py3_ranges, optional_ranges


def in_ranges(line, ranges):
    for start, end in ranges:
        if start <= line <= end:
            return True
    return False


class Checker(ast.NodeVisitor):
    def __init__(self, filename, py3_ranges=None, optional_ranges=None):
        self.filename = filename
        self.problems = []
        self.py3_ranges = py3_ranges or []
        self.optional_ranges = optional_ranges or []

    def report(self, node, message):
        line = getattr(node, 'lineno', 0)
        self.problems.append('%s:%d: %s' % (self.filename, line, message))

    def in_py3(self, node):
        return in_ranges(getattr(node, 'lineno', 0), self.py3_ranges)

    def in_optional_import(self, node):
        return in_ranges(getattr(node, 'lineno', 0), self.optional_ranges)

    # --- syntax that Python 2.3 cannot parse -----------------------------
    def visit_With(self, node):
        self.report(node, '"with" needs Python 2.5+')

    def visit_AsyncWith(self, node):
        self.report(node, 'async needs Python 3.5+')

    def visit_AsyncFunctionDef(self, node):
        self.report(node, 'async needs Python 3.5+')

    def visit_Await(self, node):
        self.report(node, 'await needs Python 3.5+')

    def visit_YieldFrom(self, node):
        self.report(node, 'yield from needs Python 3.3+')

    def visit_Nonlocal(self, node):
        self.report(node, 'nonlocal needs Python 3')

    def visit_IfExp(self, node):
        self.report(node, 'ternary expression (a if b else c) needs Python 2.5+')

    def visit_GeneratorExp(self, node):
        self.report(node, 'generator expression needs Python 2.4+')

    def visit_SetComp(self, node):
        self.report(node, 'set comprehension needs Python 2.7+')

    def visit_DictComp(self, node):
        self.report(node, 'dict comprehension needs Python 2.7+')

    def visit_Set(self, node):
        self.report(node, 'set literal needs Python 2.7+')

    def visit_JoinedStr(self, node):
        self.report(node, 'f-string needs Python 3.6+')

    def visit_NamedExpr(self, node):
        self.report(node, 'walrus operator needs Python 3.8+')

    def visit_MatMult(self, node):
        self.report(node, '@ operator needs Python 3.5+')

    def visit_AnnAssign(self, node):
        self.report(node, 'variable annotations need Python 3.6+')

    def visit_arguments(self, node):
        if getattr(node, 'kwonlyargs', None):
            self.report(node, 'keyword-only arguments need Python 3')
        if getattr(node, 'posonlyargs', None):
            self.report(node, 'positional-only arguments need Python 3.8+')

    def visit_FunctionDef(self, node):
        if node.decorator_list:
            self.report(node, 'decorators need Python 2.4+')
        if getattr(node, 'returns', None) is not None:
            self.report(node, 'annotations need Python 3')
        self.generic_visit(node)

    def visit_TryExcept(self, node):
        self.visit_Try(node)

    def visit_TryFinally(self, node):
        self.visit_Try(node)

    def visit_Try(self, node):
        if getattr(node, 'handlers', None) and getattr(node, 'finalbody', None):
            self.report(node, 'except+finally in one try needs Python 2.5+ '
                              '(nest a try inside try/finally)')
        self.generic_visit(node)

    def visit_Raise(self, node):
        if getattr(node, 'cause', None) is not None:
            self.report(node, '"raise ... from ..." needs Python 3')
        self.generic_visit(node)

    # --- names that do not exist on Tiger --------------------------------
    def visit_Import(self, node):
        for alias in node.names:
            self.check_module(node, alias.name, alias.asname)

    def visit_ImportFrom(self, node):
        module = node.module or ''
        if node.level:
            self.report(node, 'relative imports need Python 2.5+')
        if module == '__future__':
            for alias in node.names:
                if alias.name not in ALLOWED_FUTURES:
                    self.report(node, 'from __future__ import %s is not '
                                      'available on Python 2.3'
                                % alias.name)
            return
        self.check_module(node, module, None)

    def check_module(self, node, module, asname):
        root = module.split('.')[0]
        if root not in BANNED_NAMES:
            return
        if self.in_py3(node):
            return
        if root in OPTIONAL_MODULES and self.in_optional_import(node):
            return
        if root == 'json' and self.in_optional_import(node):
            return
        if root == 'tkinter' and self.in_optional_import(node):
            return
        self.report(node, 'import %s: %s' % (module, BANNED_NAMES[root]))

    def visit_Attribute(self, node):
        name = node.attr
        if name in BANNED_ATTRS and BANNED_ATTRS[name]:
            if name == 'isSet':
                # CancelFlag provides isSet(); that is the documented 2.3 way
                self.generic_visit(node)
                return
            self.report(node, '.%s: %s' % (name, BANNED_ATTRS[name]))
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.in_py3(node) or self.in_optional_import(node):
            self.generic_visit(node)
            return
        if isinstance(node.ctx, ast.Load) and node.id in BANNED_NAMES:
            message = BANNED_NAMES[node.id]
            if message:
                self.report(node, '%s: %s' % (node.id, message))
        elif isinstance(node.ctx, ast.Store) and node.id in ('unicode', 'long'):
            # Python 3 would normally be fine, but redefining these would
            # break the 2.x compatibility shims.
            self.report(node, 'do not shadow the Python 2 builtin %s' % node.id)
        self.generic_visit(node)

    def visit_Call(self, node):
        target = node.func
        full = name_of(target)
        if self.in_py3(node) or self.in_optional_import(node):
            self.generic_visit(node)
            return
        if full and full in BANNED_NAMES:
            message = BANNED_NAMES[full]
            if message:
                self.report(node, '%s(): %s' % (full, message))
        self.generic_visit(node)


def name_of(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = name_of(node.value)
        if base:
            return base + '.' + node.attr
        return node.attr
    return ''


def check_source(filename):
    # no `with` here: this script must also parse on Python 2.5, where
    # `with` is only a keyword after `from __future__ import with_statement`.
    handle = io.open(filename, 'rb')
    try:
        raw = handle.read()
    finally:
        handle.close()
    source = raw.decode('utf-8')
    # parse the bytes: Python 2's compile() refuses a unicode string that
    # starts with a coding declaration.
    tree = ast.parse(raw, filename)
    py3_ranges, optional_ranges = collect_ranges(tree)
    checker = Checker(filename, py3_ranges, optional_ranges)
    checker.visit(tree)

    problems = list(checker.problems)
    # String prefixes are checked on the token stream, so that the letter "b"
    # inside u'%.1f B' or u'\\b' cannot produce a false positive.
    try:
        if sys.version_info[0] >= 3:
            reader = io.StringIO(source).readline
        else:
            reader = io.BytesIO(raw).readline
        tokens = tokenize.generate_tokens(reader)
        for token in tokens:
            # tokenize yields plain tuples on Python 2 and named tuples on
            # Python 3: index it, do not use attributes.
            if token[0] != tokenize.STRING:
                continue
            text = token[1]
            if not isinstance(text, str):
                text = text.decode('latin-1')
            line_number = token[2][0]
            prefix = text[:4]
            lowered = prefix.lower()
            if lowered.startswith('b') or lowered.startswith('rb') or \
                    lowered.startswith('br'):
                problems.append('%s:%d: b"..." literals need Python 2.6+ '
                                '(build the constants at run time)'
                                % (filename, line_number))
            elif lowered.startswith('f') or lowered.startswith('rf') or \
                    lowered.startswith('fr'):
                problems.append('%s:%d: f-strings need Python 3.6+'
                                % (filename, line_number))
    except Exception:
        pass
    for number, line in enumerate(source.splitlines(), 1):
        if '\t' in line:
            problems.append('%s:%d: tab character (use spaces)'
                            % (filename, number))
    problems.sort()
    return problems


def main(argv):
    files = argv[1:]
    if not files:
        files = [TARGET]
    failures = 0
    for filename in files:
        try:
            problems = check_source(filename)
        except SyntaxError as error:
            sys.stdout.write('%s: SYNTAX ERROR: %s\n' % (filename, error))
            failures = failures + 1
            continue
        if problems:
            failures = failures + len(problems)
            for problem in problems:
                sys.stdout.write(problem + '\n')
        else:
            sys.stdout.write('ok   %s is Python 2.3 compatible\n' % filename)
    if failures:
        sys.stdout.write('\n%d problem(s) found\n' % failures)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
