@echo off
cd %~dp0/..
poetry run pytest test.py && poetry run python compute_element_paths.py && poetry run python main.py
pause
