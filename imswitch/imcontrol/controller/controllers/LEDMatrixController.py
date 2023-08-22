from typing import Dict, List
from functools import partial
from qtpy import QtCore, QtWidgets
import numpy as np


from imswitch.imcommon.model import APIExport
from ..basecontrollers import ImConWidgetController
from imswitch.imcontrol.view import guitools as guitools
from imswitch.imcommon.model import initLogger, APIExport


class LEDMatrixController(ImConWidgetController):
    """ Linked to LEDMatrixWidget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__logger = initLogger(self)

        # TODO: This must be easier?
        self.nLedsX = self._master.LEDMatrixsManager._subManagers['ESP32LEDMatrix'].Nx
        self.nLedsY = self._master.LEDMatrixsManager._subManagers['ESP32LEDMatrix'].Ny

        self._ledmatrixMode = ""

        # get the name that looks like an LED Matrix
        self.ledMatrix_name = self._master.LEDMatrixsManager.getAllDeviceNames()[0]
        self.ledMatrix = self._master.LEDMatrixsManager[self.ledMatrix_name]

        # set up GUI and "wire" buttons
        self._widget.add_matrix_view(self.nLedsX, self.nLedsY)
        self.connect_leds()

        # initialize matrix
        self.setAllLEDOff()

        self._widget.ButtonAllOn.clicked.connect(self.setAllLEDOn)
        self._widget.ButtonAllOff.clicked.connect(self.setAllLEDOff)
        self._widget.ButtonToggle.clicked.connect(self.togglePattern)
        self._widget.slider.sliderReleased.connect(self.setIntensity)

        self._widget.ButtonInnerRing.clicked.connect(self.toggle_inner_ring)
        self._widget.ButtonOuterRing.clicked.connect(self.toggle_outer_ring)

        self.current_pattern = self.ledMatrix.getPattern()

    @APIExport()
    def toggle_inner_ring(self):
        pattern = self.ledMatrix.getPattern()
        inner_ring = self.bool_list_to_numpy(self._widget.toggle_inner_ring())
        if self._widget.ButtonInnerRing.isChecked():
            # previous_pattern or inner_ring
            self.ledMatrix.setPattern(pattern=np.logical_or(pattern,inner_ring))
        else:
            # previous_pattern nor inner_ring
            self.ledMatrix.setPattern(pattern=np.logical_and(pattern,np.logical_not(inner_ring)))

    @APIExport()
    def toggle_outer_ring(self):
        pattern = self.ledMatrix.getPattern()
        outer_ring = self.bool_list_to_numpy(self._widget.toggle_outer_ring())
        if self._widget.ButtonOuterRing.isChecked():
            # previous_pattern or outer_ring
            self.ledMatrix.setPattern(pattern=np.logical_or(pattern,outer_ring))
        else:
            # previous_pattern nor inner_ring
            self.ledMatrix.setPattern(pattern=np.logical_and(pattern,np.logical_not(outer_ring)))

    @APIExport()
    def togglePattern(self):
        self.current_widget_pattern = self._widget.get_widget_pattern()
        if self.ledMatrix.getPattern().any():
            self.ledMatrix.setPattern(pattern=self.current_pattern*0)
        else:
            led_pattern = self.get_pattern_from_widget()
            self.ledMatrix.setPattern(pattern=led_pattern)

    def bool_list_to_numpy(self, led_pattern: List[bool] = None):
        return np.vstack([[1, 1, 1] if i else [0, 0, 0] for i in led_pattern])

    def get_pattern_from_widget(self):
        return self.bool_list_to_numpy(self.current_widget_pattern)

    @APIExport()
    def setAllLEDOn(self):
        self.setAllLED(state=(1,1,1))

    @APIExport()
    def setAllLEDOff(self):
        self.setAllLED(state=(0,0,0))

    @APIExport()
    def setAllLED(self, state=None, intensity=None):
        if intensity is not None:
            self.setIntensity(intensity=intensity)
        self.ledMatrix.setAll(state=state)
        for coords, btn in self._widget.leds.items():
            if isinstance(btn, guitools.BetterPushButton):
                btn.setChecked(np.sum(state)>0)

    @APIExport()
    def setIntensity(self, intensity=None):
        if intensity is None:
            intensity = int(self._widget.slider.value()//1)
        else:
            # this is only if the GUI/API is calling this function
            intensity = int(intensity)

        self.ledMatrix.setLEDIntensity(intensity=(intensity,intensity,intensity))

    @APIExport()
    def setLED(self, LEDid, state=None):
        self._ledmatrixMode = "single"
        self.ledMatrix.setLEDSingle(indexled=int(LEDid), state=state)
        pattern = self.ledMatrix.getPattern()
        self._widget.leds[str(LEDid)].setChecked(state)

    def connect_leds(self):
        """Connect leds (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        for coords, btn in self._widget.leds.items():
            # Connect signals
            if isinstance(btn, guitools.BetterPushButton):
                btn.clicked.connect(partial(self.setLED, coords))


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
