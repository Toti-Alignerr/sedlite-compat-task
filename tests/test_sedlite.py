import io
import os
import tempfile
import unittest

import sedlite

TEXT = "one\ntwo\nthree\n"


def sed(args, stdin=TEXT, files=None):
    """Run sedlite in a scratch directory; return (stdout, status)."""
    with tempfile.TemporaryDirectory() as d:
        for name, text in (files or {}).items():
            with open(os.path.join(d, name), "w", encoding="latin-1") as f:
                f.write(text)
        old = os.getcwd()
        os.chdir(d)
        try:
            out = io.BytesIO()
            status = sedlite.run(args, io.BytesIO(stdin.encode("latin-1")), out, io.StringIO())
        finally:
            os.chdir(old)
    return out.getvalue().decode("latin-1"), status


class CommandTest(unittest.TestCase):
    def test_substitute(self):
        self.assertEqual(sed(["s/o/0/g"]), ("0ne\ntw0\nthree\n", 0))
        self.assertEqual(sed(["-E", "s/(t)(w)/\\2\\1/"]), ("one\nwto\nthree\n", 0))

    def test_print_and_delete(self):
        self.assertEqual(sed(["-n", "2,3p"]), ("two\nthree\n", 0))
        self.assertEqual(sed(["/two/d"]), ("one\nthree\n", 0))

    def test_transliterate(self):
        self.assertEqual(sed(["y/otw/OTW/"]), ("One\nTWO\nThree\n", 0))

    def test_hold_space(self):
        self.assertEqual(sed(["1!G;h;$!d"]), ("three\ntwo\none\n", 0))

    def test_text_commands(self):
        self.assertEqual(sed(["2a\\\nadded"]), ("one\ntwo\nadded\nthree\n", 0))
        self.assertEqual(sed(["1i\\\nfirst"]), ("first\none\ntwo\nthree\n", 0))
        self.assertEqual(sed(["2c\\\nchanged"]), ("one\nchanged\nthree\n", 0))

    def test_blocks(self):
        self.assertEqual(sed(["-n", "/^t/{s/t/T/;p;}"]), ("Two\nThree\n", 0))

    def test_line_numbers_and_quit(self):
        self.assertEqual(sed(["-n", "$="]), ("3\n", 0))
        self.assertEqual(sed(["2q"]), ("one\ntwo\n", 0))

    def test_scripts_and_files(self):
        self.assertEqual(sed(["-e", "s/o/O/", "-e", "$d"]), ("One\ntwO\n", 0))
        files = {"a.txt": "alpha\nbeta\n", "b.txt": "gamma\n", "s.sed": "s/a/A/g\n$a\\\nEND\n"}
        self.assertEqual(sed(["-f", "s.sed", "a.txt", "b.txt"], "", files), ("AlphA\nbetA\ngAmmA\nEND\n", 0))
