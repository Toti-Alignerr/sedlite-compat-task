import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cli(args, stdin=b"", cwd=None):
    env = dict(os.environ, PYTHONPATH=ROOT)
    p = subprocess.run([sys.executable, "-m", "sedlite"] + args, input=stdin, capture_output=True, cwd=cwd, env=env)
    return p.stdout, p.returncode


class CliTest(unittest.TestCase):
    def test_numbered_files(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("a.txt", "alpha\nbeta\n"), ("b.txt", "gamma\n")):
                with open(os.path.join(d, name), "w") as f:
                    f.write(text)
            self.assertEqual(cli(["=", "a.txt", "b.txt"], cwd=d), (b"1\nalpha\n2\nbeta\n3\ngamma\n", 0))

    def test_stdin(self):
        self.assertEqual(cli(["s/e*$/!/"], b"one\ntwo\nthree\n"), (b"on!\ntwo!\nthr!\n", 0))
