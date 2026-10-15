"""Translate sed regular expressions to Python `re` syntax.

Basic regular expressions use `\\( \\) \\{ \\}` for groups and intervals and
`\\+ \\? \\|` for one-or-more, optional and alternation.  Extended regular
expressions (-E) already use Python's operator syntax.
"""
import re

BRE_ESCAPES = {"(": "(", ")": ")", "{": "{", "}": "}", "+": "+", "?": "?", "|": "|"}


def translate(pattern, extended):
    if extended:
        return pattern
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            d = pattern[i + 1]
            if d in BRE_ESCAPES:
                out.append(BRE_ESCAPES[d])
            elif d.isdigit():
                out.append("\\" + d)
            else:
                out.append(re.escape(d))
            i += 2
            continue
        if c in "(){}+?|":
            out.append("\\" + c)
        elif c == "*" and (i == 0 or pattern[i - 1] == "^"):
            out.append("\\*")
        elif c == "[":
            j = pattern.find("]", i + 2 if pattern[i + 1:i + 2] in ("]", "^") else i + 1)
            if j < 0:
                raise ValueError("unterminated [")
            out.append(pattern[i:j + 1].replace("\\", "\\\\"))
            i = j + 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)
