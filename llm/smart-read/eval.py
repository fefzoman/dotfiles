#!/usr/bin/env python3
"""CodeSearchNet-style retrieval eval: docstring first sentence -> its function, docstrings stripped from the index.

Usage: python eval.py REPO[,REPO...] [EMBED_MODEL,...] [RERANK_MODEL,...]
"""

import ast
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import smart_read as sr  # noqa: E402


def build_corpus(repos: list[Path], corpus: Path) -> list[tuple[str, str, int]]:
    queries = []
    for repo in repos:
        for name in sr.repo_files(repo):
            if not name.endswith(".py"):
                continue
            source = (repo / name).read_text(errors="replace")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            blank = set()
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or not body:
                    continue
                first = body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    blank.update(range(first.lineno, first.end_lineno + 1))
                    doc = first.value.value.strip().split("\n\n")[0].replace("\n", " ")
                    if not isinstance(node, ast.Module) and len(doc.split()) >= 4:
                        queries.append((doc, f"{repo.name}/{name}", node.lineno))
            # Blank docstring lines instead of deleting them so line numbers stay valid.
            kept = ["" if i in blank else line for i, line in enumerate(source.splitlines(), 1)]
            target = corpus / repo.name / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(kept))
    return queries


def main() -> int:
    repos = [Path(p).expanduser() for p in sys.argv[1].split(",")]
    embeds = sys.argv[2].split(",") if len(sys.argv) > 2 else [sr.EMBED_MODEL]
    rerankers = sys.argv[3].split(",") if len(sys.argv) > 3 else [sr.RERANK_MODEL]
    work = Path(tempfile.mkdtemp())
    sr.CACHE = work / "cache"
    queries = build_corpus(repos, work / "corpus")
    db = sr.connect(work / "corpus")
    sr.refresh(db, work / "corpus")
    spans = {i: (p, a, b) for i, p, a, b in db.execute("SELECT id, path, start, end FROM chunks")}
    print(f"{len(queries)} queries, {len(spans)} chunks")

    def report(label: str, rank) -> None:
        started, mrr, top1, top5 = time.time(), 0.0, 0, 0
        for query, path, line in queries:
            ids = rank(query)
            found = next((n for n, i in enumerate(ids, 1) if spans[i][0] == path and spans[i][1] <= line <= spans[i][2]), None)
            if found:
                mrr += 1 / found if found <= 10 else 0
                top1 += found == 1
                top5 += found <= 5
        n = len(queries)
        print(f"| {label} | {mrr / n:.3f} | {top1 / n:.3f} | {top5 / n:.3f} | {1000 * (time.time() - started) / n:.0f} |")

    print("| Method | MRR@10 | R@1 | R@5 | ms/query |\n|---|---:|---:|---:|---:|")
    report("BM25", lambda q: sr.lexical(db, q, None))
    report("BM25 + trigram", lambda q: sr.rrf([sr.lexical(db, q, None), sr.trigram(db, q, None)]))
    load_embedder = sr.embedder
    for embed in embeds:
        sr.EMBED_MODEL = embed
        db.execute("UPDATE chunks SET vec=NULL")
        sr.embed_pending(db)
        model = load_embedder()
        sr.embedder = lambda model=model: model
        short = embed.split("/")[-1]
        report(f"dense {short}", lambda q: sr.dense(db, q, None))
        fused = {q: sr.rrf([sr.lexical(db, q, None), sr.trigram(db, q, None), sr.dense(db, q, None)])
                 for q, _, _ in queries}
        report(f"hybrid RRF {short}", lambda q: fused[q])
        for reranker in rerankers:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            encoder = TextCrossEncoder(reranker, threads=os.cpu_count())

            def ranked(q, fused=fused, encoder=encoder):
                ids = fused[q][:sr.RERANK_TOP]
                docs = [f"{spans[i][0]} " + db.execute("SELECT symbol || char(10) || text FROM chunks WHERE id=?", (i,)).fetchone()[0]
                        for i in ids]
                scores = list(encoder.rerank(q, [d[:sr.RERANK_CHARS] for d in docs]))
                return [i for i, _ in sorted(zip(ids, scores), key=lambda pair: -pair[1])] + fused[q][sr.RERANK_TOP:]

            report(f"hybrid {short} + {reranker.split('/')[-1]}", ranked)
        sr.embedder = load_embedder
    return 0


if __name__ == "__main__":
    sys.exit(main())
