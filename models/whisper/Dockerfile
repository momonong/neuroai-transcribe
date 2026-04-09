FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set non-interactive to avoid apt-get prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set up alias for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Create working directory
WORKDIR /app

# Copy requirements file (now reading from the same folder)
COPY requirements.txt .

# Install python packages and PyTorch with CUDA explicitly
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    pip install --no-cache-dir -r requirements.txt

# Copy all files from models/whisper/
COPY . .

# Set Python path
ENV PYTHONPATH=/app
EXPOSE 8002

# Run the server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]