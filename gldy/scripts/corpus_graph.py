#!/usr/bin/env python3
"""Build the Corpus View graph JSON and render the self-contained widget.

Read-only against the corpus sqlite index and vault. Stdlib only.
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys

WIKILINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")
KIND_ORDER = ["knowledge", "decision", "todo", "note", "conversation", "meeting", "analysis"]
NON_CONV_CAPS = {"knowledge": None, "decision": 40, "todo": 30, "note": 60}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Build corpus graph JSON + rendered widget")
    p.add_argument("--db", default="/Volumes/gldy_corpus/GLDY/Search-Indexes/brain/index.sqlite3")
    p.add_argument("--vault", default="/Volumes/gldy_corpus/GLDY/Vault")
    p.add_argument("--out", default="corpus.json")
    p.add_argument("--rendered", default="corpus-view.rendered.html")
    p.add_argument("--max-nodes", type=int, default=420)
    p.add_argument("--template", default="corpus-view.html")
    p.add_argument("--page", default="pages/corpus.json")
    p.add_argument("--edge-cap", type=int, default=900)
    return p.parse_args(argv)


def truncate(text, limit=40):
    text = " ".join((text or "").split())
    return text[:limit]


def file_stem(path):
    base = os.path.basename(path or "")
    if base.lower().endswith(".md"):
        base = base[:-3]
    return base


def load_docs(conn):
    cur = conn.execute(
        "SELECT doc_id, kind, title, date, path, project FROM docs"
    )
    docs = []
    for doc_id, kind, title, date, path, project in cur:
        docs.append({
            "id": doc_id,
            "kind": kind,
            "title": title or "",
            "date": date or "",
            "path": path or "",
            "project": (project or "").strip() or None,
        })
    return docs


def load_chunk_counts(conn):
    counts = {}
    for doc_id, n in conn.execute("SELECT doc_id, COUNT(*) FROM chunks GROUP BY doc_id"):
        counts[doc_id] = n
    return counts


def sample_docs(docs, max_nodes):
    """All knowledge, capped decision/todo/note, remaining conversations newest first."""
    by_kind = {}
    for d in docs:
        by_kind.setdefault(d["kind"], []).append(d)

    selected = []
    selected_ids = set()

    def take(kind, cap):
        items = by_kind.get(kind, [])
        items = sorted(items, key=lambda d: (d["date"], d["id"]), reverse=True)
        if cap is not None:
            items = items[:cap]
        for d in items:
            if d["id"] not in selected_ids:
                selected.append(d)
                selected_ids.add(d["id"])

    take("knowledge", None)
    take("decision", NON_CONV_CAPS["decision"])
    take("todo", NON_CONV_CAPS["todo"])
    take("note", NON_CONV_CAPS["note"])

    remaining = max_nodes - len(selected)
    if remaining > 0:
        convs = sorted(by_kind.get("conversation", []),
                       key=lambda d: (d["date"], d["id"]), reverse=True)
        for d in convs[:remaining]:
            if d["id"] not in selected_ids:
                selected.append(d)
                selected_ids.add(d["id"])

    return selected


def build_nodes(selected, chunk_counts):
    nodes = []
    for d in selected:
        nodes.append({
            "id": d["id"],
            "kind": d["kind"],
            "label": truncate(d["title"], 40),
            "size": int(chunk_counts.get(d["id"], 0)),
            "project": d["project"],
            "date": d["date"],
        })
    return nodes


def wikilink_edges(nodes, vault):
    """Parse [[...]] links in vault markdown, resolving by title / filename stem.

    An edge exists only when both endpoints are sampled nodes.
    """
    stem_map = {}
    for idx, n in enumerate(nodes):
        for key in {n["label"].strip().lower()}:
            if key:
                stem_map.setdefault(key, idx)
    # path stems from the source docs are not carried in nodes, so titles are the
    # resolution key (knowledge titles match vault filename stems exactly).
    if not os.path.isdir(vault):
        return []

    edges = []
    seen = set()
    for root, _dirs, files in os.walk(vault):
        for fname in files:
            if not fname.lower().endswith(".md"):
                continue
            src_key = file_stem(fname).strip().lower()
            src = stem_map.get(src_key)
            if src is None:
                continue
            try:
                with open(os.path.join(root, fname), "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for raw in WIKILINK_RE.findall(text):
                target = raw.split("|", 1)[0].split("#", 1)[0].strip().lower()
                dst = stem_map.get(target)
                if dst is None or dst == src:
                    continue
                key = (min(src, dst), max(src, dst))
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"s": src, "t": dst, "w": 1.0})
    return edges


def project_edges(nodes, cap):
    groups = {}
    for idx, n in enumerate(nodes):
        if n["project"]:
            groups.setdefault(n["project"], []).append(idx)
    edges = []
    seen = set()
    for project in sorted(groups):
        members = groups[project]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                key = (min(a, b), max(a, b))
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"s": a, "t": b, "w": 0.5})
                if len(edges) >= cap:
                    return edges
    return edges


def knowledge_bridge_edges(nodes, cap):
    knowledge = [i for i, n in enumerate(nodes) if n["kind"] == "knowledge"]
    convs = [i for i, n in enumerate(nodes) if n["kind"] == "conversation"]
    convs = sorted(convs, key=lambda i: (nodes[i]["date"], nodes[i]["id"]), reverse=True)[:8]
    edges = []
    for k in knowledge:
        for c in convs:
            edges.append({"s": k, "t": c, "w": 0.3})
            if len(edges) >= cap:
                return edges
    return edges


def main(argv=None):
    args = parse_args(argv)
    if not os.path.isfile(args.db):
        sys.exit("database not found: %s" % args.db)

    conn = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    try:
        docs = load_docs(conn)
        chunk_counts = load_chunk_counts(conn)
        totals = {
            "conversations": sum(1 for d in docs if d["kind"] == "conversation"),
            "knowledge": sum(1 for d in docs if d["kind"] == "knowledge"),
            "chunks": sum(chunk_counts.values()),
            "decisions": sum(1 for d in docs if d["kind"] == "decision"),
            "todos": sum(1 for d in docs if d["kind"] == "todo"),
            "notes": sum(1 for d in docs if d["kind"] == "note"),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    finally:
        conn.close()

    selected = sample_docs(docs, args.max_nodes)
    nodes = build_nodes(selected, chunk_counts)

    edges = wikilink_edges(nodes, args.vault)[:args.edge_cap]
    if len(edges) < args.edge_cap:
        edges += project_edges(nodes, args.edge_cap - len(edges))
    if len(edges) < args.edge_cap:
        edges += knowledge_bridge_edges(nodes, args.edge_cap - len(edges))

    payload = {"nodes": nodes, "edges": edges, "totals": totals}
    data_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    # keep the payload safe when inlined inside a <script> element
    data_json = data_json.replace("<", "\\u003c")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(data_json)
        fh.write("\n")

    with open(args.template, "r", encoding="utf-8") as fh:
        template = fh.read()
    if "__CORPUS_DATA__" not in template:
        sys.exit("template is missing __CORPUS_DATA__ token")
    rendered = template.replace("__CORPUS_DATA__", data_json, 1)
    with open(args.rendered, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    page = {
        "id": "corpus",
        "title": "Corpus",
        "icon": "\U0001F30C",
        "enabled": True,
        "widgets": [{
            "id": "corpus-view",
            "type": "html",
            "x": 0, "y": 0, "w": 12, "h": 6,
            "options": {"html": rendered, "transparent": False},
        }],
    }
    page_dir = os.path.dirname(args.page)
    if page_dir:
        os.makedirs(page_dir, exist_ok=True)
    with open(args.page, "w", encoding="utf-8") as fh:
        json.dump(page, fh, ensure_ascii=False, separators=(",", ":"))

    rendered_size = os.path.getsize(args.rendered)
    print("corpus: %d nodes, %d edges, %d bytes rendered, %d bytes json, %d bytes page"
          % (len(nodes), len(edges), rendered_size, os.path.getsize(args.out),
             os.path.getsize(args.page)))


if __name__ == "__main__":
    main()
