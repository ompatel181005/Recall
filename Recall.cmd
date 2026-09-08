@echo off
rem Double-click this to start Recall.
rem Runs the launcher hidden so no console window sticks around.
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
