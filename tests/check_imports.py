"""Verify every named ES-module import in web/ actually resolves.

Worth having as its own test: a bad named import is a hard module-load error
that produces a completely blank page and NO console output — it surfaces only
as a Playwright `pageerror`. Renaming an export (flashSlot -> flashBay) silently
broke one page this way, and a console-only smoke test reported it as fine.

    ./.venv/bin/python tests/check_imports.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "web"


def exports_of(path: pathlib.Path) -> set:
    s = path.read_text()
    out = set()
    out |= set(re.findall(r'export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', s))
    out |= set(re.findall(r'export\s+(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)', s))
    for blk in re.findall(r'export\s*\{([^}]*)\}', s):
        for part in blk.split(','):
            part = part.strip()
            if part:
                out.add(part.split(' as ')[-1].strip() if ' as ' in part else part)
    return out


def main() -> int:
    modules = {m.name: exports_of(m) for m in (ROOT / "js").glob("*.js")}
    problems = []
    sources = list((ROOT / "js").glob("*.js")) + list(ROOT.glob("*.html"))
    for f in sources:
        src = f.read_text()
        for names, mod in re.findall(
                r"import\s*\{([^}]*)\}\s*from\s*'\./(?:js/)?([\w.-]+\.js)'", src):
            avail = modules.get(mod)
            if avail is None:
                continue                       # a CDN or bare specifier
            for n in names.split(','):
                n = n.strip().split(' as ')[0].strip()
                if n and n not in avail:
                    problems.append((f.name, mod, n))

    print(f"local modules: {len(modules)}   files scanned: {len(sources)}")
    if problems:
        print(f"\nBROKEN IMPORTS ({len(problems)}):")
        for f, m, n in problems:
            print(f"  {f:<22} imports '{n}' from {m} — not exported")
        return 1
    print("every named import resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
