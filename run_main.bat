@echo off
set CODE_DIR=C:\Users\matia_n97ktw5\Documents\LABMaiTE
:: set PYTHONPATH=%CODE_DIR%\lm_hardware; PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-impl; PYTHONPATH=%CODE_DIR%\BMBF-LOCai\locai-hw\ImSwitch\;

echo python path %PYTHONPATH%

cd %CODE_DIR%\BMBF-LOCai\locai-hw\ImSwitch\
@echo on
C:\Users\matia_n97ktw5\.conda\envs\imswitchUC2\python.exe "main_bat.py"
pause