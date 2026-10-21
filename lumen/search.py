"""Hybrid search: rule-based query parsing -> SQL filters + semantic residue -> CLIP & text ranking."""
import re
from datetime import datetime

import faiss
import numpy as np

from . import db, models
from .config import INDEX_DIR, W_HAZARD, W_TEXT, W_VISUAL

HAZARD_WORDS = {
    "fire_smoke": r"\b(fire|flames?|burning|smoke|smoky)\b",
    "zone_entry": r"\b(entered|entering|intru\w*|trespass\w*|restricted|zone|unauthori[sz]ed)\b",
    "removed_object": r"\b(removed?|taken|took|stole\w*|missing|theft|carr(y|ied|ying) away)\b",
    "abandoned_object": r"\b(abandoned|left behind|unattended|dropped)\b",
}
SITE_WORDS = {r"\btower\b": "unmanned_tower", r"\b(hub|exchange|staffed)\b": "staffed_hub"}
NIGHT = r"\b(at night|night ?time|night|after dark)\b"
DAY = r"\b(daytime|during the day|day ?time)\b"
STOP = r"\b(show|me|find|clips?|videos?|footage|of|with|a|an|the|any|all|where|in|on|at|from|camera|cam|site)\b"


class Index:
    def __init__(self, con):
        data = np.load(INDEX_DIR / "embeddings.npz")
        self.ids = [str(i) for i in data["ids"]]
        emb = data["emb"].astype("float32")
        self.visual = faiss.IndexFlatIP(emb.shape[1])
        self.visual.add(emb)
        self.con = con
        self.refresh_text()

    def refresh_text(self):
        desc = {r["id"]: r["description"] or "" for r in db.rows(self.con, "SELECT id, description FROM clips")}
        self.text_emb = models.embed_text([desc.get(i, "") for i in self.ids]).astype("float32")


def parse(query):
    q = query.lower()
    filters, residue = {}, q

    m = re.search(r"\b(?:camera|cam)[\s-]*([a-z0-9-]+)", q)
    if m:
        filters["camera"] = m.group(1)
        residue = residue.replace(m.group(0), " ")
    for pat, prof in SITE_WORDS.items():
        if re.search(pat, q):
            filters["profile"] = prof
            residue = re.sub(pat, " ", residue)
    if re.search(NIGHT, q):
        filters["hours"] = ("night", 19, 6)
        residue = re.sub(NIGHT, " ", residue)
    elif re.search(DAY, q):
        filters["hours"] = ("day", 6, 19)
        residue = re.sub(DAY, " ", residue)
    m = re.search(r"\b(after|before)\s+(\d{1,2})\s*(am|pm)?", q)
    if m:
        h = int(m.group(2)) % 12 + (12 if m.group(3) == "pm" else 0)
        filters["hours"] = ("after", h, 24) if m.group(1) == "after" else ("before", 0, h)
        residue = residue.replace(m.group(0), " ")
    m = re.search(r"\b(20\d\d-\d\d-\d\d)\b", q)
    if m:
        filters["date"] = m.group(1)
        residue = residue.replace(m.group(0), " ")

    hazards = [h for h, pat in HAZARD_WORDS.items() if re.search(pat, q)]
    residue = re.sub(r"\s+", " ", re.sub(STOP, " ", residue)).strip() or q
    return {"filters": filters, "hazards": hazards, "residue": residue}


def _passes(clip, f):
    if "camera" in f and f["camera"] not in clip["camera_id"]:
        return False
    if "profile" in f and clip["profile"] != f["profile"]:
        return False
    ts = datetime.fromisoformat(clip["recorded_at"])
    if "date" in f and ts.date().isoformat() != f["date"]:
        return False
    if "hours" in f:
        kind, a, b = f["hours"]
        hr = ts.hour
        ok = (hr >= a or hr < b) if kind == "night" else (a <= hr < b)
        if not ok:
            return False
    return True


def search(index, query, k=8):
    p = parse(query)
    clips = {r["id"]: r for r in db.rows(index.con, """
        SELECT c.*, s.profile, s.name AS site_name FROM clips c
        JOIN cameras cam ON cam.id = c.camera_id JOIN sites s ON s.id = cam.site_id""")}
    hz = {}
    for r in db.rows(index.con, "SELECT clip_id, type, final_conf FROM hazards"):
        hz.setdefault(r["clip_id"], {})[r["type"]] = r["final_conf"]

    cv = models.clip_texts([f"a CCTV frame of {p['residue']}"])[0]
    tv = models.embed_text([p["residue"]])[0]
    visual = index.visual.reconstruct_n(0, index.visual.ntotal) @ cv
    text = index.text_emb @ tv

    results = []
    for i, cid in enumerate(index.ids):
        c = clips.get(cid)
        if not c or not _passes(c, p["filters"]):
            continue
        boost = max([hz.get(cid, {}).get(h, 0) for h in p["hazards"]] or [0])
        score = W_VISUAL * float(visual[i]) + W_TEXT * float(text[i]) + W_HAZARD * boost
        results.append({**c, "score": round(score, 4), "visual": float(visual[i]), "text": float(text[i]),
                        "hazard_boost": boost})
    results.sort(key=lambda r: -r["score"])
    return p, results[:k]
