from imswitch.imcommon.model import initLogger
from .LEDMatrixManager import LEDMatrixManager
import numpy as np
from typing import Dict, List

import uc2rest

class ESP32LEDMatrixManager(LEDMatrixManager):
    """ LEDMatrixManager for controlling LEDs and LEDMatrixs connected to an
    ESP32 exposing a REST API
    Each LEDMatrixManager instance controls one LED.

    Manager properties:

    - ``rs232device`` -- name of the defined rs232 communication channel
      through which the communication should take place
    - ``channel_index`` -- LEDMatrix channel (A to H)
    """

    def __init__(self, LEDMatrixInfo, name, **lowLevelManagers):
        self.__logger = initLogger(self, instanceName=name)
        self.power = 0
        self.I_max = 255
        self.setEnabled = False
        self.intensity=0
        self.color = (1.0, 1.0, 1.0) # White by default

        try:
            self.Nx = LEDMatrixInfo.managerProperties['Nx']
            self.Ny = LEDMatrixInfo.managerProperties['Ny']
        except:
            self.Nx = 8
            self.Ny = 8

        self.NLeds = self.Nx*self.Ny

        self._rs232manager = lowLevelManagers['rs232sManager'][
            LEDMatrixInfo.managerProperties['rs232device']
        ]
       
        # initialize the LEDMatrix device that holds all necessary states^
        self.mLEDmatrix = self._rs232manager._esp32.led
        self.mLEDmatrix.Nx = self.Nx
        self.mLEDmatrix.Ny = self.Ny
        self.mLEDmatrix.setLEDArrayConfig(ledArrPin=None, ledArrNum=self.NLeds)

        super().__init__(LEDMatrixInfo, name, isBinary=False, valueUnits='mW', valueDecimals=0)

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value: tuple):
        self._color = value

    def setAll(self, state=(0,0,0), intensity=None):
        # dealing with on or off,
        # intensity is adjjusting the global value
        if state is not None:
            state = tuple([a*b for a,b in zip(self.color, state)])
            print(state)
        self.mLEDmatrix.setAll(state, intensity)

    def setPattern(self, pattern):
        self.mLEDmatrix.setPattern(ledpattern=pattern)
    
    def getPattern(self):
        return self.mLEDmatrix.getPattern()

    def getLEDSingle(self, index):
        return self.mLEDmatrix.getPattern()[index]

    def setEnabled(self, enabled):
        """Turn on (N) or off (F) LEDMatrix emission"""
        self.setEnabled = enabled

    def setLEDSingle(self, indexled=0, state=(0,0,0)):
        """Handles output power.
        Sends a RS232 command to the LEDMatrix specifying the new intensity.
        """
        self.mLEDmatrix.setSingle(indexled, state=state)

    def setLEDIntensity(self, intensity=(0,0,0)):
        self.mLEDmatrix.setIntensity(intensity)

    @property
    def inner_ring_mask(self):
        return [i_led if 1<=i_led<9 else False for i_led in list(range(25))]

    @property
    def outer_ring_mask(self):
        return [i_led if 9<=i_led<25 else False for i_led in list(range(25))]

    def bool_list_to_numpy(self, led_pattern: List[bool] = None):
        return np.vstack([[1, 1, 1] if i else [0, 0, 0] for i in led_pattern])

    def setInnerRIng(self, color = None):
        pattern = self.mLEDmatrix.getPattern()
        inner_ring = self.bool_list_to_numpy(self.inner_ring_mask)
        if color is None:
            color = self.color
        self.mLEDmatrix.setPattern(ledpattern=np.logical_or(pattern,inner_ring)*color)
        print(f"Color {self.color}")

    def setOuterRIng(self, color = None):
        pattern = self.mLEDmatrix.getPattern()
        outer_ring = self.bool_list_to_numpy(self.outer_ring_mask)
        if color is None:
            color = self.color
        self.mLEDmatrix.setPattern(ledpattern=np.logical_or(pattern,outer_ring)*color)
        print(f"Color {self.color}")

# Copyright (C) 2020-2021 ImSwitch developers
# This file is part of ImSwitch.
#
# ImSwitch is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ImSwitch is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
