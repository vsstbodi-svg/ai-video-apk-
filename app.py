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
from gradio_client import Client, handle_file

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
    return {"status": "ok", "message": "High-Speed AI Video Backend Live"}

def get_audio_duration(audio_file: str) -> float:
    cmd = [FFMPEG_EXE, "-i", audio_file]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    matches = re.findall(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if matches:
        h, m, s = matches[0]
        return float(h) * 3600 + float(m) * 60 + float(s)
    return 8.0

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

        # 1. Avatar Source
        if image_mode == "upload" and user_image:
            with open(avatar_path, "wb") as f:
                f.write(await user_image.read())
        elif stock_image_url:
            resp = requests.get(stock_image_url, timeout=10)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)
        else:
            default_url = "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png"
            resp = requests.get(default_url, timeout=10)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)

        # 2. Fast Speech Synthesis (Edge-TTS)
        text = script.strip() if (script and script.strip()) else "வணக்கம்"
        if user_audio:
            with open(audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            clean_text = text.replace('"', '\\"').replace("'", "")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        # 3. Generate 1 Relevant Scene Background via Pollinations (Fast)
        bg_prompt = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)[:90].strip()
        if not bg_prompt:
            bg_prompt = "cinematic colorful temple landscape digital art"
        encoded = urllib.parse.quote(f"{bg_prompt}, cinematic landscape, vertical, 4k concept art")
        poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&nologo=true"
        
        try:
            r = requests.get(poll_url, timeout=12)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(bg_path, "wb") as f:
                    f.write(r.content)
            else:
                shutil.copy(avatar_path, bg_path)
        except Exception:
            shutil.copy(avatar_path, bg_path)

        # 4. Optional Remote Lip-Sync (with tight 15s budget)
        talking_avatar = os.path.join(run_dir, "talking.mp4")
        has_lip_sync = False
        try:
            client = Client("John6666/SadTalker")
            job = client.submit(
                source_image=handle_file(avatar_path),
                driven_audio=handle_file(audio_path),
                preprocess="crop",
                still_mode=True,
                use_enhancer=False,
                batch_size=1,
                size=256,
                pose_style=0,
                facerender="facevid2vid",
                exp_weight=1.0,
                use_ref_video=False,
                ref_video=None,
                ref_info="pose",
                use_idle_mode=False,
                length_of_audio=0,
                use_blink=True,
                result_dir="./results",
                api_name="/test"
            )
            raw = job.result(timeout=15)
            res_file = raw[0] if isinstance(raw, (list, tuple)) else raw
            if res_file and os.path.exists(res_file):
                shutil.copy(res_file, talking_avatar)
                has_lip_sync = True
        except Exception:
            has_lip_sync = False

        # 5. Fast Ultrafast FFmpeg Assembly
        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)

        if has_lip_sync:
            # Composite background with the talking presenter
            cmd = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-i", bg_path,
                "-i", talking_avatar,
                "-filter_complex",
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg];"
                f"[1:v]scale=280:280[avatar];"
                f"[bg][avatar]overlay=W-w-30:H-h-50",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "copy",
                "-shortest",
                final_video_path
            ]
        else:
            # High-speed static animated picture-in-picture
            cmd = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-i", bg_path,
                "-loop", "1", "-i", avatar_path,
                "-i", audio_path,
                "-filter_complex",
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg];"
                f"[1:v]scale=260:260[avatar];"
                f"[bg][avatar]overlay=W-w-30:H-h-50",
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
    
