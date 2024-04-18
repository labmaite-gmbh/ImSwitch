#!/bin/bash

CODE_DIR="/home/worker5/Documents/repositories"
export PYTHONPATH="$CODE_DIR/lm_hardware:$CODE_DIR/locai-impl:$CODE_DIR/ImSwitch:$CODE_DIR/UC2-REST:$CODE_DIR/laia-client"

echo "python path $PYTHONPATH"

cd "$CODE_DIR/ImSwitch"


sudo chmod a+rw /dev/ttyUSB0
/home/worker5/anaconda3/envs/imswitchUC2/bin/python main.py
# TODO: missing pip install -e . in all Labmaite repositories. Check where it should be done

