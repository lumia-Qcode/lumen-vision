"""VLM import, gate+VLM fusion, and the Site-Profile rule engine."""
import json
import re
from datetime import datetime, timezone

import yaml

from . import db
from .config import GATE_WEIGHT, HAZARDS, PROFILES_YAML, VLM_RESULTS, VLM_WEIGHT


def _parse_json(text):
    """Best-effort JSON extraction from model output."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        return None
    blob = text[start:end + 1]
    for candidate in (blob, re.sub(r",\s*([}\]])", r"\1", blob)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def import_vlm(con, path=VLM_RESULTS):
    con.execute("DELETE FROM vlm_outputs")
    con.execute("DELETE FROM interpretations")
    con.execute("UPDATE clips SET vlm_ran = 0, description = tags")
    if not path.exists():
        return 0
    n = 0
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        parsed = r.get("parsed") or _parse_json(r.get("output", ""))
        if not parsed:
            continue
        con.execute("INSERT OR REPLACE INTO vlm_outputs VALUES (?,?,?,?,?)",
                    (r["clip_id"], r.get("model", ""), db.dumps(parsed), r.get("tokens_in", 0), r.get("tokens_out", 0)))
        caption = parsed.get("caption") or parsed.get("scene") or ""
        actions = "; ".join(a.get("description", "") for a in parsed.get("actions", []) if isinstance(a, dict))
        con.execute("UPDATE clips SET vlm_ran = 1, description = ? || ' | ' || ? || ' | ' || tags WHERE id = ?",
                    (caption, actions, r["clip_id"]))
        for ic in parsed.get("interpretation_candidates", []) or []:
            if isinstance(ic, dict) and ic.get("claim"):
                con.execute("INSERT INTO interpretations VALUES (?,?,?)",
                            (r["clip_id"], ic["claim"], ic.get("rationale", "")))
        n += 1
    con.commit()
    return n


def fuse(con):
    """Combine gate scores with VLM hazard flags into final hazard confidences."""
    con.execute("DELETE FROM hazards")
    vlm = {r["clip_id"]: json.loads(r["raw_json"]) for r in db.rows(con, "SELECT clip_id, raw_json FROM vlm_outputs")}
    for c in db.rows(con, "SELECT id, gate_json, suspicious FROM clips"):
        gate = json.loads(c["gate_json"])["scores"]
        v = vlm.get(c["id"])
        vflags = {}
        if v:
            for f in v.get("hazard_flags", []) or []:
                if isinstance(f, dict) and f.get("type") in HAZARDS:
                    conf = float(f.get("confidence", 0) or 0) if f.get("present", True) else 0.0
                    vflags[f["type"]] = (max(conf, vflags.get(f["type"], (0, ""))[0]), f.get("evidence", ""))
        for h in HAZARDS:
            g = gate.get(h, 0.0)
            if v is not None:
                vc, ev = vflags.get(h, (0.0, ""))
                final, vconf = GATE_WEIGHT * g + VLM_WEIGHT * vc, vc
            elif c["suspicious"]:
                final, vconf, ev = g, None, "gate only (VLM not run)"  # graceful fallback
            else:
                continue
            if final > 0:
                con.execute("INSERT INTO hazards VALUES (?,?,?,?,?,?,?)",
                            (c["id"], h, g, vconf, round(final, 3), ev, None))
    con.commit()


def _outside_hours(ts, window):
    t = datetime.fromisoformat(ts).strftime("%H:%M")
    return not (window[0] <= t < window[1])


def apply_rules(con):
    profiles = yaml.safe_load(open(PROFILES_YAML, encoding="utf-8"))
    kept = {(r["clip_id"], r["hazard_type"]): r for r in
            db.rows(con, "SELECT * FROM alerts WHERE status != 'pending'")}  # keep human decisions
    con.execute("DELETE FROM alerts WHERE status = 'pending'")
    q = """SELECT h.*, c.recorded_at, s.profile FROM hazards h JOIN clips c ON c.id = h.clip_id
           JOIN cameras cam ON cam.id = c.camera_id JOIN sites s ON s.id = cam.site_id"""
    n = 0
    for h in db.rows(con, q):
        rule = profiles.get(h["profile"], {}).get(h["type"])
        if not rule or h["final_conf"] < rule["min_conf"]:
            continue
        if rule.get("only_outside_hours") and not _outside_hours(h["recorded_at"], rule["only_outside_hours"]):
            continue
        if (h["clip_id"], h["type"]) in kept:
            continue
        con.execute("INSERT INTO alerts (clip_id, hazard_type, severity, profile, confidence, status, created_at) "
                    "VALUES (?,?,?,?,?,'pending',?)",
                    (h["clip_id"], h["type"], rule["severity"], h["profile"], h["final_conf"],
                     datetime.now(timezone.utc).isoformat(timespec="seconds")))
        n += 1
    con.commit()
    return n


def verify(con, alert_id, confirm, note=""):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = "confirmed" if confirm else "rejected"
    con.execute("UPDATE alerts SET status = ?, verified_at = ?, note = ? WHERE id = ?", (status, now, note, alert_id))
    if confirm:
        a = db.rows(con, "SELECT * FROM alerts WHERE id = ?", (alert_id,))[0]
        msg = f"[{a['severity'].upper()}] {a['hazard_type']} confirmed on clip {a['clip_id']} ({a['profile']})"
        con.execute("INSERT INTO notifications (alert_id, sent_at, message) VALUES (?,?,?)", (alert_id, now, msg))
    con.commit()
