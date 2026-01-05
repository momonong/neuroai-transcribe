# NeuroAI Clinical Transcription System

A comprehensive AI-powered clinical audio transcription and annotation system designed for ASD (Autism Spectrum Disorder) diagnostic interviews. The system combines advanced speech recognition, speaker diarization, and intelligent post-processing to create accurate, reviewable transcripts for clinical use.

## 🏗️ Architecture Overview

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   AI Pipeline   │
│   (React/TS)    │◄──►│   (FastAPI)     │◄──►│   (Whisper +    │
│                 │    │                 │    │    Pyannote)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Interface │    │   REST API      │    │   GPU Models    │
│   - Video Player│    │   - File Mgmt   │    │   - Whisper     │
│   - Text Editor │    │   - Processing  │    │   - Pyannote    │
│   - Annotation  │    │   - Validation  │    │   - LLM (Gemma) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Hardware**: NVIDIA GPU (RTX 3060+ recommended)
- **Software**: Docker, Docker Compose, Python 3.9+, Node.js 18+
- **Models**: Hugging Face account with access to Pyannote models

### Environment Setup

1. **Clone and configure environment**:
```bash
git clone <repository-url>
cd neuroai-transcription
cp .env.example .env
```

2. **Configure `.env` file**:
```env
# Model Configuration
MODEL_CACHE_DIR=D:/hf_models  # Adjust to your model storage path
HF_TOKEN=your_huggingface_token_here

# Docker Configuration
HOST_LLM_PORT=8000
HOST_BACKEND_PORT=8001
```

3. **Start the system**:
```bash
# Start all services
docker-compose up -d

# Or start individual services
docker-compose up llm-server    # LLM server only
docker-compose up backend       # Backend API only
```

### Manual Setup (Development)

**Backend Setup**:
```bash
cd backend
pip install -r requirements.txt
python main.py  # Starts on port 8001
```

**Frontend Setup**:
```bash
cd frontend
npm install
npm run dev     # Starts on port 5173
```

## 📁 Project Structure

### Backend Architecture (`/backend`)

```
backend/
├── main.py                 # FastAPI application entry point
├── app.py                  # Streamlit annotation interface
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container configuration
├── core/                  # Core AI processing modules
│   ├── ai_engine.py       # Main pipeline orchestrator
│   ├── pipeline.py        # Whisper + Pyannote processing
│   ├── split.py           # Audio segmentation
│   ├── stitch.py          # Sentence reconstruction
│   └── flag.py            # Quality assurance & flagging
├── scripts/               # Processing scripts
│   ├── transcribe.py      # Standalone transcription
│   ├── diarization.py     # Speaker identification
│   └── agent/             # AI agent modules
└── tests/                 # Unit and integration tests
```

### Frontend Architecture (`/frontend`)

```
frontend/
├── src/
│   ├── App.tsx            # Main React application
│   ├── main.tsx           # Application entry point
│   ├── App.css            # Styling
│   └── assets/            # Static resources
├── package.json           # Node.js dependencies
├── vite.config.ts         # Vite build configuration
├── tsconfig.json          # TypeScript configuration
└── public/                # Public assets
```

## 🔧 Core Features

### AI Processing Pipeline

1. **Audio Splitting** (`core/split.py`)
   - Intelligent audio segmentation
   - Configurable chunk sizes
   - Metadata preservation

2. **Speech Recognition** (`core/pipeline.py`)
   - Whisper large-v3 model
   - Chinese language optimization
   - Word-level timestamps

3. **Speaker Diarization** (`core/pipeline.py`)
   - Pyannote 3.1 speaker identification
   - Multi-speaker conversation handling
   - Speaker embedding analysis

4. **Intelligent Alignment** (`core/pipeline.py`)
   - Text-to-speaker mapping
   - Temporal overlap resolution
   - Confidence scoring

5. **Post-Processing** (`core/stitch.py`, `core/flag.py`)
   - Sentence reconstruction
   - Quality assurance flagging
   - Anomaly detection

### Web Interface Features

- **Real-time Video Synchronization**: Frame-accurate playback control
- **Interactive Text Editing**: Live transcript modification
- **Speaker Management**: Dynamic speaker identification and renaming
- **Quality Review**: Flagged segments for human verification
- **Export Capabilities**: Multiple output formats for clinical use

## 🛠️ API Endpoints

### Core API Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/temp/chunks` | List available transcript chunks |
| `GET` | `/api/temp/chunk/{filename}` | Retrieve specific chunk data |
| `POST` | `/api/temp/save` | Save edited transcript |
| `GET` | `/api/videos` | List available video files |

### Data Flow

```
Audio/Video Input → Splitting → Whisper → Pyannote → Alignment → Stitching → Flagging → Human Review
```

## 🔬 Clinical Use Case

### ASD Diagnostic Interview Processing

The system is specifically designed for processing clinical conversations between:
- **Clinicians** (醫師): Medical professionals conducting assessments
- **Parents/Caregivers** (家長): Providing developmental history
- **Children** (兒童): Direct interaction and behavioral observation

### Key Clinical Features

- **Medical Terminology Recognition**: Optimized for clinical vocabulary
- **Behavioral Annotation**: Flags for attention, social interaction patterns
- **Compliance Standards**: HIPAA-compliant local processing
- **Quality Assurance**: Multi-level review system for accuracy

## 🚀 Development

### Adding New Features

1. **Backend Extensions**: Add new processing modules in `/backend/core/`
2. **Frontend Components**: Extend React components in `/frontend/src/`
3. **API Routes**: Add endpoints in `/backend/main.py`

### Testing

```bash
# Backend tests
cd backend
python -m pytest tests/

# Frontend tests
cd frontend
npm test
```

### Performance Optimization

- **GPU Memory Management**: Automatic VRAM cleanup between processing stages
- **Batch Processing**: Configurable chunk sizes for large files
- **Caching**: Model caching for faster subsequent runs

## 📊 System Requirements

### Minimum Requirements
- **GPU**: NVIDIA GTX 1660 (6GB VRAM)
- **RAM**: 16GB system memory
- **Storage**: 50GB for models and data
- **CPU**: 8-core processor

### Recommended Requirements
- **GPU**: NVIDIA RTX 4070+ (12GB+ VRAM)
- **RAM**: 32GB system memory
- **Storage**: 100GB NVMe SSD
- **CPU**: 12+ core processor

## 🔒 Security & Privacy

- **Local Processing**: All audio processing occurs locally
- **No Cloud Dependencies**: Complete offline operation capability
- **Data Encryption**: Optional encryption for sensitive clinical data
- **Access Control**: Role-based access for clinical teams

## 📝 License

This project is designed for clinical research and diagnostic applications. Please ensure compliance with local healthcare data regulations.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit a pull request

## 📞 Support

For technical support or clinical implementation questions, please refer to the documentation or create an issue in the repository.

---

**Note**: This system requires appropriate clinical validation and should be used as a supportive tool in conjunction with professional medical judgment.