import os
import sys
from pathlib import Path

locai_pth = str(Path(__file__).parent.parent.absolute())
print("ImSwitch path is ", locai_pth)
sys.path.append(locai_pth)
print(f"System path is {sys.path}.")
os.environ["QT_API"] = "pyqt5"
from imswitch.__main__ import main
main()
