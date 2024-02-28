@echo off
cd %~dp0/../src
poetry run python -m pytest ../tests && poetry run python compute_element_paths.py && poetry run python query_full_recipe.py
pause
