@echo off
set CODE_DIR=C:\Users\matia_n97ktw5\Documents\LABMaiTE\repositories
:: set PYTHONPATH=%CODE_DIR%\lm_hardware; PYTHONPATH=%CODE_DIR%\locai-impl; PYTHONPATH=%CODE_DIR%\ImSwitch\;

echo python path %PYTHONPATH%

cd %CODE_DIR%\ImSwitch\
@echo on
C:\Users\matia_n97ktw5\.conda\envs\imswitchUC2\python.exe "main.py"