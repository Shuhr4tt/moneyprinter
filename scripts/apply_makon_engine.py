"""One-time, idempotent integration of Makon into the pinned upstream engine.

The CI preparation job commits these small source edits so end users do not
need to run an installer. Refuse unexpected source instead of guessing.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(name, before, after):
    file = ROOT / name
    text = file.read_text(encoding="utf-8")
    if after in text:
        return
    if text.count(before) != 1:
        raise RuntimeError(f"Unexpected upstream source in {name}; inspect before applying.")
    file.write_text(text.replace(before, after, 1), encoding="utf-8")


def main():
    if "436b0e9cc830ef7639e33388917e389cf30d3307" not in (ROOT / "UPSTREAM.md").read_text():
        raise RuntimeError("Unexpected upstream revision")
    replace("app/models/schema.py", '    video_language: Optional[str] = ""  # auto detect',
            '    # Makon: manual captions must remain inside the current task.\n    custom_subtitle_file: Optional[str] = None\n    video_language: Optional[str] = ""  # auto detect')
    replace("app/services/task.py",
            '    subtitle_path = path.join(utils.task_dir(task_id), "subtitle.srt")\n    subtitle_provider =',
            '    subtitle_path = path.join(utils.task_dir(task_id), "subtitle.srt")\n    manual_subtitles = getattr(params, "custom_subtitle_file", None)\n    if manual_subtitles:\n        from pathlib import Path\n        from app.makon import copy_validated_subtitles\n        return copy_validated_subtitles(\n            Path(utils.task_dir(task_id)), manual_subtitles,\n            voice.get_audio_duration(audio_file),\n        )\n    subtitle_provider =')
    needle = '    logger.success(\n        f"task {task_id} finished, generated {len(final_video_paths)} videos."\n    )'
    insert = '''    # Do not offer a partial file left by an interrupted render as a finished export.
    makon_project = path.join(utils.task_dir(task_id), "makon.json")
    if os.path.isfile(makon_project):
        from pathlib import Path
        marker = Path(utils.task_dir(task_id)) / "makon-export.json"
        temporary_marker = marker.with_suffix(".tmp")
        temporary_marker.write_text(json.dumps({"complete": True, "files": [path.basename(p) for p in final_video_paths]}), encoding="utf-8")
        temporary_marker.replace(marker)

'''
    replace("app/services/task.py", needle, insert + needle)
    replace("app/config/config.py", 'config_file = f"{root_dir}/config.toml"',
            'config_file = os.path.abspath(os.getenv("MPT_CONFIG_FILE") or f"{root_dir}/config.toml")')
    replace("app/config/config.py", '    if os.path.isdir(config_file):\n        shutil.rmtree(config_file)',
            '    if os.path.isdir(config_file):\n        raise IsADirectoryError(f"Config path is a directory: {config_file}. Choose a file path with MPT_CONFIG_FILE.")\n    os.makedirs(os.path.dirname(config_file), exist_ok=True)')
    replace("app/config/config.py", '                dir=root_dir,', '                dir=os.path.dirname(config_file),')
    for before, after in [
        ('log_level = "DEBUG"', 'log_level = "INFO"'),
        ('listen_host = "0.0.0.0"', 'listen_host = "127.0.0.1"'),
        ('llm_provider = "moonshot"', 'llm_provider = "gemini"'),
        ('gemini_model_name = ""', 'gemini_model_name = "gemini-3.8-flash"'),
        ('open_task_folder_on_completion = true', 'open_task_folder_on_completion = false'),
        ('# language = "zh"', 'language = "en"'),
        ('# voice_name = ""', 'voice_name = "en-US-AriaNeural-Female"'),
        ('# bgm_type = "random"', 'bgm_type = ""'),
        ('# font_name = "MicrosoftYaHeiBold.ttc"', 'font_name = "BeVietnamPro-Bold.ttf"'),
        ('# subtitle_position = "bottom"', 'subtitle_position = "custom"'),
    ]:
        replace("config.example.toml", before, after)
    replace("webui.bat", "webui\\Main.py", "webui\\Makon.py")
    replace("webui.sh", "webui/Main.py", "webui/Makon.py")
    replace("test/services/test_config.py", 'assert example_config["listen_host"] == "0.0.0.0"', 'assert example_config["listen_host"] == "127.0.0.1"')
    replace("test/services/test_config.py", 'assert example_config["log_level"] == "DEBUG"', 'assert example_config["log_level"] == "INFO"')
    for name, suffix in [(".gitignore", "\n# Makon local validation and credentials\n/validation/\n.env.*\n*.pem\n"),
                         (".dockerignore", "\nvalidation/\n.github/\ntest/\n")]:
        file = ROOT / name
        text = file.read_text()
        if suffix not in text:
            file.write_text(text + suffix)


if __name__ == "__main__":
    main()
