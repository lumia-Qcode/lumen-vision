"""Multi-camera room agents.

Every view in a room is a CameraAgent that can only see its own field of view. A RoomCoordinator takes
an operator request, broadcasts it, and the agents talk to each other through a message bus:

  HELLO        agent announces itself and which neighbours its field of view overlaps
  REQUEST      coordinator broadcasts the operator's question (with any time scope)
  REPORT       agent reports its best matching moments, or that it has nothing
  VERIFY       coordinator asks agents that stayed quiet to check a specific moment
  CORROBORATE  agent confirms it sees the moment from its angle
  NOT_VISIBLE  agent explains the moment is outside its field of view / doesn't match
  HANDOFF      agent tells a neighbour the subject is leaving its frame towards it
  ACQUIRED     neighbour confirms it picked the subject up
  LOST         subject left every field of view
  VERDICT      coordinator's consensus: the moment, how many angles agree, best angle per second

Agents are deterministic and run on CPU: CLIP similarity on their own crops plus person detections.
If HF_TOKEN is set, the coordinator also writes a short natural-language briefing with a free hosted LLM.
"""
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import yaml

from . import db, models
from .config import INDEX_DIR, ROOT
from .search import parse

ROOMS_YAML = ROOT / "data" / "rooms.yaml"
PERSON_WORDS = r"\b(person|people|man|men|woman|someone|somebody|worker|workers|intruder|human|guy|visitor|technician)\b"


@lru_cache(maxsize=1)
def load_rooms():
    return yaml.safe_load(open(ROOMS_YAML, encoding="utf-8"))["rooms"]


@lru_cache(maxsize=1)
def load_embeddings():
    return dict(np.load(INDEX_DIR / "rooms.npz"))


@dataclass
class Message:
    sender: str
    recipient: str
    kind: str
    text: str
    data: dict = field(default_factory=dict)


class Bus:
    def __init__(self):
        self.log = []

    def send(self, sender, recipient, kind, text, **data):
        self.log.append(Message(sender, recipient, kind, text, data))


def to_view(box, crop):
    """Source-normalised box -> view-normalised box (None if its centre is outside the view)."""
    x, y, s = crop
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if not (x <= cx <= x + s and y <= cy <= y + s):
        return None
    return [max(0, (box[0] - x) / s), max(0, (box[1] - y) / s), min(1, (box[2] - x) / s), min(1, (box[3] - y) / s)]


def overlap(a, b):
    ax, ay, as_ = a
    bx, by, bs = b
    w = max(0, min(ax + as_, bx + bs) - max(ax, bx))
    h = max(0, min(ay + as_, by + bs) - max(ay, by))
    return w * h / min(as_ * as_, bs * bs)


class CameraAgent:
    def __init__(self, view, room_id, clip_ids, counts, dets, emb):
        self.v, self.id, self.name, self.crop = view, view["id"], view["name"], view["crop"]
        self.room_id, self.clip_ids, self.counts, self.emb = room_id, clip_ids, counts, emb.astype(np.float32)
        # person boxes in this view's coordinates: {(clip_idx, frame): [box, ...]}
        self.people = {}
        for (ci, f), boxes in dets.items():
            vb = [b2 for b in boxes if (b2 := to_view(b["box"], self.crop))]
            if vb:
                self.people[(ci, f)] = vb
        self.scores = None

    def score(self, text_vec, wants_person, allowed):
        """Per-frame relevance in this view, z-scored against the agent's own footage."""
        raw = self.emb @ text_vec  # (clips, frames)
        mask = np.zeros_like(raw, dtype=bool)
        for i, n in enumerate(self.counts):
            if allowed[i]:
                mask[i, :n] = True
        vals = raw[mask]
        mu, sd = (vals.mean(), vals.std() + 1e-6) if vals.size else (0, 1)
        z = (raw - mu) / sd
        if wants_person:
            for (ci, f), boxes in self.people.items():
                z[ci, f] += 0.9 + 4 * max((b[2] - b[0]) * (b[3] - b[1]) for b in boxes)
        z[~mask] = -9
        self.scores = z
        return z

    def report(self, k=2, min_z=1.4):
        z = self.scores
        best = []
        for ci in np.argsort(-z.max(1))[: k * 3]:
            f = int(z[ci].argmax())
            if z[ci, f] >= min_z:
                best.append((int(ci), f, float(z[ci, f])))
            if len(best) == k:
                break
        return best

    def check(self, ci, f, window=2):
        lo, hi = max(0, f - window), min(int(self.counts[ci]) - 1, f + window)
        zf = float(self.scores[ci, lo:hi + 1].max()) if hi >= lo else -9
        seen = any((ci, g) in self.people for g in range(lo, hi + 1))
        return zf, seen


class RoomCoordinator:
    def __init__(self, room_id, con=None):
        self.con = con or db.connect()
        self.room_id, self.room = room_id, load_rooms()[room_id]
        e = load_embeddings()
        self.clip_ids = [str(c) for c in e[f"{room_id}__clip_ids"]]
        self.counts = e[f"{room_id}__counts"]
        clips = {r["id"]: r for r in db.rows(self.con, "SELECT id, path, recorded_at FROM clips WHERE camera_id = ?",
                                              (self.room["source_camera"],))}
        self.clips = [clips[c] for c in self.clip_ids]
        dets = {}
        idx = {c: i for i, c in enumerate(self.clip_ids)}
        for d in db.rows(self.con, f"""SELECT clip_id, frame_idx, conf, x1, y1, x2, y2 FROM detections
                WHERE label = 'person' AND clip_id IN ({','.join('?' * len(idx))})""", tuple(idx)):
            dets.setdefault((idx[d["clip_id"]], d["frame_idx"]), []).append(
                {"box": [d["x1"], d["y1"], d["x2"], d["y2"]], "conf": d["conf"]})
        self.dets = dets
        self.agents = [CameraAgent(v, room_id, self.clip_ids, self.counts, dets, e[f"view__{v['id']}"])
                       for v in self.room["views"]]

    def _time(self, ci, f):
        return datetime.fromisoformat(self.clips[ci]["recorded_at"]) + timedelta(seconds=f)

    def _fmt(self, ci, f):
        return self._time(ci, f).strftime("%H:%M:%S")

    def ask(self, query):
        bus = Bus()
        p = parse(query)
        wants_person = bool(re.search(PERSON_WORDS, query.lower()))
        hours = p["filters"].get("hours")
        allowed = []
        for c in self.clips:
            hr = datetime.fromisoformat(c["recorded_at"]).hour
            if not hours:
                allowed.append(True)
            else:
                kind, a, b = hours
                allowed.append((hr >= a or hr < b) if kind == "night" else (a <= hr < b))
        n_scope = sum(allowed)

        # 1. handshake: agents announce themselves and their overlapping neighbours
        for ag in self.agents:
            neigh = [f"{o.name} ({100 * overlap(ag.crop, o.crop):.0f}%)" for o in self.agents
                     if o is not ag and overlap(ag.crop, o.crop) > 0.05]
            bus.send(ag.id, "coordinator", "HELLO", f"{ag.name} online. Field of view overlaps " +
                     (", ".join(neigh) if neigh else "no other camera") + ".")

        # 2. broadcast the request
        scope = f", scoped to {hours[0] if hours[0] in ('night', 'day') else 'the requested hours'}" if hours else ""
        bus.send("coordinator", "all", "REQUEST",
                 f"Operator asks: \"{query}\"{scope}. Search your own footage ({n_scope} clips each) and report.")
        if n_scope == 0:
            bus.send("coordinator", "operator", "VERDICT", "No footage from this room falls inside that time scope.")
            return self._result(query, bus, None)

        text_vec = models.clip_texts([f"a CCTV frame of {p['residue']}"])[0]
        reports = {}
        for ag in self.agents:
            ag.score(text_vec, wants_person, allowed)
            hits = ag.report()
            reports[ag.id] = hits
            if hits:
                ci, f, z = hits[0]
                ppl = len(ag.people.get((ci, f), []))
                extra = f" Second candidate at {self._fmt(*hits[1][:2])}." if len(hits) > 1 else ""
                bus.send(ag.id, "coordinator", "REPORT",
                         f"Best match at {self._fmt(ci, f)} (strength {z:.1f}σ)"
                         + (f", {ppl} {'person' if ppl == 1 else 'people'} in my frame." if ppl else ".") + extra,
                         clip=ci, frame=f, z=z)
            else:
                bus.send(ag.id, "coordinator", "REPORT", "Nothing stands out in my field of view.")

        # 3. cluster reports into candidate moments (one per clip; the strongest report sets the second)
        moments = []
        for vid, hits in reports.items():
            for ci, f, z in hits:
                m = next((m for m in moments if m["clip"] == ci), None)
                if m:
                    if z > max(m["votes"].values()):
                        m["frame"] = f
                    m["votes"][vid] = max(z, m["votes"].get(vid, -9))
                else:
                    moments.append({"clip": ci, "frame": f, "votes": {vid: z}})
        for m in moments:
            m["score"] = sum(m["votes"].values())
        if not moments:
            bus.send("coordinator", "operator", "VERDICT", "No camera in this room found a convincing match.")
            return self._result(query, bus, None)
        moments.sort(key=lambda m: -m["score"])
        top = moments[0]
        ci, f = top["clip"], top["frame"]

        # 4. ask the quiet agents to verify the leading moment from their angle
        status = {vid: "reported" for vid in top["votes"]}
        for ag in self.agents:
            if ag.id in status:
                continue
            bus.send("coordinator", ag.id, "VERIFY", f"{', '.join(self._name(v) for v in top['votes'])} "
                     f"flagged {self._fmt(ci, f)}. Check that moment from your angle.")
            zf, seen = ag.check(ci, f)
            if zf >= 0.6 or (wants_person and seen):
                status[ag.id] = "corroborated"
                bus.send(ag.id, "coordinator", "CORROBORATE",
                         f"Confirmed from my angle ({zf:.1f}σ" + (", subject visible)." if seen else ")."))
            else:
                status[ag.id] = "not_visible"
                why = "The subject is outside my field of view." if wants_person and not seen else \
                    "I don't see anything matching at that moment."
                bus.send(ag.id, "coordinator", "NOT_VISIBLE", why)

        # 5. follow the subject across views: handoffs on the leading clip
        track, cut = self._track(ci, bus)

        agree = sum(s != "not_visible" for s in status.values())
        best_now = cut[f] if f < len(cut) else cut[-1]
        bus.send("coordinator", "operator", "VERDICT",
                 f"Moment at {self._fmt(ci, f)}: {agree} of {len(self.agents)} cameras agree. "
                 f"Best angle is the {self._name(best_now)}. "
                 + (f"{len(moments) - 1} other candidate moment{'s' if len(moments) > 2 else ''} ranked lower."
                    if len(moments) > 1 else ""),
                 clip=ci, frame=f)
        result = self._result(query, bus, {"clip": ci, "frame": f, "status": status, "track": track, "cut": cut,
                                           "agree": agree, "others": [
                                               {"time": self._fmt(m["clip"], m["frame"]), "clip": self.clip_ids[m["clip"]],
                                                "votes": len(m["votes"])} for m in moments[1:4]]})
        result["briefing"] = self._briefing(query, result)
        return result

    def _name(self, vid):
        return next(a.name for a in self.agents if a.id == vid)

    def _track(self, ci, bus):
        """Follow the main subject frame by frame, emit handoffs, and pick the best angle per second."""
        n = int(self.counts[ci])
        subject = []
        for f in range(n):
            boxes = self.dets.get((ci, f), [])
            subject.append(max(boxes, key=lambda b: (b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1]))["box"]
                           if boxes else None)
        # the detector sometimes misses a frame: bridge one-frame gaps by interpolating the box
        for f in range(1, n - 1):
            if subject[f] is None and subject[f - 1] and subject[f + 1]:
                subject[f] = [(a + b) / 2 for a, b in zip(subject[f - 1], subject[f + 1])]
        track = {ag.id: [] for ag in self.agents}
        for f, b in enumerate(subject):
            for ag in self.agents:
                vb = to_view(b, ag.crop) if b else None
                track[ag.id].append(round((vb[2] - vb[0]) * (vb[3] - vb[1]), 4) if vb else 0)
        cut = []
        for f in range(n):
            vis = {ag.id: track[ag.id][f] for ag in self.agents if track[ag.id][f] > 0}
            cut.append(max(vis, key=vis.get) if vis else self.agents[0].id)

        handoffs, first = 0, next((f for f, b in enumerate(subject) if b), None)
        if first is not None:
            seen_by = [a.name for a in self.agents if track[a.id][first] > 0]
            bus.send("coordinator", "all", "TRACK", f"Following the subject from {self._fmt(ci, first)}, first seen by "
                     f"{', '.join(seen_by)}.")
        lost_reported = False
        for f in range(1, n):
            if handoffs >= 4:
                break
            if subject[f] is None:
                # gone from every view: report once, and only if they don't come straight back
                if subject[f - 1] is not None and not any(subject[f:f + 3]) and not lost_reported:
                    last = [a for a in self.agents if track[a.id][f - 1] > 0]
                    who = last[0] if last else self.agents[0]
                    bus.send(who.id, "all", "LOST", f"Subject left my view at {self._fmt(ci, f)}. "
                             "No camera in this room has them now.")
                    lost_reported = True
                continue
            lost_reported = False
            for ag in self.agents:
                if track[ag.id][f - 1] > 0 and track[ag.id][f] == 0:
                    takers = [o for o in self.agents if o is not ag and track[o.id][f] > 0 and track[o.id][f - 1] == 0]
                    takers = takers or [o for o in self.agents if o is not ag and track[o.id][f] > 0]
                    if not takers:
                        continue
                    b = subject[f - 1]
                    side = "left" if (b[0] + b[2]) / 2 < ag.crop[0] + ag.crop[2] / 2 else "right"
                    o = max(takers, key=lambda t: track[t.id][f])
                    bus.send(ag.id, o.id, "HANDOFF", f"Subject leaving my {side} edge at {self._fmt(ci, f)}, "
                             f"heading into your view.")
                    bus.send(o.id, ag.id, "ACQUIRED", f"Got them at {self._fmt(ci, f)}. Tracking.")
                    handoffs += 1
        return track, cut

    def _result(self, query, bus, moment):
        views = []
        for ag in self.agents:
            boxes = {}
            if moment:
                for f in range(int(self.counts[moment["clip"]])):
                    if (moment["clip"], f) in ag.people:
                        boxes[f] = ag.people[(moment["clip"], f)]
            views.append({"id": ag.id, "name": ag.name, "crop": ag.crop, "pos": ag.v["pos"], "yaw": ag.v["yaw"],
                          "fov": ag.v["fov"], "boxes": boxes,
                          "status": moment["status"].get(ag.id) if moment else None})
        out = {"room": self.room_id, "room_name": self.room["name"], "plan": self.room["plan"], "query": query,
               "views": views, "messages": [m.__dict__ for m in bus.log], "moment": None, "briefing": None}
        if moment:
            c = self.clips[moment["clip"]]
            out["moment"] = {**{k: v for k, v in moment.items() if k != "clip"}, "clip_id": c["id"],
                             "time": self._fmt(moment["clip"], moment["frame"]),
                             "date": datetime.fromisoformat(c["recorded_at"]).strftime("%d %b %Y"),
                             "start": datetime.fromisoformat(c["recorded_at"]).strftime("%H:%M:%S"),
                             "video": f"app/static/clips/{c['id']}.mp4"}
        return out

    def _briefing(self, query, result):
        """Optional: a free hosted LLM turns the agent transcript into a two-sentence briefing."""
        token = os.environ.get("HF_TOKEN")
        if not token:
            return None
        transcript = "\n".join(f"{m['sender']} -> {m['recipient']} [{m['kind']}]: {m['text']}" for m in result["messages"])
        body = {"model": os.environ.get("LUMEN_LLM", "Qwen/Qwen2.5-7B-Instruct"), "max_tokens": 120, "temperature": 0.2,
                "messages": [{"role": "system", "content": "You brief a security operator. Two sentences, factual, "
                              "no speculation about intent. Only use facts from the transcript."},
                             {"role": "user", "content": f"Operator question: {query}\nCamera agent transcript:\n{transcript}"}]}
        try:
            req = urllib.request.Request("https://router.huggingface.co/v1/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except Exception:
            return None
