from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
import uuid
import shutil
import asyncio
from dotenv import load_dotenv
from .ocr import ocr_from_image
from .parser import parse_lines
from .generator import enqueue_generation, get_job_status, remote_generate_image
import aiofiles
from .extractor import extract_items
from .llm_parser import parse_with_llm, parse_and_describe

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_CACHE = BASE_DIR / "cache" / "images"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_CACHE.mkdir(parents=True, exist_ok=True)

# Load .env for local development (explicitly load `backend/.env` so HF_TOKEN is available)
load_dotenv(dotenv_path=BASE_DIR / '.env')

app = FastAPI(title="Menu AI Backend")

# Simple in-memory stores (for prototype)
JOBS = {}

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    temp_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{temp_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run OCR (sync) — keep it simple for prototype
    lines = ocr_from_image(str(dest))
    candidates = parse_lines(lines)
    return JSONResponse({"job_text_id": temp_id, "candidates": candidates})

@app.post("/api/confirm")
async def confirm_items(payload: dict, background_tasks: BackgroundTasks):
    # payload: { "job_text_id": "...", "items": [{"id": "...", "text": "..."}], "options": {...} }
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "items": [], "results": {}}
    items = payload.get("items", [])
    options = payload.get("options", {})
    # enqueue generation tasks
    for item in items:
        item_id = item.get("id") or str(uuid.uuid4())
        text = item.get("text")
        JOBS[job_id]["items"].append({"id": item_id, "text": text, "status": "pending"})
        background_tasks.add_task(enqueue_generation, job_id, item_id, text, options)
    JOBS[job_id]["status"] = "running"
    return {"job_id": job_id}


@app.post("/api/extract_items")
async def api_extract_items(payload: dict):
    """Accepts { lines: ["..."] } and returns cleaned item candidates."""
    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise HTTPException(status_code=400, detail="`lines` must be a list of strings")
    candidates = extract_items(lines)
    return {"candidates": candidates}


@app.post("/api/clean_items")
async def api_clean_items(payload: dict):
    """Clean OCR lines into item names. Options: { use_llm: bool, api_key: str, model: str }

    If use_llm is true, requires `api_key` (or fallback to server env key).
    """
    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise HTTPException(status_code=400, detail="`lines` must be a list of strings")
    # merge with sensible defaults (allow frontend to omit provider/model/api keys)
    options = payload.get("options", {}) or {}
    import os
    server_hf = os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_API_KEY') or os.getenv('HUGGINGFACE_TOKEN')
    server_openai = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_APIKEY')
    defaults = {
        'use_llm': False,
        'api_key': server_hf or server_openai,
        'provider': 'huggingface',
        'model': 'openai/gpt-oss-20b',
    }
    # merged options: incoming options override defaults
    merged_options = {**defaults, **options}
    options = merged_options
    use_llm = bool(options.get("use_llm"))
    api_key = options.get("api_key")
    model = options.get("model")
    provider = options.get("provider")

    include_descriptions = bool(options.get('include_descriptions'))
    if use_llm:
        # allow server env variable fallback; check common env names for OpenAI/HuggingFace
        import os

        server_key = (
            os.getenv("IMAGE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("OPENAI_APIKEY")
            or os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGINGFACE_TOKEN")
        )
        key = api_key or server_key
        if not key:
            raise HTTPException(status_code=400, detail="LLM parsing requested but no API key provided on server or in request")
        try:
            if include_descriptions:
                objs = await parse_and_describe(lines, key, model=model, provider=provider)
                return {"candidates": [{"id": str(i), "name": o.get('name',''), 'description': o.get('description',''), 'prompt': o.get('prompt','')} for i, o in enumerate(objs)]}
            items = await parse_with_llm(lines, key, model=model, provider=provider)
            return {"candidates": [{"id": str(i), "name": n} for i, n in enumerate(items)]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM parsing failed: {e}")

    # fallback to heuristic extractor
    candidates = extract_items(lines)
    return {"candidates": candidates}

@app.get("/api/job/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # attach image URLs where available
    base_url = "/api/image/"
    results = {}
    for it in job.get("items", []):
        item_id = it["id"]
        res = job.get("results", {}).get(item_id)
        if res:
            results[item_id] = {"status": "ready", "image": base_url + res}
        else:
            results[item_id] = {"status": it.get("status", "pending")}
    return {"job_id": job_id, "status": job.get("status"), "items": results}

@app.post("/api/regenerate/{job_id}/{item_id}")
async def regenerate(job_id: str, item_id: str, background_tasks: BackgroundTasks, payload: dict = {}):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # find item
    item = next((i for i in job.get("items", []) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item_text = payload.get("text") or item.get("text")
    item["status"] = "pending"
    background_tasks.add_task(enqueue_generation, job_id, item_id, item_text, payload.get("options", {}))
    return {"ok": True}


@app.post("/api/generate_images")
async def generate_images(payload: dict):
    """Generate images immediately for given items. Body: { items: [{id, text}], options: {...} }

    Returns: { results: { item_id: image_url_or_error } }
    """
    items = payload.get("items")
    options = payload.get("options", {}) or {}
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="`items` must be a list")

    # server env fallbacks
    import os as _os
    server_hf = _os.getenv('HF_TOKEN') or _os.getenv('HUGGINGFACE_API_KEY') or _os.getenv('HUGGINGFACE_TOKEN')
    server_openai = _os.getenv('OPENAI_API_KEY') or _os.getenv('OPENAI_APIKEY')

    # LLM options (support both generic and llm-prefixed keys)
    use_llm = bool(options.get('use_llm') or options.get('llm_use'))
    llm_api_key = options.get('api_key') or options.get('llm_api_key') or server_hf or server_openai
    llm_provider = options.get('provider') or options.get('llm_provider') or 'huggingface'
    llm_model = options.get('model') or options.get('llm_model')

    # Image generation options (support image-prefixed and generic keys)
    image_provider = options.get('image_provider') or options.get('provider') or 'nebius'
    image_api_key = options.get('image_api_key') or options.get('image_key') or server_hf or server_openai
    image_model = options.get('image_model') or options.get('image_model') or 'black-forest-labs/FLUX.1-dev'
    hf_provider = options.get('hf_provider') or options.get('image_hf_provider') or 'nebius'

    names = [it.get("text") or it.get("name") for it in items]
    prompts = {}
    if use_llm:
        if not llm_api_key:
            raise HTTPException(status_code=400, detail="LLM api_key required for use_llm (set server env or include in options)")
        try:
            descr = await parse_and_describe(names, llm_api_key, model=llm_model or 'google/flan-t5-base', provider=llm_provider)
            for d in descr:
                prompts[d['name']] = d.get('prompt')
        except Exception:
            for n in names:
                prompts[n] = f"Photorealistic food photography of {n}, plated, high detail, natural lighting, shallow depth of field, appetizing"
    else:
        for n in names:
            prompts[n] = f"Photorealistic food photography of {n}, plated, high detail, natural lighting, shallow depth of field, appetizing"

    results = {}
    # generate synchronously for prototype
    for it in items:
        item_id = it.get('id') or str(hash(it.get('text')))
        name = it.get('text') or it.get('name')
        prompt = it.get('prompt') or options.get('prompt') or prompts.get(name)
        gen_opts = {
            'provider': image_provider,
            'api_key': image_api_key,
            'model': image_model,
            'hf_provider': hf_provider,
        }
        try:
            img_bytes = await remote_generate_image(prompt, gen_opts)
            # save
            import hashlib
            h = hashlib.sha256((name + prompt).encode('utf-8')).hexdigest()
            filename = f"{h}.jpg"
            path = IMAGE_CACHE / filename
            async with aiofiles.open(path, 'wb') as f:
                await f.write(img_bytes)
            results[item_id] = {'status': 'ok', 'image': '/api/image/' + filename}
        except Exception as e:
            results[item_id] = {'status': 'error', 'error': str(e)}

    return {'results': results}

@app.get("/api/image/{image_hash}")
async def serve_image(image_hash: str):
    # serve cached images
    path = IMAGE_CACHE / image_hash
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
