"""The Gate: a cheap CPU first pass run on every Clip.

Produces per-hazard gate scores, frame embeddings for search, a tag string for text
search, and picks the Suspicious Frames that are worth sending to the VLM.
"""
from collections import Counter

import cv2
import imagehash
import numpy as np
from PIL import Image

from . import models
from .config import (GATE_THRESHOLDS, HAZARDS, MAX_FRAMES, OBJECT_CONF, PERSON_CONF,
                     QC_MIN_BRIGHTNESS, QC_MIN_SHARPNESS, SAMPLE_FPS, SUSPICIOUS_FRAMES_PER_CLIP)

FIRE_PROMPTS = ["a CCTV frame with visible fire and flames", "a CCTV frame with smoke rising",
                "a surveillance image of a building on fire", "thick grey smoke in the air"]
NORMAL_PROMPTS = ["a normal CCTV frame of an outdoor site", "a normal CCTV frame of an indoor room",
                  "a CCTV frame of a telecom tower and equipment", "a CCTV frame at night",
                  "a CCTV frame of a road with cars", "a CCTV frame of trees and sky",
                  "workers in safety gear at an industrial site"]
SCENE_PROMPTS = {
    "outdoor telecom site": "a telecom tower or antenna site outdoors",
    "equipment room": "an indoor room with electrical equipment cabinets",
    "electrical substation": "an electrical substation with transformers",
    "street": "a street with cars",
    "vegetation": "trees, grass and bushes",
    "night": "a dark night-time surveillance image",
    "industrial site": "an industrial plant or construction site",
}
STATIC_CLASSES = {"backpack", "handbag", "suitcase", "bottle", "chair", "bicycle", "motorcycle",
                  "laptop", "cell phone", "box", "umbrella", "bench", "potted plant", "tv"}


def sample_frames(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps / SAMPLE_FPS)))
    idxs = list(range(0, max(n, 1), step))[:MAX_FRAMES]
    frames = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if ok:
            frames.append(f)
    cap.release()
    return frames, (n / fps if n else 0)


def quality(frames):
    mid = cv2.cvtColor(frames[len(frames) // 2], cv2.COLOR_BGR2GRAY)
    brightness, sharpness = float(mid.mean()), float(cv2.Laplacian(mid, cv2.CV_64F).var())
    return brightness >= QC_MIN_BRIGHTNESS and sharpness >= QC_MIN_SHARPNESS, brightness, sharpness


def in_polygon(pt, poly):
    return cv2.pointPolygonTest(np.array(poly, dtype=np.float32), pt, False) >= 0


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0


def static_change(first, last, person_boxes):
    """Fraction of the frame that changed between first and last frame, people masked out."""
    a = cv2.GaussianBlur(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    b = cv2.GaussianBlur(cv2.cvtColor(last, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    diff = (cv2.absdiff(a, b) > 35).astype(np.uint8)
    h, w = diff.shape
    for x1, y1, x2, y2 in person_boxes:
        diff[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)] = 0
    diff = cv2.morphologyEx(diff, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(diff, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(cv2.contourArea(c) for c in contours) / (h * w)
    # A single compact changed blob of 0.3%..15% of the frame looks like an object; more is lighting/camera motion.
    return float(np.clip(largest / 0.02, 0, 1)) if 0.003 <= largest <= 0.15 else 0.0


def analyze(path, zones):
    """Run the Gate on one clip. `zones` is a list of polygons in normalised [0,1] coords."""
    frames, dur = sample_frames(path)
    if not frames:
        return None
    ok, brightness, sharpness = quality(frames)
    pil = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in frames]
    phash = str(imagehash.phash(pil[len(pil) // 2]))

    # --- objects + zone test ---
    dets, per_frame = [], []
    for fi, r in enumerate(models.yolo()(frames, verbose=False, conf=min(PERSON_CONF, OBJECT_CONF))):
        names = r.names
        frame_dets = []
        for box, c, k in zip(r.boxes.xyxyn.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            label = names[int(k)]
            if label != "person" and c < OBJECT_CONF:
                continue
            foot = ((box[0] + box[2]) / 2, box[3])
            inz = label == "person" and any(in_polygon(foot, z) for z in zones)
            d = dict(frame_idx=fi, label=label, conf=float(c), box=box, in_zone=bool(inz))
            dets.append(d)
            frame_dets.append(d)
        per_frame.append(frame_dets)

    zone_scores = [max([d["conf"] for d in fd if d["in_zone"]] or [0]) for fd in per_frame]

    # --- CLIP: embeddings + zero-shot fire/smoke + scene tags ---
    emb = models.clip_images(pil)
    txt = models.clip_texts(FIRE_PROMPTS + NORMAL_PROMPTS)
    probs = np.exp(100 * emb @ txt.T)
    probs /= probs.sum(1, keepdims=True)
    fire_scores = probs[:, :len(FIRE_PROMPTS)].sum(1).tolist()

    scene_txt = models.clip_texts(list(SCENE_PROMPTS.values()))
    clip_emb = emb.mean(0)
    clip_emb /= np.linalg.norm(clip_emb)
    scene_sims = clip_emb @ scene_txt.T
    scenes = [k for k, s in sorted(zip(SCENE_PROMPTS, scene_sims), key=lambda t: -t[1])[:2]]

    # --- removed / abandoned: object diff + masked pixel change, only if someone was present ---
    removed = abandoned = 0.0
    people = [d for d in dets if d["label"] == "person"]
    if people and len(frames) >= 2:
        first = [d for d in per_frame[0] if d["label"] in STATIC_CLASSES]
        last = [d for d in per_frame[-1] if d["label"] in STATIC_CLASSES]
        for d in first:
            if not any(iou(d["box"], e["box"]) > 0.4 for e in last):
                removed = max(removed, d["conf"])
        for e in last:
            if not any(iou(e["box"], d["box"]) > 0.4 for d in first):
                abandoned = max(abandoned, e["conf"])
        pboxes = [d["box"] for d in per_frame[0] + per_frame[-1] if d["label"] == "person"]
        removed = max(removed, 0.8 * static_change(frames[0], frames[-1], pboxes))

    n = len(frames)
    frame_scores = {
        "fire_smoke": fire_scores,
        "zone_entry": zone_scores,
        "removed_object": [0.0] * (n - 1) + [removed] if n > 1 else [removed],
        "abandoned_object": [0.0] * (n - 1) + [abandoned] if n > 1 else [abandoned],
    }
    if removed or abandoned:
        frame_scores["removed_object"][0] = max(frame_scores["removed_object"][0], removed)
    gate = {h: round(float(max(frame_scores[h])), 3) for h in HAZARDS}
    flagged = [h for h in HAZARDS if gate[h] >= GATE_THRESHOLDS[h]]

    combined = [max(frame_scores[h][i] for h in flagged) for i in range(n)] if flagged else [0] * n
    suspicious_frames = sorted(sorted(range(n), key=lambda i: -combined[i])[:SUSPICIOUS_FRAMES_PER_CLIP]) \
        if flagged else []

    counts = Counter(d["label"] for d in dets)
    max_per_frame = {lbl: max(sum(1 for d in fd if d["label"] == lbl) for fd in per_frame) for lbl in counts}
    tags = ", ".join([f"{lbl} x{c}" if c > 1 else lbl for lbl, c in sorted(max_per_frame.items())] + scenes)

    return dict(
        frames=frames, pil=pil, duration=dur, quality_ok=ok, brightness=brightness, sharpness=sharpness,
        phash=phash, detections=dets, embedding=clip_emb.astype("float32"), gate=gate, flagged=flagged,
        suspicious=bool(flagged), suspicious_frames=suspicious_frames, tags=tags, scenes=scenes,
    )
