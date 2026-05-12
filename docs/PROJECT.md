# 🧠 NeuroAI Transcribe - Project Documentation

NeuroAI Transcribe is a specialized transcription and diarization system designed for clinical interviews and ASD (Autism Spectrum Disorder) research. It utilizes advanced AI models (Whisper, BiLSTM, LLMs) to provide high-quality transcripts with speaker identification, specifically optimized for multi-speaker environments and long-form recordings.

---

## 🏗️ System Architecture

The project is divided into distinct domains, ensuring a clear separation of concerns between user interface, business logic, AI processing, data management, and research scripts.

### 1. **Core (AI Engine)**
- **Location**: `core/`
- **Role**: The "brain" of the transcription system. It handles GPU-intensive tasks.
- **Key Modules**:
    - `run_pipeline.py` / `overall_pipeline.py`: The main entry points for the transcription process.
    - `split.py`: Intelligent audio splitting based on silence detection (`SmartAudioSplitter`).
    - `pipeline/`: Phase 2 logic (Whisper ASR, Diarization, and Alignment).
    - `stitching/` & `flagging/`: Post-processing logic for rule-based merging of segments and detecting anomalies via LLMs.
- **Service**: Runs as a separate process (or background worker) to isolate heavy computation from the main API. It is deliberately kept out of the default backend Docker image to maintain a lightweight API.

### 2. **Backend (API Service)**
- **Location**: `backend/`
- **Role**: Manages the application state, project metadata, and file uploads.
- **Technology**: FastAPI, Uvicorn.
- **Service**: Port 8001. Triggers the Core pipeline via a subprocess when a new video is uploaded. 

### 3. **Frontend (User Interface)**
- **Location**: `frontend/`
- **Role**: A React-based Single Page Application (SPA) for researchers to upload videos, monitor pipeline progress, inspect EDA features, and edit/verify final transcripts.
- **Technology**: Vite, React, TypeScript, TailwindCSS.
- **Service**: Port 5173 (Local Dev) / Port 80 (Docker Nginx which reverse proxies to `/api` and `/static`).

### 4. **Shared (Utilities)**
- **Location**: `shared/`
- **Role**: Common logic shared between `backend` and `core`.
- **Key Component**: `file_manager.py` - Standardizes path generation, temporary chunk combination, and JSON storage across the entire system.

### 5. **Scripts & Research Tools**
- **Location**: `scripts/`
- **Role**: A comprehensive suite of specialized scripts for pipeline execution, data migration, evaluation, and experimental analysis.
- **Key Submodules**:
    - `aaiml_paper/`: Paper evaluation metrics (WER, ROUGE, SN Ratio) and agent analysis tools.
    - `agent/`: Flagging and stitching logic prototypes (`flag.py`, `stitch.py`).
    - `alignment/`: Pipeline logic for text and diarization alignment.
    - `coarse_split/`: Audio splitting utilities (`split.py`, `lenth_addup.py`).
    - `core/`: Core inference wrappers (`transcribe.py`, `diarization.py`, `whisper_one_chunk.py`, `whisper_reinfer.py`).
    - `data/`: Data management utilities (migration to flat structures, anonymization, mapping, and batch processing).
    - `eda/`: Exploratory Data Analysis tools (advanced acoustic and clinical features analysis) and report generation (`analyze_eda.py`, `individuals_eda.py`, etc.).
    - `evaluate/`: General evaluation and audit tools (`audit.py`, `compare_cases.py`, `insights.py`).
    - `model/`: Scripts for testing and analyzing speaker models (BiLSTM diarization, checkpoint analysis).
    - `tests/`: System and integration tests (GPU loading, API integration, overall pipeline tests).
    - `tools/`: Miscellaneous utilities (e.g., HF model setup, Traditional Chinese conversion).

---

## 🔄 The Transcription Pipeline (4 Phases)

The system follows a structured pipeline to transform raw video/audio into a refined transcript.

1.  **Phase 1: Smart Splitting** (`core/split.py`)
    - The original audio is split into multiple chunks to allow for parallel processing or to fit within memory constraints.
    - It intelligently finds silence or low-energy points to avoid cutting in the middle of a sentence.

2.  **Phase 2: ASR, Diarization & Alignment** (`core/pipeline/phase2.py` / `scripts/core/whisper_one_chunk.py`)
    - **Whisper ASR**: Converts speech to text (Traditional Chinese via OpenCC).
    - **Diarization**: Identifies "who spoke when" using `whisper_bilstm` (default) or `pyannote`.
    - **Alignment**: Merges Whisper segments with Diarization timestamps using a voting logic to assign the most likely speaker to each text segment.

3.  **Phase 3: Rule-based Stitching** (`core/stitching/`)
    - **Logic**: Segments from the same speaker with a gap $\le$ 1.5 seconds are merged into a single block. This ensures 100% data retention without the risk of LLM hallucinations.

4.  **Phase 4: Anomaly Detection (Flagging)** (`core/flagging/`)
    - Uses an LLM (Gemma/GPT-4 compatible) to analyze the merged segments.
    - Flags potential errors, identifies speaker intent, or suggests corrections without modifying the original text (preserving the "Ground Truth").

---

## 📂 Data & Case Management

The system uses a **Flat Directory Structure** for simplicity and reliability.

```text
data/
└── <case_name>/
    ├── source/         # Original video/audio file (.mp4, .wav)
    ├── intermediate/   # Per-chunk JSONs (whisper, diar, aligned, stitched, flagged)
    ├── output/         # Final combined transcript.json
    ├── case.json       # Metadata (creation date, original filename)
    └── status.json     # Real-time pipeline progress
```

---

## 📊 Evaluation, EDA & Research

Empirical evaluation and clinical insight extraction are core goals:

- **EDA (Exploratory Data Analysis)**: The `scripts/eda/` module automatically extracts acoustic features (SNR, dynamic range) and clinical interaction features (speech ratio, fragmentation ratio, pitch variance, energy bursts). Results are outputted as CSVs and visualization plots.
- **Metrics**: The `scripts/evaluate/` module tracks **CER (Character Error Rate)**, **Deletion/Insertion/Substitution** counts, and **Segment Retention Rate**.
- **Audit Tool**: Provides automated summaries comparing the pipeline output against human-edited Ground Truth to highlight data loss or misidentification.

---

## 🛠️ Setup & Deployment

- **Environment**: Managed via `.env` for API keys (HF, LLM), model paths, and diarization backend selection (`DIARIZATION_BACKEND`).
- **Docker**: Preferred deployment method for the Web stack using `docker-compose.yml`. Note that the `core` AI engine is excluded from the default backend image to keep it lightweight.
- **Local AI Execution**: `PYTHONPATH="$(pwd)" python -m core.run_pipeline <video_path> --case <name>` is used to manually run the heavy AI workloads locally on GPU-enabled machines.

---

## 📈 Recent Progress & Roadmap

- ✅ **Exploratory Data Analysis (EDA)**: Implemented an advanced acoustic and clinical feature analysis pipeline for individual and batch case reviews.
- ✅ **UI Enhancements**: Added exact time interval checkboxes for individuals, resolved video upload size limits, and improved real-time segment transcription.
- ✅ **System Reliability**: Fixed local data synchronization bugs to prevent frontend cascading deletion issues, and resolved re-inference time discrepancies.
- ✅ **Deployment Improvements**: Finalized core-container environment tests on workstations for scalable AI pipeline execution.
- 🚧 **Continuous Evaluation**: Refining the BiLSTM speaker model and integrating deeper LLM insights for precise ASD child/therapist distinction.