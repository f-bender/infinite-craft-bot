@echo off
cd %~dp0/../src
poetry run python -m pytest ../tests && poetry run python -m infinite_craft_bot crawl -psm exhaust
pause
