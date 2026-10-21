"""SQLite schema and small helpers."""
import json
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (id TEXT PRIMARY KEY, name TEXT, profile TEXT);
CREATE TABLE IF NOT EXISTS cameras (id TEXT PRIMARY KEY, site_id TEXT, name TEXT, zones_json TEXT);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY, path TEXT, source TEXT, camera_id TEXT, recorded_at TEXT,
    duration_s REAL, phash TEXT, quality_ok INTEGER, duplicate_of TEXT,
    suspicious INTEGER DEFAULT 0, gate_json TEXT, tags TEXT, description TEXT,
    vlm_ran INTEGER DEFAULT 0, frames_total INTEGER, frames_to_vlm INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS detections (
    clip_id TEXT, frame_idx INTEGER, label TEXT, conf REAL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL, in_zone INTEGER
);
CREATE TABLE IF NOT EXISTS vlm_outputs (
    clip_id TEXT PRIMARY KEY, model TEXT, raw_json TEXT, tokens_in INTEGER, tokens_out INTEGER
);
CREATE TABLE IF NOT EXISTS hazards (
    clip_id TEXT, type TEXT, gate_conf REAL, vlm_conf REAL, final_conf REAL,
    evidence TEXT, evidence_frame INTEGER, PRIMARY KEY (clip_id, type)
);
CREATE TABLE IF NOT EXISTS interpretations (clip_id TEXT, claim TEXT, rationale TEXT);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT, hazard_type TEXT, severity TEXT,
    profile TEXT, confidence REAL, status TEXT DEFAULT 'pending', created_at TEXT,
    verified_at TEXT, note TEXT, UNIQUE (clip_id, hazard_type)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER, sent_at TEXT, message TEXT
);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"))
