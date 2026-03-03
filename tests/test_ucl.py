import math

import pytest

from jailrun import ucl


def test_empty_is_empty_object() -> None:
    assert ucl.loads("") == {}
    assert ucl.loads("   \n\t  ") == {}


def test_top_level_object_without_braces() -> None:
    out = ucl.loads("a = 1; b = 2;")
    assert out == {"a": 1, "b": 2}


def test_top_level_braced_object() -> None:
    out = ucl.loads('{ "a": 1, "b": 2 }')
    assert out == {"a": 1, "b": 2}


def test_top_level_array_parses_as_list() -> None:
    out = ucl.loads("[1, 2, 3]")
    assert out == [1, 2, 3]


def test_top_level_empty_array() -> None:
    assert ucl.loads("[]") == []


def test_pairs_with_equals_and_colon() -> None:
    out = ucl.loads('a = 1; b: 2; c = "x";')
    assert out["a"] == 1
    assert out["b"] == 2
    assert out["c"] == "x"


def test_statement_separators_semicolon_and_comma() -> None:
    out = ucl.loads("a=1, b=2; c=3, d=4;")
    assert out == {"a": 1, "b": 2, "c": 3, "d": 4}


def test_newline_only_separation() -> None:
    out = ucl.loads("a = 1\nb = 2\nc = 3")
    assert out == {"a": 1, "b": 2, "c": 3}


def test_object_value_parses() -> None:
    out = ucl.loads("obj = { a=1; b=2; };")
    assert out == {"obj": {"a": 1, "b": 2}}


def test_array_value_parses() -> None:
    out = ucl.loads("arr = [1,2,3];")
    assert out == {"arr": [1, 2, 3]}


def test_nested_object_and_array() -> None:
    text = r"""
    top = {
      inner = 1;
      arr = [ {a=1}, {a=2; b=3} ];
    };
    """
    out = ucl.loads(text)
    assert out["top"]["inner"] == 1
    assert out["top"]["arr"][0] == {"a": 1}
    assert out["top"]["arr"][1] == {"a": 2, "b": 3}


def test_trailing_separator_in_array_allowed() -> None:
    out = ucl.loads("a = [1,2,3,];")
    assert out["a"] == [1, 2, 3]


def test_empty_object_value() -> None:
    assert ucl.loads("x = {};") == {"x": {}}


def test_empty_array_value() -> None:
    assert ucl.loads("x = [];") == {"x": []}


def test_nested_arrays() -> None:
    out = ucl.loads("x = [[1, 2], [3, 4]];")
    assert out == {"x": [[1, 2], [3, 4]]}


def test_array_of_mixed_types() -> None:
    out = ucl.loads('x = [1, "two", true, null, 3.14];')
    assert out == {"x": [1, "two", True, None, 3.14]}


def test_top_level_array_of_objects() -> None:
    out = ucl.loads("[ {a=1;}, {b=2;} ]")
    assert out == [{"a": 1}, {"b": 2}]


def test_array_semicolons_as_separator() -> None:
    out = ucl.loads("x = [1; 2; 3];")
    assert out == {"x": [1, 2, 3]}


def test_section_block_creates_object_value() -> None:
    out = ucl.loads("server { listen = 8080; tls = on; }")
    assert out == {"server": {"listen": 8080, "tls": True}}


def test_nested_section_block() -> None:
    out = ucl.loads("""
        top {
        inner = 1;
        nested { a = 2; }
        }
    """)
    assert out == {"top": {"inner": 1, "nested": {"a": 2}}}


def test_named_hierarchy_section_with_multiple_key_parts() -> None:
    out = ucl.loads('section "name" { a = 1; }')
    assert out == {"section": {"name": {"a": 1}}}


def test_section_inside_section() -> None:
    out = ucl.loads("a { b { c = 1; } d = 2; }")
    assert out == {"a": {"b": {"c": 1}, "d": 2}}


def test_duplicate_section_deep_merge() -> None:
    out = ucl.loads("s { a = 1; b = 2; } s { b = 3; c = 4; }")
    assert out["s"]["a"] == 1
    assert out["s"]["b"] == [2, 3]
    assert out["s"]["c"] == 4


def test_duplicate_keys_inside_section_become_array() -> None:
    out = ucl.loads("s { a=1; a=2; }")
    assert out == {"s": {"a": [1, 2]}}


def test_dotted_key_sets_nested_dicts() -> None:
    out = ucl.loads("a.b.c = 1;")
    assert out == {"a": {"b": {"c": 1}}}


def test_dotted_key_merges_with_existing() -> None:
    out = ucl.loads("a.b = 1; a.c = 2;")
    assert out == {"a": {"b": 1, "c": 2}}


def test_dotted_key_then_section_merge() -> None:
    out = ucl.loads("a.b=1; a { c=2; }")
    assert out == {"a": {"b": 1, "c": 2}}


def test_duplicate_keys_become_arrays_top_level() -> None:
    out = ucl.loads("a=1; a=2; a=3;")
    assert out["a"] == [1, 2, 3]


def test_duplicate_keys_become_arrays_nested() -> None:
    out = ucl.loads("obj={ k=1; k=2; };")
    assert out["obj"]["k"] == [1, 2]


def test_duplicate_dotted_key_becomes_array_at_leaf() -> None:
    out = ucl.loads("a.b=1; a.b=2;")
    assert out == {"a": {"b": [1, 2]}}


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("NO", False),
        ("off", False),
        ("null", None),
        ("NULL", None),
    ],
)
def test_bool_and_null_variants(token: str, expected: object) -> None:
    out = ucl.loads(f"x = {token};")
    assert out["x"] is expected


def test_numbers_int_float_scientific_hex() -> None:
    out = ucl.loads("a=123; b=-10; c=1.25; d=1e3; e=0x10;")
    assert out["a"] == 123
    assert out["b"] == -10
    assert math.isclose(out["c"], 1.25)
    assert math.isclose(out["d"], 1000.0)
    assert out["e"] == 16


def test_negative_hex() -> None:
    out = ucl.loads("x = -0xFF;")
    assert out["x"] == -255


def test_numeric_suffix_si_and_binary() -> None:
    out = ucl.loads("k1=2k; m1=3m; g1=4g; kb1=2kb; mb1=3mb; gb1=4gb;")
    assert out["k1"] == 2_000
    assert out["m1"] == 3_000_000
    assert out["g1"] == 4_000_000_000
    assert out["kb1"] == 2 * (1 << 10)
    assert out["mb1"] == 3 * (1 << 20)
    assert out["gb1"] == 4 * (1 << 30)


def test_time_suffixes() -> None:
    out = ucl.loads("a=1500ms; b=2s; c=3min; d=2h; e=2d; f=1w; g=1y;")
    assert math.isclose(out["a"], 1.5)
    assert math.isclose(out["b"], 2.0)
    assert math.isclose(out["c"], 180.0)
    assert math.isclose(out["d"], 7200.0)
    assert math.isclose(out["e"], 172800.0)
    assert math.isclose(out["f"], 604800.0)
    assert math.isclose(out["g"], 365.25 * 86400.0)


def test_double_quoted_string_escapes() -> None:
    out = ucl.loads(r'x = "a\nb\tc\"d";')
    assert out["x"] == 'a\nb\tc"d'


def test_double_quoted_unicode_escape() -> None:
    out = ucl.loads(r'x = "\u263a";')
    assert out["x"] == "☺"


def test_single_quoted_string_raw_and_escaped_quote() -> None:
    out = ucl.loads(r"x = 'it\'s ok';")
    assert out["x"] == "it's ok"


def test_single_quoted_backslash_preservation() -> None:
    out = ucl.loads(r"x = 'a\\b';")
    assert out["x"] == r"a\b"


def test_quoted_key_with_special_chars() -> None:
    out = ucl.loads('"key with spaces" = 1; "key.with.dots" = 2;')
    assert out["key with spaces"] == 1
    assert out["key.with.dots"] == 2


def test_single_quoted_key() -> None:
    out = ucl.loads("'my-key' = 1;")
    assert out == {"my-key": 1}


def test_hash_comments_ignored() -> None:
    out = ucl.loads("# comment\na = 1; # inline\nb = 2;")
    assert out == {"a": 1, "b": 2}


def test_double_slash_comments_ignored() -> None:
    out = ucl.loads("a = 1; // comment\nb = 2;")
    assert out == {"a": 1, "b": 2}


def test_nested_block_comments_ignored() -> None:
    out = ucl.loads(
        """
        a = 1;
        /* outer /* inner */ still outer */
        b = 2;
    """
    )
    assert out == {"a": 1, "b": 2}


def test_comments_inside_strings_preserved() -> None:
    out = ucl.loads(
        """
        a = "not a #comment";
        b = "not a /*comment*/ either";
        c = "not a //comment";
    """
    )
    assert out["a"] == "not a #comment"
    assert out["b"] == "not a /*comment*/ either"
    assert out["c"] == "not a //comment"


def test_heredoc_basic() -> None:
    out = ucl.loads("msg = <<EOD\nhello\nworld\nEOD;")
    assert out["msg"] == "hello\nworld"


def test_heredoc_requires_terminator() -> None:
    with pytest.raises(ucl.UCLError):
        ucl.loads("msg = <<EOD\nhello\n")


def test_heredoc_with_quotes() -> None:
    out = ucl.loads("x = <<EOD\nhas \"quotes\" and 'singles'\nEOD;")
    assert out["x"] == "has \"quotes\" and 'singles'"


def test_heredoc_with_backslashes() -> None:
    out = ucl.loads("x = <<EOD\npath\\to\\file\nEOD;")
    assert out["x"] == "path\\to\\file"


def test_variable_expansion_braced_and_plain_and_escaped() -> None:
    out = ucl.load(
        'a = "x${ABI}y"; b = "x$ABIy"; c = "cost $$5";',
        variables={"ABI": "FreeBSD:14:amd64"},
    )
    assert out["a"] == "xFreeBSD:14:amd64y"
    assert out["b"] == "xFreeBSD:14:amd64y"
    assert out["c"] == "cost $5"


def test_variable_expansion_in_bare_words() -> None:
    out = ucl.load("path = $PREFIX/bin;", variables={"PREFIX": "/usr/local"})
    assert out["path"] == "/usr/local/bin"


def test_macro_handler_called() -> None:
    seen: list[tuple[str, list[str]]] = []

    def handler(name: str, args: list[str]) -> None:
        seen.append((name, args))

    out = ucl.load(".include foo bar; a=1;", macro_handlers={"include": handler})
    assert out == {"a": 1}
    assert seen == [("include", ["foo", "bar"])]


def test_unknown_macro_ignored() -> None:
    out = ucl.loads(".unknown x y z; a=1;")
    assert out == {"a": 1}


def test_bare_key_simple() -> None:
    out = ucl.loads("mount.devfs;")
    assert out == {"mount": {"devfs": True}}


def test_bare_key_in_section() -> None:
    out = ucl.loads(
        """
    myjail {
        mount.devfs;
        exec.clean;
        allow.raw_sockets;
    }
    """
    )
    assert out["myjail"]["mount"]["devfs"] is True
    assert out["myjail"]["exec"]["clean"] is True
    assert out["myjail"]["allow"]["raw_sockets"] is True


def test_bare_key_mixed_with_pairs() -> None:
    out = ucl.loads("a = 1; bare_flag; b = 2;")
    assert out["a"] == 1
    assert out["bare_flag"] is True
    assert out["b"] == 2


def test_bare_key_at_eof() -> None:
    out = ucl.loads("my.flag")
    assert out == {"my": {"flag": True}}


def test_bare_key_before_closing_brace() -> None:
    out = ucl.loads("s { my.flag }")
    assert out == {"s": {"my": {"flag": True}}}


def test_bare_key_with_comma_separator() -> None:
    out = ucl.loads("flag1, flag2, a = 1;")
    assert out["flag1"] is True
    assert out["flag2"] is True
    assert out["a"] == 1


def test_bare_keys_do_not_affect_array_values() -> None:
    out = ucl.loads("x = [foo, bar, baz];")
    assert out["x"] == ["foo", "bar", "baz"]


def test_bare_key_real_world_jail_conf() -> None:
    text = """
    myjail {
        host.hostname = "myjail.example.com";
        path = "/jails/myjail";
        mount.devfs;
        exec.clean;
        exec.start = "/bin/sh /etc/rc";
        exec.stop = "/bin/sh /etc/rc.shutdown";
    }
    """
    out = ucl.loads(text)
    j = out["myjail"]
    assert j["host"]["hostname"] == "myjail.example.com"
    assert j["path"] == "/jails/myjail"
    assert j["mount"]["devfs"] is True
    assert j["exec"]["clean"] is True
    assert j["exec"]["start"] == "/bin/sh /etc/rc"
    assert j["exec"]["stop"] == "/bin/sh /etc/rc.shutdown"


def test_syntax_error_raises_uclerror_with_position() -> None:
    with pytest.raises(ucl.UCLError) as ei:
        ucl.loads("obj = { a=1; ")
    assert "line" in str(ei.value)


def test_dump_roundtrip_simple() -> None:
    parsed = ucl.loads("server { listen = 8080; tls = on; }")
    assert ucl.loads(ucl.dumps(parsed)) == parsed


def test_dump_json_compat_roundtrip() -> None:
    obj: dict[str, object] = {"a": 1, "b": [True, None, "x"]}
    assert ucl.loads(ucl.dump(obj, json_compat=True)) == obj


def test_dump_empty_string_roundtrip() -> None:
    obj: dict[str, object] = {"x": ""}
    assert ucl.loads(ucl.dump(obj))["x"] == ""


def test_dump_string_looking_like_bool_roundtrips() -> None:
    obj: dict[str, object] = {"x": "true", "y": "null", "z": "42"}
    r = ucl.loads(ucl.dump(obj))
    assert r["x"] == "true"
    assert r["y"] == "null"
    assert r["z"] == "42"


def test_dump_nested_with_arrays_roundtrip() -> None:
    obj: dict[str, object] = {"server": {"ports": [80, 443], "names": ["a", "b"]}}
    assert ucl.loads(ucl.dump(obj)) == obj


def test_dump_deeply_nested_roundtrip() -> None:
    obj: dict[str, object] = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    assert ucl.loads(ucl.dump(obj)) == obj


def test_dump_key_with_slashes_roundtrip() -> None:
    obj: dict[str, object] = {"path/to/thing": 1}
    assert ucl.loads(ucl.dump(obj)) == obj


def test_dump_unicode_roundtrip() -> None:
    obj: dict[str, object] = {"emoji": "hello 🌍", "cjk": "漢字"}
    assert ucl.loads(ucl.dump(obj)) == obj


def test_dump_list_of_lists_roundtrip() -> None:
    obj: dict[str, object] = {"matrix": [[1, 2], [3, 4], [5, 6]]}
    assert ucl.loads(ucl.dump(obj)) == obj


def test_dump_float_inf_nan_no_crash() -> None:
    text = ucl.dump({"x": float("inf"), "y": float("nan")})
    assert "inf" in text and "nan" in text


def test_parser_instance_reuse() -> None:
    p = ucl.UCLParser(variables={"X": "1"})
    assert p.parse('a = "$X";') == {"a": "1"}
    assert p.parse('b = "$X";') == {"b": "1"}
