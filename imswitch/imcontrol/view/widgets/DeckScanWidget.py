import csv

import pyqtgraph as pg
from imswitch.imcontrol.view import guitools as guitools
from imswitch.imcontrol.view.widgets.DeckWidget import TableWidgetDragRows
from qtpy import QtCore, QtWidgets

from .basewidgets import NapariHybridWidget


class DeckScanWidget(NapariHybridWidget):
    """ Widget in control of the piezo movement. """
    sigStepUpClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigStepDownClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigsetSpeedClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigGoToClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigAddCurrentClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigAdjustFocusClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigAddClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigPresetSelected = QtCore.Signal(str)  # (presetName)
    sigLoadPresetClicked = QtCore.Signal()
    sigSavePresetClicked = QtCore.Signal()
    sigSavePresetAsClicked = QtCore.Signal()
    sigDeletePresetClicked = QtCore.Signal()
    sigPresetScanDefaultToggled = QtCore.Signal()


    sigScanInitFilterPos = QtCore.Signal(bool)  # (enabled)
    sigScanShowLast = QtCore.Signal(bool)  # (enabled)
    sigScanStop = QtCore.Signal(bool)  # (enabled)
    sigScanStart = QtCore.Signal(bool)  # (enabled)

    sigShowToggled = QtCore.Signal(bool)  # (enabled)
    sigPIDToggled = QtCore.Signal(bool)  # (enabled)
    sigUpdateRateChanged = QtCore.Signal(float)  # (rate)

    sigSliderLEDValueChanged = QtCore.Signal(float)  # (value)

    def update_z_autofocus(self, value):
        self.z_focus = value
        self.autofocusInitial.selectAll()
        self.autofocusInitial.insert(str(value))
        # TODO: could update the whole table: z_focus and absolute_values

    def update_scan_list(self, scan_list):
        self.scan_list.clear_scan_list()
        self.scan_list.set_header()
        for row_i, row_values in enumerate(scan_list):
            self.scan_list.add_row_in_widget(row_i, row_values)
            self.scan_list_items += 1

    def get_all_positions(self):
        # TODO: implement. Return amount of positions for now.
        return self.scan_list_items

    def init_scan_list(self): #, detectorName, detectorModel, detectorParameters, detectorActions,supportedBinnings, roiInfos):
        self.scan_list = TableWidgetDragRows()
        self.scan_list.setColumnCount(5)
        self.scan_list.setHorizontalHeaderLabels(["Slot", "Well","Offset", "Z_focus","Absolute"])
        self.scan_list_items = 0
        # self.scan_list.setEditTriggers(self.scan_list.NoEditTriggers)
        self.buttonOpen = guitools.BetterPushButton('Open')
        self.buttonSave = guitools.BetterPushButton('Save')
        self.buttonOpen.setStyleSheet("background-color : gray; color: black")
        self.buttonSave.setStyleSheet("background-color : gray; color: black")

        self.grid.addWidget(self.scan_list,12, 0, 1, 8)
        self.grid.addWidget(self.buttonOpen,11, 0, 1, 1)
        self.grid.addWidget(self.buttonSave,11, 1, 1, 1) # DO not display save here

    def display_open_file_window(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'CSV(*.csv)')
        return path[0]

    def display_save_file_window(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'CSV(*.csv)')
        return path[0]

    def __post_init__(self):
        # super().__init__(*args, **kwargs)
        self.ScanFrame = pg.GraphicsLayoutWidget()
        # initialize all GUI elements
        # period
        self.ScanLabelTimePeriod = QtWidgets.QLabel('Period T:') # TODO: change for a h:m:s Widget
        self.ScanLabelTimePeriodHours = QtWidgets.QLabel('Hours')
        self.ScanLabelTimePeriodMinutes = QtWidgets.QLabel('Minutes')
        self.ScanLabelTimePeriodSeconds = QtWidgets.QLabel('Seconds')

        self.ScanValueTimePeriodHours = QtWidgets.QLineEdit('0')
        self.ScanValueTimePeriodMinutes = QtWidgets.QLineEdit('0')
        self.ScanValueTimePeriodSeconds = QtWidgets.QLineEdit('0')
        self.ScanValueTimePeriodHours.setFixedWidth(30)
        self.ScanValueTimePeriodMinutes.setFixedWidth(30)
        self.ScanValueTimePeriodSeconds.setFixedWidth(30)

        # duration
        self.ScanLabelRounds = QtWidgets.QLabel('N° Rounds:')
        self.ScanValueRounds = QtWidgets.QLineEdit('1')
        self.ScanValueRounds.setFixedWidth(30)

        # z-stack
        self.ScanDoZStack = QtWidgets.QCheckBox('Perform Z-Stack')
        self.ScanDoZStack.setCheckable(True)
        self.ScanDoZStack.stateChanged.connect(self.open_z_stack_options)
        # autofocus
        self.autofocusLabel = QtWidgets.QLabel('Autofocus (range, steps, every n-th round): ')
        self.autofocusRange = QtWidgets.QLineEdit('0.5')
        self.autofocusSteps = QtWidgets.QLineEdit('0.05')
        self.autofocusPeriod = QtWidgets.QLineEdit('1')
        self.autofocusInitial = QtWidgets.QLineEdit('0')
        self.z_focus = float(self.autofocusInitial.text())
        self.ScanLabelSampleDepth = QtWidgets.QLabel('Sample Depth [um]:')
        self.ScanValueSampleDepth = QtWidgets.QLineEdit('0')
        self.ScanLabelNSlices = QtWidgets.QLabel('N° Slices:')
        self.ScanValueNSlices = QtWidgets.QLineEdit('5')
        self.ScanLabelSampleDepth.setHidden(True)
        self.ScanValueSampleDepth.setHidden(True)
        self.ScanValueSampleDepth.setFixedWidth(30)
        self.ScanLabelNSlices.setHidden(True)
        self.ScanValueNSlices.setHidden(True)
        self.ScanValueNSlices.setFixedWidth(30)

        self.autofocusLED1Checkbox = QtWidgets.QCheckBox('LED 1')
        self.autofocusLED1Checkbox.setCheckable(True)

        self.autofocusSelectionLabel = QtWidgets.QLabel('Lightsource for AF: ')
        self.autofocusInitialZLabel = QtWidgets.QLabel('Autofocus (Initial Z): ')
        # LED
        valueDecimalsLED = 1
        valueRangeLED = (0, 2 ** 8)
        tickIntervalLED = 1
        singleStepLED = 1

        self.sliderLED, self.LabelLED = self.setupSliderGui('Intensity (LED):', valueDecimalsLED, valueRangeLED,
                                                          tickIntervalLED, singleStepLED)
        self.ValueLED = QtWidgets.QLabel("0 %")
        self.sliderLED.valueChanged.connect(
            lambda value: self.sigSliderLEDValueChanged.emit(value)
        )
        # Scan buttons
        self.ScanLabelFileName = QtWidgets.QLabel('Experiment Name:')
        self.ScanEditFileName = QtWidgets.QLineEdit('Scan')
        # Info
        self.ScanInfoLabel = QtWidgets.QLabel('Experiment info:')
        self.ScanInfoLabel.setHidden(True)
        self.ScanInfoStartTime = QtWidgets.QLabel('Started at: ')
        self.ScanInfoStartTime.setHidden(True)
        self.ScanInfoRoundStartTime = QtWidgets.QLabel('Current round started at: ')
        self.ScanInfoRoundStartTime.setHidden(True)
        self.ScanInfoTimeToNextRound = QtWidgets.QLabel('Next round in: ')
        self.ScanInfoTimeToNextRound.setHidden(True)
        self.ScanInfoNRounds = QtWidgets.QLabel('i/N')
        self.ScanInfoNRounds.setHidden(True)
        self.ScanInfoCurrentWell = QtWidgets.QLabel('Scanning well: ')
        self.ScanInfoCurrentWell.setHidden(True)

        self.ScanStartButton = guitools.BetterPushButton('Start')
        self.ScanStartButton.setCheckable(False)
        self.ScanStartButton.toggled.connect(self.sigScanStart)
        self.ScanStopButton = guitools.BetterPushButton('Stop')
        self.ScanStopButton.setCheckable(False)
        self.ScanStopButton.toggled.connect(self.sigScanStop)
        self.ScanShowLastButton = guitools.BetterPushButton('Show Last')
        self.ScanShowLastButton.setCheckable(False)
        self.ScanShowLastButton.toggled.connect(self.sigScanShowLast)
        # Defining layout
        self.grid = QtWidgets.QGridLayout()
        self.setLayout(self.grid)

        self.grid.addWidget(self.ScanLabelFileName, 0, 0, 1, 1)
        self.grid.addWidget(self.ScanEditFileName, 0, 1, 1, 2)
        self.grid.addWidget(self.ScanLabelRounds, 0, 3, 1, 2)
        self.grid.addWidget(self.ScanValueRounds, 0, 5, 1, 2)

        self.grid.addWidget(self.ScanLabelTimePeriod, 1, 1, 1, 1)
        self.grid.addWidget(self.ScanValueTimePeriodHours, 1, 2, 1, 1)
        self.grid.addWidget(self.ScanLabelTimePeriodHours, 1, 3, 1, 1)
        self.grid.addWidget(self.ScanValueTimePeriodMinutes, 1, 4, 1, 1)
        self.grid.addWidget(self.ScanLabelTimePeriodMinutes, 1, 5, 1, 1)
        self.grid.addWidget(self.ScanValueTimePeriodSeconds, 1, 6, 1, 1)
        self.grid.addWidget(self.ScanLabelTimePeriodSeconds, 1, 7, 1, 1)

        self.grid.addWidget(self.LabelLED, 2, 1, 1, 1)
        self.grid.addWidget(self.ValueLED, 2, 2, 1, 1)
        self.grid.addWidget(self.sliderLED, 2, 3, 1, 4)

        self.grid.addWidget(self.ScanDoZStack, 3, 0, 1, 1)
        self.grid.addWidget(self.ScanLabelSampleDepth, 3, 1, 1, 1)
        self.grid.addWidget(self.ScanValueSampleDepth, 3, 2, 1, 1)
        self.grid.addWidget(self.ScanLabelNSlices, 3, 3, 1, 1)
        self.grid.addWidget(self.ScanValueNSlices, 3, 4, 1, 1)
        # filesettings
        self.grid.addWidget(self.ScanInfoLabel, 6, 0, 1, 5)
        self.grid.addWidget(self.ScanInfoNRounds, 8, 0, 1, 2)
        self.grid.addWidget(self.ScanInfoStartTime, 7, 0, 1, 2)
        self.grid.addWidget(self.ScanInfoRoundStartTime, 7, 4, 1, 2)
        self.grid.addWidget(self.ScanInfoTimeToNextRound, 8, 4, 1, 2)
        self.grid.addWidget(self.ScanInfoCurrentWell, 8, 2, 1, 2)

        # autofocus
        # self.grid.addWidget(self.autofocusLabel, 8, 0, 1, 1)
        # self.grid.addWidget(self.autofocusRange, 8, 1, 1, 1) # Do not show for now. We don't use AF yet
        # self.grid.addWidget(self.autofocusSteps, 8, 2, 1, 1)
        # self.grid.addWidget(self.autofocusPeriod, 8, 3, 1, 1)
        self.grid.addWidget(self.autofocusInitialZLabel, 5, 3, 1, 2)
        self.grid.addWidget(self.autofocusInitial, 5, 5, 1, 2)
        # self.grid.addWidget(self.autofocusSelectionLabel, 9, 2, 1, 1)
        # self.grid.addWidget(self.autofocusLED1Checkbox, 9, 3, 1, 1)
        # start stop
        self.grid.addWidget(self.ScanStartButton, 5, 0, 2, 1)
        self.grid.addWidget(self.ScanStopButton, 5, 1, 2, 1)
        self.grid.addWidget(self.ScanShowLastButton, 5, 2, 2, 1)
        self.layer = None

        self.init_scan_list()


    def isAutofocus(self):
        if self.autofocusLED1Checkbox.isChecked():
            return True
        else:
            return False

    def getAutofocusValues(self):
        autofocusParams = {}
        autofocusParams["valueRange"] = self.autofocusRange.text()
        autofocusParams["valueSteps"] = self.autofocusSteps.text()
        autofocusParams["valuePeriod"] = self.autofocusPeriod.text()
        autofocusParams["valueInitial"] = self.autofocusInitial.text()
        if self.autofocusLED1Checkbox.isChecked():
            autofocusParams["illuMethod"] = 'LED'
        else:
            autofocusParams["illuMethod"] = False

        return autofocusParams

    def setupSliderGui(self, label, valueDecimals, valueRange, tickInterval, singleStep):
        ScanLabel = QtWidgets.QLabel(label)
        valueRangeMin, valueRangeMax = valueRange
        slider = guitools.FloatSlider(QtCore.Qt.Horizontal, self, allowScrollChanges=False,
                                      decimals=valueDecimals)
        slider.setFocusPolicy(QtCore.Qt.NoFocus)
        slider.setMinimum(valueRangeMin)
        slider.setMaximum(valueRangeMax)
        slider.setTickInterval(tickInterval)
        slider.setSingleStep(singleStep)
        slider.setValue(0)
        return slider, ScanLabel

    def getImage(self):
        if self.layer is not None:
            return self.img.image

    def setImage(self, im, colormap="gray", name="", pixelsize=(1, 1, 1), translation=(0, 0, 0)):
        if len(im.shape) == 2:
            translation = (translation[0], translation[1])
        if self.layer is None or name not in self.viewer.layers:
            self.layer = self.viewer.add_image(im, rgb=False, colormap=colormap,
                                               scale=pixelsize, translate=translation,
                                               name=name, blending='additive')
        self.layer.data = im

    def open_z_stack_options(self):
        if bool(self.ScanDoZStack.isChecked()):
            # z-stack
            self.ScanLabelSampleDepth.setHidden(False)
            self.ScanValueSampleDepth.setHidden(False)
            self.ScanLabelNSlices.setHidden(False)
            self.ScanValueNSlices.setHidden(False)
            # self.grid.addWidget(self.ScanValueZmin, 1, 1, 1, 1) # Just use sample depth
        else:
            self.ScanLabelSampleDepth.setHidden(True)
            self.ScanValueSampleDepth.setHidden(True)
            self.ScanLabelNSlices.setHidden(True)
            self.ScanValueNSlices.setHidden(True)
        self.setLayout(self.grid)

    def getZStackValues(self):
        valueZdepth = float(self.ScanValueSampleDepth.text())
        valueZslices = float(self.ScanValueNSlices.text())
        valueZenabled = bool(self.ScanDoZStack.isChecked())

        return valueZdepth, valueZslices, valueZenabled

    def getTimelapseValues(self):
        h = float(self.ScanValueTimePeriodHours.text())
        m = float(self.ScanValueTimePeriodMinutes.text())
        s = float(self.ScanValueTimePeriodSeconds.text())
        ScanValueTimePeriod = h*3600 + m*60 + s # Total Time Period in seconds

        ScanValueRounds = int(self.ScanValueRounds.text())
        return ScanValueTimePeriod, ScanValueRounds

    def getFilename(self):
        ScanEditFileName = self.ScanEditFileName.text()
        return ScanEditFileName

    def setNImages(self, nRounds):
        nRounds2Do = self.getTimelapseValues()[-1]
        self.ScanInfoNRounds.setHidden(False)
        self.ScanInfoNRounds.setText(f'Rounds: {str(nRounds)}/{str(nRounds2Do)}')

    def update_widget_text(self, widget, text):
        widget.setHidden(False)
        widget.setText(text)

    def show_info(self, info):
        self.ScanInfoLabel.setHidden(False)
        self.update_widget_text(self.ScanInfoLabel, info)

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