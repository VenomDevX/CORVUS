"""Local text-to-image engine: Stable Diffusion Turbo over ONNX Runtime.

No torch, no diffusers — the pipeline (CLIP text encoder → UNet Euler loop →
VAE decoder) runs on onnxruntime (already shipped for OCR), so it works on any
Windows machine: DirectML-accelerated when available, plain CPU otherwise.
SD-Turbo needs only 1–4 steps and no classifier-free guidance, which keeps
even CPU generation in the tens of seconds.

Model files download on demand (like Piper voices) into
%LOCALAPPDATA%/Corvus/image-models/<model-id>.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx
import numpy as np
import structlog

from ..config import data_dir
from .clip_tokenizer import ClipTokenizer

log = structlog.get_logger("corvus")

_HF = "https://huggingface.co"


@dataclass(frozen=True)
class ImageModel:
    id: str
    label: str
    repo: str
    download_gb: float
    steps_default: int
    blurb: str
    files: tuple[str, ...] = (
        "tokenizer/vocab.json",
        "tokenizer/merges.txt",
        "scheduler/scheduler_config.json",
        "text_encoder/model.onnx",
        "unet/model.onnx",
        "vae_decoder/model.onnx",
    )


IMAGE_MODELS: list[ImageModel] = [
    ImageModel(
        id="sdxs-512",
        label="SDXS 512 (DreamShaper)",
        repo="kmpartner/sdxs-dreamshaper-onnx",
        download_gb=1.9,
        steps_default=1,
        blurb="One-step distilled Stable Diffusion built for everyday PCs — quality 512px images in seconds, even on CPU.",
    ),
]


def _model(model_id: str) -> ImageModel:
    for m in IMAGE_MODELS:
        if m.id == model_id:
            return m
    raise ValueError(f"unknown image model: {model_id}")


# -- Euler discrete scheduler (epsilon, scaled_linear, trailing) ----------------


class _EulerScheduler:
    def __init__(self, config: dict):
        n = int(config.get("num_train_timesteps", 1000))
        beta_start = float(config.get("beta_start", 0.00085))
        beta_end = float(config.get("beta_end", 0.012))
        betas = np.linspace(beta_start**0.5, beta_end**0.5, n, dtype=np.float64) ** 2
        alphas_cumprod = np.cumprod(1.0 - betas)
        self.sigmas_all = np.sqrt((1 - alphas_cumprod) / alphas_cumprod)
        self.n_train = n

    def plan(self, steps: int) -> tuple[np.ndarray, np.ndarray]:
        """Trailing spacing: e.g. 2 steps → timesteps [999, 499]."""
        step = self.n_train / steps
        timesteps = (np.arange(self.n_train, 0, -step)).round().astype(np.int64) - 1
        sigmas = np.concatenate([self.sigmas_all[timesteps], [0.0]])
        return timesteps, sigmas

    @staticmethod
    def scale_input(sample: np.ndarray, sigma: float) -> np.ndarray:
        return sample / np.sqrt(sigma**2 + 1)

    @staticmethod
    def step(sample: np.ndarray, eps: np.ndarray, sigma: float, sigma_next: float) -> np.ndarray:
        return sample + eps * (sigma_next - sigma)


# -- engine ----------------------------------------------------------------


@dataclass
class _DownloadState:
    active: bool = False
    model_id: str = ""
    done_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class ImageEngine:
    def __init__(self, profile: dict):
        self.profile = profile
        self._sessions: dict[str, object] = {}
        self._tokenizer: ClipTokenizer | None = None
        self._scheduler: _EulerScheduler | None = None
        self._loaded_model: str | None = None
        self._load_lock = threading.Lock()
        self.download = _DownloadState()

    # -- storage ---------------------------------------------------------------

    def models_dir(self) -> Path:
        d = data_dir() / "image-models"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_installed(self, model_id: str) -> bool:
        m = _model(model_id)
        base = self.models_dir() / m.id
        return all((base / f).exists() for f in m.files)

    def catalog(self) -> list[dict]:
        return [
            {
                "id": m.id,
                "label": m.label,
                "download_gb": m.download_gb,
                "steps_default": m.steps_default,
                "blurb": m.blurb,
                "installed": self.is_installed(m.id),
            }
            for m in IMAGE_MODELS
        ]

    # -- download ---------------------------------------------------------------

    def download_model(self, model_id: str) -> None:
        """Blocking download with progress state; call via asyncio.to_thread."""
        m = _model(model_id)
        with self.download.lock:
            if self.download.active:
                raise RuntimeError("a model download is already in progress")
            self.download.active = True
            self.download.model_id = model_id
            self.download.done_bytes = 0
            self.download.total_bytes = 0
            self.download.error = None
        try:
            base = self.models_dir() / m.id
            with httpx.Client(follow_redirects=True, timeout=60) as client:
                # Size pass first so the progress bar is honest.
                sizes: dict[str, int] = {}
                for f in m.files:
                    if (base / f).exists():
                        continue
                    r = client.head(f"{_HF}/{m.repo}/resolve/main/{f}")
                    r.raise_for_status()
                    sizes[f] = int(r.headers.get("content-length", 0))
                self.download.total_bytes = sum(sizes.values())

                for f, size in sizes.items():
                    dest = base / f
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with client.stream("GET", f"{_HF}/{m.repo}/resolve/main/{f}") as resp:
                        resp.raise_for_status()
                        with open(tmp, "wb") as out:
                            for chunk in resp.iter_bytes(1024 * 512):
                                out.write(chunk)
                                self.download.done_bytes += len(chunk)
                    if size and tmp.stat().st_size != size:
                        tmp.unlink(missing_ok=True)
                        raise RuntimeError(f"download of {f} was incomplete")
                    tmp.replace(dest)
            log.info("image_model_installed", model=model_id)
        except Exception as exc:
            self.download.error = str(exc)
            log.warning("image_model_download_failed", model=model_id, error=str(exc))
            raise
        finally:
            self.download.active = False

    def download_status(self) -> dict:
        return {
            "active": self.download.active,
            "model_id": self.download.model_id,
            "done_bytes": self.download.done_bytes,
            "total_bytes": self.download.total_bytes,
            "error": self.download.error,
        }

    # -- pipeline ---------------------------------------------------------------

    def _session(self, base: Path, name: str):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(self.profile["intra_op_threads"])
        opts.log_severity_level = 3
        return ort.InferenceSession(
            str(base / name / "model.onnx"),
            sess_options=opts,
            providers=self.profile["ort_providers"],
        )

    def _load(self, model_id: str) -> None:
        if self._loaded_model == model_id and self._sessions:
            return
        self.unload()
        m = _model(model_id)
        base = self.models_dir() / m.id
        if not self.is_installed(model_id):
            raise RuntimeError("model not downloaded — install it from the Image page first")
        self._tokenizer = ClipTokenizer(base / "tokenizer")
        self._scheduler = _EulerScheduler(
            json.loads((base / "scheduler/scheduler_config.json").read_text())
        )
        for part in ("text_encoder", "unet", "vae_decoder"):
            self._sessions[part] = self._session(base, part)
        self._loaded_model = model_id
        log.info("image_model_loaded", model=model_id, providers=self.profile["ort_providers"])

    def unload(self) -> None:
        self._sessions.clear()
        self._tokenizer = None
        self._scheduler = None
        self._loaded_model = None

    @staticmethod
    def _cast_for(session, name_hint: str, arr: np.ndarray, input_index: int) -> np.ndarray:
        wanted = session.get_inputs()[input_index].type
        if "float16" in wanted:
            return arr.astype(np.float16)
        if "float" in wanted:
            return arr.astype(np.float32)
        if "int64" in wanted:
            return arr.astype(np.int64)
        if "int32" in wanted:
            return arr.astype(np.int32)
        return arr

    def generate(
        self,
        model_id: str,
        prompt: str,
        size: int = 512,
        steps: int | None = None,
        seed: int | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> bytes:
        """Render prompt → PNG bytes. Blocking; run in a worker thread under
        the API's single heavy-job lock."""
        with self._load_lock:
            m = _model(model_id)
            size = int(min(size, self.profile["image_max_size"]))
            size = max(256, size - size % 64)
            steps = int(steps or m.steps_default)
            steps = max(1, min(steps, 8))
            rng = np.random.default_rng(seed)

            self._load(model_id)
            text_encoder = self._sessions["text_encoder"]
            unet = self._sessions["unet"]
            vae = self._sessions["vae_decoder"]
            assert self._tokenizer is not None and self._scheduler is not None

            try:
                ids = np.array([self._tokenizer.encode(prompt)], dtype=np.int64)
                ids = self._cast_for(text_encoder, "ids", ids, 0)
                embeddings = text_encoder.run(None, {text_encoder.get_inputs()[0].name: ids})[0]
                embeddings = embeddings.astype(np.float32)

                timesteps, sigmas = self._scheduler.plan(steps)
                latent_shape = (1, 4, size // 8, size // 8)
                sample = rng.standard_normal(latent_shape).astype(np.float32) * float(
                    np.sqrt(sigmas[0] ** 2 + 1)
                )

                unet_inputs = {i.name: i for i in unet.get_inputs()}
                names = list(unet_inputs)
                for i, (t, sigma) in enumerate(zip(timesteps, sigmas[:-1])):
                    scaled = self._scheduler.scale_input(sample, float(sigma))
                    feed = {}
                    for name in names:
                        if "sample" in name:
                            feed[name] = self._cast_for(unet, name, scaled, names.index(name))
                        elif "timestep" in name or name == "t":
                            feed[name] = self._cast_for(
                                unet, name, np.array([t]), names.index(name)
                            )
                        else:  # encoder_hidden_states
                            feed[name] = self._cast_for(
                                unet, name, embeddings, names.index(name)
                            )
                    eps = unet.run(None, feed)[0].astype(np.float32)
                    sample = self._scheduler.step(sample, eps, float(sigma), float(sigmas[i + 1]))
                    if progress:
                        progress((i + 1) / (steps + 1))

                latents = (sample / 0.18215).astype(np.float32)
                latents = self._cast_for(vae, "latent", latents, 0)
                image = vae.run(None, {vae.get_inputs()[0].name: latents})[0]
                image = np.clip(image.astype(np.float32) / 2 + 0.5, 0, 1)
                rgb = (image[0].transpose(1, 2, 0) * 255).round().astype(np.uint8)

                from PIL import Image
                import io

                buf = io.BytesIO()
                Image.fromarray(rgb).save(buf, format="PNG")
                if progress:
                    progress(1.0)
                return buf.getvalue()
            finally:
                if self.profile["unload_after_generate"]:
                    self.unload()
