@echo off
cd %~dp0/../src
poetry run python -m pytest ../tests && poetry run python -m infinite_craft_bot query --compute_element_paths --save_path_stats
pause
