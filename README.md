```shell
docker run --rm -it --gpus all -p 8000:8000 -v D:/hf_models:/models ghcr.io/ggml-org/llama.cpp:server-cuda -m /models/gemma-3-12b-it-qat-q4_0-gguf/gemma-3-12b-it-q4_0.gguf -c 8192 -ngl 99 --host 0.0.0.0 --port 8000
```