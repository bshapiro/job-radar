"""Check that nothing personal is in this repo before it is pushed: every file, and every commit in its history.

    python scripts/privacy_check.py path/to/private_terms.txt

The terms file lives outside this repo (in your own private profile repo): one term per line, matched as
whole words ignoring case; lines starting with # are comments. Lines starting with "allow: " list text that
may appear even though it contains a term (e.g. the repo's own GitHub address).

The terms are kept out of this public repo on purpose, even hashed: a hash of a short word like a name or
an employer can be recovered by trying every word.
Exits 1 and lists each hit if anything matches.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".pytest_cache", ".venv", "build", "dist"}


def load(path: Path) -> tuple[re.Pattern, list[str]]:
    terms, allow = [], []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("allow: "):
            allow.append(line[len("allow: "):].lower())
        else:
            terms.append(re.escape(line))
    return re.compile(r"(?<!\w)(?:" + "|".join(terms) + r")(?!\w)", re.I), allow


def hits(text: str, where: str, pattern: re.Pattern, allow: list[str]):
    for n, line in enumerate(text.splitlines(), 1):
        clean = line.lower()
        for a in allow:
            clean = clean.replace(a, " ")
        for m in pattern.finditer(clean):
            yield f"{where}:{n}: {m.group(0)!r} in {line.strip()[:120]!r}"


def candidates():
    """The files a commit would include: in a git repo, tracked plus untracked-but-not-ignored files;
    otherwise everything outside SKIP."""
    if (ROOT / ".git").exists():
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                             capture_output=True, text=True, check=True).stdout
        return sorted(ROOT / f for f in out.split("\0") if f)
    return sorted(p for p in ROOT.rglob("*") if not SKIP & set(p.relative_to(ROOT).parts))


def files():
    for p in candidates():
        if p.is_file():
            try:
                yield p, p.read_text()
            except UnicodeDecodeError:
                yield p, p.read_bytes().decode("latin-1")


def history() -> str:
    """Every version of every file ever committed, plus commit messages and authors."""
    if not (ROOT / ".git").exists():
        return ""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--all", "-p", "--format=commit %H%nauthor %an <%ae>%n%B"],
                         capture_output=True, text=True)
    return out.stdout


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    pattern, allow = load(Path(argv[0]).expanduser())
    found = []
    for p, text in files():
        found += hits(p.relative_to(ROOT).as_posix(), str(p.relative_to(ROOT)), pattern, allow)
        found += hits(text, str(p.relative_to(ROOT)), pattern, allow)
    found += hits(history(), "git history", pattern, allow)
    for f in found:
        print(f)
    print(f"{len(found)} hit(s)" if found else "no personal terms found in files, file names or history")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
