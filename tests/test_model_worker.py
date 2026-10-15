import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
from model_worker import ModelWorker
from demucs_runner import serve


class CachedCLITests(unittest.TestCase):
    def test_same_model_loaded_once_and_cli_options_preserved(self):
        loads, calls = [], []
        sentinel = object()
        def loader(args):
            loads.append(args.name)
            return sentinel
        module = types.SimpleNamespace(get_model_from_args=loader)
        def main(args):
            calls.append(args)
            self.assertIs(module.get_model_from_args(types.SimpleNamespace(name="htdemucs", repo=None)), sentinel)
            if args == ["fail"]:
                raise RuntimeError("CUDA out of memory")
        module.main = main
        requests = [{"id": 1, "args": ["--device", "cuda", "--shifts", "2"]},
                    {"id": 2, "args": ["fail"]},
                    {"id": 3, "args": ["--device", "cpu", "--shifts", "2"]}]
        with tempfile.TemporaryDirectory() as scratch:
            reply = Path(scratch) / "reply.json"
            with patch("sys.stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests))):
                serve(reply, module)
            self.assertEqual(json.loads(reply.read_text()), {"id": 3, "ok": True})
        self.assertEqual(loads, ["htdemucs"])
        self.assertEqual(calls, [r["args"] for r in requests])
        self.assertIs(module.get_model_from_args, loader)

    def test_worker_response_reports_error_for_cpu_fallback(self):
        module = types.SimpleNamespace(get_model_from_args=lambda args: object())
        def fail(_):
            raise RuntimeError("CUDA out of memory")
        module.main = fail
        with tempfile.TemporaryDirectory() as scratch:
            reply = Path(scratch) / "reply.json"
            with patch("sys.stdin", io.StringIO('{"id": 7, "args": []}\n')):
                serve(reply, module)
            data = json.loads(reply.read_text())
        self.assertFalse(data["ok"])
        self.assertIn("CUDA out of memory", data["error"])


class WorkerProcessTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.cancel = threading.Event()
        self.real_popen = __import__("subprocess").Popen
        self.children = []
        self.code = '''import json,sys,pathlib,time
reply=pathlib.Path(sys.argv[1])
for line in sys.stdin:
    request=json.loads(line)
    if request['args']==['slow']: time.sleep(30)
    if request['args']==['crash']: print('worker crashed',flush=True); sys.exit(9)
    data={'id':request['id'],'ok':request['args']!=['fail'],'error':'test failure'}
    temporary=reply.with_suffix('.tmp')
    temporary.write_text(json.dumps(data),encoding='utf-8')
    temporary.replace(reply)
'''

    def tearDown(self):
        for child in self.children:
            self.assertIsNotNone(child.poll(), "Model subprocess leaked")
        self.scratch.cleanup()

    def spawn(self, args, **kwargs):
        child = self.real_popen([sys.executable, "-u", "-c", self.code, str(args[-1])], **kwargs)
        self.children.append(child)
        return child

    def worker(self):
        return ModelWorker(self.scratch.name, self.cancel, lambda *_: None)

    def test_multiple_chunks_share_process_and_errors_do_not_stall(self):
        with patch("model_worker.subprocess.Popen", side_effect=self.spawn):
            with self.worker() as worker:
                worker.run(["first"])
                pid = worker.process.pid
                with self.assertRaisesRegex(RuntimeError, "test failure"):
                    worker.run(["fail"])
                worker.run(["âm thanh thứ hai"])
                self.assertEqual(pid, worker.process.pid)
        self.assertEqual(len(self.children), 1)

    def test_cancel_stops_process(self):
        timer = threading.Timer(.2, self.cancel.set)
        with patch("model_worker.subprocess.Popen", side_effect=self.spawn):
            with self.worker() as worker:
                timer.start()
                try:
                    with self.assertRaises(engine.Cancelled):
                        worker.run(["slow"])
                finally:
                    timer.cancel()

    def test_crash_reports_child_logs_and_restart_uses_new_process(self):
        with patch("model_worker.subprocess.Popen", side_effect=self.spawn):
            with self.worker() as worker:
                with self.assertRaisesRegex(RuntimeError, "worker crashed"):
                    worker.run(["crash"])
                worker.restart()
                worker.run(["cpu retry"])
        self.assertEqual(len(self.children), 2)
