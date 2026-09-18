import os
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
    return {"status": "ok", "message": "AI Lip-Sync Backend is Live"}

def run_local_fallback(img_path: str, audio_path: str, output_video: str, aspect_ratio: str):
    """Fallback static encoder if remote GPU is backlogged."""
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
        output_video
    ]
    subprocess.run(ffmpeg_cmd, check=True)

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
        timestamp = int(time.time() * 1000)
        img_path = os.path.join(WORKSPACE, f"avatar_{timestamp}.png")
        audio_path = os.path.join(WORKSPACE, f"audio_{timestamp}.mp3")
        final_video = os.path.join(WORKSPACE, f"final_{timestamp}.mp4")

        # 1. Image Sourcing & AI Image Generation
        if image_mode == "upload" and user_image:
            with open(img_path, "wb") as f:
                f.write(await user_image.read())
        elif image_mode == "ai_prompt" and ai_prompt:
            encoded_prompt = urllib.parse.quote(f"{ai_prompt}, professional portrait, facing camera, high resolution 8k")
            pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&nologo=true"
            resp = requests.get(pollinations_url, timeout=25)
            with open(img_path, "wb") as f:
                f.write(resp.content)
        elif image_mode == "stock_cartoon" and stock_image_url:
            resp = requests.get(stock_image_url, timeout=15)
            with open(img_path, "wb") as f:
                f.write(resp.content)
        else:
            default_url = "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png"
            resp = requests.get(default_url, timeout=15)
            with open(img_path, "wb") as f:
                f.write(resp.content)

        # 2. Audio Generation (Edge-TTS)
        if user_audio:
            with open(audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            text = script.strip() if (script and script.strip()) else "வணக்கம்"
            clean_text = text.replace('"', '\\"').replace("'", "")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        # 3. Neural Lip-Sync via Hugging Face ZeroGPU
        lip_synced = False
        try:
            client = Client("John6666/SadTalker")
            job = client.submit(
                source_image=handle_file(img_path),
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
            # Wait with a timeout
            raw_result = job.result(timeout=75)
            generated_mp4 = raw_result[0] if isinstance(raw_result, (list, tuple)) else raw_result
            if generated_mp4 and os.path.exists(generated_mp4):
                shutil.copy(generated_mp4, final_video)
                lip_synced = True
        except Exception:
            lip_synced = False

        # Fallback to local encoding if remote GPU times out or fails
        if not lip_synced:
            run_local_fallback(img_path, audio_path, final_video, aspect_ratio)

        return FileResponse(final_video, media_type="video/mp4", filename="ai_video.mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
