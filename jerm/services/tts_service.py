import os
import requests
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "jvcMcno3QtjOzGtfpjoI"

def generate_speech_stream(text: str):
    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY is not set in the environment.")
        
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {
        "Accept": "audio/mpeg",
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    response = requests.post(url, json=data, headers=headers, stream=True)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=f"ElevenLabs TTS failed: {response.text}")
    
    return response.iter_content(chunk_size=1024)
