# sedlite

A pure-Python implementation of the `sed` stream editor, meant as a drop-in
replacement for the `sed` that ships with macOS (`/usr/bin/sed`, the
FreeBSD-derived sed). The same script and input must give the same output,
the same files written by `w`, and the same exit status.

```sh
python3 -m sedlite [-nEr] [-e script]... [-f script_file]... [script] [file ...]
python3 -m unittest discover -s tests
```

Python 3.10+, standard library only.

## Command line

* `-n` turns off the automatic printing of the pattern space. A script whose first line starts with `#n` has the same effect.
* `-E` / `-r` use extended regular expressions instead of basic ones.
* `-e script` adds a piece of script and `-f file` adds a script file. The pieces are joined with newlines, in order. Without `-e` or `-f`, the first operand is the script.
* The remaining operands are input files, read in order as one stream. With no input files, standard input is read.
* Exit status: 0 on success; 1 for an invalid script (nothing is processed) or when an input file cannot be read (the other files are still processed).

## Scripts

* Commands are separated by newlines or `;`. Each command may be preceded by addresses and `!`.
* **Addresses:**
  * a line number;
  * `$` (the last line);
  * `/re/` or `\cREc`, optionally followed by `I` for case-insensitive matching.

  A range is `addr1,addr2` or `addr1,+N`. An empty regular expression `//` reuses the last one used.
* **Commands:** `{ }`, `!`, `:`, `=`, `a`, `b`, `c`, `d`, `D`, `g`, `G`, `h`, `H`, `i`, `l`, `n`, `N`, `p`, `P`, `q`, `r`, `s`, `t`, `w`, `x`, `y`, `#`.
* `s/re/replacement/flags`:
  * the flags are `g`, `p`, a number N, `I`, and `w file`;
  * the replacement may use `&`, `\1` to `\9`, and an escaped newline.
* `a\`, `i\` and `c\` take their text on the following lines; a backslash at the end of a line continues the text.
* `r file` and `w file` take the rest of the line as the file name.

## Regular expressions

Basic regular expressions (BRE) by default, extended ones (ERE) with `-E`, as in POSIX.

## Status (0.2.0)

* **Implemented:** the commands above, ranges, hold space, `w` and `r`, and BRE/ERE translated to Python's `re` syntax.
* **Known gaps:** byte-exact output for unusual input (non-UTF-8 bytes, a missing final newline) and some edge cases of the macOS implementation have not been compared yet.
