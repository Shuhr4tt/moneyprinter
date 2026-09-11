# ruff: noqa: E402
"""English-first, review-first Makon workspace using MoneyPrinterTurbo's engine."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.config import config
from app.makon import (
    AUDIO_EXTENSIONS, LANGUAGES, PRESETS, VISUAL_EXTENSIONS,
    build_script_direction, estimate_speech_seconds, export_pack, persist_upload,
    redact_error, trim_audio, validate_srt, write_project,
)
from app.models import const
from app.models.schema import MaterialInfo, VideoParams
from app.services import llm, state as sm, voice, webui_task
from app.utils import utils

st.set_page_config(page_title="Makon Video Studio", page_icon="🎬", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('makon.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def load_preset() -> None:
    preset = PRESETS[st.session_state.get("preset", "music_ad")]
    st.session_state.update({
        "language": preset.language, "topic": preset.topic, "script": "",
        "caption": "", "target_seconds": preset.duration, "brief": "",
        "audio_mode": "Upload a finished song / voiceover" if preset.upload_audio else "Generate a voiceover",
        "footage": "My videos / images" if preset.local_visuals else "Pexels stock footage",
        "captions": "Off" if preset.upload_audio else "Automatic voiceover captions",
        "start_seconds": 0.0, "excerpt_seconds": float(preset.duration),
    })


if "preset" not in st.session_state:
    st.session_state["preset"] = "music_ad"
    load_preset()


def active_tasks() -> list[dict]:
    tasks, _ = sm.state.get_all_tasks(page=1, page_size=1000)
    return [task for task in tasks if task.get("state") == const.TASK_STATE_PROCESSING]


def safe_error(error: object) -> str:
    return redact_error(error, config.snapshot_config_with_pending(config.app))


def output_controls(directory: Path, key: str) -> None:
    if not (directory / "makon-export.json").is_file():
        st.info("No completed export yet. Incomplete renders are not offered for download.")
        return
    videos = [p for p in sorted(directory.glob("final-*.mp4"))
              if p.is_file() and p.resolve().is_relative_to(directory.resolve())]
    if not videos:
        st.info("No finished export yet. A failed or interrupted task has no downloadable final video.")
        return
    for index, video in enumerate(videos):
        st.video(str(video))
        cols = st.columns(2)
        with cols[0], video.open("rb") as handle:
            st.download_button("Download MP4", handle, file_name=f"makon-{directory.name[:8]}-{index+1}.mp4",
                               mime="video/mp4", key=f"mp4-{key}-{index}")
        with cols[1]:
            if st.button("Prepare posting pack", key=f"pack-{key}-{index}"):
                st.session_state[f"pack-data-{key}-{index}"] = export_pack(directory, video)
            pack = st.session_state.get(f"pack-data-{key}-{index}")
            if pack:
                st.download_button("Download ZIP · video, captions & copy", pack,
                                   file_name=f"makon-{directory.name[:8]}.zip", mime="application/zip",
                                   key=f"zip-{key}-{index}")


@st.fragment(run_every="2s")
def generation_status() -> None:
    task_id = st.session_state.get("current_task")
    if not task_id:
        return
    state = sm.state.get_task(task_id)
    if not state:
        st.warning("This session no longer has live task status. Check the Library for completed files.")
        return
    st.divider()
    st.subheader("Your export")
    status = state.get("state")
    if status == const.TASK_STATE_PROCESSING:
        st.progress(min(100, max(0, int(state.get("progress", 0)))), text="Rendering — keep the application running.")
        st.caption("You can edit the next brief while this video renders. Exports are not published automatically.")
    elif status == const.TASK_STATE_FAILED:
        st.error(safe_error(state.get("error") or "Rendering failed. Check the input media and local terminal."))
    elif status == const.TASK_STATE_COMPLETE:
        st.success("Render complete. Watch the entire video before posting.")
        directory = Path(utils.task_dir(task_id))
        if st.session_state.get("requested_captions") and not (directory / "subtitle.srt").is_file():
            st.warning("This export has no subtitle file, although captions were requested. Check the voice provider or supply a timed SRT.")
        output_controls(directory, f"current-{task_id}")


st.markdown('<div class="makon-kicker">MAKON / CREATIVE OPERATIONS</div>', unsafe_allow_html=True)
st.title("Your next video starts here.")
st.markdown("**Makon Video Studio** · English controls. Uzbek stories. Your music, your footage, your final say.")
create_tab, library_tab, settings_tab = st.tabs(["Create", "Library", "Settings"])

with settings_tab:
    st.header("A small setup, not a wall of providers.")
    st.caption("Single-user local workspace. Credentials are stored in your local config file, never in export packs. Do not expose this app publicly without authentication.")
    snapshot = config.snapshot_config_with_pending(config.app)
    providers = {"gemini": "Google Gemini", "openrouter": "OpenRouter", "openai": "OpenAI"}
    current_provider = snapshot.get("llm_provider", "gemini")
    provider = st.selectbox("Script provider", list(providers), format_func=providers.get,
                            index=list(providers).index(current_provider) if current_provider in providers else 0)
    defaults = {"gemini": "gemini-3.8-flash", "openrouter": "google/gemini-2.5-flash", "openai": "gpt-4.1-mini"}
    model = st.text_input("Model ID", value=snapshot.get(f"{provider}_model_name") or defaults[provider], key=f"model-{provider}")
    api_key = st.text_input("New script API key", type="password", key=f"key-{provider}",
                            placeholder="A key is already saved; leave blank to keep it." if snapshot.get(f"{provider}_api_key") else "Paste a key from your provider")
    clear_key = st.checkbox("Remove the saved script key", key=f"clear-{provider}")
    st.caption("A saved key is not a connection test. AI drafting makes a provider request and may incur charges. Upload-only rendering needs no script API key.")
    a, b = st.columns(2)
    with a:
        pexels_key = st.text_input("New Pexels API key", type="password", placeholder="Leave blank to keep the existing key")
        clear_pexels = st.checkbox("Remove saved Pexels keys")
    with b:
        pixabay_key = st.text_input("New Pixabay API key", type="password", placeholder="Leave blank to keep the existing key")
        clear_pixabay = st.checkbox("Remove saved Pixabay keys")
    st.subheader("Your offers · editable UZS amounts")
    a, b, c = st.columns(3)
    basic_price = a.number_input("Music Basic", min_value=0, value=int(config.ui.get("makon_basic_price", 50000)), step=10000)
    pro_price = b.number_input("Music Pro", min_value=0, value=int(config.ui.get("makon_pro_price", 100000)), step=10000)
    room_price = c.number_input("Visual · per room", min_value=0, value=int(config.ui.get("makon_room_price", 400000)), step=50000)
    st.caption("These are starting presets, not a claim about current pricing. A price enters an AI draft only when your brief requests it.")
    if st.button("Save local settings", type="primary"):
        with config.try_runtime_config_lock() as acquired:
            if not acquired or active_tasks():
                st.warning("Finish the current render before changing global provider settings.")
            elif not model.strip():
                st.error("Enter a model ID.")
            else:
                config.app.update({"llm_provider": provider, f"{provider}_model_name": model.strip(),
                                   "upload_post_enabled": False, "upload_post_auto_upload": False})
                for field, entered, remove in [(f"{provider}_api_key", api_key, clear_key),
                                                ("pexels_api_keys", pexels_key, clear_pexels),
                                                ("pixabay_api_keys", pixabay_key, clear_pixabay)]:
                    if remove or entered.strip():
                        value = entered.strip() if not remove else ""
                        config.app[field] = ([value] if value else []) if field.endswith("keys") else value
                config.ui.update({"language": "en", "makon_basic_price": int(basic_price),
                                  "makon_pro_price": int(pro_price), "makon_room_price": int(room_price)})
                try:
                    config.save_config()
                    st.success("Saved locally. Automatic publishing stays disabled.")
                except OSError as error:
                    st.error(safe_error(error))
    with st.expander("Runtime checks"):
        if st.button("Check local rendering tools"):
            try:
                ready = utils.check_ffmpeg_ready()
                (st.success if ready else st.error)("FFmpeg is ready." if ready else "FFmpeg is unavailable. Install FFmpeg or use the Docker setup.")
            except Exception as error:
                st.error(safe_error(error))
        st.write("Subtitle font:", "Available" if (ROOT / "resource/fonts/BeVietnamPro-Bold.ttf").is_file() else "Missing — use a complete Git clone.")
        st.write("Script key:", "Configured (not network-tested)" if snapshot.get(f"{provider}_api_key") else "Not configured")
    st.info("Need the full upstream controls? Run: uv run streamlit run webui/Main.py --server.address 127.0.0.1 --server.port 8502")

with create_tab:
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.subheader("01 / Shape the story")
        preset_id = st.selectbox("Workflow", list(PRESETS), format_func=lambda x: PRESETS[x].title,
                                key="preset", on_change=load_preset)
        st.caption(PRESETS[preset_id].description)
        a, b = st.columns(2)
        language = a.selectbox("Content language", list(LANGUAGES), format_func=LANGUAGES.get, key="language")
        seconds = b.slider("Writing target · seconds", 5, 90, key="target_seconds")
        topic = st.text_input("Video title / topic", key="topic", max_chars=300)
        brief = st.text_area("Details the script must use", key="brief", height=100,
                              placeholder="Occasion, recipient, real details, offer, and the call to action. Do not paste private customer details you cannot send to the selected AI provider.", max_chars=3000)
        if st.button("Draft with AI", help="Sends the title and brief to the configured provider. Review the draft before rendering."):
            settings = config.snapshot_config_with_pending(config.app)
            chosen = settings.get("llm_provider", "gemini")
            if not topic.strip():
                st.error("Add a topic first.")
            elif not settings.get(f"{chosen}_api_key"):
                st.error("Add a script API key in Settings, or write the script yourself below.")
            else:
                try:
                    direction = build_script_direction(preset_id, language, seconds,
                                                       int(config.ui.get("makon_basic_price", 50000)),
                                                       int(config.ui.get("makon_pro_price", 100000)),
                                                       int(config.ui.get("makon_room_price", 400000)))
                    with st.spinner("Drafting your script…"):
                        script = llm.generate_script(video_subject=f"{topic.strip()}\n{brief.strip()}",
                                                     language=LANGUAGES[language], paragraph_number=1,
                                                     video_script_prompt=direction, app_config=settings)
                    if script and script.strip():
                        st.session_state["script"] = script.strip()
                    else:
                        st.error("The provider returned no script. Check your key, model ID and provider balance, or enter a script manually.")
                except Exception as error:
                    st.error(safe_error(error))
        script = st.text_area("Script / lyric reference", key="script", height=220, max_chars=8000,
                              placeholder="Edit freely. With uploaded audio this is a text reference, not automatically timed lyrics.")
        st.caption(f"Approximate speech length: {estimate_speech_seconds(script)} seconds. Actual voice speed and pauses determine the export length.")
        caption = st.text_area("Post caption", key="caption", height=100, max_chars=5000,
                               placeholder="Your Instagram caption and call to action. Included in the posting ZIP; not burned onto the video.")
    with right:
        st.subheader("02 / Choose the sound & visuals")
        audio_mode = st.radio("Soundtrack", ["Generate a voiceover", "Upload a finished song / voiceover"], key="audio_mode")
        audio_upload = None
        if audio_mode.startswith("Upload"):
            audio_upload = st.file_uploader("Your finished audio", type=sorted(x[1:] for x in AUDIO_EXTENSIONS), key="audio-upload")
            a, b = st.columns(2)
            excerpt_start = a.number_input("Start at · seconds", min_value=0.0, step=1.0, key="start_seconds")
            excerpt_length = b.number_input("Excerpt length · seconds", min_value=1.0, max_value=90.0, step=1.0, key="excerpt_seconds")
            if audio_upload:
                st.audio(audio_upload)
            voice_name = ""
            st.caption("Use an exported Suno/Kie audio file. No Suno API request is made by this workspace. No extra background music is added.")
        else:
            voices = voice.get_all_azure_voices(filter_locals=[language])
            voice_name = st.selectbox("Edge voice", voices or ["en-US-AriaNeural-Female"], key=f"voice-{language}")
            st.caption("Voice synthesis uses an online service. Uzbek pronunciation still needs human review.")
            excerpt_start, excerpt_length = 0.0, float(seconds)
        choices = ["Off", "Upload timed SRT"] if audio_mode.startswith("Upload") else ["Automatic voiceover captions", "Upload timed SRT", "Off"]
        if st.session_state.get("captions") not in choices:
            st.session_state["captions"] = "Off"
        captions = st.selectbox("Caption timing", choices, key="captions")
        srt_upload = None
        if captions == "Upload timed SRT":
            srt_upload = st.file_uploader("UTF-8 SRT · relative to the excerpt", type=["srt"], key="srt-upload")
            st.caption("00:00 means the beginning of the selected excerpt, not the original full song. Invalid or overlapping timings are rejected.")
        footage = st.selectbox("Visual source", ["My videos / images", "Pexels stock footage", "Pixabay stock footage"], key="footage")
        uploads = []
        terms = ""
        if footage == "My videos / images":
            uploads = st.file_uploader("Upload in story order · up to 20 files", type=sorted(x[1:] for x in VISUAL_EXTENSIONS), accept_multiple_files=True, key="visual-uploads")
            if uploads:
                st.caption("Sequence: " + " → ".join(f"{i+1}. {p.name}" for i, p in enumerate(uploads)))
            st.caption("Your footage plays in this order and may loop to fill the soundtrack. A design reveal uses your images; it does not generate a new interior design.")
        else:
            terms = st.text_input("Footage search keywords · comma-separated", placeholder="anniversary gift, couple, flowers", max_chars=500)
            st.caption("Enter visual search terms in English. Stock footage is illustrative, not evidence of a real customer reaction.")
        with st.expander("Export style", expanded=False):
            aspect = st.selectbox("Canvas", ["9:16", "16:9", "1:1"])
            fit = st.selectbox("Fit", ["cover", "contain"], help="Cover crops to fill the canvas; contain preserves the whole image with padding.")
            clip_duration = st.slider("Seconds per visual clip", 1, 10, 4)
            font_size = st.slider("Caption size", 30, 100, 58)
            caption_position = st.slider("Caption vertical position · %", 20, 80, 68)
            style = st.selectbox("Caption style", ["Clean sentences", "Word by word"] if captions == "Automatic voiceover captions" else ["Clean sentences"])
            st.caption("Export is Full HD: 1080×1920 portrait, 1920×1080 landscape, or 1080×1080 square. No platform interface, watermark or fake engagement is added.")
    st.divider()
    st.subheader("03 / Review, then render")
    review_data = [preset_id, language, topic, brief, script, caption, audio_mode, voice_name,
                   excerpt_start, excerpt_length, captions, footage, terms, aspect, fit,
                   clip_duration, font_size, caption_position, style]
    for upload in [audio_upload, srt_upload, *uploads]:
        if upload is not None:
            review_data.append([upload.name, getattr(upload, "file_id", None), upload.size])
    review_id = hashlib.sha256(json.dumps(review_data, ensure_ascii=False).encode()).hexdigest()[:16]
    approved = st.checkbox("I reviewed the script, have permission to use the media, and will review the finished video before posting.", key=f"approved-{review_id}")
    st.caption("One video per render. Nothing is automatically posted, and rendering does not guarantee views or sales.")
    if st.button("Render my video", type="primary", disabled=not approved):
        directory = None
        try:
            if not topic.strip():
                raise ValueError("Enter a video title / topic.")
            if not audio_mode.startswith("Upload") and not script.strip():
                raise ValueError("Write or generate a script before rendering a voiceover.")
            if audio_mode.startswith("Upload") and audio_upload is None:
                raise ValueError("Upload your finished audio first.")
            if footage == "My videos / images" and not 1 <= len(uploads) <= 20:
                raise ValueError("Upload between 1 and 20 visual files.")
            if sum(p.size for p in uploads) + (audio_upload.size if audio_upload else 0) > 600 * 1024 * 1024:
                raise ValueError("Keep the total media size below 600 MB per task.")
            if captions == "Upload timed SRT" and srt_upload is None:
                raise ValueError("Upload an SRT file, or change caption timing.")
            source = "local" if footage == "My videos / images" else ("pexels" if footage.startswith("Pexels") else "pixabay")
            settings = config.snapshot_config_with_pending(config.app)
            if source != "local" and (not terms.strip() or not settings.get(f"{source}_api_keys")):
                raise ValueError("Stock footage requires search keywords and a saved API key in Settings. Use your own media to render without a stock API.")
            if not utils.check_ffmpeg_ready():
                raise ValueError("FFmpeg is unavailable. Install FFmpeg or use the Docker setup.")
            with config.try_runtime_config_lock() as acquired:
                if not acquired or active_tasks():
                    raise ValueError("There is already a render in progress. Let it finish before starting the next one.")
                config.app.update({"upload_post_enabled": False, "upload_post_auto_upload": False,
                                   "subtitle_provider": "edge"})
                task_id = str(uuid4())
                directory = Path(utils.task_dir(task_id))
                audio_path = None
                if audio_upload:
                    original = persist_upload(directory, audio_upload.name, audio_upload.getvalue(), AUDIO_EXTENSIONS)
                    audio_path = trim_audio(original, directory / "excerpt.mp3", excerpt_start,
                                            excerpt_length, voice.get_audio_duration(str(original)), utils.get_ffmpeg_binary())
                subtitle_path = None
                if srt_upload:
                    normalized = validate_srt(srt_upload.getvalue().decode("utf-8-sig"), excerpt_length if audio_upload else None)
                    subtitle_path = directory / "uploaded.srt"
                    subtitle_path.write_text(normalized, encoding="utf-8")
                materials = [MaterialInfo(provider="local", url=str(persist_upload(directory, u.name, u.getvalue(), VISUAL_EXTENSIONS))) for u in uploads] if source == "local" else None
                pipeline_script = script.strip() or topic.strip()
                params = VideoParams(video_subject=topic.strip(), video_script=pipeline_script,
                    video_language=language, voice_name=voice_name,
                    custom_audio_file=str(audio_path) if audio_path else None,
                    custom_subtitle_file=str(subtitle_path) if subtitle_path else None,
                    video_source=source, video_terms=[t.strip() for t in terms.split(",") if t.strip()],
                    video_materials=materials, video_aspect=aspect, video_fit_mode=fit,
                    video_concat_mode="sequential", video_clip_duration=clip_duration, video_count=1,
                    bgm_type="", bgm_volume=0.0, subtitle_enabled=captions != "Off",
                    subtitle_position="custom", custom_position=float(caption_position),
                    font_name="MicrosoftYaHeiBold.ttc" if language == "ru-RU" else "BeVietnamPro-Bold.ttf",
                    font_size=font_size, stroke_width=2.0,
                    subtitle_display_mode="word_by_word" if style == "Word by word" else "sentence",
                    n_threads=2)
                write_project(directory, title=topic.strip(), preset=preset_id, language=language, script=script, caption=caption)
                webui_task.submit_generation(task_id, params)
                st.session_state["current_task"] = task_id
                st.session_state["requested_captions"] = captions != "Off"
        except Exception as error:
            st.error(safe_error(error))
    generation_status()

with library_tab:
    st.header("Your finished work stays here.")
    st.caption("Local task folders survive browser refreshes and application restarts. In Docker, keep the named storage volume. No customer media is synced to GitHub.")
    if st.button("Refresh library"):
        st.rerun()
    tasks_root = ROOT / "storage" / "tasks"
    projects = sorted(tasks_root.glob("*/makon.json"), key=lambda p: p.stat().st_mtime, reverse=True) if tasks_root.is_dir() else []
    if not projects:
        st.info("Your Makon projects appear here after your first render submission.")
    for project_file in projects[:30]:
        try:
            metadata = json.loads(project_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        directory = project_file.parent
        with st.expander(f"{metadata.get('title', 'Untitled')} · {directory.name[:8]}"):
            output_controls(directory, f"library-{directory.name}")
            if directory.joinpath("caption.txt").is_file():
                st.text(directory.joinpath("caption.txt").read_text(encoding="utf-8"))
    if len(projects) > 30:
        st.caption("Showing the 30 most recent projects. Older exports remain in storage/tasks on disk.")

st.caption("Makon Video Studio · Based on MoneyPrinterTurbo by Harry, MIT license. Local production tool — not a hosted publishing service.")
