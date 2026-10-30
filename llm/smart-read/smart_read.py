#!/usr/bin/env python3
"""Hybrid code search for agents: symbol-aware chunks, BM25 + trigram + embeddings, weighted RRF."""

from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

EMBED_MODEL = os.environ.get("SMART_READ_EMBED", "jinaai/jina-embeddings-v2-base-code")
CACHE = Path(os.environ.get("SMART_READ_CACHE") or Path.home() / ".cache" / "smart-read")
WINDOW, OVERLAP, MAX_SEGMENT = 60, 10, 80
MAX_FILE_BYTES = 512_000
RRF_K, CANDIDATES = 60, 50
# BM25, trigram, dense; tuned on the README eval (trigram only helps partial identifiers, so it weighs least).
RRF_WEIGHTS = (0.7, 0.3, 1.0)
HIT_LINES, OUTPUT_CAP = 40, 9000
EMBED_CHARS = 2000
TEXT_SUFFIXES = {
    ".py", ".pyi", ".sql", ".j2", ".jinja", ".tf", ".hcl", ".tfvars", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".md", ".rst", ".txt", ".sh", ".bash", ".zsh", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".scala",
    ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".lua", ".r", ".html", ".css", ".scss", ".xml",
    ".dockerfile", ".mk", ".graphql", ".proto",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Justfile", "Procfile", ".gitignore"}
# Lines that open a new definition, per file family; chunk boundaries snap to them.
STARTS = {
    "sql": r"^\s*(create|alter|insert|merge|update|delete|with|select|grant|\{%-?\s*(macro|test|snapshot|materialization)|\{\{\s*config)\b",
    "hcl": r"^(resource|data|module|variable|output|locals|provider|terraform)\b",
    "yaml": r"^([A-Za-z_][\w.-]*:|\s{0,4}- name:)",
    "md": r"^#{1,6} ",
    "code": r"^\s*(export\s+)?(default\s+)?(async\s+)?(pub(\(\w+\))?\s+)?(function|class|def|func|fn|interface|struct|enum|trait|impl|type|module|object)\b"
            r"|^\s*[\w.]+\s*\(\)\s*\{",
}
FAMILY = {".sql": "sql", ".j2": "sql", ".jinja": "sql", ".tf": "hcl", ".hcl": "hcl", ".tfvars": "hcl",
          ".yaml": "yaml", ".yml": "yaml", ".md": "md", ".rst": "md"}
WORD = re.compile(r"[A-Za-z0-9]+")
CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


@dataclass
class Chunk:
    path: str
    start: int
    end: int
    symbol: str
    text: str


def split_identifiers(text: str) -> str:
    """Append camelCase/snake_case parts so BM25 matches `refresh` inside `refreshToken`."""
    extra = []
    for word in set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", text)):
        parts = [p for piece in word.split("_") for p in CAMEL.findall(piece)]
        if len(parts) > 1:
            extra.extend(parts)
    return text + "\n" + " ".join(extra)


def windows(path: str, lines: list[str], start: int, end: int, symbol: str) -> list[Chunk]:
    """Lines start..end (1-based, inclusive), split into overlapping windows when longer than MAX_SEGMENT."""
    if end - start + 1 <= MAX_SEGMENT:
        return [Chunk(path, start, end, symbol, "\n".join(lines[start - 1:end]))]
    out = []
    for first in range(start, end + 1, WINDOW - OVERLAP):
        last = min(end, first + WINDOW - 1)
        out.append(Chunk(path, first, last, symbol, "\n".join(lines[first - 1:last])))
        if last == end:
            break
    return out


def python_segments(text: str) -> list[tuple[int, int, str]] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    segments: list[tuple[int, int, str]] = []

    def visit(nodes: list[ast.stmt], prefix: str) -> None:
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            name = prefix + node.name
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            if isinstance(node, ast.ClassDef) and methods and node.end_lineno - first + 1 > MAX_SEGMENT:
                header_end = min(m.lineno for m in methods) - 1
                segments.append((first, max(first, header_end), f"class {name}"))
                visit(node.body, name + ".")
            else:
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                segments.append((first, node.end_lineno, f"{kind} {name}"))

    visit(tree.body, "")
    return segments


def boundary_segments(lines: list[str], family: str) -> list[tuple[int, int, str]]:
    pattern = re.compile(STARTS[family], re.I)
    starts = [i for i, line in enumerate(lines, 1) if pattern.search(line)]
    if not starts or starts[0] != 1:
        starts.insert(0, 1)
    bounds = [*starts, len(lines) + 1]
    return [(a, b - 1, lines[a - 1].strip()[:80]) for a, b in zip(bounds, bounds[1:]) if b - 1 >= a]


def label(symbols: list[str]) -> str:
    named = [s for s in dict.fromkeys(symbols) if s != "module"] or ["module"]
    return ", ".join(named[:3]) + (f" +{len(named) - 3}" if len(named) > 3 else "")


def segments_of(path: str, lines: list[str]) -> list[tuple[int, int, str]]:
    suffix = Path(path).suffix.lower()
    segments = python_segments("\n".join(lines)) if suffix in (".py", ".pyi") else None
    if segments is not None:
        # Module-level code between definitions becomes its own segments.
        covered, gaps, cursor = sorted(segments), [], 1
        for first, last, _ in covered:
            if first > cursor:
                gaps.append((cursor, first - 1, "module"))
            cursor = max(cursor, last + 1)
        if cursor <= len(lines):
            gaps.append((cursor, len(lines), "module"))
        return sorted(covered + [g for g in gaps if any(lines[i - 1].strip() for i in range(g[0], g[1] + 1))])
    return boundary_segments(lines, FAMILY.get(suffix, "code"))


def chunk_file(path: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    # Merge small neighbours so one chunk holds about WINDOW lines.
    merged: list[list] = []
    for first, last, symbol in segments_of(path, lines):
        if merged and last - merged[-1][0] + 1 <= WINDOW and merged[-1][1] - merged[-1][0] < WINDOW // 2:
            merged[-1][1] = last
            merged[-1][2].append(symbol)
        else:
            merged.append([first, last, [symbol]])
    return [c for first, last, symbols in merged for c in windows(path, lines, first, last, label(symbols))]


def repo_root(start: Path) -> Path:
    found = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if found.returncode:
        raise ValueError(f"{start} is not inside a Git repository; cd into the target repository first")
    return Path(found.stdout.strip()).resolve()


def repo_files(root: Path) -> list[str]:
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True)
    if listed.returncode == 0:
        names = [n for n in listed.stdout.decode("utf-8", "replace").split("\0") if n]
    else:
        names = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [n for n in names if Path(n).suffix.lower() in TEXT_SUFFIXES or Path(n).name in TEXT_NAMES]


def cache_key(root: Path) -> str:
    return hashlib.sha1(str(root).encode()).hexdigest()[:16]


def connect(root: Path, memory: bool = False) -> sqlite3.Connection:
    if not memory:
        CACHE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(":memory:" if memory else CACHE / f"{cache_key(root)}.db")
    db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER);
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, path TEXT, start INTEGER, end INTEGER,
                                          symbol TEXT, text TEXT, vec BLOB);
        CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
        CREATE VIRTUAL TABLE IF NOT EXISTS lex USING fts5(symbol, path, body, tokenize='porter unicode61');
        CREATE VIRTUAL TABLE IF NOT EXISTS tri USING fts5(body, tokenize='trigram');
    """)
    if db.execute("SELECT value FROM meta WHERE key='embed'").fetchone() not in (None, (EMBED_MODEL,)):
        db.execute("UPDATE chunks SET vec=NULL")
    db.execute("INSERT OR REPLACE INTO meta VALUES('embed', ?)", (EMBED_MODEL,))
    return db


def refresh(db: sqlite3.Connection, root: Path) -> int:
    """Re-chunk files whose mtime or size changed; returns the number of files re-indexed."""
    known = {p: (m, s) for p, m, s in db.execute("SELECT path, mtime, size FROM files")}
    current = {}
    for name in repo_files(root):
        try:
            stat = (root / name).stat()
        except OSError:
            continue
        if stat.st_size <= MAX_FILE_BYTES:
            current[name] = (stat.st_mtime, stat.st_size)
    changed = [n for n, sig in current.items() if known.get(n) != sig]
    for name in [*changed, *(set(known) - set(current))]:
        ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE path=?", (name,))]
        db.executemany("DELETE FROM lex WHERE rowid=?", [(i,) for i in ids])
        db.executemany("DELETE FROM tri WHERE rowid=?", [(i,) for i in ids])
        db.execute("DELETE FROM chunks WHERE path=?", (name,))
        db.execute("DELETE FROM files WHERE path=?", (name,))
    for name in changed:
        raw = (root / name).read_bytes()
        if b"\0" in raw[:4096]:
            continue
        for chunk in chunk_file(name, raw.decode("utf-8", "replace")):
            cur = db.execute("INSERT INTO chunks(path, start, end, symbol, text) VALUES(?,?,?,?,?)",
                             (name, chunk.start, chunk.end, chunk.symbol, chunk.text))
            db.execute("INSERT INTO lex(rowid, symbol, path, body) VALUES(?,?,?,?)",
                       (cur.lastrowid, split_identifiers(chunk.symbol), split_identifiers(name), split_identifiers(chunk.text)))
            db.execute("INSERT INTO tri(rowid, body) VALUES(?,?)", (cur.lastrowid, chunk.text))
        db.execute("INSERT INTO files VALUES(?,?,?)", (name, *current[name]))
    db.commit()
    return len(changed)


def path_clause(path: str | None) -> tuple[str, tuple]:
    return ("AND c.path GLOB ?", (path if any(ch in path for ch in "*?[") else path + "*",)) if path else ("", ())


def fts(db: sqlite3.Connection, table: str, rank: str, terms: set[str], path: str | None) -> list[int]:
    if not terms:
        return []
    clause, args = path_clause(path)
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in sorted(terms))
    return [r[0] for r in db.execute(
        f"SELECT c.id FROM {table} JOIN chunks c ON c.id = {table}.rowid WHERE {table} MATCH ? {clause} "
        f"ORDER BY {rank} LIMIT {CANDIDATES}", (match, *args))]


def lexical(db: sqlite3.Connection, query: str, path: str | None) -> list[int]:
    words = {w.lower() for w in WORD.findall(split_identifiers(query)) if len(w) > 1}
    return fts(db, "lex", "bm25(lex, 5.0, 2.0, 1.0)", words, path)


def trigram(db: sqlite3.Connection, query: str, path: str | None) -> list[int]:
    return fts(db, "tri", "bm25(tri)", set(re.findall(r"[\w./-]{3,}", query)), path)


def embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(EMBED_MODEL, threads=os.cpu_count(), cache_dir=str(CACHE / "models"))


def embed_pending(db: sqlite3.Connection) -> int:
    import numpy as np

    total = db.execute("SELECT count(*) FROM chunks WHERE vec IS NULL").fetchone()[0]
    if not total:
        return 0
    print(f"Embedding 0/{total} chunks; loading {EMBED_MODEL} (Ctrl-C to stop)", file=sys.stderr, flush=True)
    model = embedder()
    completed, last_id = 0, 0
    while batch := db.execute("SELECT id, path, symbol, text FROM chunks WHERE vec IS NULL AND id > ? "
                             "ORDER BY id LIMIT 64", (last_id,)).fetchall():
        vectors = model.embed([f"{p}\n{s}\n{t}"[:EMBED_CHARS] for _, p, s, t in batch], batch_size=64)
        db.executemany("UPDATE chunks SET vec=? WHERE id=?",
                       [(np.asarray(v, dtype=np.float32).tobytes(), i) for (i, *_), v in zip(batch, vectors)])
        db.commit()
        last_id = batch[-1][0]
        completed += len(batch)
        print(f"Embedded {completed}/{total} chunks", file=sys.stderr, flush=True)
    return completed


def dense(db: sqlite3.Connection, query: str, path: str | None) -> list[int]:
    import numpy as np

    clause, args = path_clause(path)
    rows = db.execute(f"SELECT c.id, c.vec FROM chunks c WHERE c.vec IS NOT NULL {clause}", args).fetchall()
    if not rows:
        return []
    # ponytail: exact brute-force cosine; switch to an ANN index (HNSW) past ~100K chunks.
    matrix = np.frombuffer(b"".join(v for _, v in rows), dtype=np.float32).reshape(len(rows), -1)
    q = np.asarray(next(iter(embedder().query_embed([query]))), dtype=np.float32)
    scores = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)
    return [rows[i][0] for i in np.argsort(-scores)[:CANDIDATES]]


def rrf(rankings: list[list[int]], weights: tuple[float, ...] = RRF_WEIGHTS) -> list[int]:
    scores: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + weight / (RRF_K + rank + 1)
    return sorted(scores, key=lambda i: -scores[i])


def search(db: sqlite3.Connection, root: Path, query: str, path: str | None, k: int,
           use_dense: bool = True) -> tuple[list[tuple[int, float]], str]:
    refresh(db, root)
    note = ""
    rankings = [lexical(db, query, path), trigram(db, query, path)]
    if use_dense:
        pending = db.execute("SELECT count(*) FROM chunks WHERE vec IS NULL").fetchone()[0]
        if pending:
            note = f"note: {pending} chunks use lexical retrieval only; run `smart-read index` explicitly to embed them"
        rankings.append(dense(db, query, path))
    fused = rrf(rankings)
    return [(i, 1.0 / (n + 1)) for n, i in enumerate(fused[:k])], note


def render(db: sqlite3.Connection, hits: list[tuple[int, float]], note: str) -> str:
    out = [note] if note else []
    for n, (cid, score) in enumerate(hits, 1):
        path, start, end, symbol, text = db.execute(
            "SELECT path, start, end, symbol, text FROM chunks WHERE id=?", (cid,)).fetchone()
        lines = text.splitlines()
        shown = lines[:HIT_LINES]
        body = "\n".join(f"{start + i:>5}  {line}" for i, line in enumerate(shown))
        more = f"\n      … {len(lines) - len(shown)} more lines (read {path} lines {start + len(shown)}-{end})" \
            if len(lines) > len(shown) else ""
        out.append(f"[{n}] {path}:{start}-{end}  {symbol}  ({score:.2f})\n{body}{more}")
    text = "\n\n".join(out) or "No matches."
    return text if len(text) <= OUTPUT_CAP else text[:OUTPUT_CAP] + "\n… output capped; narrow with --path or -k"


def outline(file: Path) -> str:
    lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = segments_of(file.name, lines) if lines else []
    return f"{file} ({len(lines)} lines)\n" + "\n".join(f"{a:>5}-{b:<5} {s}" for a, b, s in rows)


def main() -> int:
    parser = argparse.ArgumentParser(prog="smart-read", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search", help="find the code relevant to a question or identifier")
    find.add_argument("query")
    find.add_argument("--path", help="limit to a file, directory prefix or glob (repo-relative)")
    find.add_argument("-k", type=int, default=5)
    find.add_argument("--lexical", action="store_true", help="BM25 + trigram only, no models")
    show = commands.add_parser("outline", help="symbols of a file with line ranges")
    show.add_argument("file")
    build = commands.add_parser("index", help="refresh and embed pending chunks in the foreground (Ctrl-C to stop)")
    build.add_argument("--root")
    args = parser.parse_args()
    if args.command == "outline":
        print(outline(Path(args.file)))
        return 0
    try:
        root = repo_root(Path(getattr(args, "root", None) or os.getcwd()))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        with (CACHE / f"{cache_key(root)}.indexing").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(f"{root}: index in use by another smart-read command; retry after it finishes", file=sys.stderr)
                return 1
            with closing(connect(root)) as db:
                if args.command == "index":
                    files = refresh(db, root)
                    print(f"{root}: {files} files re-chunked", file=sys.stderr, flush=True)
                    print(f"{root}: {embed_pending(db)} chunks embedded")
                else:
                    path = args.path
                    if path and Path(path).is_absolute():
                        path = os.path.relpath(path, root)
                    hits, note = search(db, root, args.query, path, args.k, use_dense=not args.lexical)
                    print(render(db, hits, note))
    except PermissionError:
        if args.command != "search" or not args.lexical:
            raise
        with closing(connect(root, memory=True)) as db:
            path = os.path.relpath(args.path, root) if args.path and Path(args.path).is_absolute() else args.path
            hits, note = search(db, root, args.query, path, args.k, use_dense=False)
            print(render(db, hits, note))
    except KeyboardInterrupt:
        print("Index/search interrupted; completed embedding batches are saved.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
