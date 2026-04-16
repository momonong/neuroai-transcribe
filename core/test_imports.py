import sys

def test_imports():
    print("Python executable:", sys.executable)
    
    print("\n--- Testing faster_whisper ---")
    try:
        from faster_whisper import WhisperModel as FasterWhisperModel
        print("✅ Successfully imported WhisperModel from faster_whisper")
    except Exception as e:
        print(f"❌ Failed to import from faster_whisper: {e}")

    print("\n--- Testing transformers ---")
    try:
        from transformers import WhisperModel as TransformersWhisperModel
        print("✅ Successfully imported WhisperModel from transformers")
    except Exception as e:
        print(f"❌ Failed to import from transformers: {e}")

if __name__ == "__main__":
    test_imports()
