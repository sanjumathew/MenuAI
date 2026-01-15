import hashlib
import os
import asyncio
import aiofiles
import logging
import base64
from pathlib import Path
from typing import Dict

logging.basicConfig()
logger = logging.getLogger("bmad.generator")
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]
IMAGE_CACHE = BASE_DIR / "cache" / "images"
IMAGE_CACHE.mkdir(parents=True, exist_ok=True)


def _image_hash_for(text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{h}.jpg"


async def remote_generate_image(prompt: str, options: Dict) -> bytes:
    """Generate image bytes using configured provider. Options may include:
    { provider: 'nebius'|'openai', api_key, model, hf_provider }
    """
    provider = options.get("provider", "nebius")
    api_key = options.get("api_key") or os.getenv("HF_TOKEN") or os.getenv("IMAGE_API_KEY")
    # If api_key still missing, try to read backend/.env manually (no python-dotenv required)
    if not api_key:
        try:
            env_path = BASE_DIR / '.env'
            if env_path.exists():
                with env_path.open('r', encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        k = k.strip(); v = v.strip().strip('"').strip("'")
                        if k == 'HF_TOKEN' or k == 'IMAGE_API_KEY':
                            api_key = v
                            break
        except Exception:
            pass
    model = options.get("model")

    # Use Hugging Face InferenceClient for text-to-image generation
    if provider == "nebius":
        try:
            from huggingface_hub import InferenceClient
            from PIL import Image
            import io
        except Exception:
            logger.exception("Required libraries for HF image generation missing; using placeholder")
            return _placeholder_image_bytes(prompt)

        # default to 'nebius' provider and FLUX model if not provided
        hf_provider = options.get("hf_provider") or "nebius"
        hf_model = model or options.get("model") or "black-forest-labs/FLUX.1-dev"

        def hf_call():
            client = InferenceClient(api_key=api_key, provider=hf_provider)
            # call once; callers may return PIL Image, bytes, base64 string, dict, etc.
            return client.text_to_image(prompt, model=hf_model)

        try:
            img_resp = await asyncio.to_thread(hf_call)
        except Exception:
            logger.exception("HF text_to_image call failed; returning placeholder image")
            return _placeholder_image_bytes(prompt)

        # Normalize response into bytes
        # If already bytes
        if isinstance(img_resp, (bytes, bytearray)):
            return bytes(img_resp)

        # If PIL Image
        try:
            from PIL import Image as PILImage
            import io as _io
            if isinstance(img_resp, PILImage.Image):
                buf = _io.BytesIO()
                img_resp.save(buf, format="JPEG")
                return buf.getvalue()
        except Exception:
            # not a PIL Image
            pass

        # If string, maybe base64
        if isinstance(img_resp, str):
            s = img_resp.strip()
            # try base64 decode
            try:
                b = base64.b64decode(s, validate=True)
                # basic sanity: must start with JPEG magic
                if b[:2] == b"\xff\xd8":
                    return b
            except Exception:
                pass

        # If dict or list, look for image bytes/base64
        if isinstance(img_resp, dict):
            # common HF fields
            for key in ("image", "images", "generated_images", "data"):
                if key in img_resp:
                    val = img_resp[key]
                    if isinstance(val, (bytes, bytearray)):
                        return bytes(val)
                    if isinstance(val, str):
                        try:
                            b = base64.b64decode(val)
                            if b[:2] == b"\xff\xd8":
                                return b
                        except Exception:
                            continue

        # Could not normalize; log and return placeholder
        logger.warning("HF response could not be converted to image bytes; type=%s", type(img_resp))
        return _placeholder_image_bytes(prompt)


    # other providers: return placeholder
    return _placeholder_image_bytes(prompt)


def _placeholder_image_bytes(prompt: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    import io
    img = Image.new("RGB", (640, 480), color=(240, 240, 240))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.load_default()
        d.text((10, 10), prompt[:200], fill=(10, 10, 10), font=f)
    except Exception:
        d.text((10, 10), prompt[:200], fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def enqueue_generation(job_id: str, item_id: str, item_text: str, options: Dict):
    # Compose prompt (if prompt provided in options use it)
    prompt = options.get("prompt") or f"Photorealistic food photography of {item_text}, plated, high detail, natural lighting, shallow depth of field, appetizing"
    img_bytes = await remote_generate_image(prompt, options)
    filename = _image_hash_for(item_text + prompt)
    path = IMAGE_CACHE / filename
    async with aiofiles.open(path, "wb") as f:
        await f.write(img_bytes)
    # update in-memory job store
    try:
        from .main import JOBS
        job = JOBS.get(job_id)
        if job:
            job.setdefault("results", {})[item_id] = filename
            for it in job.get("items", []):
                if it["id"] == item_id:
                    it["status"] = "done"
            if all(it.get("status") == "done" for it in job.get("items", [])):
                job["status"] = "completed"
    except Exception:
        pass


def get_job_status(job_id: str, JOBS: dict):
    return JOBS.get(job_id)
