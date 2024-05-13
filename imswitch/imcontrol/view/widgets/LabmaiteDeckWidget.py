import json
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QMessageBox, QFileDialog, QHBoxLayout, QRadioButton, QDialog, QGridLayout, \
    QComboBox, QFrame

from imswitch.imcommon.model import initLogger
from imswitch.imcontrol.view import guitools as guitools
from qtpy import QtCore, QtWidgets, QtGui
from functools import partial

from .basewidgets import Widget, NapariHybridWidget

from locai_app.impl.deck.sd_deck_manager import DeckManager
from config.config_definitions import ZStackParameters


class LabmaiteDeckWidget(NapariHybridWidget):
    """ Widget in control of the piezo movement. """
    sigStepUpClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigStepDownClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigsetSpeedClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigScanStop = QtCore.Signal(bool)  # (enabled)
    sigScanStart = QtCore.Signal(bool)  # (enabled)
    sigScanSave = QtCore.Signal()
    sigScanOpen = QtCore.Signal()

    sigStepAbsoluteClicked = QtCore.Signal(str)
    sigHomeAxisClicked = QtCore.Signal(str, str)
    sigStopAxisClicked = QtCore.Signal(str, str)

    sigZeroZAxisClicked = QtCore.Signal(float)

    sigSliderLEDValueChanged = QtCore.Signal(float)  # (value)
    sigSliderValueChanged = QtCore.Signal(str, float)  # (value)

    sigZScanValue = QtCore.Signal(float)  # (value)

    sigTableSelect = QtCore.Signal(int)
    sigScanInfoTextChanged = QtCore.Signal(str)

    sigPositionUpdate = QtCore.Signal(str, float, float, float)
    sigLabwareSelect = QtCore.Signal(str)
    sigWellSelect = QtCore.Signal(str)

    sigZPositionUpdate = QtCore.Signal(str)

    def __post_init__(self):
        # super().__init__(*args, **kwargs)
        self.setMaximumWidth(800)
        self.setMinimumWidth(600)
        self.numPositioners = 0
        self.pars = {}
        self.main_grid_layout = QtWidgets.QGridLayout()
        self.scan_list = TableWidgetDragRows()  # Initialize empty table
        self.info = ""  # TODO: use QLabel...
        self.current_slot = None
        self.current_well = None
        self.layer = None
        self.__logger = initLogger(self, instanceName="DeckWidget")

    def update_scan_list(self, scan_list):
        # self.scan_list.clear_scan_list()
        self.scan_list.clear()
        self.scan_list.set_header()
        for row_i, row_values in enumerate(scan_list):
            self.scan_list.add_row_in_widget(row_i, row_values)
            self.scan_list_items += 1

    def display_open_file_window(self):
        options = QtWidgets.QFileDialog.Options()

        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'JSON(*.json)', options=options)
        return path[0]

    def display_save_file_window(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'JSON(*.json)')
        return path[0]

    def update_stage_position(self, positioner_name: str, x_pos: float, y_pos: float, z_pos: float):
        self.updatePosition(positioner_name, "X", x_pos)
        self.updatePosition(positioner_name, "Y", y_pos)
        self.updatePosition(positioner_name, "Z", z_pos)

    def addPositioner(self, positionerName, axes, hasSpeed, hasHome=True, hasStop=True, symbols=None,
                      options=(0, 0, 1, 1)):
        self._positioner_widget = QtWidgets.QGroupBox(f"{positionerName}")
        layout = QtWidgets.QGridLayout()
        self.sigPositionUpdate.connect(self.update_stage_position)
        for i in range(len(axes)):
            axis = axes[i]
            parNameSuffix = self._getParNameSuffix(positionerName, axis)
            # label = f'{positionerName} -- {axis}' if positionerName != axis else positionerName
            self.pars['Label' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{axis}</strong>')
            self.pars['Label' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['Position' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{0:.2f} mm</strong>')
            self.pars['Position' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['UpButton' + parNameSuffix] = guitools.BetterPushButton(
                symbols[axis][0] if symbols is not None else "+")
            self.pars['DownButton' + parNameSuffix] = guitools.BetterPushButton(
                symbols[axis][1] if symbols is not None else "-")
            if axis == "Z":
                self.pars['StepEdit' + parNameSuffix] = QtWidgets.QLineEdit('0.1')
            else:
                self.pars['StepEdit' + parNameSuffix] = QtWidgets.QLineEdit('1')
            self.pars['AbsolutePosEdit' + parNameSuffix] = QtWidgets.QLineEdit('0')
            self.pars['AbsolutePosButton' + parNameSuffix] = guitools.BetterPushButton('Go!')

            layout.addWidget(self.pars['Label' + parNameSuffix], self.numPositioners, 0)
            layout.addWidget(self.pars['Position' + parNameSuffix], self.numPositioners, 1)
            layout.addWidget(self.pars['UpButton' + parNameSuffix], self.numPositioners, 2)
            layout.addWidget(self.pars['DownButton' + parNameSuffix], self.numPositioners, 3)
            layout.addWidget(QtWidgets.QLabel('Rel'), self.numPositioners, 4)
            layout.addWidget(self.pars['StepEdit' + parNameSuffix], self.numPositioners, 5)
            layout.addWidget(QtWidgets.QLabel('Abs'), self.numPositioners, 6)

            layout.addWidget(self.pars['AbsolutePosEdit' + parNameSuffix], self.numPositioners, 7)
            layout.addWidget(self.pars['AbsolutePosButton' + parNameSuffix], self.numPositioners, 8)

            if hasSpeed:
                self.pars['Speed' + parNameSuffix] = QtWidgets.QLabel('Speed:')
                self.pars['Speed' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
                self.pars['SpeedEdit' + parNameSuffix] = QtWidgets.QLineEdit(
                    '12') if axis != "Z" else QtWidgets.QLineEdit('8')

                layout.addWidget(self.pars['Speed' + parNameSuffix], self.numPositioners, 9)
                layout.addWidget(self.pars['SpeedEdit' + parNameSuffix], self.numPositioners, 10)

            if hasHome:
                self.pars['Home' + parNameSuffix] = guitools.BetterPushButton('Home')
                layout.addWidget(self.pars['Home' + parNameSuffix], self.numPositioners, 11)

                self.pars['Home' + parNameSuffix].clicked.connect(
                    lambda *args, axis=axis: self.sigHomeAxisClicked.emit(positionerName, axis)
                )

            if hasStop:
                self.pars['Stop' + parNameSuffix] = guitools.BetterPushButton('Stop')
                layout.addWidget(self.pars['Stop' + parNameSuffix], self.numPositioners, 12)

                self.pars['Stop' + parNameSuffix].clicked.connect(
                    lambda *args, axis=axis: self.sigStopAxisClicked.emit(positionerName, axis)
                )

            # Connect signals
            self.pars['UpButton' + parNameSuffix].clicked.connect(
                lambda *args, axis=axis: self.sigStepUpClicked.emit(positionerName, axis)
            )
            self.pars['DownButton' + parNameSuffix].clicked.connect(
                lambda *args, axis=axis: self.sigStepDownClicked.emit(positionerName, axis)
            )
            self.pars['AbsolutePosButton' + parNameSuffix].clicked.connect(
                lambda *args, axis=axis: self.sigStepAbsoluteClicked.emit(axis)
            )

            self.numPositioners += 1

        self._positioner_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                              QtWidgets.QSizePolicy.Expanding)
        self._positioner_widget.setLayout(layout)
        self.main_grid_layout.addWidget(self._positioner_widget, *options)

    def select_well(self, well: str = None):
        if well == self.current_well:
            return
        self.current_well = well
        for well_id, btn in self.wells.items():
            if isinstance(btn, guitools.BetterPushButton):
                if well_id == well:
                    btn.setStyleSheet("background-color: green; font-size: 14px")
                else:
                    btn.setStyleSheet("background-color: grey; font-size: 14px")
        self.beacons_selected_well.setText(f"{self.current_well}")

    def select_labware(self, slot: str = None, options=(1, 0, 3, 3)):
        if slot is None:
            slot = self.slots_combobox.currentText()
        self._select_labware(str(slot), options)
        # self.change_slot_color(slot) # TODO: this causes an infinite recursion...

    def _select_labware(self, slot, options=(1, 0, 3, 3)):
        if slot == self.current_slot:
            return
        self.current_slot = slot
        if hasattr(self, "_wells_group_box"):
            self.main_grid_layout.removeWidget(self._wells_group_box)
        self._wells_group_box = QtWidgets.QGroupBox(f"{self._labware_dict[self.current_slot]}")
        layout = QtWidgets.QGridLayout()

        labware = self._labware_dict[self.current_slot]
        # Create dictionary to hold buttons
        self.wells = {}
        # Create grid layout for wells (buttons)
        well_buttons = {}
        rows = len(self._labware_dict[self.current_slot].rows())
        columns = len(self._labware_dict[self.current_slot].columns())
        for r in list(range(rows)):
            for c in list(range(columns)):
                well_buttons[c + 1] = (0, c + 1)
                well = labware.rows()[r][c]
                well_buttons[well.well_name] = (r + 1, c + 1)
            well_buttons[well.well_name[0]] = (r + 1, 0)
        well_buttons[""] = (0, 0)
        # Create wells (buttons) and add them to the grid layout
        for corrds, pos in well_buttons.items():
            if 0 in pos:
                self.wells[corrds] = QtWidgets.QLabel(text=str(corrds))  # QtWidgets.QPushButton(corrds)
                # self.wells[corrds].setFixedSize(25, 20)
                self.wells[corrds].setMaximumSize(30, 25)
                self.wells[corrds].setStyleSheet("background-color: None; font-size: 12px")
            else:
                self.wells[corrds] = guitools.BetterPushButton(corrds)  # QtWidgets.QPushButton(corrds)
                self.wells[corrds].setMaximumSize(30, 25)
                self.wells[corrds].setStyleSheet("background-color: grey; font-size: 14px")
            self.wells[corrds].setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                             QtWidgets.QSizePolicy.Expanding)
            # Set style for empty cell
            # self.wells[corrds].setStyleSheet("background-color: none")
            # Add button/label to layout
            layout.addWidget(self.wells[corrds], pos[0], pos[1])
        self._wells_group_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                            QtWidgets.QSizePolicy.Expanding)
        # self._wells_group_box.setMinimumSize(100,100)
        self._wells_group_box.setLayout(layout)
        self.main_grid_layout.addWidget(self._wells_group_box, *options)
        self.setLayout(self.main_grid_layout)

    def init_zstack_config_widget(self, default_values_in_mm: ZStackParameters, options=(4, 2, 2, 1)):
        # z-stack
        self.z_height = default_values_in_mm.z_height * 1000
        self.z_sep = default_values_in_mm.z_sep * 1000
        self.z_slices = default_values_in_mm.z_slices

        self.z_stack_config_widget = QtWidgets.QGroupBox("Z-Stack Configuration")
        self.z_stack_config_widget.setMinimumWidth(150)
        self.z_stack_config_widget.setMaximumWidth(180)
        self.z_stack_config_widget.setContentsMargins(0, 0, 0, 0)
        zstack_configuration_layout = QtWidgets.QGridLayout()

        self.z_stack_checkbox_widget = QtWidgets.QCheckBox('Depth/Separation [um]')
        self.z_stack_checkbox_widget.setCheckable(True)
        self.z_stack_checkbox_widget.stateChanged.connect(self.open_z_stack_options)

        self.z_stack_sample_depth_label = QtWidgets.QLabel('Depth:')
        self.z_stack_sample_depth_label.setMaximumWidth(85)
        self.z_stack_sample_depth_value = QtWidgets.QLineEdit()
        self.z_stack_sample_depth_value.setText(f"{self.z_height:.1f}" if self.z_height else str(1))
        self.z_stack_sample_depth_value.setEnabled(True)
        self.z_stack_sample_depth_value.setMaximumWidth(65)
        self.z_stack_sample_depth_value.textChanged.connect(self.calculate_z_stack)  # Connect valueChanged signal

        self.z_stack_slice_sep_label = QtWidgets.QLabel('Separation:')
        self.z_stack_slice_sep_label.setMaximumWidth(95)
        self.z_stack_slice_sep_value = QtWidgets.QLineEdit()
        self.z_stack_slice_sep_value.setText(f"{self.z_sep:.1f}" if self.z_sep else str(1))  # TODO: check
        self.z_stack_slice_sep_value.setEnabled(False)
        self.z_stack_slice_sep_value.setMaximumWidth(65)
        self.z_stack_slice_sep_value.textChanged.connect(self.calculate_z_stack)

        self.z_stack_slices_label = QtWidgets.QLabel('N° Slices:')
        self.z_stack_slices_label.setMaximumWidth(65)
        self.z_stack_slices_value = QtWidgets.QSpinBox()
        self.z_stack_slices_value.setValue(self.z_slices)
        self.z_stack_slices_value.setMaximumWidth(65)
        self.z_stack_slices_value.setMinimum(1)
        self.z_stack_slices_value.setMaximum(1000)
        self.z_stack_slices_value.valueChanged.connect(self.calculate_z_stack)

        zstack_configuration_layout.addWidget(self.z_stack_checkbox_widget, 0, 0, 1, 2)
        zstack_configuration_layout.addWidget(self.z_stack_sample_depth_label, 1, 0, 1, 1)
        zstack_configuration_layout.addWidget(self.z_stack_sample_depth_value, 1, 1, 1, 1)
        zstack_configuration_layout.addWidget(self.z_stack_slice_sep_label, 2, 0, 1, 1)
        zstack_configuration_layout.addWidget(self.z_stack_slice_sep_value, 2, 1, 1, 1)
        zstack_configuration_layout.addWidget(self.z_stack_slices_label, 3, 0, 1, 1)
        zstack_configuration_layout.addWidget(self.z_stack_slices_value, 3, 1, 1, 1)
        self.z_stack_config_widget.setLayout(zstack_configuration_layout)
        self.main_grid_layout.addWidget(self.z_stack_config_widget, *options)
        self.calculate_z_stack()
        self.ScanInfo.setText("")

    def calculate_z_stack(self):
        try:
            if not self.z_stack_checkbox_widget.isChecked():
                self.z_height = float(self.z_stack_sample_depth_value.text())
                self.z_slices = self.z_stack_slices_value.value()
                if self.z_slices < 1:
                    raise ValueError("Number of slices must be greater or equal than 1")
                self.z_sep = self.z_height / self.z_slices
                self.z_stack_slice_sep_value.setText(f"{self.z_sep:.2f}")
            else:
                self.z_sep = float(self.z_stack_slice_sep_value.text())
                self.z_slices = self.z_stack_slices_value.value()
                if self.z_slices < 1:
                    raise ValueError("Number of slices must be greater or equal than 1")
                self.z_height = self.z_sep * self.z_slices
                self.z_stack_sample_depth_value.setText(f"{self.z_height:.1f}")
            self.ScanInfo.setText("Unsaved changes.")
        except Exception as e:
            self.__logger.warning(f"calculate_z_stack:  {e}")

    def get_z_stack_values_in_um(self):
        z_height = float(self.z_stack_sample_depth_value.text())
        z_sep = float(self.z_stack_slice_sep_value.text())
        z_slices = self.z_stack_slices_value.value()
        z_stack_bool = bool(self.z_stack_checkbox_widget.isChecked())
        return z_height, z_sep, z_slices, z_stack_bool

    def open_z_stack_options(self):
        if bool(self.z_stack_checkbox_widget.isChecked()):
            # z-stack
            self.z_stack_sample_depth_value.setEnabled(False)
            self.z_stack_slice_sep_value.setEnabled(True)
            self.z_stack_slice_sep_value.textChanged.connect(self.calculate_z_stack)
            self.z_stack_sample_depth_value.textChanged.disconnect(self.calculate_z_stack)

            # self.main_grid_layout.addWidget(self.ScanValueZmin, 1, 1, 1, 1) # Just use sample depth
        else:
            self.z_stack_sample_depth_value.setEnabled(True)
            self.z_stack_slice_sep_value.setEnabled(False)
            self.z_stack_sample_depth_value.textChanged.connect(self.calculate_z_stack)  # Connect valueChanged signal
            self.z_stack_slice_sep_value.textChanged.disconnect(self.calculate_z_stack)

        self.setLayout(self.main_grid_layout)

    def init_z_scan_widget(self, options=[(3, 3, 1, 2)]):
        self._z_scan_box = QtWidgets.QGroupBox("Z-Scan:")
        layout = QtWidgets.QGridLayout()
        well_base_label = QtWidgets.QLabel("Well base:")
        self.well_base_widget = QtWidgets.QLineEdit('3.00')
        self.well_base_widget.setMaximumWidth(60)
        well_top_label = QtWidgets.QLabel("Well top:")
        self.well_top_widget = QtWidgets.QLineEdit('6.00')
        self.well_top_widget.setMaximumWidth(60)
        self.z_scan_step_label = QtWidgets.QLabel("Step:")
        self.z_scan_step_widget = QtWidgets.QLineEdit('0.25')
        self.z_scan_zpos_label = QtWidgets.QLabel(f"Adjust focus of row {'-'} to ")
        self.z_scan_zpos_widget = QtWidgets.QLineEdit('')
        self.z_scan_adjust_focus_widget = guitools.BetterPushButton("Focus!")
        self.z_scan_step_widget.setMaximumWidth(60)
        self.z_scan_preview_button = guitools.BetterPushButton("Preview")  # QtWidgets.QPushButton(corrds)
        self.z_scan_preview_button.setStyleSheet("font-size: 14px")
        self.z_scan_preview_button.setMinimumWidth(75)
        # self.z_scan_stop_button = guitools.BetterPushButton("Stop")  # QtWidgets.QPushButton(corrds)
        layout.addWidget(well_base_label, 0, 0, 1, 1)
        layout.addWidget(self.well_base_widget, 0, 1, 1, 1)
        layout.addWidget(well_top_label, 1, 0, 1, 1)
        layout.addWidget(self.well_top_widget, 1, 1, 1, 1)
        layout.addWidget(self.z_scan_step_label, 0, 2, 1, 1)
        layout.addWidget(self.z_scan_step_widget, 0, 3, 1, 1)
        layout.addWidget(self.z_scan_preview_button, 1, 2, 1, 2)
        layout.addWidget(self.z_scan_zpos_label, 2, 0, 1, 2)
        layout.addWidget(self.z_scan_zpos_widget, 2, 2, 1, 1)
        layout.addWidget(self.z_scan_adjust_focus_widget, 2, 3, 1, 1)
        # layout.addWidget(self.z_scan_stop_button)
        self._z_scan_box.setLayout(layout)
        self.main_grid_layout.addWidget(self._z_scan_box, *options)
        self.setLayout(self.main_grid_layout)

    def set_preview(self, im, colormap="gray", name="", pixelsize=(1, 1, 1), translation=(0, 0, 0)):
        if len(im.shape) == 2:
            translation = (translation[0], translation[1])
        for layer in self.viewer.layers:  # TODO: only have one preview
            if "Preview" in layer.name:
                self.viewer.layers.remove(layer.name)
        if self.layer is None or name not in self.viewer.layers:
            self.layer = self.viewer.add_image(im, rgb=False, colormap=colormap,
                                               scale=pixelsize, translate=translation,
                                               name=name, blending='additive')
        self.layer.data = im
        # # Connect to the slider
        # # slider_layer = self.viewer.layers[name]
        # self.viewer.dims.events.current_step.connect(self.update_slider)

    def update_slider(self, z_pos, name, event):
        index = event.value[0]
        # TODO: get selected layer.
        # only trigger if update comes from first axis (optional)
        try:
            print(f"Name {name}. Z={z_pos[index]} mm. Length {len(self.viewer.layers[name].data)}")
            self.sigZScanValue.emit(z_pos[index])
        except Exception as e:
            self.__logger.warning(f"Exception: {e}")
        # print(f"Slider index {index} changed to: {event.value[0]}")

    def init_light_sources(self, light_sources, options=(4, 3, 2, 1)):
        # LEDs grid
        self.LEDWidget = QtWidgets.QGroupBox("Lights: [%]")
        self.LEDWidget.setMaximumWidth(110)
        led_layout = QtWidgets.QGridLayout()

        self.light_sources_widgets = {}
        self.light_sources_signals = {}
        for light in light_sources:
            LEDWidget = QtWidgets.QSpinBox()
            LEDWidget.setMaximum(100)
            LEDWidget.setMinimum(0)
            LEDWidget.setMinimumWidth(50)
            LEDWidget.setMaximumWidth(60)
            # LED_spinbox.valueChanged.connect(LED_spinbox, self.led_value_change)
            ledName = f'{light.config.readable_name}'
            nameLabel = QtWidgets.QLabel(ledName)
            led_layout.addWidget(nameLabel, len(self.light_sources_widgets), 0)
            led_layout.addWidget(LEDWidget, len(self.light_sources_widgets), 1)
            self.light_sources_widgets[ledName] = LEDWidget
            self.light_sources_signals[ledName] = QtCore.Signal(float)

            LEDWidget.valueChanged.connect(partial(self.light_intensity_change, ledName))

        self.LEDWidget.setLayout(led_layout)
        self.main_grid_layout.addWidget(self.LEDWidget, *options)

    def light_intensity_change(self, ledName):
        self.sigSliderValueChanged.emit(ledName, self.light_sources_widgets[ledName].value())

    def init_light_source(self, options=(3, 0, 1, 1)):
        # LED
        self.LEDWidget = QtWidgets.QGroupBox()

        led_layout = QtWidgets.QHBoxLayout()
        self.LabelLED = QtWidgets.QLabel("LED Intensity [mA]: ")
        self.LED_spinbox = QtWidgets.QSpinBox()
        self.LED_spinbox.setMaximum(1000)
        self.LED_spinbox.setMinimum(0)
        led_layout.addWidget(self.LabelLED)
        led_layout.addWidget(self.LED_spinbox)
        self.LED_spinbox.valueChanged.connect(self.led_value_change)

        self.LEDWidget.setLayout(led_layout)
        self.main_grid_layout.addWidget(self.LEDWidget, *options)

    def led_value_change(self):
        self.sigSliderLEDValueChanged.emit(self.LED_spinbox.value())

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

    def init_experiment_buttons(self, options=(4, 4, 1, 1)):
        exp_buttons_layout = QtWidgets.QGridLayout()
        self.ScanActionsWidget = QtWidgets.QGroupBox("Scan List Actions")
        self.ScanSaveButton = guitools.BetterPushButton('Save')
        self.ScanSaveButton.setStyleSheet("font-size: 14px")
        self.ScanSaveButton.setFixedHeight(30)
        self.ScanSaveButton.setMaximumWidth(80)
        self.ScanSaveButton.setCheckable(False)
        self.ScanSaveButton.toggled.connect(self.sigScanSave)

        self.ScanOpenButton = guitools.BetterPushButton('Open')
        self.ScanOpenButton.setStyleSheet("font-size: 14px")
        self.ScanOpenButton.setFixedHeight(30)
        self.ScanOpenButton.setMaximumWidth(80)
        self.ScanOpenButton.setCheckable(False)
        self.ScanOpenButton.toggled.connect(self.sigScanOpen)

        self.ScanStartButton = guitools.BetterPushButton('Start')
        self.ScanStartButton.setStyleSheet("background-color: black; font-size: 14px")
        self.ScanStartButton.setFixedHeight(30)
        self.ScanStartButton.setMaximumWidth(80)
        self.ScanStartButton.setCheckable(False)
        self.ScanStartButton.toggled.connect(self.sigScanStart)

        self.ScanStopButton = guitools.BetterPushButton('Stop')
        self.ScanStopButton.setStyleSheet("background-color: gray; font-size: 14px")
        self.ScanStopButton.setFixedHeight(30)
        self.ScanStopButton.setMaximumWidth(80)
        self.ScanStopButton.setCheckable(False)
        self.ScanStopButton.setEnabled(False)
        self.ScanStopButton.toggled.connect(self.sigScanStop)

        self.adjust_all_focus_button = guitools.BetterPushButton('Focus All')
        self.adjust_all_focus_button.setStyleSheet("font-size: 14px")
        self.adjust_all_focus_button.setFixedHeight(30)
        self.adjust_all_focus_button.setMinimumWidth(40)

        self.OffsetsWidgets = QtWidgets.QGroupBox("Offsets")
        self.OffsetsWidgets.setFixedHeight(60)
        offset_buttons_layout = QtWidgets.QGridLayout()

        self.x_offset_all_value = QtWidgets.QLineEdit()
        self.x_offset_all_value.setText(f"{0:.2f}")
        self.x_offset_all_value.setEnabled(True)
        self.x_offset_all_value.setFixedWidth(50)

        self.y_offset_all_value = QtWidgets.QLineEdit()
        self.y_offset_all_value.setText(f"{0:.2f}")
        self.y_offset_all_value.setEnabled(True)
        self.y_offset_all_value.setFixedWidth(50)

        self.adjust_offset_button = guitools.BetterPushButton('Set!')
        self.adjust_offset_button.setStyleSheet("font-size: 14px")
        self.adjust_offset_button.setMinimumWidth(90)

        offset_buttons_layout.addWidget(self.x_offset_all_value, 0, 0, 1, 1)
        offset_buttons_layout.addWidget(self.y_offset_all_value, 0, 1, 1, 1)
        offset_buttons_layout.addWidget(self.adjust_offset_button, 0, 2, 1, 1)
        self.OffsetsWidgets.setLayout(offset_buttons_layout)

        exp_buttons_layout.addWidget(self.ScanStartButton, 0, 0, 1, 1)
        exp_buttons_layout.addWidget(self.ScanStopButton, 0, 1, 1, 1)
        exp_buttons_layout.addWidget(self.ScanSaveButton, 1, 0, 1, 1)
        exp_buttons_layout.addWidget(self.ScanOpenButton, 1, 1, 1, 1)
        exp_buttons_layout.addWidget(self.OffsetsWidgets, 2, 0, 1, 2)
        exp_buttons_layout.addWidget(self.adjust_all_focus_button, 3, 0, 1, 2)

        self.ScanActionsWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                             QtWidgets.QSizePolicy.Expanding)
        self.ScanActionsWidget.setLayout(exp_buttons_layout)
        self.main_grid_layout.addWidget(self.ScanActionsWidget, *options)

    def get_offset_all(self):
        return float(self.x_offset_all_value.text()), float(self.y_offset_all_value.text())

    def update_scan_info_text(self, text):
        self.ScanInfo.setText(text)
        self.ScanInfo.setHidden(False)

    def init_experiment_info(self, options=(8, 0, 1, 1)):
        self.ScanInfo = QtWidgets.QLabel('')
        self.ScanInfo.setWordWrap(True)
        self.sigScanInfoTextChanged.connect(self.update_scan_info_text)
        self.ScanInfo_widget = QtWidgets.QGroupBox("Scan Info")
        self.ScanInfo_widget.setMaximumWidth(200)
        ScanInfo_layout = QtWidgets.QGridLayout()
        ScanInfo_layout.addWidget(self.ScanInfo)
        self.ScanInfo_widget.setLayout(ScanInfo_layout)
        self.main_grid_layout.addWidget(self.ScanInfo_widget, *options)
        self.setLayout(self.main_grid_layout)

    def initialize_deck(self, deck_manager: DeckManager, options=[(1, 0, 3, 3), (2, 4, 1, 1)]):
        self._deck_dict = deck_manager.deck_layout
        self._labware_dict = deck_manager.labwares
        self._deck_group_box = QtWidgets.QGroupBox("")
        self._deck_group_box.setMinimumHeight(40)
        layout = QtWidgets.QHBoxLayout()
        self.sigLabwareSelect.connect(self.select_labware)
        self.sigWellSelect.connect(self.select_well)
        # Create dictionary to hold buttons
        slots = [slot.id for slot in deck_manager.deck_layout.locations.orderedSlots]

        used_slots = list(deck_manager.labwares.keys())
        self.slot_label = QtWidgets.QLabel("Slot: ")
        self.slot_label.setMinimumWidth(40)
        self.slot_label.setMinimumHeight(35)
        self.slot_label.setMaximumHeight(40)
        self.slots_combobox = QtWidgets.QComboBox(self)
        self.slots_combobox.setMinimumWidth(40)
        self.slots_combobox.setMinimumHeight(35)
        self.slots_combobox.setMaximumHeight(40)
        [self.slots_combobox.addItem(f"{s}") for s in used_slots]
        layout.addWidget(self.slot_label)
        layout.addWidget(self.slots_combobox)
        self._deck_group_box.setLayout(layout)
        self.setLayout(layout)
        self.main_grid_layout.addWidget(self._deck_group_box, *options[1])
        self.setLayout(self.main_grid_layout)

    def init_home_button(self, options=(2, 2, 1, 1)):
        self.home_button_widget = QtWidgets.QGroupBox("Stage")
        self.home_button_widget.setMinimumWidth(45)
        self.home_button_widget.setMinimumHeight(50)
        self.home_button_widget.setMaximumHeight(60)
        home_button_layout = QtWidgets.QGridLayout()
        self.home_button = guitools.BetterPushButton(text="HOME")  # QtWidgets.QPushButton(corrds)
        self.home_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.home_button.setMinimumWidth(35)
        self.home_button.setMinimumHeight(30)
        self.home_button.setMaximumHeight(35)
        self.home_button.setStyleSheet("background-color: black; font-size: 14px")
        home_button_layout.addWidget(self.home_button)
        self.home_button_widget.setLayout(home_button_layout)
        self.main_grid_layout.addWidget(self.home_button_widget, *options)
        self.setLayout(self.main_grid_layout)

    def init_park_button(self, options=(2, 2, 1, 1)):
        self.park_button_widget = QtWidgets.QGroupBox("Stage")
        self.park_button_widget.setMinimumWidth(45)
        self.park_button_widget.setMinimumHeight(50)
        self.park_button_widget.setMaximumHeight(60)
        park_button_layout = QtWidgets.QGridLayout()
        self.park_button = guitools.BetterPushButton(text="PARK")  # QtWidgets.QPushButton(corrds)
        self.park_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.park_button.setMinimumWidth(35)
        self.park_button.setMinimumHeight(30)
        self.park_button.setMaximumHeight(35)
        self.park_button.setStyleSheet("background-color: black; font-size: 14px")
        park_button_layout.addWidget(self.park_button)
        self.park_button_widget.setLayout(park_button_layout)
        self.main_grid_layout.addWidget(self.park_button_widget, *options)
        self.setLayout(self.main_grid_layout)

    def update_scan_info(self, dict_info):
        self.ScanInfo.setText(dict_info["experiment_status"])

    def init_well_action(self, options=(1, 3, 2, 1)):
        self.well_action_widget = QtWidgets.QGroupBox("Selected well")
        well_action_layout = QtWidgets.QGridLayout()
        self.beacons_selected_well = QtWidgets.QLabel("<Well>")
        well_action_layout.addWidget(self.beacons_selected_well, 0, 0, 1, 1)

        self.goto_btn = guitools.BetterPushButton('GO TO')
        self.goto_btn.setMaximumHeight(50)
        self.goto_btn.setMaximumWidth(40)
        well_action_layout.addWidget(self.goto_btn, 1, 0, 1, 1)

        self.well_action_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                              QtWidgets.QSizePolicy.Expanding)

        self.well_action_widget.setLayout(well_action_layout)
        self.main_grid_layout.addWidget(self.well_action_widget, *options)
        self.setLayout(self.main_grid_layout)

    def init_scan_list(self, options=(4, 0, 1, 1)):
        self.currentIndex = 0
        self.scan_list_widget = QtWidgets.QGroupBox("Scan List: positions to scan")

        buttons_layout = QtWidgets.QHBoxLayout()
        self.prevButton = guitools.BetterPushButton('Previous')
        self.adjustFocusButton = guitools.BetterPushButton('Focus')
        self.nextButton = guitools.BetterPushButton('Next')
        self.prevButton.clicked.connect(self.prevRow)
        self.prevButton.hide()
        self.nextButton.clicked.connect(self.nextRow)
        self.nextButton.hide()
        buttons_layout.addWidget(self.prevButton)
        buttons_layout.addWidget(self.nextButton)

        self.scan_list = TableWidgetDragRows()
        self.scan_list.set_header()
        self.scan_list_items = 0
        self.scan_list.itemPressed.connect(self.onSelectionChanged)
        # self.scan_list.itemSelectionChanged.connect(self.onSelectionChanged)
        # self.scan_list.setMaximumHeight(500)
        self.scan_list.setMinimumHeight(235)
        self.scan_list.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                     QtWidgets.QSizePolicy.Expanding)

        # Create a vertical layout and add the table and the buttons layout
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.scan_list)
        main_layout.addLayout(buttons_layout)

        self.scan_list_widget.setLayout(main_layout)
        self.main_grid_layout.addWidget(self.scan_list_widget, *options)
        self.setLayout(self.main_grid_layout)

    def onSelectionChanged(self):
        selected_items = self.scan_list.selectedItems()
        if selected_items:
            self.currentIndex = selected_items[0].row()
            self.highlightCurrentRow()
            self.displayRowData()
            self.updateButtonState()

    def displayRowData(self):
        self.sigTableSelect.emit(self.currentIndex)
        print(self.currentIndex)

    def updateButtonState(self):
        if self.currentIndex == 0:
            self.prevButton.setEnabled(False)
        else:
            self.prevButton.setEnabled(True)

        if self.currentIndex == self.scan_list.rowCount() - 1:
            self.nextButton.setEnabled(False)
        else:
            self.nextButton.setEnabled(True)

    def prevRow(self):
        if self.currentIndex > 0:
            self.currentIndex -= 1
            self.displayRowData()
        self.updateButtonState()
        self.highlightCurrentRow()

    def nextRow(self):
        if self.currentIndex < self.scan_list.rowCount() - 1:
            self.currentIndex += 1
            self.displayRowData()
        self.updateButtonState()
        self.highlightCurrentRow()

    def highlightCurrentRow(self):
        for row in range(self.scan_list.rowCount()):
            for col in range(self.scan_list.columnCount()):
                item = self.scan_list.item(row, col)
                if item is not None:
                    if row == self.currentIndex:
                        item.setSelected(True)  # Highlight the current row
                    else:
                        item.setSelected(False)  # Reset other rows

    def _get_items(self):
        rows = []
        for row in range(self.scan_list.rowCount()):
            rowdata = []
            for column in range(self.scan_list.columnCount()):
                item = self.scan_list.item(row, column)
                if item is not None:
                    rowdata.append(item.text())
                else:
                    rowdata.append('')
            rows.append(rowdata)

        return rows

    def confirm_start_run(self):
        reply = QMessageBox.question(self, 'Run Experiment',
                                     f'The unsaved changes wont be reflected in the current run. Are you sure you want to continue?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            return True
        else:
            return False

    def getAbsPosition(self, positionerName, axis):
        """ Returns the absolute position of the  specified positioner axis in
        micrometers. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        return float(self.pars['AbsolutePosEdit' + parNameSuffix].text())

    def getStepSize(self, positionerName, axis):
        """ Returns the step size of the specified positioner axis in
        milimeters. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        return float(self.pars['StepEdit' + parNameSuffix].text())

    def setStepSize(self, positionerName, axis, stepSize):
        """ Sets the step size of the specified positioner axis to the
        specified number of milimeters. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        self.pars['StepEdit' + parNameSuffix].setText(stepSize)

    def getSpeed(self, positionerName, axis):
        """ Returns the step size of the specified positioner axis in
        milimeters. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        return float(self.pars['SpeedEdit' + parNameSuffix].text())

    def setSpeedSize(self, positionerName, axis, speedSize):
        """ Sets the step size of the specified positioner axis to the
        specified number of micrometers. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        self.pars['SpeedEdit' + parNameSuffix].setText(speedSize)

    def updatePosition(self, positionerName, axis, position):
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        self.pars['Position' + parNameSuffix].setText(
            f'<strong>{position:.3f} mm</strong>')

    def updateSpeed(self, positionerName, axis, speed):
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        self.pars['Speed' + parNameSuffix].setText(f'<strong>{speed} mm/s</strong>')

    def _getParNameSuffix(self, positionerName, axis):
        return f'{positionerName}--{axis}'


from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QCheckBox
from PyQt5.QtGui import QPainter, QColor


class MyDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Call the base paint method to draw the item
        super().paint(painter, option, index)

        # If the item is selected, draw the background of the full row
        if option.state & QStyle.State_Selected:
            option = QStyleOptionViewItem(option)
            self.initStyleOption(option, index)
            widget = option.widget
            if widget is None:
                return
            # TODO: fix hardcoded
            # Get the checkbox size
            checkbox_size = widget.cellWidget(index.row(), widget.columns.index("Done")).sizeHint()
            # Get the rect for the checkbox column
            checkbox_rect = widget.visualRect(widget.model().index(index.row(), widget.columns.index("Done")))

            # Draw the background of the selected row including the checkbox column
            selected_color = option.palette.highlight().color()
            selected_rect = option.rect
            selected_rect.setLeft(checkbox_rect.left())  # Adjust the left boundary
            painter.fillRect(selected_rect,
                             QColor(selected_color.red(), selected_color.green(), selected_color.blue(), 50))
            # Draw the background of the selected row
            selected_color = option.palette.highlight().color()
            painter.fillRect(option.rect,
                             QColor(selected_color.red(), selected_color.green(), selected_color.blue(), 50))


from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt5.QtCore import QObject, pyqtSignal


class InitializationWizard(QObject):
    def __init__(self):
        super().__init__()
        self.widget = InitializationWizardWidget()
        self.widget.save_signal.connect(self.save_json_data)
        self.widget.load_signal.connect(self.load_json_data)
        self.widget.load_signal.emit()
        # self.widget.closeEvent.connect(self.load_signal.emit)  # Connect finished signal to save method

    def save_json_data(self, data):
        with open(r"C:\Users\matia_n97ktw5\Documents\LABMaiTE\repositories\ImSwitch\labmaite_config.json", "w") as file:
            json.dump(data, file, indent=4)

    def load_json_data(self):
        data = {}
        try:
            with open(r"C:\Users\matia_n97ktw5\Documents\LABMaiTE\repositories\ImSwitch\labmaite_config.json",
                      "r") as file:
                data = json.load(file)
                self.widget.load_default_values(data)
        except FileNotFoundError:
            pass
        return data


class InitializationWizardWidget(QDialog):
    save_signal = pyqtSignal(dict)
    load_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Initialization Wizard")
        self.initUI()

    def initUI(self):
        layout = QGridLayout()
        # Define input fields for each JSON key
        self.fields = {}
        self.modules_checkboxes = []  # Initialize list to store module checkboxes
        json_keys = [
            "EXPERIMENT_JSON_PATH", "PROJECT_FOLDER", "MODULES", "DEBUG", "DEVICE",
            "DEVICE_JSON_PATH", "APP",
        ]
        for key in json_keys:
            if key == "MODULES":
                label = QLabel(key + ":")
                modules_layout = QHBoxLayout()
                self.modules = ["scan", "analysis", "fluidics"]
                self.fields[key] = {}
                modules_layout.addWidget(label)
                for module in self.modules:
                    checkbox = QCheckBox(module)
                    modules_layout.addWidget(checkbox)
                    checkbox.stateChanged.connect(partial(self.toggle_module, module))
                    self.fields[key][module] = checkbox
                layout.addLayout(modules_layout, *(7, 0, 1, 1))
            elif key == "DEBUG":
                debug_layout = QHBoxLayout()
                debug_label = QLabel("DEBUG:")
                self.debug_checkbox = QCheckBox("Mocks")
                self.debug_checkbox.stateChanged.connect(self.toggle_debug_label)
                debug_layout.addWidget(debug_label)
                debug_layout.addWidget(self.debug_checkbox)
                layout.addLayout(debug_layout, *(6, 0, 1, 1))
                self.fields[key] = self.debug_checkbox.text()
            elif key == "DEVICE":
                device_layout = QHBoxLayout()
                device_label = QLabel("DEVICE:")
                self.device_checkbox = QCheckBox("UC2_INVESTIGATOR")
                self.device_checkbox.stateChanged.connect(self.toggle_device_label)
                device_layout.addWidget(device_label)
                device_layout.addWidget(self.device_checkbox)
                layout.addLayout(device_layout, *(5, 0, 1, 1))
                self.fields[key] = self.device_checkbox.text()
            elif key == "APP":
                app_layout = QHBoxLayout()
                app_label = QLabel("APP:")
                self.app_selector = QComboBox()
                self.app_selector.addItems(["BCALL", "LOCAI", "ICARUS"])
                self.app_selector.setDisabled(True)
                # self.app_selector.stateChanged.connect(self.toggle_device_label)
                app_layout.addWidget(app_label)
                app_layout.addWidget(self.device_checkbox)
                layout.addLayout(app_layout, *(4, 0, 1, 1))
                self.fields[key] = self.app_selector.currentText()
            else:
                if key == "EXPERIMENT_JSON_PATH":
                    p0 = (0, 0, 1, 1)
                elif key == "PROJECT_FOLDER":
                    # Create a separator using QFrame
                    separator = QFrame()
                    separator.setFrameShape(QFrame.HLine)  # Horizontal line
                    separator.setFrameShadow(QFrame.Sunken)  # Sunken effect
                    layout.addWidget(separator)
                    p0 = (2, 0, 1, 1)
                elif key == "DEVICE_JSON_PATH":
                    p0 = (3, 0, 1, 1)
                layout_ = QVBoxLayout()
                label = QLabel(key + ":")
                edit = QPushButton("Select")
                edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                layout_.addWidget(label)
                layout_.addWidget(edit)
                layout.addLayout(layout_, *p0)
                self.fields[key] = edit

        # Load JSON data from file and populate input fields
        self.setLayout(layout)

    def closeEvent(self, event):
        self.save_json_data()
        event.accept()

    def load_default_values(self, data):
        for key, value in data.items():
            if key == "MODULES":
                for module in data[key]:
                    if module:
                        self.fields[key][module].setChecked(True)
                    else:
                        self.fields[key][module].setChecked(False)
            elif key == "DEBUG":
                if value == "2":
                    self.debug_checkbox.setChecked(True)
                    self.debug_checkbox.setText("Device")
                else:
                    self.debug_checkbox.setChecked(False)
                    self.debug_checkbox.setText("Mocks")
            elif key == "DEVICE":
                if value == "UC2_INVESTIGATOR":
                    self.device_checkbox.setChecked(True)
                    self.device_checkbox.setText("UC2_INVESTIGATOR")
                else:
                    self.device_checkbox.setChecked(False)
                    self.device_checkbox.setText("BTIG_A")
            elif key == "APP":
                apps = [self.app_selector.itemText(i) for i in range(self.app_selector.count())]
                if value not in apps:
                    raise ValueError(
                        f"APP {value} not in current applications: {[self.app_selector.itemText(i) for i in range(self.app_selector.count())]}.")
                else:
                    i = apps.index(value)
                    self.app_selector.setCurrentIndex(i)
            elif key in self.fields:
                self.fields[key].setText(str(value))

    def save_json_data(self):
        data = {}
        for key, edit in self.fields.items():
            if key == "MODULES":
                modules = [checkbox.text() for module, checkbox in self.fields[key].items() if checkbox.isChecked()]
                data[key] = modules
            elif key == "DEBUG":
                if self.debug_checkbox.isChecked():
                    data[key] = "2"
                else:
                    data[key] = "1"
            elif key == "DEVICE":
                if self.device_checkbox.isChecked():
                    data[key] = "UC2_INVESTIGATOR"
                else:
                    data[key] = "BTIG_A"
            elif key == "APP":
                data[key] = self.app_selector.currentText()
            else:
                data[key] = edit.text()
        self.save_signal.emit(data)

    def open_file_dialog(self, key):
        if key == "PROJECT_FOLDER":
            directory = QFileDialog.getExistingDirectory(self, "Select Project Folder")
            if directory:
                self.fields[key].setText(directory)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, f"Select {key.replace('_', ' ')}", "", "All Files (*)")
            if file_path:
                self.fields[key].setText(file_path)

    def toggle_module(self, module, state):
        self.fields["MODULES"][module].setChecked(state)

    def toggle_debug_label(self, state):
        if state == 2:  # checked
            self.debug_checkbox.setText("Device")
        else:
            self.debug_checkbox.setText("Mocks")

    def toggle_device_label(self, state):
        if state:  # checked
            self.device_checkbox.setText("UC2_INVESTIGATOR")
        else:
            self.device_checkbox.setText("BTIG_A")


# From https://stackoverflow.com/questions/26227885/drag-and-drop-rows-within-qtablewidget
class TableWidgetDragRows(QtWidgets.QTableWidget):
    sigGoToTableClicked = QtCore.Signal(int)
    sigAdjustFocusClicked = QtCore.Signal(int)
    sigDeleteRowClicked = QtCore.Signal(int)
    sigAdjustPositionClicked = QtCore.Signal(int)
    sigDuplicatePositionClicked = QtCore.Signal(int)
    sigSelectedDragRows = QtCore.Signal(list, int)  # list of selected rows, position to drag to.
    sigRowChecked = QtCore.Signal(bool, int)

    from locai_app.exp_control.scanning.scan_entities import ScanPoint

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.columns = ["Slot", "Labware", "Well", "Index", "Offset", "Z_focus", "Absolute", "Done"]
        self.column_mapping = {
            "Slot": "slot",
            "Labware": "labware",
            "Well": "well",
            "Index": "position_in_well_index",
            "Offset": ("offset_from_center_x", "offset_from_center_y"),
            "Z_focus": "relative_focus_z",
            "Absolute": ("position_x", "position_y", "position_z"),
            "Done": "checked"
        }
        default_hidden = [6]
        self.mapping = {}
        self.set_header()
        self.scan_list_items = 0
        self.columns_menu = QtWidgets.QMenu("Hide columns:", self)
        self.columns_actions = []
        for n, col in enumerate(self.columns):
            action = self.columns_menu.addAction(col)
            action.setCheckable(True)
            action.setChecked(True)
            action.triggered.connect(partial(self.column_checked, n))
            self.columns_actions.append(action)
            if n in default_hidden:
                self.setColumnHidden(n, True)
                action.setChecked(False)
        self.context_menu_enabled = True
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.resizeColumnsToContents()
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.onHorizontalHeaderClicked)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setItemDelegate(MyDelegate())

    def set_item(self, row, col, item):
        self.setItem(row, col, QtWidgets.QTableWidgetItem(str(item)))

    def add_row_in_widget(self, row_id, current_point: ScanPoint):
        self.insertRow(row_id)
        self.set_item(row=row_id, col=self.columns.index("Slot"), item=current_point.slot)
        self.set_item(row=row_id, col=self.columns.index("Labware"), item=current_point.labware)
        self.set_item(row=row_id, col=self.columns.index("Well"), item=current_point.well)
        self.set_item(row=row_id, col=self.columns.index("Index"), item=round(current_point.position_in_well_index))
        self.set_item(row=row_id, col=self.columns.index("Offset"),
                      item=(round(current_point.offset_from_center_x, 1),
                            round(current_point.offset_from_center_y, 1)))
        self.set_item(row=row_id, col=self.columns.index("Z_focus"), item=round(current_point.relative_focus_z, 2))
        self.set_item(row=row_id, col=self.columns.index("Absolute"),
                      item=(round(current_point.position_x, 2),
                            round(current_point.position_y, 2),
                            round(current_point.position_z, 2)))
        checkbox = QCheckBox()
        checkbox.setChecked(current_point.checked)
        checkbox.setMaximumSize(20, 20)
        checkbox.stateChanged.connect(partial(self.row_checked, row_id))
        self.setCellWidget(row_id, self.columns.index("Done"), checkbox)
        self.resizeColumnsToContents()

    def row_checked(self, row):
        state = self.cellWidget(row, self.columns.index("Done")).isChecked()
        self.sigRowChecked.emit(state, row)

    def onHorizontalHeaderClicked(self, point):
        # https://www.programcreek.com/python/?code=danigargu%2Fheap-viewer%2Fheap-viewer-master%2Fheap_viewer%2Fwidgets%2Fstructs.py
        self.columns_menu.exec_(self.mapToGlobal(point))

    def column_checked(self, n):
        if not self.columns_actions[n].isChecked():
            self.setColumnHidden(n, True)
            self.columns_actions[n].setChecked(False)
            print(f"Hiding column {self.columns_actions[n]}")
        else:
            self.setColumnHidden(n, False)
            self.columns_actions[n].setChecked(True)
            print(f"Showing column {self.columns_actions[n]}")

    def set_header(self):
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)

    def clear_scan_list(self):
        self.clear()
        self.setHorizontalHeaderLabels(self.columns)
        self.setRowCount(0)
        self.scan_list_items = 0

    def get_first_z_focus(self):
        return float(self.item(0, 3).text())

    def getSignal(self, oObject: QtCore.QObject, strSignalName: str):
        oMetaObj = oObject.metaObject()
        for i in range(oMetaObj.methodCount()):
            oMetaMethod = oMetaObj.method(i)
            if not oMetaMethod.isValid():
                continue
            if oMetaMethod.methodType() == QtCore.QMetaMethod.Signal and \
                    oMetaMethod.name() == strSignalName:
                return oMetaMethod

        return None

    def contextMenuEvent(self, event):
        if self.context_menu_enabled:
            self._contextMenuEvent(event)
        else:
            event.ignore()

    def _contextMenuEvent(self, event):
        if self.selectionModel().selection().indexes():
            for i in self.selectionModel().selection().indexes():
                row, column = i.row(), i.column()
            menu = QtWidgets.QMenu()
            goto_action = menu.addAction("Go To") if self.isSignalConnected(
                self.getSignal(self, "sigGoToTableClicked")) else None
            delete_action = menu.addAction("Delete") if self.isSignalConnected(
                self.getSignal(self, "sigDeleteRowClicked")) else None
            adjust_focus_action = menu.addAction("Adjust Focus") if self.isSignalConnected(
                self.getSignal(self, "sigAdjustFocusClicked")) else None
            adjust_pos_action = menu.addAction("Adjust Position") if self.isSignalConnected(
                self.getSignal(self, "sigAdjustPositionClicked")) else None
            duplicate_pos_action = menu.addAction("Duplicate Position") if self.isSignalConnected(
                self.getSignal(self, "sigDuplicatePositionClicked")) else None
            action = menu.exec_(self.mapToGlobal(event.pos()))
            if action == goto_action:
                self.go_to_action(row)
            elif action == delete_action:
                self.deleteSelected(row)
            elif action == adjust_focus_action:
                self.adjust_focus_action(row)
            elif action == adjust_pos_action:
                self.adjust_position_action(row)
            elif action == duplicate_pos_action:
                self.duplicate_position_action(row)

    def go_to_action(self, row):
        self.sigGoToTableClicked.emit(row)

    def adjust_focus_action(self, row):
        self.sigAdjustFocusClicked.emit(row)

    def adjust_position_action(self, row):
        self.sigAdjustPositionClicked.emit(row)

    def duplicate_position_action(self, row):
        self.sigDuplicatePositionClicked.emit(row)

    def deleteSelected(self, row):
        reply = QMessageBox.question(self, 'Delete Confirmation', f'Are you sure you want to delete this row ({row})?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Perform the delete action here
            print("Delete confirmed")
            self.sigDeleteRowClicked.emit(row)
        else:
            print("Delete canceled")
            return

    def dropEvent(self, event):
        if not event.isAccepted() and event.source() == self:
            drop_row = self.drop_on(event)

            rows = sorted(set(item.row() for item in self.selectedItems()))

            rows_to_move = []
            for row_index in rows:
                items = dict()
                for column_index in range(self.columnCount()):
                    # get the widget or item of current cell
                    widget = self.cellWidget(row_index, column_index)
                    if isinstance(widget, type(None)):
                        # if widget is NoneType, it is a QTableWidgetItem
                        items[column_index] = {"kind": "QTableWidgetItem",
                                               "item": QtWidgets.QTableWidgetItem(self.item(row_index, column_index))}
                    else:
                        # otherwise it is any other kind of widget. So we catch the widgets unique (hopefully) objectname
                        items[column_index] = {"kind": "QWidget",
                                               "item": widget.objectName()}

                rows_to_move.append(items)

            for row_index in reversed(rows):
                self.removeRow(row_index)
                if row_index < drop_row:
                    drop_row -= 1

            for row_index, data in enumerate(rows_to_move):
                row_index += drop_row
                self.insertRow(row_index)

                for column_index, column_data in data.items():
                    if column_data["kind"] == "QTableWidgetItem":
                        # for QTableWidgetItem we can re-create the item directly
                        self.setItem(row_index, column_index, column_data["item"])
                    else:
                        # for others we call the parents callback function to get the widget
                        _widget = self._parent.get_table_widget(column_data["item"])
                        if _widget is not None:
                            self.setCellWidget(row_index, column_index, _widget)

            event.accept()

        super().dropEvent(event)

    def drop_on(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return self.rowCount()

        return index.row() + 1 if self.is_below(event.pos(), index) else index.row()

    def is_below(self, pos, index):
        rect = self.visualRect(index)
        margin = 2
        if pos.y() - rect.top() < margin:
            return False
        elif rect.bottom() - pos.y() < margin:
            return True
        # noinspection PyTypeChecker
        return rect.contains(pos, True) and not (
                int(self.model().flags(index)) & Qt.ItemIsDropEnabled) and pos.y() >= rect.center().y()

    def addColumn(self, name):
        newColumn = self.columnCount()
        self.beginInsertColumns(Qt.QModelIndex(), newColumn, newColumn)
        self.headerdata.append(name)
        for row in self.arraydata:
            row.append('')
        self.endInsertColumns()

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
