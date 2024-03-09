@echo off
cd %~dp0/../src
poetry run python -m pytest ../tests && poetry run python -m infinite_craft_bot compute_paths --save_path_stats
