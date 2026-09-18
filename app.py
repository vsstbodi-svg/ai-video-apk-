import os
import subprocess
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE = "/tmp/workspace"
os.makedirs(WORKSPACE, exist_ok=True)

@app.get("/")
def health():
    return {"status": "ok", "message": "AI Video Backend is Live"}

@app.post("/generate")
async def generate_video(
    aspect_ratio: str = Form("9:16"),
    image_mode: str = Form("stock_cartoon"),
    voice: str = Form("ta-IN-PallaviNeural"),
    script: str = Form(None),
    stock_image_url: str = Form(None),
    ai_prompt: str = Form(None),
    user_image: UploadFile = File(None),
    user_audio: UploadFile = File(None)
):
    img_path = os.path.join(WORKSPACE, "avatar.png")
    audio_path = os.path.join(WORKSPACE, "speech.mp3")
    final_video = os.path.join(WORKSPACE, "output.mp4")

    # 1. Avatar selection
    if image_mode == "stock_cartoon":
        url = stock_image_url if stock_image_url else "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png"
        resp = requests.get(url, timeout=15)
        with open(img_path, "wb") as f:
            f.write(resp.content)
    elif image_mode == "upload" and user_image:
        with open(img_path, "wb") as f:
            f.write(await user_image.read())
    else:
        resp = requests.get("https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png", timeout=15)
        with open(img_path, "wb") as f:
            f.write(resp.content)

    # 2. Audio generation
    if user_audio:
        with open(audio_path, "wb") as f:
            f.write(await user_audio.read())
    elif script:
        clean_script = script.replace('"', '\\"').replace("'", "")
        tts_cmd = f'edge-tts --voice {voice} --text "{clean_script}" --write-media {audio_path}'
        subprocess.run(tts_cmd, shell=True, check=True)
    else:
        default_text = "வணக்கம்" if "ta-" in voice else "Hello"
        tts_cmd = f'edge-tts --voice {voice} --text "{default_text}" --write-media {audio_path}'
        subprocess.run(tts_cmd, shell=True, check=True)

    # 3. Android-compatible MP4 encoding
    w, h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", img_path,
        "-i", audio_path,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        final_video
    ]
    subprocess.run(ffmpeg_cmd, check=True)

    return FileResponse(final_video, media_type="video/mp4", filename="ai_video.mp4")
  
