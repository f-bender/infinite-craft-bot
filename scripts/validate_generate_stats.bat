@echo off
cd %~dp0/../src
poetry run python -m pytest ../tests && poetry run python compute_element_paths.py
