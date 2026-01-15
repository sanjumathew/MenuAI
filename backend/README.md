MenuAI — Backend (FastAPI)

Quick start (dev):

1. Create and activate a virtualenv

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Ensure Tesseract is installed and on PATH, or set `TESSERACT_CMD` in a `.env` file.

Installing Tesseract (Windows)

-   Download the Windows installer from: https://github.com/tesseract-ocr/tesseract/wiki
-   Install and make sure the `tesseract.exe` location (e.g. `C:\Program Files\Tesseract-OCR`) is added to your system `PATH`.
-   Alternatively create a `.env` next to `backend/requirements.txt` with:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
IMAGE_API_KEY=<Image generation API key if Hugging Face Token is not provided>
HF_TOKEN=<Hugging Face Token>
```

On success, restart the backend and try uploading an image again.

3. Run the app:

**Option A:** From the `backend` folder:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

**Option B:** From the root directory (if `.venv` is already activated):

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

The `--reload` flag enables auto-restart on file changes. Access the API at `http://127.0.0.1:8000` and interactive docs at `http://127.0.0.1:8000/docs`.

Notes

-   This is a lightweight scaffold for local development. The image generation call in `app/generator.py` is stubbed; replace `remote_generate_image` with actual API integration.
-   Cached images are stored under `cache/images/`.
