@echo off
cd %~dp0/..
poetry run pytest tests/ && poetry run python src/compute_element_paths.py && poetry run python src/main.py
pause
