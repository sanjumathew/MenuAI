# MenuAI

A local-only prototype that accepts a photo of a restaurant menu, extracts item names using OCR, and displays a picture for each item next to its name.

## Overview

Menu AI is a full-stack application designed to:

-   Upload and process restaurant menu photos
-   Extract menu item names using OCR (Tesseract)
-   Generate or retrieve images for each menu item
-   Display results in an intuitive web interface
-   Allow users to edit extracted items and regenerate images

## Project Structure

```
menuai/
├── backend/          # FastAPI backend application
├── frontend/         # Frontend application (Svelte)
├── .gitignore        # Git ignore file for sensitive files and build artifacts
└── README.md         # This file
```

## Quick Start

### Prerequisites

-   Python 3.8+ (for backend)
-   Node.js 16+ (for frontend)
-   Tesseract OCR engine (required for menu text extraction)

### Setup

1. **Clone or navigate to the project directory**

```powershell
cd menuai
```

2. **Create and activate virtual environment**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

3. **Install dependencies**

```powershell
pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
```

## Running the Application

### Backend

See [backend/README.md](backend/README.md) for detailed setup and running instructions.

**Quick start:**

```powershell
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

The backend API will be available at `http://127.0.0.1:8000`

-   Interactive API docs: `http://127.0.0.1:8000/docs`

### Frontend

See [frontend/README.md](frontend/README.md) for detailed setup and running instructions.

**Quick start:**

```powershell
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Key Features

-   **Image Upload**: Upload menu photos for processing
-   **OCR Extraction**: Tesseract-based text extraction with preprocessing
-   **Item Parsing**: Intelligent menu item name extraction and normalization
-   **Image Generation**: Generate or retrieve images for menu items
-   **Interactive UI**: View results, edit items, and regenerate images
-   **Local Processing**: Runs entirely locally (with optional external API integration)

## Important Configuration

### Environment Variables

Create a `.env` file in the `backend/` folder for configuration:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
IMAGE_API_KEY=<your-api-key-if-using-external-service>
HF_TOKEN=<hugging-face-token-for-model-access>
```

See [backend/README.md](backend/README.md) for more details on Tesseract installation and configuration.

## Development Notes

-   **Cached images** are stored under `backend/cache/images/`
-   **Uploaded files** are stored under `backend/uploads/`
-   The image generation in `backend/app/generator.py` is currently stubbed; integrate with your preferred image generation API or local model
-   Sensitive files and environment variables are excluded from git (see `.gitignore`)

## Contributing

Please ensure:

-   Environment variables and secrets are in `.env` files (never commit them)
-   Follow the project structure and naming conventions
-   Update relevant README files when making changes to backend or frontend

## License

[Add your license here]

## Support

For issues or questions:

-   **Backend issues**: See [backend/README.md](backend/README.md)
-   **Frontend issues**: See [frontend/README.md](frontend/README.md)
