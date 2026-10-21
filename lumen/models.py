"""Lazy, cached model loaders (CPU)."""
from functools import lru_cache

import numpy as np
import torch

from .config import CLIP_ARCH, CLIP_PRETRAINED, TEXT_MODEL, YOLO_WEIGHTS

torch.set_num_threads(max(1, torch.get_num_threads()))


@lru_cache(maxsize=1)
def yolo():
    from ultralytics import YOLO
    return YOLO(YOLO_WEIGHTS)


@lru_cache(maxsize=1)
def clip():
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms(CLIP_ARCH, pretrained=CLIP_PRETRAINED)
    model.eval()
    return model, preprocess, open_clip.get_tokenizer(CLIP_ARCH)


@lru_cache(maxsize=1)
def text_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(TEXT_MODEL, device="cpu")


def _norm(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True).clip(1e-8)


@torch.no_grad()
def clip_images(pil_images):
    model, preprocess, _ = clip()
    batch = torch.stack([preprocess(im) for im in pil_images])
    return _norm(model.encode_image(batch).float().numpy())


@lru_cache(maxsize=256)
def _clip_text_cached(texts):
    model, _, tokenizer = clip()
    with torch.no_grad():
        return _norm(model.encode_text(tokenizer(list(texts))).float().numpy())


def clip_texts(texts):
    return _clip_text_cached(tuple(texts))


def embed_text(texts):
    return text_encoder().encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
