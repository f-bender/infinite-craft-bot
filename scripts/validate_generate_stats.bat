@echo off
cd %~dp0/..
poetry run pytest && poetry run python src/compute_element_paths.py
