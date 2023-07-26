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

    def display_open_file_window(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'CSV(*.csv)')
        return path[0]

    def display_save_file_window(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'CSV(*.csv)')
        return path[0]

    def init_scan_config_widget(self, options=(0, 0, 1, 1)):
        # Scan buttons
        experiment_configuration_layout = QtWidgets.QGridLayout()
        self.ScanConfigurationWidget = QtWidgets.QGroupBox("Experiment Configuration")

        self.ScanLabelFileName = QtWidgets.QLabel('Experiment Name:')
        self.ScanEditFileName = QtWidgets.QLineEdit('Scan')
        experiment_configuration_layout.addWidget(self.ScanLabelFileName, 0, 0, 1, 1)
        experiment_configuration_layout.addWidget(self.ScanEditFileName, 0, 1, 1, 3)
        # duration N
        self.ScanRoundsWidget = QtWidgets.QGroupBox("N° Rounds:")
        scan_rounds_layout = QtWidgets.QHBoxLayout()
        self.ScanLabelRounds = QtWidgets.QLabel('N° Rounds:')
        # self.ScanValueRounds = QtWidgets.QLineEdit('1')
        self.ScanValueRounds = QtWidgets.QSpinBox()
        self.ScanValueRounds.setMinimum(1)
        # self.ScanValueRounds.setFixedWidth(30)
        # scan_rounds_layout.addWidget(self.ScanLabelRounds, 0, 3, 1, 2)
        scan_rounds_layout.addWidget(self.ScanValueRounds)
        self.ScanRoundsWidget.setLayout(scan_rounds_layout)
        experiment_configuration_layout.addWidget(self.ScanRoundsWidget, 1,0,1,1)
        # duration T
        self.PeriodWidget = QtWidgets.QGroupBox("Period T:")
        period_layout = QtWidgets.QHBoxLayout()
        self.ScanLabelTimePeriodHours = QtWidgets.QLabel('Hours')
        self.ScanLabelTimePeriodMinutes = QtWidgets.QLabel('Minutes')
        self.ScanLabelTimePeriodSeconds = QtWidgets.QLabel('Seconds')
        self.ScanValueTimePeriodHours = QtWidgets.QSpinBox()
        self.ScanValueTimePeriodHours.setMinimum(0)
        self.ScanValueTimePeriodMinutes = QtWidgets.QSpinBox()
        self.ScanValueTimePeriodMinutes.setMinimum(0)
        self.ScanValueTimePeriodMinutes.setMaximum(59)
        self.ScanValueTimePeriodSeconds = QtWidgets.QSpinBox()
        self.ScanValueTimePeriodSeconds.setMinimum(0)
        self.ScanValueTimePeriodSeconds.setMaximum(59)
        period_layout.addWidget(self.ScanLabelTimePeriodHours)
        period_layout.addWidget(self.ScanValueTimePeriodHours)
        period_layout.addWidget(self.ScanLabelTimePeriodMinutes)
        period_layout.addWidget(self.ScanValueTimePeriodMinutes)
        period_layout.addWidget(self.ScanLabelTimePeriodSeconds)
        period_layout.addWidget(self.ScanValueTimePeriodSeconds)
        self.PeriodWidget.setLayout(period_layout)
        experiment_configuration_layout.addWidget(self.PeriodWidget, 1, 1, 1, 3)
        # LED
        led_layout = QtWidgets.QHBoxLayout()
        self.LEDWidget = QtWidgets.QGroupBox()
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
        led_layout.addWidget(self.LabelLED)
        led_layout.addWidget(self.ValueLED)
        led_layout.addWidget(self.sliderLED, 3)
        self.LEDWidget.setLayout(led_layout)
        experiment_configuration_layout.addWidget(self.LEDWidget, 2,0,1,4)
        self.ScanConfigurationWidget.setLayout(experiment_configuration_layout)
        self.main_grid_layout.addWidget(self.ScanConfigurationWidget, *options)

    def init_zstack_config_widget(self, options=(1, 0, 1, 4)):
        # z-stack
        zstack_configuration_layout = QtWidgets.QHBoxLayout()
        self.ZStackConfigurationWidget = QtWidgets.QGroupBox("Z-Stack Configuration")
        self.ScanDoZStack = QtWidgets.QCheckBox('Perform Z-Stack')
        self.ScanDoZStack.setCheckable(True)
        self.ScanDoZStack.stateChanged.connect(self.open_z_stack_options)
        self.ScanLabelSampleDepth = QtWidgets.QLabel('Sample Depth [um]:')
        self.ScanValueSampleDepth = QtWidgets.QLineEdit('0')
        self.ScanLabelNSlices = QtWidgets.QLabel('N° Slices:')
        # self.ScanValueNSlices = QtWidgets.QLineEdit('5')
        self.ScanValueNSlices = QtWidgets.QSpinBox()
        self.ScanValueNSlices.setMinimum(2)
        self.ScanLabelSampleDepth.setHidden(True)
        self.ScanValueSampleDepth.setHidden(True)
        self.ScanLabelNSlices.setHidden(True)
        self.ScanValueNSlices.setHidden(True)
        zstack_configuration_layout.addWidget(self.ScanDoZStack)
        zstack_configuration_layout.addWidget(self.ScanLabelSampleDepth)
        zstack_configuration_layout.addWidget(self.ScanValueSampleDepth)
        zstack_configuration_layout.addWidget(self.ScanLabelNSlices)
        zstack_configuration_layout.addWidget(self.ScanValueNSlices)
        self.ZStackConfigurationWidget.setLayout(zstack_configuration_layout)
        self.main_grid_layout.addWidget(self.ZStackConfigurationWidget, *options)

    def init_autofocus_config_widget(self, options=(2, 0, 1, 1)):
        # autofocus
        autofocus_configuration_layout = QtWidgets.QGridLayout()
        self.AutofocusConfigurationWidget = QtWidgets.QGroupBox("Autofocus Configuration")
        self.autofocusLabel = QtWidgets.QLabel('Autofocus (range, steps, every n-th round): ')
        self.autofocusRange = QtWidgets.QLineEdit('0.5')
        self.autofocusSteps = QtWidgets.QLineEdit('0.05')
        self.autofocusPeriod = QtWidgets.QLineEdit('1')
        self.autofocusInitial = QtWidgets.QLineEdit('0')
        self.autofocusLED1Checkbox = QtWidgets.QCheckBox('LED 1')
        self.autofocusLED1Checkbox.setCheckable(True)
        self.autofocusSelectionLabel = QtWidgets.QLabel('Lightsource for AF: ')
        self.autofocusInitialZLabel = QtWidgets.QLabel('Autofocus (Initial Z): ')
        self.z_focus = float(self.autofocusInitial.text())
        autofocus_configuration_layout.addWidget(self.autofocusLabel, 0, 0, 1, 1)
        autofocus_configuration_layout.addWidget(self.autofocusRange, 0, 1, 1, 1)
        autofocus_configuration_layout.addWidget(self.autofocusSteps, 0, 2, 1, 1)
        autofocus_configuration_layout.addWidget(self.autofocusPeriod, 0, 3, 1, 1)
        autofocus_configuration_layout.addWidget(self.autofocusInitialZLabel, 1, 3, 1, 2)
        autofocus_configuration_layout.addWidget(self.autofocusInitial, 1, 5, 1, 2)
        autofocus_configuration_layout.addWidget(self.autofocusSelectionLabel, 2, 2, 1, 1)
        autofocus_configuration_layout.addWidget(self.autofocusLED1Checkbox, 2, 3, 1, 1)
        self.AutofocusConfigurationWidget.setLayout(autofocus_configuration_layout)
        self.AutofocusConfigurationWidget.setHidden(True)
        self.main_grid_layout.addWidget(self.AutofocusConfigurationWidget, *options)

    def init_info_widget(self, options = (3,0,1,1)):
        # Info
        scan_info_layout = QtWidgets.QGridLayout()
        self.ScanInfoWidget = QtWidgets.QGroupBox("Scan Information:")
        self.ScanInfoLabel = QtWidgets.QLabel('Experiment info:')
        self.ScanInfoRoundStartTime = QtWidgets.QLabel('Current round started at: ')
        self.ScanInfoTimeToNextRound = QtWidgets.QLabel('Next round in: ')
        self.ScanInfoNRounds = QtWidgets.QLabel('i/N')
        self.ScanInfoCurrentWell = QtWidgets.QLabel('Scanning well: ')
        scan_info_layout.addWidget(self.ScanInfoLabel, 0, 0, 1, 4)
        scan_info_layout.addWidget(self.ScanInfoNRounds, 1, 0, 1, 2)
        scan_info_layout.addWidget(self.ScanInfoRoundStartTime, 1, 2, 1, 2)
        scan_info_layout.addWidget(self.ScanInfoTimeToNextRound, 3, 0, 1, 4)
        scan_info_layout.addWidget(self.ScanInfoCurrentWell, 2, 0, 1, 4)
        self.ScanInfoWidget.setLayout(scan_info_layout)
        [widget.setHidden(True) if widget.isWidgetType() else False for widget in self.ScanInfoWidget.children() ]
        # self.ScanInfoWidget.setHidden(True)
        self.main_grid_layout.addWidget(self.ScanInfoWidget, *options)

    def show_scan_info(self):
        self.ScanInfoWidget.setHidden(False)

    def init_scan_list_widget(self, options = (5,0,1,1)):
        # Scan list
        self.scan_list = TableWidgetDragRows()
        self.scan_list.set_header()
        self.scan_list_items = 0
        self.scan_list.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                     QtWidgets.QSizePolicy.Expanding)
        self.main_grid_layout.addWidget(self.scan_list, *options)

    def init_actions_widget(self, options = (4,0,1,1)):
        # Scan List actions
        scan_list_actions_layout = QtWidgets.QGridLayout()
        self.ScanListActionsWidget = QtWidgets.QGroupBox("Scan List Actions")
        self.scan_list_actions_info = QtWidgets.QLabel("")
        self.scan_list_actions_info.setFixedHeight(20)
        self.scan_list_actions_info.setHidden(True)
        self.ScanStartButton = guitools.BetterPushButton('Start')
        self.ScanStartButton.setFixedHeight(35)
        self.ScanStartButton.setCheckable(False)
        self.ScanStartButton.toggled.connect(self.sigScanStart)
        self.ScanStopButton = guitools.BetterPushButton('Stop')
        self.ScanStopButton.setFixedHeight(35)
        self.ScanStopButton.setCheckable(False)
        self.ScanStopButton.toggled.connect(self.sigScanStop)
        self.ScanShowLastButton = guitools.BetterPushButton('Show Last')
        self.ScanShowLastButton.setFixedHeight(35)
        self.ScanShowLastButton.setCheckable(False)
        self.ScanShowLastButton.toggled.connect(self.sigScanShowLast)
        self.ScanInfoStartTime = QtWidgets.QLabel('')
        self.ScanInfoStartTime.setFixedHeight(20)

        scan_list_actions_layout.addWidget(self.ScanInfoStartTime, 2, 0, 1, 3)

        scan_list_actions_layout.addWidget(self.ScanStartButton, 1, 0, 1, 1)
        scan_list_actions_layout.addWidget(self.ScanStopButton, 1, 1, 1, 1)
        scan_list_actions_layout.addWidget(self.ScanShowLastButton, 1, 2, 1, 1)
        scan_list_actions_layout.addWidget(self.scan_list_actions_info, 0, 0, 1, 3)
        self.ScanListActionsWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                                 QtWidgets.QSizePolicy.Expanding)
        self.ScanListActionsWidget.setMaximumHeight(120)
        self.ScanListActionsWidget.setLayout(scan_list_actions_layout)
        self.main_grid_layout.addWidget(self.ScanListActionsWidget, *options)

    def __post_init__(self):
        # Defining layout
        self.main_grid_layout = QtWidgets.QGridLayout()
        self.setLayout(self.main_grid_layout)
        # super().__init__(*args, **kwargs)
        self.ScanFrame = pg.GraphicsLayoutWidget()
        # initialize all GUI elements
        self.init_scan_config_widget((0, 0, 1, 4))
        self.init_zstack_config_widget((1, 0, 1, 4))
        self.init_autofocus_config_widget((2, 0, 1, 4))
        self.init_info_widget((3, 2, 1, 2))
        self.init_actions_widget((3,0,1,2))
        self.init_scan_list_widget((5,0,1,4))

        self.layer = None

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
            # self.main_grid_layout.addWidget(self.ScanValueZmin, 1, 1, 1, 1) # Just use sample depth
        else:
            self.ScanLabelSampleDepth.setHidden(True)
            self.ScanValueSampleDepth.setHidden(True)
            self.ScanLabelNSlices.setHidden(True)
            self.ScanValueNSlices.setHidden(True)
        self.setLayout(self.main_grid_layout)

    def getZStackValues(self):
        valueZdepth = float(self.ScanValueSampleDepth.text())
        valueZslices = self.ScanValueNSlices.value()
        valueZenabled = bool(self.ScanDoZStack.isChecked())

        return valueZdepth, valueZslices, valueZenabled

    def getTimelapseValues(self):
        h = self.ScanValueTimePeriodHours.value()
        m = self.ScanValueTimePeriodMinutes.value()
        s = self.ScanValueTimePeriodSeconds.value()
        ScanValueTimePeriod = h * 3600 + m * 60 + s  # Total Time Period in seconds
        # ScanValueRounds = int(self.ScanValueRounds.text())
        ScanValueRounds = self.ScanValueRounds.value()
        return ScanValueTimePeriod, ScanValueRounds

    def getFilename(self):
        ScanEditFileName = self.ScanEditFileName.text()
        return ScanEditFileName

    def setNImages(self, nRounds):
        nRounds2Do = self.getTimelapseValues()[-1]
        self.ScanInfoNRounds.setHidden(False)
        self.ScanInfoNRounds.setText(f'Rounds done: {str(nRounds)}/{str(nRounds2Do)}')

    def update_widget_text(self, widget, text):
        widget.setHidden(False)
        widget.setText(text)

    def show_info(self, info):
        if self.ScanInfoLabel.isHidden():
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
