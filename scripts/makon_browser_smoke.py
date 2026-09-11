"""Real-browser upload -> excerpt -> captions -> render -> download smoke test."""
from __future__ import annotations
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "validation"


def choose(page, label, option):
    page.get_by_label(label, exact=True).click()
    page.get_by_role("option", name=option, exact=True).click()


def upload(page, label, file):
    page.get_by_test_id("stFileUploader").filter(has_text=label).locator('input[type="file"]').set_input_files(str(file))


def main():
    OUT.mkdir(exist_ok=True)
    log = (OUT / "browser-server.log").open("w")
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "webui/Makon.py", "--server.address=127.0.0.1",
                               "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError("Streamlit failed to start")
            try:
                urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
            page.set_default_timeout(30000)
            page.goto("http://127.0.0.1:8501")
            page.get_by_role("heading", name="Your next video starts here.").wait_for()
            try:
                choose(page, "Workflow", "Makon Music · Song showcase")
                upload(page, "Your finished audio", OUT / "fixtures/technical-tone.wav")
                page.get_by_label("Excerpt length · seconds", exact=True).fill("4")
                page.get_by_label("Excerpt length · seconds", exact=True).press("Tab")
                choose(page, "Caption timing", "Upload timed SRT")
                upload(page, "UTF-8 SRT · relative to the excerpt", OUT / "fixtures/uploaded.srt")
                upload(page, "Upload in story order", OUT / "fixtures/test-card.png")
                page.get_by_label("Post caption", exact=True).fill("Makon browser validation — synthetic media, not an advertisement.")
                page.get_by_label("Post caption", exact=True).press("Tab")
                page.get_by_role("checkbox", name="I reviewed the script, have permission").check()
                page.get_by_role("button", name="Render my video", exact=True).click()
                page.get_by_text("Render complete. Watch the entire video before posting.", exact=True).wait_for(timeout=240000)
                page.get_by_role("button", name="Download MP4", exact=True).first.scroll_into_view_if_needed()
                with page.expect_download(timeout=30000) as download:
                    page.get_by_role("button", name="Download MP4", exact=True).first.click()
                download.value.save_as(str(OUT / "makon-browser-export.mp4"))
                page.screenshot(path=str(OUT / "makon-render-result.png"), full_page=True)
                page.get_by_role("heading", name="Your next video starts here.").scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / "makon-workspace.png"), full_page=False)
                probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(OUT / "makon-browser-export.mp4")]))
                video = next(s for s in probe["streams"] if s["codec_type"] == "video")
                assert (video["width"], video["height"]) == (1080,1920)
                assert any(s["codec_type"] == "audio" for s in probe["streams"])
                assert 3.8 <= float(probe["format"]["duration"]) <= 4.3
                (OUT / "browser-validation.json").write_text(json.dumps({"browser_upload_render_download": "passed", "resolution": "1080x1920", "duration_seconds": float(probe["format"]["duration"]), "fixture": "synthetic image + tone + SRT"}, indent=2))
            except Exception:
                page.screenshot(path=str(OUT / "browser-failure.png"), full_page=True)
                (OUT / "browser-failure.txt").write_text(page.locator("body").inner_text())
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        log.close()


if __name__ == "__main__":
    main()
