# NeuroAI Transcribe

A clinical interview speech transcription and editing system for use in ASD (autism spectrum disorder) diagnostic interviews and similar settings. It combines speech recognition, speaker diarization, and post-processing to produce reviewable, editable transcripts.

## Architecture Overview

The project uses a **decoupled architecture**: the **Web interface** (frontend + backend) is separate from the **AI transcription core** (`core/`).

- **Docker images** include only the Web stack (Frontend + Backend + shared). They do not include GPU or heavy AI dependencies.
- **AI pipeline** (Whisper, Pyannote, alignment, stitch, flag) lives in the project root under `core/`. It is run in a GPU-capable environment by the lab and is **not** bundled into Docker.

```
┌─────────────────────────────────────────────────────────────────┐
│  Docker images (suitable for Docker Hub)                         │
│  ┌─────────────┐         ┌─────────────┐                         │
│  │  Frontend   │ --80--> │   Nginx     │  Static files +         │
│  │  (React)    │         │   :80       │  proxy /api, /static    │
│  └─────────────┘         └──────┬──────┘  to Backend             │
│                                 │                                 │
│                                 ▼                                 │
│  ┌─────────────┐         ┌─────────────┐   ┌──────────┐          │
│  │  Backend    │ <------ │   shared/   │   │  data/   │          │
│  │  (FastAPI)  │         │ file_manager│   │ (volume) │          │
│  └─────────────┘         └─────────────┘   └──────────┘          │
└─────────────────────────────────────────────────────────────────┘

Project root (not packaged into Docker)
  core/           # AI pipeline: split, pipeline, stitch, flag, run_pipeline
  backend/        # Backend source
  frontend/       # Frontend source
  shared/         # Path/file logic (shared with backend)
  data/           # Cases and media (mounted as volume in Docker)
```

## Quick Start

### Requirements

- Docker and Docker Compose
- (Optional) To run the AI pipeline: Python 3.10+, NVIDIA GPU, Hugging Face account and Pyannote model access

### Using Docker (recommended)

1. **Clone and enter the project**
   ```bash
   git clone <repository-url>
   cd neuroai-transcribe
   ```

2. **Build and start**
   ```bash
   docker-compose up --build -d
   ```

3. **Open the app**  
   In your browser go to **http://localhost**  
   (If the frontend port in `docker-compose.yml` is mapped as `55688:80`, use **http://localhost:55688** instead.)

### Local development

**Backend** (project root must be on `PYTHONPATH` so `shared` can be imported):
```bash
cd neuroai-transcribe
pip install -r backend/requirements.txt
# Windows PowerShell
$env:PYTHONPATH = "."
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

**Frontend**
```bash
cd frontend
npm install
npm run dev   # Dev server on port 5173; proxies /api and /static to 8001
```

**AI pipeline** (requires core dependencies; see root `requirements.txt` or `core/requirements.txt`):
```bash
# Run from project root with project root on PYTHONPATH
python -m core.run_pipeline <video_path> --case <case_name>
```

## Project Structure

```
neuroai-transcribe/
├── frontend/           # React + Vite frontend
│   ├── src/
│   ├── nginx.conf      # Production: SPA + proxy /api, /static
│   ├── Dockerfile      # Multi-stage: Node build → Nginx serves static
│   └── package.json
├── backend/            # FastAPI backend (editing API)
│   ├── main.py         # Entry point, API, static mounts
│   ├── requirements.txt
│   └── Dockerfile      # Copies only backend/ and shared/
├── shared/             # Shared layer (paths and file logic)
│   ├── __init__.py
│   └── file_manager.py # Case dirs, status, merge chunks, find_video_files
├── core/               # AI core (not in Docker image)
│   ├── config.py
│   ├── run_pipeline.py
│   ├── pipeline.py, split.py, stitch.py, flag.py, ai_engine.py, overall_pipeline.py
│   └── requirements.txt
├── data/               # Cases and media (Docker volume → /app/data)
├── docker-compose.yml # Two services: backend + frontend
├── .dockerignore       # Excludes core/, frontend/, etc. from backend build
└── README.md
```

## Features

### Web interface (available with Docker deployment)

- List and select videos by case
- Upload videos and create cases
- Read, edit, and save transcript chunks
- Progress polling (`/api/status/{case_name}`)
- Export datasets (whisper, diar, aligned, stitched, flagged, edited)
- Static video playback (`/static/`)

### AI pipeline (run in an environment that includes `core/`)

- Audio splitting (`core/split.py`)
- Whisper ASR + Pyannote diarization + alignment (`core/pipeline.py`)
- Sentence stitching and quality flagging (`core/stitch.py`, `core/flag.py`)
- One-shot pipeline: `core/run_pipeline.py` or `core/overall_pipeline.py`

## API Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/videos` | List videos (by case) |
| GET | `/api/temp/chunks` | List transcript chunks (optional `?case=`) |
| GET | `/api/temp/chunk/{filename}` | Get a single chunk |
| POST | `/api/temp/save` | Save edited transcript |
| POST | `/api/upload` | Upload video (requires `case_name`) |
| GET | `/api/status/{case_name}` | Get processing progress |
| GET | `/api/export/{case_name}/{dataset_type}` | Export dataset (e.g. edited, flagged) |
| - | `/static/` | Static files (e.g. videos) |

## Deployment and Pushing Images

- Example image names: `momonong/neuroai-backend:latest`, `momonong/neuroai-frontend:latest` (editable in `docker-compose.yml`).
- After building, push to Docker Hub:
  ```bash
  docker push momonong/neuroai-backend:latest
  docker push momonong/neuroai-frontend:latest
  ```
- For full deployment steps and offline deployment, see **`docs/INSTRUCTION.md`**.

## Clinical Use

This system is intended for transcribing and reviewing clinical interviews (e.g. clinician, parent, child). It is an assistive tool and must be used together with professional judgment. Ensure compliance with local healthcare and data protection regulations.

## License and Support

- Use in accordance with the project license and clinical research requirements.
- For technical issues, open an issue in the repository. For deployment details, see `docs/INSTRUCTION.md`.
