"""The sedlite stream editor.

`parse_script` turns the script into a list of commands (blocks are nested
lists); `Editor` runs them over the input lines.  Regular expressions are
translated to Python's `re` syntax by `regex.translate`.
"""
import re

from .regex import translate


class SedError(Exception):
    pass


class Quit(Exception):
    def __init__(self, status=0):
        super().__init__(status)
        self.status = status


class Address:
    def __init__(self, kind, value=None):
        self.kind, self.value = kind, value     # "line", "last", "re", "step", "rel"


class Command:
    def __init__(self, name):
        self.name = name
        self.addr1 = self.addr2 = None
        self.negate = False
        self.arg = None            # text, file name, label, or (regex, repl, flags)
        self.block = None
        self.active = False        # inside a range


# ---------------------------------------------------------------- parsing

ADDR_RE = re.compile(r"(\d+)~(\d+)|(\d+)|\$|/((?:\\.|[^/\\])*)/(I?)|\\(.)")


def parse_address(text, i, extended):
    if text.startswith("$", i):
        return Address("last"), i + 1
    m = re.compile(r"(\d+)~(\d+)").match(text, i)
    if m:
        return Address("step", (int(m.group(1)), int(m.group(2)))), m.end()
    m = re.compile(r"\d+").match(text, i)
    if m:
        return Address("line", int(m.group())), m.end()
    if i < len(text) and text[i] in "/\\":
        delim = "/"
        if text[i] == "\\":
            i += 1
            delim = text[i]
        pattern, i = read_delimited(text, i + 1, delim)
        flags = 0
        if text.startswith("I", i):
            flags = re.I
            i += 1
        return Address("re", re.compile(translate(pattern, extended), flags) if pattern else None), i
    return None, i


def read_delimited(text, i, delim):
    out = []
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            if text[i + 1] == delim:
                out.append(delim)
            elif text[i + 1] == "n":
                out.append("\n")
            else:
                out.append(text[i:i + 2])
            i += 2
            continue
        if c == delim:
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise SedError("unterminated `s' command")


def read_word(text, i):
    """Read a label or file name: up to `;` or end of line."""
    m = re.compile(r"\s*([^;\n]*)").match(text, i)
    return m.group(1).strip(), m.end()


def read_text(text, i):
    """Text for a, i, c: GNU one-liner form or the `a\\` form."""
    while i < len(text) and text[i] in " \t":
        i += 1
    if text.startswith("\\\n", i):
        i += 2
    elif text.startswith("\\", i):
        i += 1
    lines = []
    while i <= len(text):
        j = text.find("\n", i)
        if j < 0:
            j = len(text)
        line = text[i:j]
        if line.endswith("\\"):
            lines.append(line[:-1])
            i = j + 1
            continue
        lines.append(line)
        i = j + 1
        break
    return "\n".join(lines) + "\n", i


def parse_script(text, extended):
    cmds, i = parse_block(text, 0, extended, top=True)
    return cmds


def parse_block(text, i, extended, top=False):
    cmds = []
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\n;":
            i += 1
        if i >= n:
            break
        if text[i] == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if text[i] == "}":
            if top:
                raise SedError("unexpected `}'")
            return cmds, i + 1
        cmd = Command(None)
        cmd.addr1, i = parse_address(text, i, extended)
        if cmd.addr1 is not None and text.startswith(",", i):
            i += 1
            if text.startswith("+", i):
                m = re.compile(r"\+(\d+)").match(text, i)
                cmd.addr2, i = Address("rel", int(m.group(1))), m.end()
            else:
                cmd.addr2, i = parse_address(text, i, extended)
        while i < n and text[i] in " \t":
            i += 1
        if text.startswith("!", i):
            cmd.negate = True
            i += 1
            while i < n and text[i] in " \t":
                i += 1
        if i >= n:
            raise SedError("missing command")
        name = text[i]
        cmd.name = name
        i += 1
        if name == "{":
            cmd.block, i = parse_block(text, i, extended)
        elif name in "aic":
            cmd.arg, i = read_text(text, i)
        elif name in "bt:rw":
            cmd.arg, i = read_word(text, i)
        elif name == "q":
            m = re.compile(r"\s*(\d*)").match(text, i)
            cmd.arg = int(m.group(1)) if m.group(1) else 0
            i = m.end()
        elif name == "s":
            delim = text[i]
            pattern, i = read_delimited(text, i + 1, delim)
            repl, i = read_delimited(text, i, delim)
            m = re.compile(r"[gpI0-9]*(w [^\n;]*)?").match(text, i)
            flags = m.group()
            i = m.end()
            rx = re.compile(translate(pattern, extended), re.I if "I" in flags else 0) if pattern else None
            cmd.arg = (rx, repl, flags)
        elif name == "y":
            delim = text[i]
            src, i = read_delimited(text, i + 1, delim)
            dst, i = read_delimited(text, i, delim)
            if len(src) != len(dst):
                raise SedError("strings for `y' command are different lengths")
            cmd.arg = dict(zip(src, dst))
        elif name not in "=dDgGhHlnNpPx":
            raise SedError("unknown command: `%s'" % name)
        cmds.append(cmd)
    if not top:
        raise SedError("unmatched `{'")
    return cmds, i


# ---------------------------------------------------------------- running

class Editor:
    def __init__(self, cmds, quiet, out, inputs):
        self.cmds = cmds
        self.quiet = quiet
        self.out = out
        self.lines = inputs           # list of lines without newlines
        self.index = 0
        self.lineno = 0
        self.ps = ""
        self.hs = ""
        self.appends = []
        self.subst_done = False
        self.last_re = None
        self.wfiles = {}
        self.labels = {}
        self.index_labels(cmds)

    def index_labels(self, cmds):
        for c in cmds:
            if c.name == ":":
                self.labels[c.arg] = c
            if c.block:
                self.index_labels(c.block)

    def next_line(self):
        if self.index >= len(self.lines):
            return None
        line = self.lines[self.index]
        self.index += 1
        self.lineno += 1
        return line

    def is_last(self):
        return self.index >= len(self.lines)

    def match(self, a):
        if a.kind == "line":
            return self.lineno == a.value
        if a.kind == "last":
            return self.is_last()
        if a.kind == "step":
            first, step = a.value
            return self.lineno == first if step == 0 else (self.lineno >= first and (self.lineno - first) % step == 0)
        rx = a.value or self.last_re
        self.last_re = rx
        return rx.search(self.ps) is not None

    def selected(self, c):
        if c.addr1 is None:
            hit = True
        elif c.addr2 is None:
            hit = self.match(c.addr1)
        elif c.active:
            hit = True
            if c.addr2.kind == "rel":
                if self.lineno >= c.start + c.addr2.value:
                    c.active = False
            elif c.addr2.kind == "line":
                if self.lineno >= c.addr2.value:
                    c.active = False
            elif self.match(c.addr2):
                c.active = False
        elif self.match(c.addr1):
            hit = True
            c.active = True
            c.start = self.lineno
            if c.addr2.kind == "line" and c.addr2.value <= self.lineno:
                c.active = False
        else:
            hit = False
        return hit != c.negate

    def emit(self, text):
        self.out.append(text + "\n")

    def run(self):
        while True:
            line = self.next_line()
            if line is None:
                break
            self.ps = line
            deleted = self.execute(self.cmds)
            if not deleted and not self.quiet:
                self.emit(self.ps)
            self.flush()
        return 0

    def flush(self):
        for kind, value in self.appends:
            if kind == "text":
                self.out.append(value)
            else:
                try:
                    with open(value, encoding="utf-8") as f:
                        self.out.append(f.read())
                except OSError:
                    pass
        self.appends = []

    def execute(self, cmds):
        """Run `cmds`; return True if the pattern space was deleted."""
        i = 0
        while i < len(cmds):
            c = cmds[i]
            i += 1
            if not self.selected(c):
                continue
            n = c.name
            if n == "{":
                if self.execute(c.block):
                    return True
            elif n == "=":
                self.emit(str(self.lineno))
            elif n == "a":
                self.appends.append(("text", c.arg))
            elif n == "i":
                self.out.append(c.arg)
            elif n == "c":
                self.out.append(c.arg)
                return True
            elif n == "d":
                return True
            elif n == "D":
                if "\n" not in self.ps:
                    return True
                self.ps = self.ps.split("\n", 1)[1]
                i = 0
                continue
            elif n == "p":
                self.emit(self.ps)
            elif n == "P":
                self.emit(self.ps.split("\n", 1)[0])
            elif n == "n":
                if not self.quiet:
                    self.emit(self.ps)
                line = self.next_line()
                if line is None:
                    raise Quit(0)
                self.ps = line
            elif n == "N":
                line = self.next_line()
                if line is None:
                    if not self.quiet:
                        self.emit(self.ps)
                    raise Quit(0)
                self.ps += "\n" + line
            elif n == "g":
                self.ps = self.hs
            elif n == "G":
                self.ps += "\n" + self.hs
            elif n == "h":
                self.hs = self.ps
            elif n == "H":
                self.hs += "\n" + self.ps
            elif n == "x":
                self.ps, self.hs = self.hs, self.ps
            elif n == "l":
                self.list_line()
            elif n == "q":
                if not self.quiet:
                    self.emit(self.ps)
                self.flush()
                raise Quit(c.arg)
            elif n == "r":
                self.appends.append(("file", c.arg))
            elif n == "w":
                self.write_file(c.arg, self.ps)
            elif n == "s":
                if self.substitute(c):
                    self.subst_done = True
            elif n == "y":
                self.ps = "".join(c.arg.get(ch, ch) for ch in self.ps)
            elif n in "bt":
                if n == "t" and not self.subst_done:
                    continue
                self.subst_done = False
                if not c.arg:
                    return False
                target = self.labels.get(c.arg)
                if target is None:
                    raise SedError("can't find label for jump to `%s'" % c.arg)
                return self.jump(target)
        return False

    def jump(self, target):
        # find the label at the top level and continue after it
        for k, c in enumerate(self.cmds):
            if c is target:
                return self.execute(self.cmds[k + 1:])
        return False

    def list_line(self):
        out = []
        for ch in self.ps:
            if ch == "\\":
                out.append("\\\\")
            elif ch == "\t":
                out.append("\\t")
            elif ch == "\n":
                out.append("\\n")
            elif " " <= ch <= "~":
                out.append(ch)
            else:
                out.append("\\%03o" % ord(ch))
        s = "".join(out)
        while len(s) > 69:
            self.out.append(s[:69] + "\\\n")
            s = s[69:]
        self.out.append(s + "$\n")

    def write_file(self, name, text):
        if name not in self.wfiles:
            self.wfiles[name] = open(name, "w", encoding="utf-8")
        self.wfiles[name].write(text + "\n")

    def substitute(self, c):
        rx, repl, flags = c.arg
        rx = rx or self.last_re
        if rx is None:
            raise SedError("no previous regular expression")
        self.last_re = rx
        count = 0
        nth = int("".join(ch for ch in flags if ch.isdigit()) or 1)
        glob = "g" in flags

        def expand(m):
            out = []
            i = 0
            while i < len(repl):
                ch = repl[i]
                if ch == "\\" and i + 1 < len(repl):
                    d = repl[i + 1]
                    if d.isdigit():
                        out.append(m.group(int(d)) or "")
                    elif d == "n":
                        out.append("\n")
                    elif d == "t":
                        out.append("\t")
                    else:
                        out.append(d)
                    i += 2
                    continue
                out.append(m.group(0) if ch == "&" else ch)
                i += 1
            return "".join(out)

        def sub(m):
            nonlocal count
            count += 1
            if count == nth or (glob and count >= nth):
                return expand(m)
            return m.group(0)

        new, n = rx.subn(sub, self.ps, count=0 if glob or nth > 1 else 1)
        if count < nth:
            return False
        self.ps = new
        if "p" in flags:
            self.emit(self.ps)
        w = re.search(r"w (.*)$", flags)
        if w:
            self.write_file(w.group(1), self.ps)
        return True

    def close(self):
        for f in self.wfiles.values():
            f.close()


# ---------------------------------------------------------------- driver

def run(argv, stdin, stdout, stderr):
    """Run sedlite with command-line `argv`; return the exit status."""
    quiet = extended = False
    scripts = []
    files = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-n":
            quiet = True
        elif a in ("-E", "-r"):
            extended = True
        elif a == "-e":
            i += 1
            scripts.append(argv[i])
        elif a == "-f":
            i += 1
            with open(argv[i], encoding="utf-8") as f:
                scripts.append(f.read())
        else:
            files.append(a)
        i += 1
    if not scripts:
        if not files:
            stderr.write("usage: sedlite [-nE] [-e script] [-f file] [script] [file ...]\n")
            return 1
        scripts.append(files.pop(0))
    status = 0
    text = []
    for name in files or ["-"]:
        if name == "-":
            text.append(stdin.read().decode("utf-8"))
            continue
        try:
            with open(name, encoding="utf-8") as f:
                text.append(f.read())
        except OSError:
            stderr.write("sedlite: can't read %s: No such file or directory\n" % name)
            status = 2
    data = "".join(t if t.endswith("\n") or not t else t + "\n" for t in text)
    out = []
    editor = None
    try:
        cmds = parse_script("\n".join(scripts), extended)
        editor = Editor(cmds, quiet, out, data.split("\n")[:-1] if data else [])
        editor.run()
    except Quit as q:
        status = q.status
    except SedError as e:
        stderr.write("sedlite: -e expression #1: %s\n" % e)
        status = 1
    finally:
        if editor:
            editor.close()
    stdout.write("".join(out).encode("utf-8"))
    return status
