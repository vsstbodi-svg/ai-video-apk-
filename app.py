import os
import re
import time
import shutil
import urllib.parse
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
        req_id = int(time.time() * 1000)
        run_dir = os.path.join(WORKSPACE, f"run_{req_id}")
        os.makedirs(run_dir, exist_ok=True)

        avatar_path = os.path.join(run_dir, "avatar.png")
        bg_path = os.path.join(run_dir, "bg.png")
        audio_path = os.path.join(run_dir, "audio.mp3")
        final_video_path = os.path.join(run_dir, "final_video.mp4")

        # 1. Avatar Handling
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
        
        # Fallback placeholder if avatar download fails
        if not os.path.exists(avatar_path) or os.path.getsize(avatar_path) == 0:
            resp = requests.get("https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png", timeout=5)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)

        # 2. Audio Generation via Edge-TTS
        text = script.strip() if (script and script.strip()) else "வணக்கம்"
        if user_audio:
            with open(audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            clean_text = text.replace('"', '').replace("'", "").replace("\n", " ")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        # 3. Dynamic Scene Background with strict 5s timeout
        bg_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)[:60].strip()
        if not bg_query:
            bg_query = "cinematic nature digital art"
        encoded = urllib.parse.quote(f"{bg_query}, 4k scenery")
        poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width=540&height=960&nologo=true"

        has_bg = False
        try:
            r = requests.get(poll_url, timeout=5)
            if r.status_code == 200 and len(r.content) > 2000:
                with open(bg_path, "wb") as f:
                    f.write(r.content)
                has_bg = True
        except Exception:
            has_bg = False

        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)

        # 4. Instant Ultrafast FFmpeg Encoding (Under 5 seconds)
        if has_bg:
            # Composite background with avatar in lower right
            cmd = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-i", bg_path,
                "-loop", "1", "-i", avatar_path,
                "-i", audio_path,
                "-filter_complex",
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg];"
                f"[1:v]scale=240:240[av];"
                f"[bg][av]overlay=W-w-30:H-h-50",
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-b:a", "96k",
                "-shortest",
                final_video_path
            ]
        else:
            # Full-frame avatar centered
            cmd = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-i", avatar_path,
                "-i", audio_path,
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-b:a", "96k",
                "-shortest",
                final_video_path
            ]

        subprocess.run(cmd, check=True)
        return FileResponse(final_video_path, media_type="video/mp4", filename="ai_video.mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
                
