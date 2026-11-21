"""Find the files a ``Bash`` or ``PowerShell`` command can write, textually (decision log D47).

Used by :mod:`tracecontract.ingest.replay` to tell when a shell command, rather than an edit
tool, may have changed a replayed file. It recognises:

* output redirections (``>``, ``>>``, ``&>``) and ``tee``; ``cat > f <<'EOF'`` is returned with
  its content, so that the replay can apply it;
* in-place editors: ``sed -i``, ``perl -i``;
* ``mv``, ``cp``, ``install``, ``ln``, ``rsync``, ``rm``, ``touch``, ``truncate``, ``dd of=``;
* interpreter code that writes files (``open(..., 'w')``, ``write_text``, ``shutil``, ``os``,
  ``fs.writeFileSync``, ...) given with ``-c``/``-e``, as a heredoc, or as a script whose
  content the caller knows;
* ``git checkout``, ``restore``, ``rm``, ``mv``, ``apply``, ``reset --hard``, ``stash``, ``merge``,
  ``pull``, ``rebase``, ``cherry-pick``, ``revert``, ``switch``, ``am``, ``clean``; ``patch``;
* in-place formatters (``black``, ``isort``, ``ruff format``, ``ruff --fix``, ``prettier --write``,
  ``eslint --fix``, ``clang-format -i``, ``gofmt -w``, ``cargo fmt``, ...);
* PowerShell file cmdlets and their aliases (``Set-Content``, ``Out-File``, ``Copy-Item``,
  ``Move-Item``, ``Remove-Item``, ...) and ``[IO.File]::WriteAllText`` and the like;
* ``bash -c``, ``pwsh -Command``, ``xargs`` and ``find -exec``/``-delete`` around them.

This is a conservative detector, not a shell: it does not expand variables or follow scripts
it cannot see, and a write whose target it cannot resolve is returned with ``target=None``.
Programs a command runs (build tools, test runners) can still write files it does not see.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ShellWrite:
    """One possible write. ``target`` is the path as written, or None when it cannot be resolved."""

    kind: str
    target: str | None
    content: str | None = None  # the known content of a ``cat > f <<EOF`` heredoc
    append: bool = False
    exact: bool = True  # False when the shell would expand variables in ``content``
    source: str | None = None  # the one source of a copy or move, as written


Lookup = Callable[[str], str | None]  # content of a file the session wrote, by path as written
Known = Callable[[str], bool]  # whether a path as written names a tracked file

_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")  # not a here-string (<<< word)
_SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "{", "}"}
_NULL = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "$null", "nul")
_INTERPRETER = re.compile(r"^(?:python[\d.]*|py|pypy3?|node|nodejs|bun|deno|perl|ruby|php)(?:\.exe)?$", re.I)
_CODE_WRITE = re.compile(
    r"\bopen\s*\([^)]*?['\"](?:[wax]|[rwa]\+)[bt+]*['\"]|\.write_(?:text|bytes)\s*\(|\bshutil\.(?:copy\w*|move|rmtree)\s*\("
    r"|\bos\.(?:rename|replace|remove|unlink|rmdir|removedirs|truncate)\s*\(|\.(?:unlink|rename|replace|touch)\s*\("
    r"|\bfs\.(?:write|append|rename|unlink|rm|copyFile|cp)\w*\s*\(|\bwriteFileSync\b|\bcreateWriteStream\b"
    r"|\bFile\.(?:write|delete|rename)\b|\bWriteAll(?:Text|Lines|Bytes)\b|\bopen\s*\(?\s*\w*\s*,?\s*['\"]\+?>")
_PATH_LITERAL = re.compile(r"['\"]([\w.~:\\/-]{1,240})['\"]")
# name -> (flags that make it write; None: writes unless a check flag is given, flags that make it check only)
_FORMATTERS: dict[str, tuple[tuple[str, ...] | None, tuple[str, ...]]] = {
    "black": (None, ("--check", "--diff")), "isort": (None, ("--check", "--check-only", "--diff")),
    "rustfmt": (None, ("--check",)), "stylua": (None, ("--check",)), "autopep8": (("-i", "--in-place"), ()),
    "yapf": (("-i", "--in-place"), ()), "prettier": (("--write", "-w"), ()), "eslint": (("--fix",), ()),
    "clang-format": (("-i",), ()), "gofmt": (("-w",), ()), "goimports": (("-w",), ()), "shfmt": (("-w",), ())}
_GIT_TREE = {"merge", "pull", "rebase", "cherry-pick", "revert", "switch", "am", "clean"}
_PS_CMDLETS = {"set-content", "add-content", "out-file", "clear-content", "new-item", "copy-item", "move-item",
               "remove-item", "rename-item", "tee-object", "export-csv"}
_PS_ALIASES = {"sc": "set-content", "ac": "add-content", "ni": "new-item", "cpi": "copy-item", "copy": "copy-item",
               "cp": "copy-item", "mi": "move-item", "move": "move-item", "mv": "move-item", "ri": "remove-item",
               "rm": "remove-item", "del": "remove-item", "erase": "remove-item", "rd": "remove-item",
               "rmdir": "remove-item", "ren": "rename-item", "rni": "rename-item", "tee": "tee-object"}
_PS_SWITCHES = {"force", "recurse", "append", "nonewline", "whatif", "confirm", "passthru", "noclobber"}
_PS_DOTNET = re.compile(r"\[(?:System\.)?IO\.File\]::(WriteAll\w*|AppendAll\w*|Create|Delete|Copy|Move|Replace)\s*\(([^)]*)\)",
                        re.I)
DELETIONS = ("rm", "git rm", "unlink", "rmdir", "shred", "mv source", "remove-item", "move-item source")
COPIES = ("mv", "cp", "copy-item", "move-item")


# ---------------------------------------------------------------------------
# Lexing
# ---------------------------------------------------------------------------


def _scan(line: str, quote: str | None) -> tuple[str, str | None]:
    """The line without a trailing comment, and the quote still open at its end."""
    j = 0
    while j < len(line):
        c = line[j]
        if quote:
            if c == "\\" and quote == '"':
                j += 1
            elif c == quote:
                quote = None
        elif c == "\\":
            j += 1
        elif c in "'\"":
            quote = c
        elif c == "#" and (j == 0 or line[j - 1] in " \t;"):
            return line[:j], None
        j += 1
    return line, quote


def logical_lines(cmd: str) -> list[tuple[str, list[str], bool]]:
    """Command lines with their heredoc bodies set aside: ``(line, bodies, delimiters all quoted)``.

    A newline inside quotes or after a backslash continues the line; ``#`` at the start of a
    word starts a comment. A here-string (``<<< word``) has no body: the lines after it are
    commands.
    """
    out: list[tuple[str, list[str], bool]] = []
    lines = cmd.split("\n")
    i, buf, quote = 0, "", None
    while i < len(lines):
        line, quote = _scan(lines[i], quote)
        i += 1
        if quote:  # a newline inside a quoted string
            buf += line + "\n"
            continue
        if line.endswith("\\") and not line.endswith("\\\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        bodies, quoted = [], True
        for m in _HEREDOC.finditer(buf):
            delim, strip = m.group(3), m.group(1) == "-"
            quoted = quoted and bool(m.group(2))
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if strip else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append("".join(b + "\n" for b in body))
        out.append((buf, bodies, quoted))
        buf = ""
    if buf.strip():
        out.append((buf, [], True))
    return out


def _tokens(line: str, posix: bool) -> list[str]:
    lx = shlex.shlex(line, posix=posix, punctuation_chars=True)
    lx.whitespace_split = True
    try:
        toks = list(lx)
    except ValueError:  # unbalanced quotes
        toks = line.split()
    if not posix:
        toks = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "'\"" else t for t in toks]
    return toks


def simple_commands(line: str, posix: bool = True) -> list[list[str]]:
    """Words of each simple command, split at unquoted ``&&``, ``||``, ``;``, ``|``, ``&`` and parentheses."""
    cmds: list[list[str]] = []
    cur: list[str] = []
    for t in _tokens(line, posix):
        if t in _SEPARATORS:
            if cur:
                cmds.append(cur)
            cur = []
            continue
        if t.startswith("`") and len(t) > 1:  # `cmd ...` command substitution
            if cur:
                cmds.append(cur)
            cur, t = [], t[1:]
        cur.append(t.rstrip("`") if t.endswith("`") and len(t) > 1 else t)
    if cur:
        cmds.append(cur)
    return [c for c in cmds if c != ["$"]]


def _split_redirects(words: list[str]) -> tuple[list[str], list[tuple[str, bool]], bool]:
    """``(words without redirections, output targets as (path, append), stdin is a heredoc)``."""
    out: list[str] = []
    targets: list[tuple[str, bool]] = []
    heredoc, i = False, 0
    while i < len(words):
        w, nxt = words[i], words[i + 1] if i + 1 < len(words) else None
        if w in (">", ">>", "&>", "&>>", ">|") and nxt is not None:
            if out and out[-1].isdigit():
                out.pop()  # the descriptor of "2> file"
            if nxt.lower() not in _NULL:
                targets.append((nxt, w in (">>", "&>>")))
            i += 2
        elif w in (">&", "<&") and nxt is not None:
            if out and out[-1].isdigit():
                out.pop()
            if w == ">&" and not (nxt.isdigit() or nxt == "-") and nxt.lower() not in _NULL:
                targets.append((nxt, False))
            i += 2
        elif w in ("<", "<<", "<<-", "<<<", "<>") and nxt is not None:
            heredoc = heredoc or w in ("<<", "<<-")
            i += 2
        else:
            out.append(w)
            i += 1
    return out, targets, heredoc


def command_words(words: list[str]) -> list[str]:
    """Words without leading assignments, keywords and wrappers (``env``, ``sudo``, ``timeout`` ...)."""
    ws = list(words)
    keywords = ("do", "then", "else", "elif", "if", "!", "while", "until", "time", "exec", "&")
    while ws and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", ws[0]) or ws[0] in keywords):
        ws = ws[1:]
    while ws and posixpath.basename(ws[0]) in ("env", "sudo", "nohup", "nice", "stdbuf", "command", "builtin", "timeout"):
        wrapper, ws = posixpath.basename(ws[0]), ws[1:]
        while ws and (ws[0].startswith("-") or (wrapper == "env" and "=" in ws[0])):
            ws = ws[1:]
        if wrapper == "timeout" and ws:
            ws = ws[1:]  # the duration
    return ws


def _positional(args: list[str], value_opts: tuple[str, ...] = ()) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in value_opts:
            skip = True
        elif not a.startswith("-") or a == "-":
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def code_writes(code: str) -> list[ShellWrite]:
    """Writes in interpreter code: one per path literal if the code calls a write function, else one unresolved."""
    if not _CODE_WRITE.search(code):
        return []
    paths = [m.group(1) for m in _PATH_LITERAL.finditer(code)
             if ("/" in m.group(1) or "\\" in m.group(1) or re.search(r"\w\.\w{1,8}$", m.group(1)))
             and not m.group(1).startswith(("http:", "https:"))]
    return [ShellWrite("interpreter", p) for p in dict.fromkeys(paths)] or [ShellWrite("interpreter", None)]


def _git(args: list[str], known: Known) -> list[ShellWrite]:
    rest, prefix = list(args), ""
    while rest and rest[0].startswith("-"):
        if rest[0] == "-C" and len(rest) > 1:
            prefix, rest = rest[1].rstrip("/") + "/", rest[2:]
        elif rest[0] in ("-c", "--git-dir", "--work-tree") and len(rest) > 1:
            rest = rest[2:]
        else:
            rest = rest[1:]
    if not rest:
        return []
    sub, rest = rest[0], rest[1:]
    opts = [a for a in rest if a.startswith("-")]
    pos = _positional(rest, ("-b", "-B", "--orphan", "-m", "-F", "-s", "-X", "--source", "-p"))
    paths = rest[rest.index("--") + 1:] if "--" in rest else None

    def each(kind: str, items: list[str]) -> list[ShellWrite]:
        return [ShellWrite(kind, prefix + p) for p in items]

    if sub == "checkout":
        if paths is not None:
            return each("git checkout", paths)
        if any(o in opts for o in ("-b", "-B", "--orphan")):
            return [ShellWrite("git checkout", None)] if pos else []  # a start point switches the tree
        files = [p for p in pos if known(prefix + p)]
        return each("git checkout", files) if files else ([ShellWrite("git checkout", None)] if pos else [])
    if sub == "restore":
        staged_only = "--staged" in opts and not any(o in opts for o in ("--worktree", "-W"))
        return [] if staged_only else each("git restore", paths if paths is not None else pos)
    if sub == "rm":
        return [] if "--cached" in opts else each("git rm", paths if paths is not None else pos)
    if sub == "mv":
        items = paths if paths is not None else pos
        if len(items) < 2:
            return []
        one = prefix + items[0] if len(items) == 2 else None
        return [ShellWrite("mv", prefix + items[-1], source=one)] + each("mv source", items[:-1])
    if sub == "apply":
        check = ("--check", "--stat", "--numstat", "--summary", "--cached")
        return [] if any(o in opts for o in check) else [ShellWrite("git apply", None)]
    if sub == "reset":
        return [ShellWrite("git reset", None)] if any(o in opts for o in ("--hard", "--keep", "--merge")) else []
    if sub == "stash":
        readonly = ("list", "show", "drop", "clear", "branch", "create", "store")
        return [] if pos[:1] and pos[0] in readonly else [ShellWrite("git stash", None)]
    if sub in _GIT_TREE:
        return [] if sub == "clean" and any(o in opts for o in ("-n", "--dry-run")) else [ShellWrite(f"git {sub}", None)]
    return []


def _formatter(name: str, args: list[str]) -> list[ShellWrite] | None:
    """Writes of an in-place formatter, or None if ``name`` is not one."""
    if name not in _FORMATTERS:
        return None
    write_flags, check_flags = _FORMATTERS[name]
    flags = {a.split("=")[0] for a in args if a.startswith("-")}
    if (write_flags and not flags & set(write_flags)) or flags & {*check_flags, "--version", "--help", "-h", "-V"}:
        return []
    return [ShellWrite(f"formatter {name}", p) for p in _positional(args)] or [ShellWrite(f"formatter {name}", None)]


def _tool_runner(name: str, args: list[str]) -> list[ShellWrite] | None:
    """Writes of ``ruff``, ``cargo fmt``, package-manager format scripts; None if ``name`` is none of them."""
    sub = args[0] if args else ""
    if name == "ruff":
        if sub == "format" and not {"--check", "--diff"} & set(args):
            return [ShellWrite("formatter ruff", p) for p in _positional(args[1:])] or [ShellWrite("formatter ruff", None)]
        return [ShellWrite("formatter ruff --fix", None)] if {"--fix", "--unsafe-fixes"} & set(args) else []
    if name == "cargo":
        return [ShellWrite("formatter cargo fmt", None)] if sub == "fmt" and "--check" not in args else []
    if name in ("dotnet", "terraform"):
        fmt = sub == ("format" if name == "dotnet" else "fmt") and not {"-check", "--verify-no-changes"} & set(args)
        return [ShellWrite(f"formatter {name}", None)] if fmt else []
    if name in ("npm", "pnpm", "yarn"):
        script = args[1] if sub == "run" and len(args) > 1 else sub
        return [ShellWrite(f"{name} {script}", None)] if re.fullmatch(r"(?:format|fmt|lint:fix|fix|prettier)(?::\w+)?",
                                                                      script) else []
    return None


def _bash(words: list[str], body: str | None, line_bodies: list[str], *, sandboxed: tuple[str, ...], script: Lookup,
          known: Known) -> list[ShellWrite]:
    ws = command_words(words)
    if not ws or posixpath.basename(ws[0]) in sandboxed:
        return []
    name, args = posixpath.basename(ws[0]), ws[1:]
    if name == "tee":
        return [ShellWrite("tee", p, append="-a" in args) for p in _positional(args)]
    if name == "sed":
        if not any(a.startswith(("-i", "--in-place")) or (re.fullmatch(r"-[a-zA-Z]+", a) and "i" in a) for a in args):
            return []
        script_opts = ("-e", "--expression", "-f", "--file")
        pos = _positional(args, script_opts)
        given = any(a in script_opts or a.startswith(("--expression=", "--file=")) for a in args)
        return [ShellWrite("sed -i", p) for p in (pos if given else pos[1:])]
    if name == "perl" and any(re.match(r"^-[a-zA-Z]*i", a) for a in args):
        return [ShellWrite("perl -i", p) for p in _positional(args, ("-e", "-E"))]
    if name in ("mv", "cp", "install", "ln", "rsync"):
        pos = _positional(args, ("-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "-g"))
        if "-t" in args or "--target-directory" in args:
            k = args.index("-t") if "-t" in args else args.index("--target-directory")
            dst, srcs = (args[k + 1] if k + 1 < len(args) else None), pos
        else:
            dst, srcs = (pos[-1], pos[:-1]) if len(pos) >= 2 else (None, pos)
        one = srcs[0] if len(srcs) == 1 and name in ("mv", "cp") else None
        out = [ShellWrite(name, dst, source=one)] if dst is not None else []
        return out + ([ShellWrite("mv source", s) for s in srcs] if name == "mv" else [])
    if name in ("rm", "unlink", "rmdir", "shred", "touch", "truncate"):
        return [ShellWrite(name, p) for p in _positional(args, ("-s", "--size", "-r", "--reference"))]
    if name == "dd":
        return [ShellWrite("dd", a[3:]) for a in args if a.startswith("of=")]
    if name == "git":
        return _git(args, known)
    if name == "patch":
        return [] if "--dry-run" in args else [ShellWrite("patch", None)]
    if name in ("xargs", "find"):
        if name == "find" and "-delete" in args:
            return [ShellWrite("find -delete", None)]
        inner = " ".join(args)
        writes = re.search(r"(?:^|\s)(?:sed\s+-[a-zA-Z]*i|rm|mv|cp|tee|perl\s+-[a-zA-Z]*i|truncate|black|isort|"
                           r"prettier\s+--write)(?:\s|$)", inner)
        return [ShellWrite(name, None)] if writes else []
    if name in ("npx", "bunx", "uv", "poetry", "pipx") and args:
        inner = args[1:] if name in ("uv", "poetry", "pipx") and args[0] == "run" else args
        inner = [a for a in inner if a not in ("--yes", "-y")]
        return _bash(inner, body, line_bodies, sandboxed=sandboxed, script=script, known=known) if inner else []
    for found in (_tool_runner(name, args), _formatter(name, args)):
        if found is not None:
            return found
    if name in ("bash", "sh", "zsh") and "-c" in args:
        k = args.index("-c")
        return shell_writes(args[k + 1], sandboxed=sandboxed, script=script, known=known) if k + 1 < len(args) else []
    if name.lower() in ("pwsh", "powershell", "powershell.exe", "pwsh.exe"):
        k = next((args.index(f) for f in ("-c", "-Command", "-command") if f in args), None)
        if k is None or k + 1 >= len(args):
            return []
        return shell_writes(" ".join(args[k + 1:]), shell="PowerShell", sandboxed=sandboxed, script=script, known=known)
    if _INTERPRETER.match(name):
        return _interpreter(args, body, line_bodies, script)
    return []


def _interpreter(args: list[str], body: str | None, line_bodies: list[str], script: Lookup) -> list[ShellWrite]:
    if "-m" in args:
        k = args.index("-m")
        found = _formatter(args[k + 1], args[k + 2:]) if k + 1 < len(args) else None
        return found or []
    for flag in ("-c", "-e", "-E", "--eval", "-p", "-r"):
        if flag in args and args.index(flag) + 1 < len(args):
            return code_writes(args[args.index(flag) + 1])
    pos = _positional(args)
    if not pos or pos[0] == "-":  # code on stdin: its heredoc, or any heredoc of the line (cat <<EOF | python -)
        return [w for b in ([body] if body is not None else line_bodies) for w in code_writes(b)]
    content = script(pos[0])
    return code_writes(content) if content else []


def _powershell(words: list[str], *, sandboxed: tuple[str, ...], script: Lookup, known: Known) -> list[ShellWrite]:
    ws = [w for w in words if w != "&"]
    if not ws:
        return []
    name = ws[0].lower()
    if posixpath.basename(name.replace("\\", "/")) in sandboxed:
        return []
    cmdlet = _PS_ALIASES.get(name, name)
    if cmdlet not in _PS_CMDLETS:
        if name in ("git", "git.exe"):
            return _git(ws[1:], known)
        if _INTERPRETER.match(name) or name in ("sed", "black", "isort", "prettier", "ruff", "npm", "npx", "cargo"):
            return _bash(ws, None, [], sandboxed=sandboxed, script=script, known=known)
        return []
    named: dict[str, str] = {}
    pos: list[str] = []
    args, i = ws[1:], 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and len(a) > 1 and not a[1].isdigit():
            key = a[1:].rstrip(":").lower()
            if key not in _PS_SWITCHES and i + 1 < len(args):
                named[key] = args[i + 1]
                i += 1
        else:
            pos.append(a)
        i += 1

    def param(*names: str) -> str | None:
        return next((v for k, v in named.items() if len(k) >= 2 and any(n.startswith(k) for n in names)), None)

    if cmdlet == "new-item" and (param("itemtype") or "").lower() in ("directory", "dir", "d"):
        return []
    if cmdlet in ("copy-item", "move-item"):
        src = param("path", "literalpath") or (pos[0] if pos else None)
        dst = param("destination") or (pos[1] if len(pos) > 1 else None)
        out = [ShellWrite(cmdlet, dst, source=src)]
        return out + ([ShellWrite("move-item source", src)] if cmdlet == "move-item" and src else [])
    return [ShellWrite(cmdlet, param("path", "literalpath", "filepath") or (pos[0] if pos else None))]


def shell_writes(command: str, *, shell: str = "Bash", sandboxed: tuple[str, ...] = (), script: Lookup = lambda _p: None,
                 known: Known = lambda _p: False) -> list[ShellWrite]:
    """The writes a ``Bash`` or ``PowerShell`` command can make.

    ``sandboxed`` names commands that cannot write the workspace (wrappers that mount it
    read-only); ``script`` returns the content of a script the session wrote, so that
    ``python fix.py`` is analysed; ``known`` tells a tracked file from a branch name
    (``git checkout <file>`` against a branch switch). Paths are returned as written.
    """
    posix = shell != "PowerShell"
    out: list[ShellWrite] = []
    for line, bodies, quoted in logical_lines(command):
        if not posix:
            for m in _PS_DOTNET.finditer(line):
                lits = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))
                out += [ShellWrite(f"[IO.File]::{m.group(1)}", p) for p in lits[:2]] or [ShellWrite("[IO.File]", None)]
        pending = iter(bodies)
        for raw in simple_commands(line, posix):
            words, targets, heredoc_in = _split_redirects(raw)
            body = next(pending, None) if heredoc_in else None
            cw = command_words(words)
            is_cat = cw == ["cat"] and body is not None
            for path, append in targets:
                expands = not quoted and bool(body and re.search(r"[$`]", body))
                out.append(ShellWrite("heredoc", path, body, append, not expands) if is_cat
                           else ShellWrite("redirect", path, append=append))
            if posix:
                out += _bash(words, body, bodies, sandboxed=sandboxed, script=script, known=known)
            else:
                out += _powershell(words, sandboxed=sandboxed, script=script, known=known)
    return out
