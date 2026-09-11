# Makon Video Studio

**English-first short-video production for Makon Music and Makon Visual.**
Built on the complete MoneyPrinterTurbo engine, pinned to upstream commit
`436b0e9cc830ef7639e33388917e389cf30d3307`. This is an independent customized
copy, not the upstream project's official release. Original MIT license and
attribution are retained in `LICENSE` and `UPSTREAM.md`.

## Your personalized workflows

| Workflow | Purpose |
| --- | --- |
| Makon Music · Gift ad | Editable emotional gift scripts, truthful offers and a message-the-team call to action |
| Makon Music · Song showcase | Upload a finished Suno/Kie song, choose an excerpt and supply your own visuals |
| Makon Visual · Design reveal | Show your actual before-and-after images in upload order |
| General · Story / explainer | Keep a general English-language topic-to-video workflow |

The interface is English. Content can be Uzbek (Latin), English or Russian.
Prices are editable UZS starting presets, not hardcoded claims about your current offer.
AI drafting is explicit; you can write the script yourself. Song mode keeps the
uploaded song as the soundtrack, without unwanted narration or background music.

**Caption timing:** generated voiceovers can use automatic captions. Uploaded
songs default to captions off until you supply a UTF-8 SRT. Its timestamps must
be relative to the selected excerpt, not the full original song. Malformed,
overlapping, out-of-range and out-of-task subtitle files are rejected. This
workspace does not claim automatic singing alignment.

Exports are Full-HD portrait, landscape or square MP4s. Posting ZIPs contain the
video, available SRT, script and post caption—not config, logs or server paths.
The Library retains completed projects across restarts. Failed/interrupted
renders are not presented as completed exports. **Nothing is posted automatically.**

## Start locally — Windows, macOS, Linux

Install Git and uv, then run:

```bash
git clone https://github.com/Shuhr4tt/moneyprinter.git
cd moneyprinter
uv python install 3.11
uv sync --frozen
```

Windows PowerShell / CMD:

```powershell
.\webui.bat
```

macOS / Linux:

```bash
sh webui.sh
```

Open the local address printed by the launcher, normally `http://127.0.0.1:8501`.
The launcher selects another port when needed. Keep the application/terminal
running while rendering. A usable FFmpeg is required; the locked imageio-ffmpeg
package supplies a binary on supported platforms. If the runtime check fails,
install FFmpeg on PATH or use Docker.

Direct launch from the repository also works:

```bash
uv run streamlit run webui/Makon.py --server.address 127.0.0.1 --server.port 8501
```

## Docker — local-only, persistent workspace

With Docker Desktop / Docker Engine and Compose installed:

```bash
docker compose -f compose.makon.yml up --build
```

Open `http://127.0.0.1:8501`. This builds **your customized code**, not the upstream
release image. The container uses a non-root user and publishes only to loopback.
Its named `makon-storage` volume stores credentials, uploads and exports. Do not
remove that volume or use `down -v` unless you intend to delete the data.

`MPT_CONFIG_FILE` selects a config file. Docker uses `/app/storage/config.toml`,
created on first launch; native runs default to the repository's `config.toml`.
A config path that is a directory is rejected, never recursively deleted.

## First useful video — no paid API key required

Choose **Makon Music · Song showcase**, upload a finished audio file you have
rights to use, set an excerpt that fits inside it, and upload your images/videos
in story order. Leave captions off or supply a timed SRT. Add your title and post
caption, review the inputs, render, watch and download.

This path makes no LLM, TTS, stock-provider or Suno-generation request. It uses
local rendering resources. Visuals may loop to cover the audio duration.

For AI drafts, save a provider key and a model available to your account in
**Settings**. Gemini is the starting provider; OpenRouter and OpenAI are also
exposed. A saved key is **not** a successful connection test. Provider requests
may cost money. Stock footage requires its own Pexels/Pixabay key and explicit
English search terms. Edge voice synthesis requires internet and service
availability. Review Uzbek pronunciation before publishing.

**Direct Suno/Kie API generation is not added by this customization.** Use an
exported audio file. The original advanced providers remain available. No
HyperFrames integration or exact Instagram interface recreation is claimed.

## Advanced tools retained

```bash
uv run streamlit run webui/Main.py --server.address 127.0.0.1 --server.port 8502
uv run python cli.py --help
uv run python main.py
```

`README-en.md` documents the original project. Its release images and upstream
update/download instructions refer to the original product, not this Makon
build. Use this README for personalized startup. An upstream updater may
overwrite your customizations.

## Validation

```bash
uv run pytest test/test_makon_helpers.py test/test_makon_integration.py -q
uv run python scripts/makon_smoke.py
```

The smoke test creates a **real 1080×1920 MP4** through the production pipeline
using a synthetic title card, a trimmed test tone and manual SRT. It checks
resolution, audio, duration, full decoding and the posting pack while blocking
LLM/TTS/transcription calls. It is a technical demo, not a sample AI song or proof
that paid providers work with your credentials. Developer smoke tests also need
`ffprobe` on PATH.

CI checks the English page with Streamlit's app tester, exercises upload to
render to download in a real browser, and includes native Windows/Linux tests
and a separate Docker build/health check. **Workflow results and artifacts are
the source of truth for which checks actually passed.**

## Storage and safety

Uploaded visuals stay in `storage/local_videos/makon/<task-id>/`, inside the engine's allowed media directory.
Project files, audio and captions live in `storage/tasks/<task-id>/`; the Library shows the most
recent 30, while older projects remain on disk. Browser draft state is not an
autosaved project. No automatic cleanup deletes customer files.

This is a **single-user trusted local app**, not a hardened multi-tenant service.
Config contains plaintext credentials; keep it and its backups private. Runtime
files, keys and exports are Git-ignored. Never paste keys into GitHub issues or
prompts. Do not expose the WebUI/API publicly without authentication, TLS and
resource limits. Use only music, footage and customer information you are
permitted to process and publish. Stock media is not evidence of a real customer
reaction. No view count or sales result is guaranteed.
