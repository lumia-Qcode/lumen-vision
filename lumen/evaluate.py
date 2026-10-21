"""Evaluation: per-hazard P/R/F1 (gate-only vs gate+VLM), gate recall, VLM cost savings, retrieval P@K/R@K."""
import csv
import json

import yaml

from . import db
from .config import (CLIPS_CSV, GATE_THRESHOLDS, HAZARDS, INDEX_DIR, PROFILES_YAML, QUERIES_YAML)


def prf(pred, gold):
    tp = sum(p and g for p, g in zip(pred, gold))
    fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(prec, 3), recall=round(rec, 3), f1=round(f1, 3))


def hazard_metrics(con):
    labels = {r["id"]: r for r in csv.DictReader(open(CLIPS_CSV, encoding="utf-8"))}
    clips = {r["id"]: r for r in db.rows(con, "SELECT id, gate_json, suspicious, vlm_ran FROM clips")}
    final = {(r["clip_id"], r["type"]): r["final_conf"] for r in db.rows(con, "SELECT * FROM hazards")}
    profiles = yaml.safe_load(open(PROFILES_YAML, encoding="utf-8"))
    out = {}
    for h in HAZARDS:
        ids = [i for i in clips if labels.get(i, {}).get(h, "") in ("0", "1")]
        if not ids:
            continue
        gold = [labels[i][h] == "1" for i in ids]
        gate_pred = [json.loads(clips[i]["gate_json"])["scores"][h] >= GATE_THRESHOLDS[h] for i in ids]
        thr = min(p[h]["min_conf"] for p in profiles.values())
        fused_pred = [final.get((i, h), 0) >= thr for i in ids]
        out[h] = {"n_labelled": len(ids), "positives": sum(gold),
                  "gate_only": prf(gate_pred, gold), "gate_plus_vlm": prf(fused_pred, gold),
                  "gate_recall": prf(gate_pred, gold)["recall"]}
    return out


def cost_metrics(con):
    r = db.rows(con, """SELECT COUNT(*) n, SUM(suspicious) sus, SUM(vlm_ran) vlm,
                        SUM(frames_total) frames, SUM(frames_to_vlm) vframes FROM clips""")[0]
    tok = db.rows(con, "SELECT COUNT(*) n, SUM(tokens_in) tin, SUM(tokens_out) tout FROM vlm_outputs")[0]
    n, frames, vframes = r["n"] or 0, r["frames"] or 0, r["vframes"] or 0
    per_frame_tokens = (tok["tin"] or 0) / max(vframes, 1) if tok["n"] else None
    return {
        "clips_total": n, "clips_sent_to_vlm": r["sus"] or 0,
        "clips_pct_to_vlm": round(100 * (r["sus"] or 0) / max(n, 1), 1),
        "frames_total": frames, "frames_sent_to_vlm": vframes,
        "frames_pct_to_vlm": round(100 * vframes / max(frames, 1), 1),
        "vlm_tokens_in": tok["tin"] or 0, "vlm_tokens_out": tok["tout"] or 0,
        "est_tokens_if_all_frames": round(per_frame_tokens * frames) if per_frame_tokens else None,
    }


def retrieval_metrics(index, k=5):
    from .search import search
    if not QUERIES_YAML.exists():
        return {}
    queries = yaml.safe_load(open(QUERIES_YAML, encoding="utf-8")) or []
    labels = list(csv.DictReader(open(CLIPS_CSV, encoding="utf-8")))
    indexed = set(index.ids)
    rows, ps, rs = [], [], []
    for q in queries:
        # relevance = explicit ids  ∪  clips whose clips.csv columns match every `relevant_if` condition
        rel = set(q.get("relevant", []))
        cond = q.get("relevant_if") or {}
        if cond:
            rel |= {r["id"] for r in labels if all(str(r.get(c, "")) == str(v) for c, v in cond.items())}
        rel &= indexed
        if not rel:
            continue
        _, res = search(index, q["query"], k=k)
        got = [r["id"] for r in res]
        hit = len(rel & set(got))
        ps.append(hit / k)
        rs.append(hit / len(rel))
        rows.append({"query": q["query"], "p_at_k": round(hit / k, 2), "r_at_k": round(hit / len(rel), 2)})
    if not rows:
        return {}
    return {"k": k, "mean_p_at_k": round(sum(ps) / len(ps), 3), "mean_r_at_k": round(sum(rs) / len(rs), 3),
            "queries": rows}


def run(con, index=None):
    report = {"hazards": hazard_metrics(con), "cost": cost_metrics(con)}
    if index is not None:
        report["retrieval"] = retrieval_metrics(index)
    with open(INDEX_DIR / "eval_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report
