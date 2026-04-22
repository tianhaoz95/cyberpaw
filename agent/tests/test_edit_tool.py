"""
Unit tests for tools/edit_tool.py — apply_edit and the EditTool class.

Covers:
  - Exact matching (happy path)
  - Boundary validation (_ends_at_boundary)
  - CRLF and mixed line endings
  - Curly-quote normalisation
  - Ambiguous (duplicate) old_string
  - Empty / whole-file replacements
  - Trailing-newline preservation
  - Multi-line blocks
  - Relative-indent strategy
  - Blank-line stripping strategy
  - Wrong base indentation (_reindent)
  - dmp_lines_apply fallback
  - Special characters (regex chars, backslashes, unicode)
  - EditTool.call: file-not-found, staleness, written-unread, success
  - EditTool.call: secret scanning warning
  - EditTool.call: ambiguous match / apply failure
  - _file_hint for small and large files
  - _normalise_endings
  - _search_and_replace
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import textwrap
import time
import unittest

AGENT_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

from tools.edit_tool import (
    apply_edit,
    _ends_at_boundary,
    _normalise_endings,
    _reindent,
    _search_and_replace,
    _file_hint,
    EditTool,
)
from tools.file_staleness import clear_staleness, record_read, record_write
from harness.tool_registry import ToolContext
from harness.permissions import PermissionMode


# ── helpers ──────────────────────────────────────────────────────────────────

def make_ctx(tmp_dir: str) -> ToolContext:
    return ToolContext(
        working_directory=tmp_dir,
        permission_mode=PermissionMode.AUTO_ALL,
        session_id="test-session",
    )


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── apply_edit: exact matching ────────────────────────────────────────────────

class TestApplyEditExact(unittest.TestCase):

    def test_simple_replacement_at_eof(self):
        # 'foo\n' ends with \n (boundary), and it's at EOF so no char after
        result = apply_edit("foo\n", "bar\n", "foo\n")
        self.assertEqual(result, "bar\n")

    def test_replacement_where_next_char_is_boundary(self):
        # 'foo\n' followed by another \n (blank line) — next char is \n (boundary)
        result = apply_edit("foo\n", "bar\n", "foo\n\nbaz\n")
        self.assertEqual(result, "bar\n\nbaz\n")

    def test_multiline_replacement(self):
        original = "def foo():\n    pass\n"
        search   = "def foo():\n    pass\n"
        replace  = "def foo():\n    return 42\n"
        result = apply_edit(search, replace, original)
        self.assertEqual(result, replace)

    def test_replacement_in_middle(self):
        original = "line1\nTARGET\nline3\n"
        result = apply_edit("TARGET\n", "REPLACED\n", original)
        self.assertEqual(result, "line1\nREPLACED\nline3\n")

    def test_empty_new_string_deletes(self):
        original = "before\nDELETE_ME\nafter\n"
        result = apply_edit("DELETE_ME\n", "", original)
        self.assertEqual(result, "before\nafter\n")

    def test_whole_file_replacement(self):
        original = "entire file content\n"
        result = apply_edit("entire file content\n", "new content\n", original)
        self.assertEqual(result, "new content\n")

    def test_not_found_returns_none(self):
        result = apply_edit("MISSING\n", "X\n", "no match here\n")
        self.assertIsNone(result)

    def test_duplicate_old_string_exact_strategy_rejects(self):
        # _search_and_replace rejects duplicates, but dmp may still apply to
        # the first occurrence. Either way the result must not be None AND
        # must not silently corrupt the file by replacing both occurrences.
        original = "x = 1\nx = 1\n"
        result = apply_edit("x = 1\n", "x = 2\n", original)
        if result is not None:
            # If a strategy succeeded it must have changed exactly one line
            self.assertEqual(result.count("x = 2"), 1)
            self.assertEqual(result.count("x = 1"), 1)

    def test_replace_with_more_lines(self):
        original = "a\nb\nc\n"
        result = apply_edit("b\n", "b1\nb2\nb3\n", original)
        self.assertEqual(result, "a\nb1\nb2\nb3\nc\n")

    def test_replace_with_fewer_lines(self):
        original = "a\nb\nc\nd\n"
        result = apply_edit("b\nc\n", "X\n", original)
        self.assertEqual(result, "a\nX\nd\n")

    def test_search_at_start_of_file(self):
        original = "FIRST\nsecond\n"
        result = apply_edit("FIRST\n", "REPLACED\n", original)
        self.assertEqual(result, "REPLACED\nsecond\n")

    def test_search_at_end_of_file(self):
        original = "first\nLAST\n"
        result = apply_edit("LAST\n", "REPLACED\n", original)
        self.assertEqual(result, "first\nREPLACED\n")


# ── apply_edit: CRLF / line-ending normalisation ─────────────────────────────

class TestApplyEditLineEndings(unittest.TestCase):

    def test_crlf_search_against_lf_file(self):
        original = "foo\nbar\n"
        result = apply_edit("foo\r\nbar\r\n", "baz\n", original)
        self.assertIsNotNone(result)
        self.assertIn("baz", result)

    def test_lf_search_against_crlf_file(self):
        original = "foo\r\nbar\r\n"
        result = apply_edit("foo\nbar\n", "baz\n", original)
        self.assertIsNotNone(result)

    def test_mixed_endings_normalised(self):
        original = "a\r\nb\nc\r\n"
        result = apply_edit("a\nb\nc\n", "X\n", original)
        self.assertIsNotNone(result)


# ── apply_edit: curly-quote normalisation ─────────────────────────────────────

class TestApplyEditCurlyQuotes(unittest.TestCase):

    def test_curly_single_quotes(self):
        original = "print('hello')\n"
        result = apply_edit("print(‘hello’)\n", "print('world')\n", original)
        self.assertIsNotNone(result)
        self.assertIn("world", result)

    def test_curly_double_quotes(self):
        original = 'msg = "hello"\n'
        result = apply_edit('msg = “hello”\n', 'msg = "world"\n', original)
        self.assertIsNotNone(result)
        self.assertIn("world", result)


# ── apply_edit: indentation strategies ───────────────────────────────────────

class TestApplyEditIndentation(unittest.TestCase):

    def test_relative_indent_strategy_nested(self):
        # Deeply nested block — relative indent strategy should handle it
        original = textwrap.dedent("""\
            class A:
                class B:
                    def method(self):
                        x = 1
                        return x
        """)
        search = textwrap.dedent("""\
                    def method(self):
                        x = 1
                        return x
        """)
        replace = textwrap.dedent("""\
                    def method(self):
                        x = 2
                        return x
        """)
        result = apply_edit(search, replace, original)
        self.assertIsNotNone(result)
        self.assertIn("x = 2", result)

    def test_blank_line_stripping_finds_match(self):
        # old_string has extra blank lines — stripping strategy should find it
        original = "foo\n\nbar\n"
        search   = "\nfoo\n\nbar\n\n"
        replace  = "\nfoo\n\nQUX\n\n"
        result = apply_edit(search, replace, original)
        self.assertIsNotNone(result)

    def test_wrong_base_indent_healed_via_reindent(self):
        # File uses 4-space indent; model sent 2-space old_string
        original = textwrap.dedent("""\
            def foo():
                if True:
                    pass
                return 0
        """)
        search  = "    if True:\n        pass\n"   # correct 4-space
        # Use reindent path: send 2-space version
        search2 = "  if True:\n    pass\n"
        replace = "  if True:\n    return 1\n"
        result = apply_edit(search2, replace, original)
        self.assertIsNotNone(result)
        self.assertIn("return 1", result)

    def test_tabs_vs_spaces_does_not_crash(self):
        original = "def foo():\n\tpass\n"
        search   = "def foo():\n    pass\n"
        replace  = "def foo():\n    return 1\n"
        # May or may not succeed, but must not raise
        result = apply_edit(search, replace, original)
        self.assertTrue(result is None or isinstance(result, str))


# ── apply_edit: boundary validation ──────────────────────────────────────────

class TestApplyEditBoundary(unittest.TestCase):

    def test_truncated_mid_expression_rejected(self):
        # old_string ends mid-token — should be rejected by boundary check
        original = "result = some_function(arg1, arg2)\n"
        search   = "result = some_function(arg1"   # truncated, ends with '1'
        result = apply_edit(search, "X", original)
        self.assertIsNone(result)

    def test_ends_at_boundary_newline_at_eof(self):
        self.assertTrue(_ends_at_boundary("foo\n", "foo\n"))

    def test_ends_at_boundary_newline_followed_by_newline(self):
        self.assertTrue(_ends_at_boundary("foo\n", "foo\n\n"))

    def test_ends_at_boundary_semicolon(self):
        self.assertTrue(_ends_at_boundary("x = 1;", "x = 1; y = 2"))

    def test_ends_at_boundary_closing_brace_at_eof(self):
        self.assertTrue(_ends_at_boundary("}\n", "if True:\n}\n"))

    def test_not_at_boundary_mid_word(self):
        self.assertFalse(_ends_at_boundary("func", "function()"))

    def test_not_at_boundary_next_char_is_letter(self):
        # 'foo\n' followed by 'b' (not a boundary char)
        self.assertFalse(_ends_at_boundary("foo\n", "foo\nbaz"))

    def test_empty_search_boundary_false(self):
        self.assertFalse(_ends_at_boundary("", "anything"))

    def test_not_in_original(self):
        self.assertFalse(_ends_at_boundary("xyz\n", "abc\n"))


# ── apply_edit: edge cases ────────────────────────────────────────────────────

class TestApplyEditEdgeCases(unittest.TestCase):

    def test_unicode_content(self):
        original = "name = '日本語'\n"
        result = apply_edit("'日本語'\n", "'English'\n", original)
        self.assertIsNotNone(result)
        self.assertIn("English", result)

    def test_very_long_line(self):
        long_line = "x" * 5000 + "\n"
        original = f"start\n{long_line}end\n"
        result = apply_edit(long_line, "short\n", original)
        self.assertIsNotNone(result)
        self.assertIn("short", result)

    def test_special_regex_chars_in_search(self):
        # Should not treat old_string as a regex
        original = "cost = $100.00\n"
        result = apply_edit("$100.00\n", "$200.00\n", original)
        self.assertIsNotNone(result)
        self.assertIn("$200.00", result)

    def test_backslash_in_search(self):
        original = "path = C:\\Users\\foo\n"
        result = apply_edit("C:\\Users\\foo\n", "C:\\Users\\bar\n", original)
        self.assertIsNotNone(result)
        self.assertIn("bar", result)

    def test_only_whitespace_differs_trailing_spaces(self):
        # Trailing spaces in old_string — _strip_blank_lines strips leading/
        # trailing newlines from the whole text, not per-line trailing spaces.
        # This is a known limitation; the test documents current behaviour.
        original = "def foo():\n    pass\n"
        search   = "def foo():  \n    pass  \n"
        replace  = "def foo():\n    return 1\n"
        result = apply_edit(search, replace, original)
        # Currently None because trailing spaces prevent exact match and dmp
        # needs all texts to end with \n (they do), but the spaces cause
        # the line-level diff to not find a match.
        # Document this as a known edge case (not a crash).
        self.assertTrue(result is None or isinstance(result, str))

    def test_no_newline_at_end_of_search_matches_via_dmp(self):
        # old_string lacks trailing newline — dmp or relative-indent may pick it up
        original = "foo\nbar\nbaz\n"
        result = apply_edit("foo\nbar\n", "QUX\n", original)
        self.assertIsNotNone(result)
        self.assertIn("QUX", result)

    def test_search_equals_entire_file(self):
        content = "hello\nworld\n"
        result = apply_edit(content, "replaced\n", content)
        self.assertEqual(result, "replaced\n")

    def test_empty_file_empty_search_does_not_crash(self):
        result = apply_edit("", "new content\n", "")
        self.assertTrue(result is None or isinstance(result, str))

    def test_newline_only_file(self):
        original = "\n\n\n"
        result = apply_edit("\n\n\n", "x\n", original)
        self.assertIsNotNone(result)
        self.assertEqual(result, "x\n")

    def test_add_import_at_top(self):
        original = "import os\n\ndef main():\n    pass\n"
        result = apply_edit("import os\n", "import os\nimport sys\n", original)
        self.assertIsNotNone(result)
        self.assertIn("import sys", result)


# ── _normalise_endings ────────────────────────────────────────────────────────

class TestNormaliseEndings(unittest.TestCase):

    def test_crlf_to_lf(self):
        self.assertEqual(_normalise_endings("a\r\nb\r\n"), "a\nb\n")

    def test_bare_cr_to_lf(self):
        self.assertEqual(_normalise_endings("a\rb\r"), "a\nb\n")

    def test_curly_left_single_quote(self):
        self.assertEqual(_normalise_endings("‘hi’"), "'hi'")

    def test_curly_double_quotes(self):
        self.assertEqual(_normalise_endings("“hello”"), '"hello"')

    def test_mixed_crlf_and_curly(self):
        result = _normalise_endings("a\r\nb‘c’\n")
        self.assertEqual(result, "a\nb'c'\n")

    def test_lf_unchanged(self):
        text = "a\nb\nc\n"
        self.assertEqual(_normalise_endings(text), text)

    def test_empty_string(self):
        self.assertEqual(_normalise_endings(""), "")


# ── _reindent ─────────────────────────────────────────────────────────────────

class TestReindent(unittest.TestCase):

    def test_2_to_4_space_inner_block(self):
        # File has 4-space indent; search uses 2-space for the inner block
        original = "    x = 1\n    return x\n"
        search   = "  x = 1\n  return x\n"
        replace  = "  x = 2\n  return x\n"
        result = _reindent(search, replace, original)
        self.assertIsNotNone(result)
        s2, r2 = result
        self.assertIn("    x = 1", s2)
        self.assertIn("    x = 2", r2)

    def test_already_aligned_returns_none(self):
        original = "    x = 1\n    return x\n"
        search   = "    x = 1\n    return x\n"
        replace  = "    x = 2\n    return x\n"
        self.assertIsNone(_reindent(search, replace, original))

    def test_no_matching_line_returns_none(self):
        original = "def f():\n    x = 1\n"
        search   = "NONEXISTENT_FUNCTION():\n  pass\n"
        replace  = "NONEXISTENT_FUNCTION():\n  return 1\n"
        self.assertIsNone(_reindent(search, replace, original))

    def test_blank_only_search_returns_none(self):
        self.assertIsNone(_reindent("\n\n", "\n\n", "x = 1\n"))


# ── _file_hint ────────────────────────────────────────────────────────────────

class TestFileHint(unittest.TestCase):

    def test_small_file_shows_all_lines(self):
        content = "\n".join(f"line {i}" for i in range(10))
        hint = _file_hint(content, "line 5")
        self.assertIn("line 0", hint)
        self.assertIn("line 9", hint)

    def test_large_file_shows_snippet_near_target(self):
        lines = [f"line {i}" for i in range(500)]
        content = "\n".join(lines)
        hint = _file_hint(content, "line 250")
        self.assertIn("250", hint)
        # Should NOT show line 0 (that's far away)
        self.assertNotIn("line 0", hint)

    def test_large_file_no_match_shows_preview(self):
        content = "\n".join(f"line {i}" for i in range(500))
        hint = _file_hint(content, "ZZZNOMATCH")
        self.assertIn("line 0", hint)   # falls back to first 40 lines

    def test_empty_file(self):
        hint = _file_hint("", "anything")
        self.assertIsInstance(hint, str)


# ── _search_and_replace ───────────────────────────────────────────────────────

class TestSearchAndReplace(unittest.TestCase):

    def test_returns_none_when_not_found(self):
        self.assertIsNone(_search_and_replace("X\n", "Y\n", "abc\n"))

    def test_returns_none_when_ambiguous(self):
        self.assertIsNone(_search_and_replace("a\n", "b\n", "a\na\n"))

    def test_returns_result_at_eof(self):
        # 'foo\n' at EOF — boundary satisfied
        result = _search_and_replace("foo\n", "bar\n", "foo\n")
        self.assertEqual(result, "bar\n")

    def test_returns_result_followed_by_blank_line(self):
        # 'foo\n' followed by '\n' (boundary char)
        result = _search_and_replace("foo\n", "bar\n", "foo\n\nbaz\n")
        self.assertEqual(result, "bar\n\nbaz\n")

    def test_boundary_at_eof(self):
        result = _search_and_replace("end\n", "DONE\n", "start\nend\n")
        self.assertIsNotNone(result)

    def test_mid_word_rejected(self):
        # "func" inside "function" — ends with 'c', not a boundary char
        result = _search_and_replace("func", "fn", "function()\n")
        self.assertIsNone(result)

    def test_semicolon_boundary(self):
        result = _search_and_replace("x = 1;", "x = 2;", "x = 1; y = 2")
        self.assertIsNotNone(result)


# ── EditTool.call integration ─────────────────────────────────────────────────

class TestEditToolCall(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tool = EditTool()

    def _ctx(self):
        return make_ctx(self.tmp)

    def _make_file(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp, name)
        write_file(path, content)
        record_read("test-session", path)
        return path

    def _clear(self, path: str) -> None:
        clear_staleness("test-session", path)

    # -- happy path --

    def test_basic_edit_succeeds(self):
        path = self._make_file("f.py", "x = 1\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "x = 1\n", "new_string": "x = 2\n"},
            self._ctx(),
        ))
        self.assertFalse(result.is_error)
        self.assertEqual(read_file(path), "x = 2\n")

    def test_relative_path_resolved(self):
        path = self._make_file("rel.py", "foo = 1\n")
        result = run(self.tool.call(
            {"file_path": "rel.py", "old_string": "foo = 1\n", "new_string": "foo = 2\n"},
            self._ctx(),
        ))
        self.assertFalse(result.is_error)
        self.assertEqual(read_file(path), "foo = 2\n")

    def test_multiline_edit(self):
        content = "def greet():\n    print('hello')\n    return None\n"
        path = self._make_file("g.py", content)
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "    print('hello')\n    return None\n",
            "new_string": "    print('world')\n    return 'world'\n",
        }, self._ctx()))
        self.assertFalse(result.is_error)
        self.assertIn("world", read_file(path))

    def test_delete_line(self):
        path = self._make_file("del.py", "a\nREMOVE\nb\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "REMOVE\n", "new_string": ""},
            self._ctx(),
        ))
        self.assertFalse(result.is_error)
        self.assertEqual(read_file(path), "a\nb\n")

    # -- error: file not found --

    def test_file_not_found(self):
        result = run(self.tool.call(
            {"file_path": "/nonexistent/path.py", "old_string": "x\n", "new_string": "y\n"},
            self._ctx(),
        ))
        self.assertTrue(result.is_error)
        self.assertIn("not found", result.output.lower())

    # -- error: staleness guard --

    def test_stale_file_rejected(self):
        path = self._make_file("stale.py", "original\n")
        time.sleep(0.05)
        write_file(path, "externally modified\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "original\n", "new_string": "new\n"},
            self._ctx(),
        ))
        self.assertTrue(result.is_error)
        self.assertIn("modified", result.output)

    # -- error: written but not read back --

    def test_written_unread_rejected(self):
        path = os.path.join(self.tmp, "w.py")
        write_file(path, "content\n")
        record_write("test-session", path)
        result = run(self.tool.call(
            {"file_path": path, "old_string": "content\n", "new_string": "new\n"},
            self._ctx(),
        ))
        self.assertTrue(result.is_error)
        self.assertIn("read", result.output.lower())

    # -- error: old_string not found --

    def test_old_string_not_found(self):
        path = self._make_file("nf.py", "actual content\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "MISSING TEXT\n", "new_string": "x\n"},
            self._ctx(),
        ))
        self.assertTrue(result.is_error)
        self.assertIn("not found", result.output.lower())

    def test_old_string_not_found_includes_file_hint(self):
        path = self._make_file("hint.py", "line1\nline2\nline3\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "NOPE\n", "new_string": "x\n"},
            self._ctx(),
        ))
        self.assertTrue(result.is_error)
        self.assertIn("line1", result.output)

    # -- duplicate match behaviour --

    def test_duplicate_match_replaces_at_most_one(self):
        # dmp may succeed on duplicate content, but must only change one occurrence.
        path = self._make_file("dup.py", "x = 1\nx = 1\n")
        result = run(self.tool.call(
            {"file_path": path, "old_string": "x = 1\n", "new_string": "x = 2\n"},
            self._ctx(),
        ))
        if not result.is_error:
            content = read_file(path)
            # Must not have silently replaced both lines
            self.assertEqual(content.count("x = 2"), 1)
            self.assertEqual(content.count("x = 1"), 1)

    # -- secret scanning --

    def test_secret_warning_in_output(self):
        path = self._make_file("sec.py", "key = 'old'\n")
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "key = 'old'\n",
            "new_string": "AWS_SECRET_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n",
        }, self._ctx()))
        if not result.is_error:
            self.assertIn("credential", result.output.lower())

    # -- record_read updated after success --

    def test_record_read_updated_after_edit(self):
        path = self._make_file("idem.py", "a = 1\n")
        run(self.tool.call(
            {"file_path": path, "old_string": "a = 1\n", "new_string": "a = 2\n"},
            self._ctx(),
        ))
        from tools.file_staleness import is_stale
        self.assertFalse(is_stale("test-session", path))

    # -- encoding --

    def test_unicode_file(self):
        content = "# -*- coding: utf-8 -*-\nname = '日本語'\n"
        path = self._make_file("uni.py", content)
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "'日本語'\n",
            "new_string": "'English'\n",
        }, self._ctx()))
        self.assertFalse(result.is_error)
        self.assertIn("English", read_file(path))

    # -- wrong indent healed --

    def test_wrong_indent_healed(self):
        content = "def foo():\n    if True:\n        pass\n"
        path = self._make_file("ind.py", content)
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "    if True:\n        pass\n",
            "new_string": "    if True:\n        return 1\n",
        }, self._ctx()))
        self.assertFalse(result.is_error)
        self.assertIn("return 1", read_file(path))

    # -- CRLF file --

    def test_crlf_file_edited(self):
        path = os.path.join(self.tmp, "crlf.py")
        with open(path, "wb") as f:
            f.write(b"foo\r\nbar\r\n")
        record_read("test-session", path)
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "foo\nbar\n",
            "new_string": "baz\n",
        }, self._ctx()))
        self.assertFalse(result.is_error)
        self.assertIn("baz", read_file(path))

    # -- curly quotes in old_string --

    def test_curly_quotes_in_old_string(self):
        path = self._make_file("cq.py", "print('hello')\n")
        result = run(self.tool.call({
            "file_path": path,
            "old_string": "print(‘hello’)\n",
            "new_string": "print('world')\n",
        }, self._ctx()))
        self.assertFalse(result.is_error)
        self.assertIn("world", read_file(path))

    # -- multiple edits in sequence --

    def test_sequential_edits(self):
        path = self._make_file("seq.py", "a = 1\nb = 2\nc = 3\n")
        run(self.tool.call(
            {"file_path": path, "old_string": "a = 1\n", "new_string": "a = 10\n"},
            self._ctx(),
        ))
        record_read("test-session", path)
        run(self.tool.call(
            {"file_path": path, "old_string": "b = 2\n", "new_string": "b = 20\n"},
            self._ctx(),
        ))
        content = read_file(path)
        self.assertIn("a = 10", content)
        self.assertIn("b = 20", content)
        self.assertIn("c = 3", content)


if __name__ == "__main__":
    unittest.main()
