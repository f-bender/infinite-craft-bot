@echo off
cd %~dp0/../src
poetry run pytest ../tests && poetry run python compute_element_paths.py && poetry run python -m infinite_craft_bot
pause
