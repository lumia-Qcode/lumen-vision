"""Paths and tunable thresholds. Everything else reads from here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
CLIPS_DIR = ROOT / "clips"
DATA_DIR = ROOT / "data"
INDEX_DIR = ROOT / "index"
KAGGLE_IN = ROOT / "kaggle_in"
DB_PATH = ROOT / "lumen.db"

CLIPS_CSV = DATA_DIR / "clips.csv"
ZONES_YAML = DATA_DIR / "zones.yaml"
PROFILES_YAML = DATA_DIR / "profiles.yaml"
QUERIES_YAML = DATA_DIR / "queries.yaml"
VLM_RESULTS = DATA_DIR / "vlm_results.jsonl"

# Clip preparation
MAX_CLIP_SECONDS = 15
CLIP_HEIGHT = 480
MAX_TELECOM_PER_CAMERA = 40  # subsample the 271 real telecom clips to keep the demo light

# Gate
SAMPLE_FPS = 1.0
MAX_FRAMES = 15
YOLO_WEIGHTS = "yolo11n.pt"
CLIP_ARCH, CLIP_PRETRAINED = "ViT-B-32", "laion2b_s34b_b79k"
TEXT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

PERSON_CONF = 0.35
OBJECT_CONF = 0.35
# Low thresholds on purpose: the Gate optimises recall, the VLM restores precision.
GATE_THRESHOLDS = {
    "fire_smoke": 0.30,
    "zone_entry": 0.35,
    "removed_object": 0.30,
    "abandoned_object": 0.30,
}
SUSPICIOUS_FRAMES_PER_CLIP = 3
QC_MIN_BRIGHTNESS = 15
QC_MIN_SHARPNESS = 5.0

HAZARDS = ["fire_smoke", "zone_entry", "removed_object", "abandoned_object"]

# Fusion
GATE_WEIGHT, VLM_WEIGHT = 0.3, 0.7

# Search
W_VISUAL, W_TEXT, W_HAZARD = 0.6, 0.4, 0.1
