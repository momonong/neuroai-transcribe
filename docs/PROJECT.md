# 🧠 NeuroAI Transcribe - Project Documentation

NeuroAI Transcribe is a specialized transcription and diarization system designed for ASD (Autism Spectrum Disorder) research. It utilizes advanced AI models (Whisper, BiLSTM, LLMs) to provide high-quality transcripts with speaker identification, specifically optimized for multi-speaker environments and long-form recordings.

---

## 🏗️ System Architecture

The project is divided into four main pillars, ensuring a clear separation of concerns between user interface, business logic, AI processing, and data management.

### 1. **Core (AI Engine)**
- **Location**: `core/`
- **Role**: The "brain" of the system. It handles GPU-intensive tasks.
- **Key Modules**:
    - `run_pipeline.py`: The main entry point for the 4-phase transcription process.
    - `split.py`: Intelligent audio splitting based on silence detection.
    - `pipeline/`: Phase 2 logic (Whisper ASR, Diarization, and Alignment).
    - `stitching/` & `flagging/`: Post-processing logic for merging segments and detecting anomalies.
- **Service**: Runs as a background worker (FastAPI on port 8003) to isolate heavy computation from the main API.

### 2. **Backend (API Service)**
- **Location**: `backend/`
- **Role**: Manages the application state, user authentication, project metadata, and file uploads.
- **Technology**: FastAPI, SQLAlchemy (SQLite/PostgreSQL).
- **Service**: Port 8001. It triggers the Core service via REST API.

### 3. **Frontend (User Interface)**
- **Location**: `frontend/`
- **Role**: A React-based web interface for researchers to upload videos, monitor pipeline progress, and edit/verify final transcripts.
- **Technology**: Vite, React, TypeScript, TailwindCSS.
- **Service**: Port 5173.

### 4. **Shared (Utilities)**
- **Location**: `shared/`
- **Role**: Common logic shared between `backend` and `core`.
- **Key Component**: `file_manager.py` - Standardizes path generation and JSON storage across the entire system.

---

## 🔄 The Transcription Pipeline (4 Phases)

The system follows a structured pipeline to transform raw video/audio into a refined transcript.

1.  **Phase 1: Smart Splitting** (`core/split.py`)
    - The original audio is split into multiple chunks (default: 4) to allow for parallel processing or to fit within memory constraints.
    - It intelligently finds silence or low-energy points to avoid cutting in the middle of a sentence.

2.  **Phase 2: ASR, Diarization & Alignment** (`core/pipeline/phase2.py`)
    - **Whisper ASR**: Converts speech to text (Traditional Chinese via OpenCC).
    - **Diarization**: Identifies "who spoke when" using `whisper_bilstm` (default) or `pyannote`.
    - **Alignment**: Merges Whisper segments with Diarization timestamps using a voting logic to assign the most likely speaker to each text segment.

3.  **Phase 3: Rule-based Stitching** (`core/stitching/`)
    - **Evolution**: Shifted from LLM-based to **Rule-based** to prevent "hallucinations" and data loss.
    - **Logic**: Segments from the same speaker with a gap $\le$ 1.5 seconds are merged into a single block. This ensures 100% data retention.

4.  **Phase 4: Anomaly Detection (Flagging)** (`core/flagging/`)
    - Uses an LLM (Gemma/GPT-4 compatible) to analyze the merged segments.
    - Flags potential errors, identifies speaker intent, or suggests corrections without modifying the original text (preserving the "Ground Truth").

---

## 📂 Data & Case Management

The system uses a **Flat Directory Structure** for simplicity and reliability.

```text
data/
└── <case_name>/
    ├── source/         # Original video/audio file
    ├── intermediate/   # Per-chunk JSONs (whisper, diar, aligned, stitched, flagged)
    ├── output/         # Final combined transcript.json
    ├── case.json       # Metadata (creation date, original filename)
    └── status.json     # Real-time pipeline progress
```

---

## 📊 Evaluation & Research

One of the project's core goals is empirical evaluation.

- **Metrics**: The system tracks **CER (Character Error Rate)**, **Deletion/Insertion/Substitution** counts, and **Segment Retention Rate**.
- **Audit Tool**: `python -m core.scripts.evaluate --case <name>` generates detailed reports comparing the pipeline output against human-edited Ground Truth.
- **Insights**: `core/scripts/evaluate/insights.py` provides automated summaries of pipeline performance, highlighting where data might be lost or misidentified.

---

## 🛠️ Setup & Development

- **Environment**: Managed via `.env` for ports, API keys (HF, LLM), and model paths.
- **Docker**: Preferred deployment method using `docker-compose.yml`.
- **PYTHONPATH**: Critical for local execution; always ensure the project root is in your path.

---

## 📈 Recent Progress & Roadmap

- ✅ **Migration to Flat Structure**: Simplified file management.
- ✅ **Rule-based Stitching**: Replaced LLM stitching to eliminate 25% data loss.
- ✅ **Core/Backend Isolation**: Improved system stability during heavy inference.
- 🚧 **Continuous Evaluation**: Refining the BiLSTM speaker model for better ASD child/therapist distinction.
- 🚧 **UI Enhancement**: Improving the transcript editor's performance with large datasets.
