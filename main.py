import sys
from pathlib import Path

import os

locai_pth = str(Path(__file__).parent.parent.absolute())
print("Locai path is ", locai_pth)
sys.path.append(locai_pth)
print(sys.path)
from imswitch.__main__ import main
main()