@echo off
set CODE_DIR=C:\Users\matia_n97ktw5\Documents\LABMaiTE\BMBF-LOCai
set PYTHONPATH=%CODE_DIR%\;PYTHONPATH=%CODE_DIR%\lm_hardware;PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-hw\ImSwitch\;PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-impl;PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-impl\config;PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-impl\locai_app;

echo python path %PYTHONPATH%
@echo on
C:\Users\matia_n97ktw5\.conda\envs\imswitchUC2\python.exe "C:\Users\matia_n97ktw5\Documents\LABMaiTE\BMBF-LOCai\locai-hw\ImSwitch\main.py"
