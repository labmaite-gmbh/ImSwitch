@echo off
setlocal

set CODE_DIR=C:\Users\hardw\Desktop\uc2i-installer\uc2i_conda
set MICROSCOPE_API_DIR=C:\Users\hardw\Desktop\microscope-api
set PYTHON=C:\Users\hardw\anaconda3\envs\uc2i_env\python.exe

:: microscope-api must come first so "import main" resolves to its main.py
set PYTHONPATH=%MICROSCOPE_API_DIR%;%CODE_DIR%\ImSwitch;%CODE_DIR%\lm_hardware;%CODE_DIR%\locai-impl;%CODE_DIR%\UC2-REST;%CODE_DIR%\laia-client\src

:: Tell LabmaiteDeckController to run as a microscope_api client
set MICROSCOPE_API_CLIENT=1

echo PYTHONPATH=%PYTHONPATH%
echo Starting ImSwitch in client mode (microscope_api owns hardware)...

cd /d %CODE_DIR%\ImSwitch
%PYTHON% main.py

endlocal
