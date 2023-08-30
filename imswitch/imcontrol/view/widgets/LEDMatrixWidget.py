from qtpy import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QPushButton, QColorDialog
from PyQt5.QtGui import QPainter, QColor, QPixmap, QIcon

from imswitch.imcontrol.view import guitools as guitools
from .basewidgets import Widget
from imswitch.imcommon.model import initLogger


class LEDMatrixWidget(Widget):
    """ Widget in control of the piezo movement. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.pars = {}
        self.grid = QtWidgets.QGridLayout()
        self.setLayout(self.grid)
        self.current_pattern = None
        self.__logger = initLogger(self, instanceName="LEDMatrixWidget")
    # TODO: remove hardcode with size/Nx,Ny

    def add_matrix_view(self, nLedsX = 4, nLedsY=6):
        """Create matrix Layout Interface"""

        # Create dictionary to hold buttons
        self.leds = {}
        # Create grid layout for leds (buttons)
        gridLayout = self.grid

        # Create dictionary to store well names (button texts)
        buttons = self.get_spiral_pattern_buttons()

        # for ix in range(nLedsX):
        #     for iy in range(nLedsY):
        #         buttons[str(nLedsX*iy+ix)]=(ix,iy)

        # Create leds (buttons) and add them to the grid layout
        for corrds, pos in buttons.items():
            self.leds[corrds] = guitools.BetterPushButton(corrds)
            self.leds[corrds].setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                            QtWidgets.QSizePolicy.Expanding)
            self.leds[corrds].setCheckable(True)
            self.leds[corrds].setStyleSheet("""background-color: grey;
                                            font-size: 15px""")
            self.leds[corrds].setMaximumHeight(25)
            self.leds[corrds].setMaximumWidth(25)
            # Add button/label to layout
            gridLayout.addWidget(self.leds[corrds], pos[0], pos[1])

        self.ButtonAllOn = guitools.BetterPushButton("All On")
        self.ButtonAllOn.setMaximumHeight(25)
        gridLayout.addWidget(self.ButtonAllOn, 0, nLedsY, 1, 1)

        self.ButtonAllOff = guitools.BetterPushButton("All Off")
        self.ButtonAllOff.setMaximumHeight(25)
        gridLayout.addWidget(self.ButtonAllOff, 1, nLedsY, 1, 1)

        self.ButtonSubmit = guitools.BetterPushButton("Submit")
        self.ButtonSubmit.setMaximumHeight(25)
        gridLayout.addWidget(self.ButtonSubmit, 2, nLedsY, 1, 1)

        self.ButtonToggle = guitools.BetterPushButton("Toggle")
        self.ButtonToggle.setMaximumHeight(25)
        gridLayout.addWidget(self.ButtonToggle, 3, nLedsY, 1, 1)

        self.ButtonInnerRing = guitools.BetterPushButton("Inner")
        self.ButtonInnerRing.setMaximumHeight(25)
        self.ButtonInnerRing.setCheckable(True)
        gridLayout.addWidget(self.ButtonInnerRing, 0, nLedsY+1, 1, 1)

        self.ButtonOuterRing = guitools.BetterPushButton("Outer")
        self.ButtonOuterRing.setMaximumHeight(25)
        self.ButtonOuterRing.setCheckable(True)
        gridLayout.addWidget(self.ButtonOuterRing, 1, nLedsY+1, 1, 1)

        self.ButtonColorDialog = guitools.BetterPushButton("Select color")
        gridLayout.addWidget(self.ButtonColorDialog, 2, nLedsY+1, 1, 1)
        self.ColorLabelRGBValue = QtWidgets.QLabel("")
        gridLayout.addWidget(self.ColorLabelRGBValue, 3, nLedsY+1, 1, 1)

        self.slider = guitools.FloatSlider(QtCore.Qt.Horizontal, self, allowScrollChanges=False,
                                           decimals=1)
        self.slider.setFocusPolicy(QtCore.Qt.NoFocus)

        self.slider.setMinimum(0)
        self.slider.setMaximum(255)
        self.slider.setTickInterval(5)
        self.slider.setSingleStep(5)
        self.slider.setValue(0)
        gridLayout.addWidget(self.slider, nLedsX, 0, 1, nLedsY+1)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Expanding)        # Add button layout to base well layout
        self.setLayout(gridLayout)

    def get_rgb_from_dialog(self):
        self.SelectedColor =  ColorDialog().getColor()
        r,g,b = self.SelectedColor.redF(), self.SelectedColor.greenF(), self.SelectedColor.blueF()
        self.ColorLabelRGBValue.setText(f"R: {r:.2f}, G: {g:.2f}, B: {b:.2f}")
        return (r,g,b)

    def _getParNameSuffix(self, positionerName, axis):
        return f'{positionerName}--{axis}'

    def get_spiral_pattern_buttons(self):
        buttons = {}
        size = 5
        center = size // 2  # Center of the matrix
        # Define the order of movements: right, down, left, up
        movements = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        current_x, current_y = center, center
        buttons["0"] = (current_x, current_y)
        num = 1
        movement_index = 0
        steps = 1
        while num < size * size:
            movement = movements[movement_index % 4]
            for _ in range(steps):
                current_x += movement[0]
                current_y += movement[1]
                buttons[str(num)] = (current_x, current_y)
                num += 1
            if movement_index % 2 == 1:  # Increase steps every two movements
                steps += 1
            movement_index += 1
        first_coord = buttons[str(9)]
        for num in range(9,size*size):
            buttons[str(num)] = buttons[str(num+1)]
        buttons[str(size*size-1)] = first_coord
        buttons.pop(str(size*size))
        return buttons

    def get_widget_pattern(self):
        return [i_led.isChecked() for i_led in self.leds.values()]

    def toggle_inner_ring(self):
        if self.ButtonInnerRing.isChecked():
            for i_led in list(range(1, 9)):
                self.leds[str(i_led)].setChecked(True)
        else:
            for i_led in list(range(1, 9)):
                self.leds[str(i_led)].setChecked(False)
        return self.inner_ring_mask

    def toggle_outer_ring(self):
        glare_leds = [15]
        if self.ButtonOuterRing.isChecked():
            for i_led in list(range(9, 25)):
                if i_led not in glare_leds:
                    self.leds[str(i_led)].setChecked(True)
        else:
            for i_led in list(range(9, 25)):
                if i_led not in glare_leds:
                    self.leds[str(i_led)].setChecked(False)
        return self.outer_ring_mask

    @property
    def inner_ring_mask(self):
        return [i_led if 1<=i_led<9 else False for i_led in list(range(25))]

    @property
    def outer_ring_mask(self):
        glare_leds = [15]
        return [i_led if (9<=i_led<25 and i_led not in glare_leds) else False for i_led in list(range(25))]


class ColorDialog(QtWidgets.QColorDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOptions(self.options() | QtWidgets.QColorDialog.DontUseNativeDialog)

        # for children in self.findChildren(QtWidgets.QWidget):
        #     classname = children.metaObject().className()
        #     if classname not in ("QColorPicker","QSpinBox", "QColorLuminancePicker", "QColorShowLabel", "QColorShower", "QLabel"):
        #         children.hide()

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
