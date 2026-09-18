import os
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
    return {"status": "ok", "message": "Backend Live"}

@app.post("/generate")
async def generate_video(
    aspect_ratio: str = Form("9:16"),
    image_mode: str = Form("stock_cartoon"),
    voice: str = Form("ta-IN-PallaviNeural"),
    script: str = Form(None),
    stock_image_url: str = Form(None),
    user_image: UploadFile = File(None),
    user_audio: UploadFile = File(None)
):
    try:
        img_path = os.path.join(WORKSPACE, "avatar.png")
        audio_path = os.path.join(WORKSPACE, "speech.mp3")
        final_video = os.path.join(WORKSPACE, "output.mp4")

        # 1. Avatar selection
        if image_mode == "upload" and user_image:
            with open(img_path, "wb") as f:
                f.write(await user_image.read())
        elif image_mode == "stock_cartoon" and stock_image_url:
            resp = requests.get(stock_image_url, timeout=10)
            with open(img_path, "wb") as f:
                f.write(resp.content)
        else:
            default_url = "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png"
            resp = requests.get(default_url, timeout=10)
            with open(img_path, "wb") as f:
                f.write(resp.content)

        # 2. Audio Generation
        if user_audio:
            with open(audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            text = script.strip() if (script and script.strip()) else "வணக்கம்"
            clean_text = text.replace('"', '\\"').replace("'", "")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        # 3. High-Speed Encoding: 720p at 1 fps encoded with ultrafast preset
        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
        ffmpeg_cmd = [
            FFMPEG_EXE, "-y",
            "-loop", "1", "-framerate", "1", "-i", img_path,
            "-i", audio_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-b:a", "96k",
            "-movflags", "+faststart",
            "-shortest",
            final_video
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        return FileResponse(final_video, media_type="video/mp4", filename="ai_video.mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
