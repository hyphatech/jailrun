import re
from collections.abc import Callable, Sequence
from typing import Any

from lark import Lark, Token, Transformer
from lark.exceptions import UnexpectedInput


class UCLError(Exception):
    line: int
    col: int

    def __init__(self, message: str, line: int = 0, col: int = 0) -> None:
        self.line = line
        self.col = col
        if line:
            super().__init__(f"line {line}, col {col}: {message}")
        else:
            super().__init__(message)


def _is_escaped(text: str, i: int) -> bool:
    """Check if character at position *i* is escaped by counting preceding backslashes."""
    n = 0
    j = i - 1
    while j >= 0 and text[j] == "\\":
        n += 1
        j -= 1
    return n % 2 == 1


def _strip_nested_block_comments(text: str) -> str:
    """Remove /* ... */ comments (nested), but preserve them inside strings."""
    out: list[str] = []
    i = 0
    depth = 0
    in_dq = False
    in_sq = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if depth == 0:
            # Track entering/leaving strings (ignore escaped quotes)
            if ch == '"' and not in_sq:
                if not _is_escaped(text, i):
                    in_dq = not in_dq
            elif ch == "'" and not in_dq:
                if not _is_escaped(text, i):
                    in_sq = not in_sq

            # Start a block comment only if not in string
            if not in_dq and not in_sq and ch == "/" and nxt == "*":
                depth = 1
                i += 2
                continue

            out.append(ch)
            i += 1
            continue

        # depth > 0: we are inside a block comment
        if ch == "/" and nxt == "*":
            depth += 1
            i += 2
            continue
        if ch == "*" and nxt == "/":
            depth -= 1
            i += 2
            if depth == 0:
                out.append(" ")  # replace comment with a space
            continue

        # Preserve newlines to keep line numbers stable
        if ch == "\n":
            out.append("\n")
        i += 1

    if depth != 0:
        raise UCLError("Unterminated block comment")
    return "".join(out)


def _escape_for_dq(s: str) -> str:
    """Escape a raw string so it can live inside double-quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


_HEREDOC_RE = re.compile(
    r"""
    <<(?P<tag>[A-Z]+)\n
    (?P<body>.*?)
    \n(?P<indent>[ \t]*)(?P=tag)[ \t]*(?P<tail>[;,]?)
    (?=[\s}\])]|$)
    """,
    re.DOTALL | re.VERBOSE,
)

_UNTERMINATED_HEREDOC = re.compile(r"<<[A-Z]+\n")


def _dedent_heredoc_body(body: str, indent: str) -> str:
    """Remove terminator indentation from each line (if present)."""
    if not body:
        return body
    lines = body.split("\n")
    if not indent:
        return body

    out_lines: list[str] = []
    for ln in lines:
        if ln.startswith(indent):
            out_lines.append(ln[len(indent) :])
        else:
            out_lines.append(ln)
    return "\n".join(out_lines)


def _convert_heredocs(text: str) -> str:
    """Replace <<TAG ... TAG heredoc strings with double-quoted strings."""

    def _repl(m: re.Match[str]) -> str:
        body = m.group("body")
        indent = m.group("indent") or ""
        tail = m.group("tail") or ""
        body = _dedent_heredoc_body(body, indent)
        return '"' + _escape_for_dq(body) + '"' + tail

    new = _HEREDOC_RE.sub(_repl, text)
    if _UNTERMINATED_HEREDOC.search(new):
        raise UCLError("Unterminated heredoc")
    return new


def _expand_variables(s: str, variables: dict[str, str]) -> str:
    """Expand $VAR and ${VAR}. Prefer a defined variable name for $VAR."""
    if "$" not in s or not variables:
        return s

    result: list[str] = []
    i = 0
    n = len(s)

    while i < n:
        if s[i] != "$":
            result.append(s[i])
            i += 1
            continue

        # Escaped $$
        if i + 1 < n and s[i + 1] == "$":
            result.append("$")
            i += 2
            continue

        # ${VAR}
        if i + 1 < n and s[i + 1] == "{":
            end = s.find("}", i + 2)
            if end != -1:
                name = s[i + 2 : end]
                result.append(variables.get(name, s[i : end + 1]))
                i = end + 1
                continue
            # no closing brace: treat '$' literally
            result.append("$")
            i += 1
            continue

        # $VAR (prefer defined variable name)
        if i + 1 < n and (s[i + 1].isalpha() or s[i + 1] == "_"):
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            run = s[i + 1 : j]  # e.g. "ABIy"

            # find the longest prefix present in variables
            match_len = 0
            for k in range(1, len(run) + 1):
                if run[:k] in variables:
                    match_len = k
            if match_len:
                name = run[:match_len]
                result.append(variables[name])
                result.append(run[match_len:])  # remainder literal
                i = j
                continue

            # no prefix matches: keep original
            result.append("$" + run)
            i = j
            continue

        # Just a lone '$'
        result.append("$")
        i += 1

    return "".join(result)


def _preprocess(text: str) -> str:
    """Run all pre-processing passes over raw UCL text."""
    text = _strip_nested_block_comments(text)
    text = _strip_double_slash_comments(text)
    text = _convert_heredocs(text)
    text = _expand_bare_keys(text)
    return text


def _strip_double_slash_comments(text: str) -> str:
    """Remove // line comments, preserving them inside strings."""
    out: list[str] = []
    i = 0
    in_dq = False
    in_sq = False

    while i < len(text):
        ch = text[i]

        # Track strings
        if ch == '"' and not in_sq and not _is_escaped(text, i):
            in_dq = not in_dq
        elif ch == "'" and not in_dq and not _is_escaped(text, i):
            in_sq = not in_sq

        # // comment outside strings
        if not in_dq and not in_sq and ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            # skip to end of line
            j = text.find("\n", i)
            if j == -1:
                break
            out.append("\n")  # preserve line number
            i = j + 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _expand_bare_keys(text: str) -> str:
    """Insert ``= true`` for bare keys that have no value (e.g. ``mount.devfs;``).

    Also insert ``= `` before ``[`` when a key precedes an array literal
    without an explicit assignment operator, so that ``depends ["x"]``
    is treated the same as ``depends = ["x"]``.

    Strategy: tokenise the preprocessed text (strings are opaque blobs,
    everything else is whitespace / punctuation / WORD tokens).  We track
    a simple state machine:

    * WANT_KEY  – we expect a key (or macro, or closing brace, etc.)
    * WANT_SEP  – we just saw a key; expect ``=`` / ``:`` / ``{`` / ``[``
    * WANT_VAL  – we just saw ``=`` or ``:``, expect a value token
    * IN_VAL    – we consumed the value; expect ``;`` / ``,`` / ``}`` / newline

    A bare key is a WORD in WANT_SEP state whose lookahead is a terminator
    (`;  ,  }  newline  EOF`) rather than ``=  :  {  [``.
    """
    _WS = frozenset(" \t\r\n")
    _SEP = frozenset(";,")
    _WORD_STOP = frozenset(" \t\r\n,;{}[]()#\"'=:")

    out: list[str] = []
    i = 0
    n = len(text)

    # Brace/bracket depth to know if we're inside an array
    bracket_depth = 0  # [] depth

    # State: 'key', 'sep', 'val', 'inval'
    state = "key"

    while i < n:
        ch = text[i]

        # ── whitespace ──
        if ch in _WS:
            out.append(ch)
            i += 1
            continue

        # ── strings: pass through verbatim ──
        if ch == '"':
            j = i + 1
            while j < n:
                if text[j] == '"' and not _is_escaped(text, j):
                    break
                j += 1
            out.append(text[i : j + 1])
            i = j + 1
            if state == "val":
                state = "inval"
            elif state == "key":
                state = "sep"  # quoted key part
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and not _is_escaped(text, j):
                    break
                j += 1
            out.append(text[i : j + 1])
            i = j + 1
            if state == "val":
                state = "inval"
            elif state == "key":
                state = "sep"
            continue

        # ── opening braces / brackets ──
        if ch == "{":
            out.append(ch)
            i += 1
            state = "key"
            continue
        if ch == "[":
            if state == "sep" and bracket_depth == 0:
                out.append(" = ")
            bracket_depth += 1
            out.append(ch)
            i += 1
            state = "val"
            continue

        # ── closing braces / brackets ──
        if ch == "}":
            # If we were in 'sep' state (saw a key, no = : {), this is a bare key
            if state == "sep" and bracket_depth == 0:
                out.append(" = true")
            out.append(ch)
            i += 1
            state = "inval"  # after } we might see ; or ,
            continue
        if ch == "]":
            bracket_depth = max(0, bracket_depth - 1)
            out.append(ch)
            i += 1
            state = "inval"
            continue

        # ── separators: ; and , ──
        if ch in _SEP:
            if state == "sep" and bracket_depth == 0:
                # Bare key: WORD followed by ; or , with no = : {
                out.append(" = true")
            out.append(ch)
            i += 1
            state = "key" if bracket_depth == 0 else "val"
            continue

        # ── assignment operators ──
        if ch == "=" or ch == ":":
            out.append(ch)
            i += 1
            state = "val"
            continue

        # ── hash comment (already handled by grammar, but skip in preprocessor) ──
        if ch == "#":
            j = text.find("\n", i)
            if j == -1:
                out.append(text[i:])
                break
            out.append(text[i:j])
            i = j
            continue

        # ── WORD token ──
        if ch not in _WORD_STOP and ch.isprintable():
            j = i
            while j < n and text[j] not in _WORD_STOP:
                j += 1
            word = text[i:j]
            out.append(word)
            i = j

            if word.startswith("."):
                # Macro — skip everything until the next semicolon.
                # The grammar handles macro arg parsing; we just need to
                # not insert = true for the macro args.
                while i < n and text[i] != ";":
                    out.append(text[i])
                    i += 1
                if i < n:
                    out.append(text[i])  # the ;
                    i += 1
                state = "key"
                continue

            if state == "key":
                state = "sep"  # saw a key, now expect = : or {
            elif state == "sep":
                # Another WORD after a key — multi-part key (section "name")
                # Stay in "sep" state
                pass
            elif state == "val":
                state = "inval"  # consumed the value
            elif state == "inval":
                # After a value with no separator, implicit newline sep
                # This word starts a new key
                state = "sep"
            continue

        # ── anything else ──
        out.append(ch)
        i += 1

    # End of input: if we ended in 'sep' state, it's a bare key at EOF
    if state == "sep" and bracket_depth == 0:
        out.append(" = true")

    return "".join(out)


_UCL_GRAMMAR = r"""
    // Top level: implicit object, braced object, or bare array
    start: "[" _arr_body? "]"               -> top_array
         | "{" _block "}"                   -> top_object
         | _block                           -> top_object

    // Block: sequence of entries with optional terminators
    _block: (_sep* _entry)* _sep*

    _entry: pair
          | section
          | macro

    // ── Key-value pair with explicit separator ────────────────────
    pair: key_parts "=" value
        | key_parts ":" value

    // ── Section: key [names…] { block }  (implicit object) ───────
    section: key_parts "{" _block "}"

    // Key path — one or more segments for dotted/named hierarchy
    key_parts: _key_part+
    _key_part: WORD
             | DQ_STRING
             | SQ_STRING

    // ── Values ───────────────────────────────────────────────────
    ?value: "{" _block "}"                  -> object
          | "[" _arr_body? "]"              -> array
          | DQ_STRING                       -> dqstring
          | SQ_STRING                       -> sqstring
          | WORD                            -> bare

    // Array body — elements separated by , or ;
    _arr_body: value (_arr_sep value)* _arr_sep?
    _arr_sep:  "," | ";"

    // Statement terminators
    _sep: ";" | ","

    // ── Macros (.include, .priority, …) ──────────────────────────
    macro: MACRO_NAME (DQ_STRING | SQ_STRING | WORD)*

    // ═════════════════════════════════════════════════════════════
    //  Terminals
    // ═════════════════════════════════════════════════════════════
    MACRO_NAME.2:  /\.[a-zA-Z_]\w*/
    DQ_STRING:     /"(?:[^"\\]|\\.)*"/
    SQ_STRING:     /'(?:[^'\\]|\\.)*'/
    WORD:          /[^\s,;{}\[\]()#"'=:]+/

    %ignore /[ \t\r\n]+/
    %ignore /#[^\n]*/
"""

_lark_parser: Lark = Lark(
    _UCL_GRAMMAR,
    parser="lalr",
    propagate_positions=True,
)


_BOOL_TRUE = frozenset(("true", "yes", "on"))
_BOOL_FALSE = frozenset(("false", "no", "off"))

_SI_MULT: dict[str, int] = {"k": 1_000, "m": 1_000_000, "g": 1_000_000_000}
_BIN_MULT: dict[str, int] = {"k": 1 << 10, "m": 1 << 20, "g": 1 << 30}
_TIME_MULT: dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "min": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
    "y": 365.25 * 86400.0,
}

_NUM_SUFFIX_RE = re.compile(
    r"""^
    (?P<num> [+-]? (?: 0[xX][0-9a-fA-F]+ | \d+(?:\.\d*)?(?:[eE][+-]?\d+)? ) )
    (?P<suf> ms | min | [smhdwy] | [kKmMgG][bB]? )?
    $""",
    re.VERBOSE,
)


def _interpret_bare(s: str) -> Any:
    """Convert an unquoted value string to the appropriate Python type."""
    low = s.lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    if low == "null":
        return None

    m = _NUM_SUFFIX_RE.match(s)
    if m:
        num_s, suf = m.group("num"), m.group("suf")
        num: int | float
        raw = num_s.lstrip("+-")
        if raw.lower().startswith("0x"):
            num = int(raw, 16)
            if num_s.startswith("-"):
                num = -num
        elif "." in num_s or "e" in num_s.lower():
            num = float(num_s)
        else:
            num = int(num_s)
        if suf:
            sl = suf.lower()
            if sl in _TIME_MULT:
                return float(num) * _TIME_MULT[sl]
            if len(sl) == 2 and sl[1] == "b" and sl[0] in _BIN_MULT:
                v = num * _BIN_MULT[sl[0]]
                return int(v) if isinstance(num, int) else v
            if sl in _SI_MULT:
                v = num * _SI_MULT[sl]
                return int(v) if isinstance(num, int) else v
        return num
    return s


_DQ_ESC: dict[str, str] = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "/": "/",
    "b": "\b",
    "f": "\f",
}


def _unescape_dq(raw: str) -> str:
    """Process a double-quoted token (including surrounding quotes)."""
    inner = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\":
            i += 1
            if i >= len(inner):
                break
            c = inner[i]
            if c in _DQ_ESC:
                out.append(_DQ_ESC[c])
            elif c == "u":
                h = inner[i + 1 : i + 5]
                out.append(chr(int(h, 16)) if len(h) == 4 else "\\u")
                i += 4
            else:
                out.append("\\" + c)
            i += 1
        else:
            out.append(inner[i])
            i += 1
    return "".join(out)


def _unescape_sq(raw: str) -> str:
    """Process a single-quoted token.

    Rules (UCL-lite):
      - \\'  -> '
      - \\\\ -> \\
      - other backslashes are preserved (e.g. \\n stays two chars: backslash+n)
    """
    inner = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        c = inner[i]
        if c == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt == "'" or nxt == "\\":
                out.append(nxt)
                i += 2
                continue
            # preserve the backslash for unknown escapes
            out.append("\\")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


_KV = object()  # sentinel: (_KV, key_path, value)
_MACRO = object()  # sentinel: (_MACRO, name, args)

KVEntry = tuple[object, list[str], Any]
MacroEntry = tuple[object, str, list[str]]


def _deep_merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Merge src into dst, using UCL duplicate semantics."""
    for k, v in src.items():
        if k not in dst:
            dst[k] = v
            continue

        existing = dst[k]
        # dict + dict => recursive merge
        if isinstance(existing, dict) and isinstance(v, dict):
            _deep_merge_dict(existing, v)
            continue

        # list => append
        if isinstance(existing, list):
            existing.append(v)
            continue

        # otherwise => make array
        dst[k] = [existing, v]


def _deep_set(obj: dict[str, Any], keys: list[str], value: Any) -> None:
    """Insert value into nested dict along keys, merging duplicates."""
    for k in keys[:-1]:
        if k not in obj or not isinstance(obj[k], dict):
            obj[k] = {}
        obj = obj[k]

    k = keys[-1]
    if k not in obj:
        obj[k] = value
        return

    existing = obj[k]

    if isinstance(existing, dict) and isinstance(value, dict):
        _deep_merge_dict(existing, value)
        return

    if isinstance(existing, list):
        existing.append(value)
        return

    obj[k] = [existing, value]


class _UCLTransformer(Transformer[Any, Any]):
    """Convert a Lark parse tree into native Python objects."""

    _vars: dict[str, str]
    _macro_handlers: dict[str, "MacroHandler"]

    def __init__(self, variables: dict[str, str], macro_handlers: dict[str, "MacroHandler"]) -> None:
        super().__init__()
        self._vars = variables
        self._macro_handlers = macro_handlers

    def _resolve(self, s: str) -> str:
        return _expand_variables(s, self._vars) if self._vars else s

    def _unquote(self, tok: Token) -> str:
        if tok.type == "DQ_STRING":
            return self._resolve(_unescape_dq(str(tok)))
        if tok.type == "SQ_STRING":
            return _unescape_sq(str(tok))
        return str(tok)

    def _key_segments(self, parts: list[Token]) -> list[str]:
        """Flatten key_parts tokens into a list of key segments."""
        segs: list[str] = []
        for tok in parts:
            s = self._unquote(tok)
            if tok.type == "WORD" and "." in s:
                segs.extend(s.split("."))
            else:
                segs.append(s)
        return segs

    @staticmethod
    def _merge_entries(items: Sequence[Any]) -> dict[str, Any]:
        """Merge (_KV, keys, value) tuples into a dict."""
        obj: dict[str, Any] = {}
        for item in items:
            if isinstance(item, tuple) and len(item) == 3 and item[0] is _KV:
                _, key_path, value = item
                _deep_set(obj, key_path, value)
        return obj

    def top_object(self, items: list[Any]) -> dict[str, Any]:
        return self._merge_entries(items)

    def top_array(self, items: list[Any]) -> list[Any]:
        return list(items)

    def key_parts(self, items: list[Token]) -> list[str]:
        return self._key_segments(items)

    def pair(self, items: list[Any]) -> KVEntry:
        return (_KV, items[0], items[1])

    def section(self, items: list[Any]) -> KVEntry:
        keys = items[0]
        obj = self._merge_entries(items[1:])
        return (_KV, keys, obj)

    def object(self, items: list[Any]) -> dict[str, Any]:
        return self._merge_entries(items)

    def array(self, items: list[Any]) -> list[Any]:
        return list(items)

    def dqstring(self, items: list[Any]) -> str:
        return self._resolve(_unescape_dq(str(items[0])))

    def sqstring(self, items: list[Any]) -> str:
        return _unescape_sq(str(items[0]))

    def bare(self, items: list[Any]) -> Any:
        return _interpret_bare(self._resolve(str(items[0])))

    def macro(self, items: list[Any]) -> MacroEntry:
        name = str(items[0]).lstrip(".")
        args = [self._unquote(t) for t in items[1:]]
        handler = self._macro_handlers.get(name)
        if handler:
            handler(name, args)
        return (_MACRO, name, args)


MacroHandler = Callable[[str, list[str]], None]


class UCLParser:
    """
    Reusable UCL parser instance.

    Parameters
    ----------
    variables : dict, optional
        Mapping of variable names → values for ``$VAR`` expansion.
    macro_handlers : dict, optional
        Mapping of macro names (without leading dot) → handler callables.
        Each handler receives ``(macro_name, args_list)``.
    """

    variables: dict[str, str]
    macro_handlers: dict[str, MacroHandler]

    def __init__(
        self,
        variables: dict[str, str] | None = None,
        macro_handlers: dict[str, MacroHandler] | None = None,
    ) -> None:
        self.variables = variables or {}
        self.macro_handlers = macro_handlers or {}

    def parse(self, text: str) -> Any:
        """Parse a UCL string and return the resulting Python object."""
        try:
            preprocessed = _preprocess(text)
            tree = _lark_parser.parse(preprocessed)
            xform = _UCLTransformer(self.variables, self.macro_handlers)
            return xform.transform(tree)
        except UnexpectedInput as exc:
            raise UCLError(
                str(exc),
                line=getattr(exc, "line", 0),
                col=getattr(exc, "column", 0),
            ) from exc

    def parse_file(self, path: str) -> Any:
        """Parse a UCL file and return the resulting Python object."""
        with open(path, encoding="utf-8") as fh:
            return self.parse(fh.read())


def load(
    text: str,
    variables: dict[str, str] | None = None,
    macro_handlers: dict[str, MacroHandler] | None = None,
) -> Any:
    """
    Parse a UCL string → Python object.

    >>> load('server { listen = 8080; tls = on; }')
    {'server': {'listen': 8080, 'tls': True}}
    """
    return UCLParser(variables=variables, macro_handlers=macro_handlers).parse(text)


loads = load  # alias matching ``json.loads``


def load_file(
    path: str,
    variables: dict[str, str] | None = None,
    macro_handlers: dict[str, MacroHandler] | None = None,
) -> Any:
    """Parse a UCL file → Python object."""
    return UCLParser(variables=variables, macro_handlers=macro_handlers).parse_file(path)


def dump(obj: Any, *, indent: int = 4, json_compat: bool = False) -> str:
    """
    Serialize a Python object to UCL format.

    Parameters
    ----------
    obj : Any
        The object to serialize.
    indent : int
        Spaces per indentation level.
    json_compat : bool
        Emit strict JSON instead of relaxed UCL notation.
    """
    return _emit(obj, 0, indent, json_compat)


dumps = dump  # alias


def _emit(obj: Any, level: int, indent: int, jc: bool) -> str:
    pad = " " * (level * indent)
    inner = " " * ((level + 1) * indent)
    sep = ": " if jc else " = "
    end = "," if jc else ";"

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines: list[str] = []
        for k, v in obj.items():
            ks = _quote_key(str(k), jc)
            vs = _emit(v, level + 1, indent, jc)
            if isinstance(v, dict) and not jc:
                lines.append(f"{inner}{ks} {vs}")
            else:
                lines.append(f"{inner}{ks}{sep}{vs}{end}")
        if jc and lines:
            lines[-1] = lines[-1].rstrip(",")
        return "{\n" + "\n".join(lines) + "\n" + pad + "}"

    if isinstance(obj, list):
        if not obj:
            return "[]"
        items = [inner + _emit(v, level + 1, indent, jc) for v in obj]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"

    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return repr(obj)
    if obj is None:
        return "null"

    return _quote_string(str(obj))


_SAFE_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_./-]*$")


def _quote_key(k: str, jc: bool) -> str:
    if jc or not _SAFE_KEY_RE.match(k):
        return f'"{_escape_for_dq(k)}"'
    return k


def _quote_string(s: str) -> str:
    return f'"{_escape_for_dq(s)}"'
