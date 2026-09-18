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
    return {"status": "ok", "message": "Cinematic AI Video Backend Live"}

def get_audio_duration(audio_file: str) -> float:
    cmd = [
        FFMPEG_EXE, "-i", audio_file
    ]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    matches = re.findall(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if matches:
        h, m, s = matches[0]
        return float(h) * 3600 + float(m) * 60 + float(s)
    return 10.0

def split_into_scenes(text: str, max_scenes: int = 4):
    """Splits script into distinct narrative scenes."""
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', text) if len(s.strip()) > 5]
    if not sentences:
        return [text]
    if len(sentences) <= max_scenes:
        return sentences
    step = len(sentences) / max_scenes
    scenes = []
    for i in range(max_scenes):
        start = int(i * step)
        end = int((i + 1) * step) if i < max_scenes - 1 else len(sentences)
        chunk = ". ".join(sentences[start:end])
        if chunk:
            scenes.append(chunk)
    return scenes

def generate_ai_scene_image(prompt_text: str, scene_idx: int, output_path: str):
    """Generates 8K cinematic background matching the scene content."""
    clean_prompt = re.sub(r'[^a-zA-Z0-9\s]', ' ', prompt_text)[:120]
    full_prompt = f"cinematic 3d animation, {clean_prompt}, colorful detailed environment, vibrant unreal engine 5, 8k vertical concept art"
    encoded = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&nologo=true&seed={scene_idx + int(time.time())}"
    resp = requests.get(url, timeout=25)
    with open(output_path, "wb") as f:
        f.write(resp.content)

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
        full_audio_path = os.path.join(run_dir, "full_audio.mp3")
        final_video_path = os.path.join(run_dir, "final_video.mp4")

        # 1. Source Avatar
        if image_mode == "upload" and user_image:
            with open(avatar_path, "wb") as f:
                f.write(await user_image.read())
        elif stock_image_url:
            resp = requests.get(stock_image_url, timeout=15)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)
        else:
            default_url = "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png"
            resp = requests.get(default_url, timeout=15)
            with open(avatar_path, "wb") as f:
                f.write(resp.content)

        # 2. Generate Narration Audio
        text = script.strip() if (script and script.strip()) else "வணக்கம்"
        if user_audio:
            with open(full_audio_path, "wb") as f:
                f.write(await user_audio.read())
        else:
            clean_text = text.replace('"', '\\"').replace("'", "")
            tts_cmd = f'edge-tts --voice {voice} --text "{clean_text}" --write-media "{full_audio_path}"'
            subprocess.run(tts_cmd, shell=True, check=True)

        total_duration = get_audio_duration(full_audio_path)

        # 3. Create Scene Backgrounds
        scenes = split_into_scenes(text, max_scenes=4)
        scene_duration = total_duration / len(scenes)
        scene_video_files = []

        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)

        for i, sc_text in enumerate(scenes):
            bg_img = os.path.join(run_dir, f"bg_{i}.png")
            sc_clip = os.path.join(run_dir, f"clip_{i}.mp4")

            try:
                generate_ai_scene_image(sc_text, i, bg_img)
            except Exception:
                shutil.copy(avatar_path, bg_img)

            # Ken Burns cinematic slow pan/zoom effect
            bg_cmd = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-t", str(scene_duration),
                "-i", bg_img,
                "-vf", f"scale=1080:1920,zoompan=z='min(zoom+0.0015,1.2)':d={int(scene_duration*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-r", "25",
                sc_clip
            ]
            subprocess.run(bg_cmd, check=True)
            scene_video_files.append(sc_clip)

        # Concatenate background scene clips
        concat_txt = os.path.join(run_dir, "concat.txt")
        with open(concat_txt, "w") as f:
            for sc in scene_video_files:
                f.write(f"file '{sc}'\n")

        bg_stitched = os.path.join(run_dir, "bg_stitched.mp4")
        subprocess.run([
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt, "-c", "copy", bg_stitched
        ], check=True)

        # 4. Generate Talking Avatar via Lip-Sync
        talking_avatar = os.path.join(run_dir, "avatar_talk.mp4")
        lip_synced = False
        try:
            client = Client("John6666/SadTalker")
            job = client.submit(
                source_image=handle_file(avatar_path),
                driven_audio=handle_file(full_audio_path),
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
            raw_result = job.result(timeout=75)
            res_file = raw_result[0] if isinstance(raw_result, (list, tuple)) else raw_result
            if res_file and os.path.exists(res_file):
                shutil.copy(res_file, talking_avatar)
                lip_synced = True
        except Exception:
            lip_synced = False

        # 5. Composite Background + Picture-in-Picture Presenter + Audio
        if lip_synced:
            # Overlay lip-synced presenter in lower right circle
            overlay_cmd = [
                FFMPEG_EXE, "-y",
                "-i", bg_stitched,
                "-i", talking_avatar,
                "-filter_complex",
                "[1:v]scale=260:260,format=yuva420p[pip];[0:v][pip]overlay=W-w-30:H-h-50",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                final_video_path
            ]
            subprocess.run(overlay_cmd, check=True)
        else:
            # Direct merge background with voice audio
            merge_cmd = [
                FFMPEG_EXE, "-y",
                "-i", bg_stitched,
                "-i", full_audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                final_video_path
            ]
            subprocess.run(merge_cmd, check=True)

        return FileResponse(final_video_path, media_type="video/mp4", filename="cinematic_ai_video.mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
