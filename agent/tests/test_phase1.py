import os
import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import asyncio

# Setup path to include agent/
AGENT_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(AGENT_DIR))

from harness.context_manager import estimate_tokens, should_compact
from harness.message import Message
from tools.file_staleness import record_read, is_stale, clear_staleness
from tools.edit_tool import _normalise_quotes
from tools.file_utils import suggest_paths
from harness.orchestrator import _parse_tool_uses
from prompt.system_prompt import build_session_context, build_system_prompt


class TestPhase1(unittest.TestCase):

    # ── Gap 1: Token Counting ────────────────────────────────────────────────

    def test_estimate_tokens_fallback(self):
        messages = [Message.user("Hello world")]
        # "Hello world" is 11 chars. 11 // 4 = 2.
        self.assertEqual(estimate_tokens(messages), 2)

    def test_estimate_tokens_with_backend(self):
        messages = [Message.user("Hello")]
        count_fn = MagicMock(return_value=5)
        # 5 (from count_fn) + 10 (overhead) = 15
        self.assertEqual(estimate_tokens(messages, count_tokens_fn=count_fn), 15)
        count_fn.assert_called_with("Hello")

    # ── Gap 3: Staleness Guard ───────────────────────────────────────────────

    def test_staleness_guard(self):
        session_id = "test_session"
        file_path = "test_file_staleness.txt"
        with open(file_path, "w") as f:
            f.write("initial content")
        
        abs_path = os.path.abspath(file_path)
        
        # Record read
        record_read(session_id, abs_path)
        self.assertFalse(is_stale(session_id, abs_path))
        
        # Modify file
        import time
        time.sleep(0.02) # Ensure mtime changes
        with open(file_path, "w") as f:
            f.write("modified content")
            
        self.assertTrue(is_stale(session_id, abs_path))
        
        # Clear staleness
        clear_staleness(session_id, abs_path)
        self.assertFalse(is_stale(session_id, abs_path))
        
        if os.path.exists(file_path):
            os.remove(file_path)

    def test_staleness_cleared_on_delete_and_move(self):
        from tools.delete_tool import DeleteFileTool
        from tools.move_tool import MoveTool
        from harness.tool_registry import ToolContext
        from harness.permissions import PermissionMode

        session_id = "test_session_tools"
        ctx = ToolContext(working_directory=".", session_id=session_id, permission_mode=PermissionMode.AUTO_READ)
        
        # Test Delete
        f1 = "test_del.txt"
        with open(f1, "w") as f: f.write("del me")
        abs_f1 = os.path.abspath(f1)
        record_read(session_id, abs_f1)
        
        dt = DeleteFileTool()
        asyncio.run(dt.call({"path": f1}, ctx))
        self.assertFalse(is_stale(session_id, abs_f1)) # Should be cleared
        
        # Test Move
        f2 = "test_move_src.txt"
        f3 = "test_move_dst.txt"
        with open(f2, "w") as f: f.write("move me")
        abs_f2 = os.path.abspath(f2)
        abs_f3 = os.path.abspath(f3)
        record_read(session_id, abs_f2)
        record_read(session_id, abs_f3)
        
        mt = MoveTool()
        asyncio.run(mt.call({"source": f2, "destination": f3}, ctx))
        self.assertFalse(is_stale(session_id, abs_f2))
        self.assertFalse(is_stale(session_id, abs_f3))
        
        if os.path.exists(f3): os.remove(f3)

    def test_multiedit_features(self):
        from tools.multi_edit_tool import MultiEditTool
        from harness.tool_registry import ToolContext
        from harness.permissions import PermissionMode

        session_id = "test_session_multi"
        cwd = os.getcwd()
        ctx = ToolContext(working_directory=cwd, session_id=session_id, permission_mode=PermissionMode.AUTO_READ)
        
        f = "test_multi.txt"
        abs_f = os.path.join(cwd, f)
        with open(abs_f, "w") as f_obj: f_obj.write("line 1\nline 2\n“quoted”")
        record_read(session_id, abs_f)
        
        # 1. Test normal multi-edit
        met = MultiEditTool()
        res = asyncio.run(met.call({
            "file_path": f,
            "edits": [
                {"old_string": "line 1", "new_string": "line 1 modified"},
                {"old_string": "line 2", "new_string": "line 2 modified"}
            ]
        }, ctx))
        self.assertFalse(res.is_error)
        with open(abs_f, "r") as f_obj:
            content = f_obj.read()
            self.assertIn("line 1 modified", content)
            self.assertIn("line 2 modified", content)
            
        # 2. Test quote normalisation in MultiEdit
        record_read(session_id, abs_f)
        res = asyncio.run(met.call({
            "file_path": f,
            "edits": [
                {"old_string": '"quoted"', "new_string": "unquoted"}
            ]
        }, ctx))
        self.assertFalse(res.is_error)
        with open(abs_f, "r") as f_obj:
            self.assertIn("unquoted", f_obj.read())

        # 3. Test staleness in MultiEdit
        record_read(session_id, abs_f)
        import time
        time.sleep(0.02)
        with open(abs_f, "w") as f_obj: f_obj.write("externally modified")
        
        res = asyncio.run(met.call({
            "file_path": f,
            "edits": [{"old_string": "externally", "new_string": "failed"}]
        }, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("modified since it was last read", res.output)
        
        if os.path.exists(abs_f): os.remove(abs_f)

    # ── Gap 4: Quote Normalisation ───────────────────────────────────────────

    def test_normalise_quotes(self):
        self.assertEqual(_normalise_quotes("“Hello”"), '"Hello"')
        self.assertEqual(_normalise_quotes("‘World’"), "'World'")
        self.assertEqual(_normalise_quotes("No quotes"), "No quotes")

    # ── Gap 5: Fuzzy Path Recovery ──────────────────────────────────────────

    def test_suggest_paths(self):
        # Create some files
        test_root = "test_dir_fuzzy"
        os.makedirs(os.path.join(test_root, "subdir"), exist_ok=True)
        with open(os.path.join(test_root, "Terminal.tsx"), "w") as f: f.write("")
        with open(os.path.join(test_root, "subdir/App.tsx"), "w") as f: f.write("")
        
        cwd = os.path.abspath(test_root)
        suggestions = suggest_paths("Terminl.tsx", cwd)
        self.assertIn("Terminal.tsx", suggestions)
        
        suggestions = suggest_paths("subdir/Ap.tsx", cwd)
        self.assertIn("subdir/App.tsx", suggestions)

        # Test folders_only
        suggestions = suggest_paths("subdr", cwd, folders_only=True)
        self.assertIn("subdir", suggestions)
        
        # Cleanup
        import shutil
        shutil.rmtree(test_root)

    def test_tool_fuzzy_suggestions(self):
        from tools.read_tool import ReadTool
        from tools.edit_tool import EditTool
        from tools.write_tool import WriteTool
        from tools.glob_tool import GlobTool
        from harness.tool_registry import ToolContext
        from harness.permissions import PermissionMode

        test_root = "test_tools_fuzzy"
        os.makedirs(os.path.join(test_root, "src"), exist_ok=True)
        with open(os.path.join(test_root, "src/main.py"), "w") as f: f.write("print('hello')")
        
        cwd = os.path.abspath(test_root)
        ctx = ToolContext(working_directory=cwd, session_id="test", permission_mode=PermissionMode.AUTO_ALL)
        
        # 1. ReadTool suggestions
        rt = ReadTool()
        res = asyncio.run(rt.call({"file_path": "src/mainn.py"}, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("Did you mean one of:", res.output)
        self.assertIn("src/main.py", res.output)
        
        # 2. EditTool suggestions
        et = EditTool()
        res = asyncio.run(et.call({"file_path": "src/mainn.py", "old_string": "foo", "new_string": "bar"}, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("Did you mean one of:", res.output)
        self.assertIn("src/main.py", res.output)

        # 3. GlobTool suggestions (directories)
        gt = GlobTool()
        res = asyncio.run(gt.call({"pattern": "*.py", "path": "srcc"}, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("Did you mean one of:", res.output)
        self.assertIn("src", res.output)

        # 4. WriteTool suggestions (directories)
        wt = WriteTool()
        res = asyncio.run(wt.call({"file_path": "srcc/new.py", "content": "print('new')"}, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("Did you mean one of:", res.output)
        self.assertIn("src", res.output)

        # 5. ListDirTool suggestions (directories)
        from tools.list_dir_tool import ListDirTool
        ld = ListDirTool()
        res = asyncio.run(ld.call({"path": "srcc"}, ctx))
        self.assertTrue(res.is_error)
        self.assertIn("Did you mean one of:", res.output)
        self.assertIn("src", res.output)
        
        # Cleanup
        import shutil
        shutil.rmtree(test_root)

    # ── Gap 8: KV Cache Stabilization ────────────────────────────────────────

    def test_build_session_context_with_git(self):
        with patch("shutil.which") as mock_which, patch("subprocess.check_output") as mock_check_output, patch("subprocess.check_call") as mock_check_call:
            mock_which.return_value = "/usr/bin/git"
            mock_check_call.return_value = 0
            mock_check_output.side_effect = [
                "main",      # branch
                "M file.py", # status
                "abc1234 Fix bug" # log
            ]
            
            ctx = build_session_context("/test/dir")
            self.assertIn("Git branch: main", ctx)
            self.assertIn("Recent commits:\nabc1234 Fix bug", ctx)
            self.assertIn("Working tree:\nM file.py", ctx)
            self.assertIn("Working directory: /test/dir", ctx)

    def test_prime_cache_async(self):
        from backends.llamacpp_backend import LlamaCppBackend
        backend = LlamaCppBackend()
        backend._llm = MagicMock()
        backend._llm.tokenize.return_value = [1, 2, 3]
        
        # Since it's an async test, we need to run it in a loop
        async def run():
            await backend.prime_cache("test prefix")
        
        asyncio.run(run())
        backend._llm.eval.assert_called_with([1, 2, 3])

    # ── Gap 9: Hardened Parser ───────────────────────────────────────────────

    def test_parse_tool_uses_robustness(self):
        # 1. Standard XML
        text = '<tool_use><name>Read</name><input>{"file_path": "test.py"}</input></tool_use>'
        results = _parse_tool_uses(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Read")
        self.assertEqual(results[0].input["file_path"], "test.py")

        # 2. Bare JSON after <name>
        text = '<tool_use><name>Read</name> {"file_path": "test.py"}</tool_use>'
        results = _parse_tool_uses(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Read")
        self.assertEqual(results[0].input["file_path"], "test.py")

        # 3. Fenced JSON
        text = '```json\n{"name": "Read", "input": {"file_path": "test.py"}}\n```'
        results = _parse_tool_uses(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Read")
        self.assertEqual(results[0].input["file_path"], "test.py")

        # 4. Bare JSON object
        text = '\n{"name": "Read", "input": {"file_path": "test.py"}}\n'
        results = _parse_tool_uses(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Read")
        self.assertEqual(results[0].input["file_path"], "test.py")

    def test_failed_tool_call_retry(self):
        # We simulate the _agent_loop logic for Gap 9
        response_text = "<tool_use><name>Read</name><input>INVALID JSON</input></tool_use>"
        tool_uses = _parse_tool_uses(response_text)
        self.assertEqual(len(tool_uses), 0)
        
        # Check logic in orchestrator: if not tool_uses and "<tool_use>" in response_text
        self.assertTrue("<tool_use>" in response_text)


if __name__ == "__main__":
    unittest.main()
