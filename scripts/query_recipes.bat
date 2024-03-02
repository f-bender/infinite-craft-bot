@echo off
cd %~dp0/../src
poetry run python -m infinite_craft_bot query
pause
