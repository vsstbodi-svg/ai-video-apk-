import os
import gc
import re
import time
import subprocess
import requests
import imageio_ffmpeg
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

@app.get("/")
def health():
    return {"status": "ok", "message": "Ultra-Fast AI Video Backend Live"}

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
    try:
        # Clean workspace to prevent RAM/disk buildup
        req_id = int(time.time() * 1000)
        avatar_path = os.path.join(WORKSPACE, f"av_{req_id}.png")
        audio_path = os.path.join(WORKSPACE, f"au_{req_id}.mp3")
        final_video_path = os.path.join(WORKSPACE, f"out_{req_id}.mp4")

        # 1. Avatar Source
        if image_mode == "upload" and user_image:
            with open(avatar_path, "wb") as f:
                f.write(await user_image.read())
        elif stock_image_url:
            try:
                resp = requests.get(stock_image_url, timeout=5)
                with open(avatar_path, "wb") as f:
                    f.write(resp.content)
            except Exception:
                pass

        if not os.path.exists(avatar_path) or os.path.getsize(avatar_path) == 0:
            resp = requests.get("https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png", timeout=5)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)

        # 2. Audio Generation (Edge-TTS)
        text = script.strip() if (script and script.strip()) else "வணக்கம்"
        if user_audio:
            with open(audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        # 3. Standard Mobile Dimensions (480x854 uses 70% less RAM than 1080p)
        w, h = (480, 854) if aspect_ratio == "9:16" else (854, 480)

        # 4. Ultra Low-Memory FFmpeg Pipeline
        cmd = [
            FFMPEG_EXE, "-y",
            "-loop", "1",
            "-framerate", "1",
            "-i", avatar_path,
            "-i", audio_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "64k",
            "-movflags", "+faststart",
            "-shortest",
            final_video_path
        ]
        subprocess.run(cmd, check=True)

        # Clean memory immediately
        gc.collect()

        return FileResponse(final_video_path, media_type="video/mp4", filename="ai_video.mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
