import json
import os
import sys
import time
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QMessageBox, QFileDialog, QHBoxLayout, QRadioButton, QDialog, \
    QGridLayout, \
    QComboBox, QFrame, QMainWindow, QAction, QMenuBar, QTabWidget, QSpinBox
from dotenv import load_dotenv

from imswitch.imcommon.model import initLogger
from imswitch.imcontrol.view import guitools as guitools
from qtpy import QtCore, QtWidgets, QtGui
from functools import partial

from .basewidgets import Widget, NapariHybridWidget

from locai_app.impl.deck.sd_deck_manager import DeckManager
from locai_app.exp_control.experiment_context import ExperimentModules
from config.config_definitions import ZStackParameters, ZScanParameters


class LabmaiteDeckWidget(NapariHybridWidget):
    """ Widget in control of the piezo movement. """
    sigStepUpClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigStepDownClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigsetSpeedClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigScanStop = QtCore.Signal(bool)  # (enabled)
    sigScanStart = QtCore.Signal(bool)  # (enabled)

    sigScanSave = QtCore.Signal()
    sigScanOpen = QtCore.Signal()
    sigScanNew = QtCore.Signal()

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
    sigOffsetsSet = QtCore.Signal(float, float, float)

    sigSlicesChanged = QtCore.Signal(int)
    sigSeparationChanged = QtCore.Signal(float)
    sigDepthChanged = QtCore.Signal(float)
    sigZstackCheckboxChanged = QtCore.Signal(bool)

    sigPlot3DPlate = QtCore.Signal()

    sigAutofocusRun = QtCore.Signal()
    sigAutofocusStop = QtCore.Signal()

    def __post_init__(self):
        # super().__init__(*args, **kwargs)
        self.setMaximumWidth(800)
        self.setMinimumWidth(600)
        self.numPositioners = 0
        self.pars = {}
        self.main_grid_layout = QtWidgets.QGridLayout()
        self.stage_grid_layout = QtWidgets.QGridLayout()
        self.scan_list = TableWidgetDragRows()  # Initialize empty table
        self.info = ""  # TODO: use QLabel...
        self.current_slot = None
        self.current_well = None
        self.layer = None
        self.getSignal = getSignal
        self.init_menu_bar()
        self.__logger = initLogger(self, instanceName="DeckWidget")

    @property
    def current_slot(self):
        return self._current_slot

    @current_slot.setter
    def current_slot(self, slot):
        self._current_slot = slot

    def init_menu_bar(self):
        # Create a menu bar
        menu_bar = QMenuBar()
        menu_bar = self.add_file_menu(menu_bar)
        menu_bar = self.add_settings_menu(menu_bar)
        menu_bar = self.add_help_menu(menu_bar)

        self.main_grid_layout.setMenuBar(menu_bar)

    def add_help_menu(self, menu_bar):
        # Create a help menu
        helpMenu = menu_bar.addMenu('Help')

        aboutAction = QAction('About', self)
        aboutAction.setStatusTip('About this application')
        helpMenu.addAction(aboutAction)

        return menu_bar

    def add_file_menu(self, menu_bar):
        # Create a File menu
        file_menu = menu_bar.addMenu("File")
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.emit_open_signal)

        file_menu.addAction(open_action)
        save_config_action = QAction("Save", self)
        save_config_action.triggered.connect(self.emit_save_signal)
        file_menu.addAction(save_config_action)

        file_menu.addSeparator()  # Add a separator
        new_config_action = QAction("New", self)
        new_config_action.triggered.connect(self.emit_new_signal)
        file_menu.addAction(new_config_action)

        return menu_bar

    def add_settings_menu(self, menu_bar):
        # Create a File menu
        file_menu = menu_bar.addMenu("Options")
        zstack_dialog_action = QAction("Z-Stack", self)
        zstack_dialog_action.triggered.connect(self.open_zstack_dialog)
        file_menu.addAction(zstack_dialog_action)

        zscan_dialog_action = QAction("Z-Scan", self)
        zscan_dialog_action.triggered.connect(self.open_zscan_dialog)
        file_menu.addAction(zscan_dialog_action)
        zscan_dialog_action.setStatusTip('About Z-Scan')

        offsets_dialog_action = QAction("Offsets", self)
        offsets_dialog_action.triggered.connect(self.open_offsets_dialog)
        file_menu.addAction(offsets_dialog_action)

        file_menu.addSeparator()  # Add a separator
        illumination_dialog_action = QAction("Illumination", self)
        illumination_dialog_action.triggered.connect(self.open_illumination_dialog)
        file_menu.addAction(illumination_dialog_action)

        slot_dialog_action = QAction("Slot", self)
        slot_dialog_action.triggered.connect(self.open_slot_dialog)
        file_menu.addAction(slot_dialog_action)

        file_menu.addSeparator()  # Add a separator
        plot_plate_3d_dialog_action = QAction("3D Plate plot", self)
        plot_plate_3d_dialog_action.triggered.connect(self.open_plot_plate_3d_dialog)
        file_menu.addAction(plot_plate_3d_dialog_action)

        file_menu.addSeparator()  # Add a separator
        autofocus_dialog_action = QAction("Autofocus", self)
        autofocus_dialog_action.triggered.connect(self.open_autofocus_dialog)
        file_menu.addAction(autofocus_dialog_action)

        return menu_bar

    def open_autofocus_dialog(self):
        autofocus_dialog = QDialog()
        autofocus_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QGridLayout()

        af_base, af_top, z_scan_step = self.get_af_values()

        af_base_label = QtWidgets.QLabel("AF Start:")
        self.af_base_widget = QtWidgets.QLineEdit(f"{af_base}")
        self.af_base_widget.setMaximumWidth(60)

        af_top_label = QtWidgets.QLabel("AF End:")
        self.af_top_widget = QtWidgets.QLineEdit(f"{af_top}")
        self.af_top_widget.setMaximumWidth(60)

        self.z_scan_step_label = QtWidgets.QLabel("Step:")
        self.af_step_widget = QtWidgets.QLineEdit(f"{z_scan_step}")
        self.af_step_widget.setMaximumWidth(60)

        layout.addWidget(af_base_label, 0, 0, 1, 1)
        layout.addWidget(self.af_base_widget, 0, 1, 1, 1)
        layout.addWidget(af_top_label, 1, 0, 1, 1)
        layout.addWidget(self.af_top_widget, 1, 1, 1, 1)
        layout.addWidget(self.z_scan_step_label, 0, 2, 1, 1)
        layout.addWidget(self.af_step_widget, 0, 3, 1, 1)
        # af_run_button, af_stop_button in init_autofocus_widget.
        layout.addWidget(self.af_run_button, 2, 0, 1, 2)
        layout.addWidget(self.af_stop_button, 2, 2, 1, 2)

        self.af_base_widget.textChanged.connect(self.calculate_autofocus)  # Connect valueChanged signal
        self.af_top_widget.textChanged.connect(self.calculate_autofocus)
        self.af_step_widget.textChanged.connect(self.calculate_autofocus)

        self.af_run_button.clicked.connect(self.run_autofocus)
        self.af_stop_button.clicked.connect(self.stop_autofocus)

        self.calculate_autofocus()
        autofocus_dialog.setLayout(layout)
        autofocus_dialog.show()
        autofocus_dialog.exec_()

    def calculate_autofocus(self):
        self.af_base_value = float(self.af_base_widget.text())
        self.af_top_value = float(self.af_top_widget.text())
        self.af_step_value = float(self.af_step_widget.text())

    def run_autofocus(self):
        self.sigAutofocusRun.emit()

    def stop_autofocus(self):
        self.sigAutofocusStop.emit()

    def open_plot_plate_3d_dialog(self):
        plot_plate_3d_dialog = QDialog()
        layout = QHBoxLayout()
        self.sigPlot3DPlate.emit()

    def open_slot_dialog(self):
        slot_dialog = QDialog()
        layout = QHBoxLayout()
        slot_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.slot_label = QtWidgets.QLabel("Slot: ")
        self.slot_label.setMinimumWidth(40)
        self.slot_label.setMinimumHeight(35)
        self.slot_label.setMaximumHeight(40)

        self.slots_combobox = QtWidgets.QComboBox(self)
        self.slots_combobox.setMinimumWidth(40)
        self.slots_combobox.setMinimumHeight(35)
        self.slots_combobox.setMaximumHeight(40)
        [self.slots_combobox.addItem(f"{s}") for s in list(self._labware_dict.keys())]

        layout.addWidget(self.slot_label)
        layout.addWidget(self.slots_combobox)
        self.slots_combobox.currentTextChanged.connect(self.slot_change)

        slot_dialog.setLayout(layout)
        slot_dialog.show()
        slot_dialog.exec_()

    def slot_change(self):
        self.sigSlotChanged.emit(self.slots_combobox.text())

    def open_zstack_dialog(self):
        zstack_dialog = QDialog()
        zstack_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QGridLayout()
        self.z_stack_checkbox_widget = QCheckBox('Depth/Separation [um]')
        self.z_stack_checkbox_widget.setCheckable(True)

        self.z_stack_sample_depth_label = QLabel('Depth:')
        self.z_stack_sample_depth_value = QLineEdit()
        self.z_stack_sample_depth_value.setText(f"{self.z_height:.1f}" if self.z_height else str(1))
        self.z_stack_sample_depth_value.setEnabled(True)

        self.z_stack_slice_sep_label = QLabel('Separation:')
        self.z_stack_slice_sep_value = QLineEdit()
        self.z_stack_slice_sep_value.setText(f"{self.z_sep:.1f}" if self.z_sep else str(1))
        self.z_stack_slice_sep_value.setEnabled(False)

        self.z_stack_slices_label = QLabel('N° Slices:')
        self.z_stack_slices_value = QSpinBox()
        self.z_stack_slices_value.setValue(self.z_slices)
        self.z_stack_slices_value.setMinimum(1)
        self.z_stack_slices_value.setMaximum(1000)

        layout.addWidget(self.z_stack_checkbox_widget, 0, 0, 1, 2)
        layout.addWidget(self.z_stack_sample_depth_label, 1, 0, 1, 1)
        layout.addWidget(self.z_stack_sample_depth_value, 1, 1, 1, 1)
        layout.addWidget(self.z_stack_slice_sep_label, 2, 0, 1, 1)
        layout.addWidget(self.z_stack_slice_sep_value, 2, 1, 1, 1)
        layout.addWidget(self.z_stack_slices_label, 3, 0, 1, 1)
        layout.addWidget(self.z_stack_slices_value, 3, 1, 1, 1)

        self.z_stack_checkbox_widget.stateChanged.connect(self.toggle_z_stack_options)
        self.z_stack_sample_depth_value.textChanged.connect(self.calculate_z_stack)  # Connect valueChanged signal
        self.z_stack_slice_sep_value.textChanged.connect(self.calculate_z_stack)
        self.z_stack_slices_value.valueChanged.connect(self.calculate_z_stack)

        zstack_dialog.setLayout(layout)
        zstack_dialog.show()
        zstack_dialog.exec_()

    def open_offsets_dialog(self):
        offsets_dialog = QDialog()
        offsets_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        offset_buttons_layout = QtWidgets.QGridLayout()
        self.OffsetsWidgets = QtWidgets.QGroupBox("Offsets:")
        self.OffsetsWidgets.setFixedWidth(130)

        self.x_offset_all_value = QtWidgets.QLineEdit()
        self.x_offset_all_value.setText(f"{0:.2f}")
        self.x_offset_all_value.setEnabled(True)

        self.y_offset_all_value = QtWidgets.QLineEdit()
        self.y_offset_all_value.setText(f"{0:.2f}")
        self.y_offset_all_value.setEnabled(True)

        self.z_offset_all_value = QtWidgets.QLineEdit()
        self.z_offset_all_value.setText(f"{0:.2f}")
        self.z_offset_all_value.setEnabled(True)

        self.adjust_offset_button = guitools.BetterPushButton('Set!')
        self.adjust_offset_button.setStyleSheet("font-size: 14px")
        self.adjust_offset_button.setMinimumWidth(90)

        self.adjust_offset_button.clicked.connect(self.emit_offsets)

        offset_buttons_layout.addWidget(QLabel("X"), *(0, 0, 1, 1))
        offset_buttons_layout.addWidget(self.x_offset_all_value, *(0, 1, 1, 1))
        offset_buttons_layout.addWidget(QLabel("Y"), *(1, 0, 1, 1))
        offset_buttons_layout.addWidget(self.y_offset_all_value, *(1, 1, 1, 1))
        offset_buttons_layout.addWidget(QLabel("Z"), *(2, 0, 1, 1))
        offset_buttons_layout.addWidget(self.z_offset_all_value, *(2, 1, 1, 1))
        offset_buttons_layout.addWidget(self.adjust_offset_button, *(3, 0, 1, 2))

        self.OffsetsWidgets.setLayout(offset_buttons_layout)
        offsets_dialog.setLayout(offset_buttons_layout)
        offsets_dialog.show()
        offsets_dialog.exec_()

    def emit_offsets(self):
        x, y, z = self.get_offset_all()
        self.sigOffsetsSet.emit(x, y, z)

    def open_zscan_dialog(self):
        zscan_dialog = QDialog()
        zscan_dialog.setWhatsThis('About Z-Scan')  # TODO: fix, needs to click on sth to show
        zscan_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QtWidgets.QGridLayout()
        well_base, well_top, z_scan_step = self.get_zscan_values()

        well_base_label = QtWidgets.QLabel("Well base:")
        self.well_base_widget = QtWidgets.QLineEdit(f"{well_base}")
        self.well_base_widget.setMaximumWidth(60)

        well_top_label = QtWidgets.QLabel("Well top:")
        self.well_top_widget = QtWidgets.QLineEdit(f"{well_top}")
        self.well_top_widget.setMaximumWidth(60)

        self.z_scan_step_label = QtWidgets.QLabel("Step:")
        self.z_scan_step_widget = QtWidgets.QLineEdit(f"{z_scan_step}")
        self.z_scan_step_widget.setMaximumWidth(60)

        layout.addWidget(well_base_label, 0, 0, 1, 1)
        layout.addWidget(self.well_base_widget, 0, 1, 1, 1)
        layout.addWidget(well_top_label, 1, 0, 1, 1)
        layout.addWidget(self.well_top_widget, 1, 1, 1, 1)
        layout.addWidget(self.z_scan_step_label, 0, 2, 1, 1)
        layout.addWidget(self.z_scan_step_widget, 0, 3, 1, 1)

        self.well_base_widget.textChanged.connect(self.calculate_z_scan)  # Connect valueChanged signal
        self.well_top_widget.textChanged.connect(self.calculate_z_scan)
        self.z_scan_step_widget.textChanged.connect(self.calculate_z_scan)

        self.calculate_z_scan()
        zscan_dialog.setLayout(layout)
        zscan_dialog.show()
        zscan_dialog.exec_()

    def calculate_z_scan(self):
        self.well_base_value = float(self.well_base_widget.text())
        self.well_top_value = float(self.well_top_widget.text())
        self.z_scan_step_value = float(self.z_scan_step_widget.text())

    def get_zscan_values(self):
        return self.well_base_value, self.well_top_value, self.z_scan_step_value

    def get_af_values(self):
        return self.af_base_value, self.af_top_value, self.af_step_value

    def open_illumination_dialog(self):
        illu_dialog = QDialog()
        illu_dialog.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        # LEDs grid
        self.LEDWidget = QtWidgets.QGroupBox("Lights: Not implemented yet.")
        self.LEDWidget.setMaximumWidth(110)
        led_layout = QtWidgets.QGridLayout()
        self.LEDWidget = QtWidgets.QGroupBox("Lights: [%]")
        self.LEDWidget.setMaximumWidth(150)
        self.LEDWidget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.LEDWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                     QtWidgets.QSizePolicy.Expanding)
        self.LED_selection_combobox = QtWidgets.QComboBox()
        led_layout = QtWidgets.QGridLayout()

        self.light_sources_widgets = {}
        self.light_sources_signals = {}
        led_layout.addWidget(self.LED_selection_combobox, len(self.light_sources_widgets), 0)
        led_layout.addWidget(QLabel("Live [%]"), len(self.light_sources_widgets), 1)
        led_layout.addWidget(QLabel("Experiment [%]"), len(self.light_sources_widgets), 2)
        for name, light in self.light_sources.items():
            self.LED_selection_combobox.addItem(light.config.readable_name)
            if name in self.illumination_params.keys():
                exp_light_value = QtWidgets.QSpinBox()
                exp_light_value.setMaximum(100)
                exp_light_value.setMinimum(0)
                value = 100 * self.illumination_params[name].intensity / self.light_sources[name].config.value_range_max
                exp_light_value.setValue(value)
                exp_light_value.valueChanged.connect(partial(self.light_intensity_config_change, name))
            else:
                exp_light_value = QLabel().setDisabled(True)
            LEDWidget = QtWidgets.QSpinBox()
            LEDWidget.setMaximum(100)
            LEDWidget.setMinimum(0)
            LEDWidget.setMinimumWidth(50)
            LEDWidget.setMaximumWidth(60)
            LEDWidget.setValue(0)
            # LED_spinbox.valueChanged.connect(LED_spinbox, self.led_value_change)
            ledName = f'{light.config.readable_name}'
            nameLabel = QtWidgets.QLabel(ledName)

            self.light_sources_widgets[ledName] = LEDWidget
            self.light_sources_signals[ledName] = QtCore.Signal(float)
            led_layout.addWidget(nameLabel, len(self.light_sources_widgets), 0)
            led_layout.addWidget(LEDWidget, len(self.light_sources_widgets), 1)
            led_layout.addWidget(exp_light_value, len(self.light_sources_widgets), 2)

            LEDWidget.valueChanged.connect(partial(self.light_intensity_change, ledName))
            # LED_selection_checkbox.checked.connect(partial(self.light_intensity_change, ledName))
        self.LED_selection_combobox.currentIndexChanged.connect(self.on_combobox_changed)

        illu_dialog.setLayout(led_layout)
        illu_dialog.show()
        illu_dialog.exec_()

    def on_combobox_changed(self, index):
        print(f'Selected: {self.LED_selection_combobox.currentText()}. Index {index}')

    def emit_open_signal(self):
        self.sigScanOpen.emit()

    def emit_save_signal(self):
        self.sigScanSave.emit()

    def emit_new_signal(self):
        self.sigScanNew.emit()

    def emit_zstack_checkbox_changed(self, state):
        self.sigZstackCheckboxChanged.emit(state)

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
        self.layout_positioner = QtWidgets.QGridLayout()
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

            self.layout_positioner.addWidget(self.pars['Label' + parNameSuffix], self.numPositioners, 0)
            self.layout_positioner.addWidget(self.pars['Position' + parNameSuffix], self.numPositioners, 1)
            self.layout_positioner.addWidget(self.pars['UpButton' + parNameSuffix], self.numPositioners, 2)
            self.layout_positioner.addWidget(self.pars['DownButton' + parNameSuffix], self.numPositioners, 3)
            self.layout_positioner.addWidget(QtWidgets.QLabel('Rel'), self.numPositioners, 4)
            self.layout_positioner.addWidget(self.pars['StepEdit' + parNameSuffix], self.numPositioners, 5)
            self.layout_positioner.addWidget(QtWidgets.QLabel('Abs'), self.numPositioners, 6)

            self.layout_positioner.addWidget(self.pars['AbsolutePosEdit' + parNameSuffix], self.numPositioners, 7)
            self.layout_positioner.addWidget(self.pars['AbsolutePosButton' + parNameSuffix], self.numPositioners, 8)

            if hasSpeed:
                self.pars['Speed' + parNameSuffix] = QtWidgets.QLabel('Speed:')
                self.pars['Speed' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
                self.pars['SpeedEdit' + parNameSuffix] = QtWidgets.QLineEdit(
                    '12') if axis != "Z" else QtWidgets.QLineEdit('8')

                self.layout_positioner.addWidget(self.pars['Speed' + parNameSuffix], self.numPositioners, 9)
                self.layout_positioner.addWidget(self.pars['SpeedEdit' + parNameSuffix], self.numPositioners, 10)

            if hasHome:
                self.pars['Home' + parNameSuffix] = guitools.BetterPushButton('Home')
                self.layout_positioner.addWidget(self.pars['Home' + parNameSuffix], self.numPositioners, 11)

                self.pars['Home' + parNameSuffix].clicked.connect(
                    lambda *args, axis=axis: self.sigHomeAxisClicked.emit(positionerName, axis)
                )

            if hasStop:
                self.pars['Stop' + parNameSuffix] = guitools.BetterPushButton('Stop')
                self.layout_positioner.addWidget(self.pars['Stop' + parNameSuffix], self.numPositioners, 12)

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
        self._positioner_widget.setLayout(self.layout_positioner)
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
        self.well_action_widget.setText(f"Selected well: {self.current_well}")

    def select_labware(self, options=(1, 0, 3, 3), slot: str = None):
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

    def init_zstack_config_widget(self, default_values_in_mm: ZStackParameters):
        # z-stack
        self.z_stack_checkbox_widget = QCheckBox('Depth/Separation [um]')
        self.z_height = default_values_in_mm.z_height * 1000
        self.z_sep = default_values_in_mm.z_sep * 1000
        self.z_slices = default_values_in_mm.z_slices
        self.calculate_z_stack()

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
        self.calculate_z_stack()
        return self.z_height, self.z_sep, self.z_slices

    def toggle_z_stack_options(self):
        if bool(self.z_stack_checkbox_widget.isChecked()):
            self.z_stack_sample_depth_value.setEnabled(False)
            self.z_stack_slice_sep_value.setEnabled(True)
            self.z_stack_slice_sep_value.textChanged.connect(self.calculate_z_stack)
            self.z_stack_sample_depth_value.textChanged.disconnect(self.calculate_z_stack)
        else:
            self.z_stack_sample_depth_value.setEnabled(True)
            self.z_stack_slice_sep_value.setEnabled(False)
            self.z_stack_sample_depth_value.textChanged.connect(self.calculate_z_stack)  # Connect valueChanged signal
            self.z_stack_slice_sep_value.textChanged.disconnect(self.calculate_z_stack)
        self.setLayout(self.main_grid_layout)

    def init_autofocus_widget(self, default_values_in_mm: Optional[ZScanParameters] = None, options=[(3, 3, 1, 2)]):
        self.af_base_value = default_values_in_mm.well_base if default_values_in_mm is not None else 7.00
        self.af_top_value = default_values_in_mm.well_top if default_values_in_mm is not None else 7.30
        self.af_step_value = default_values_in_mm.z_scan_step if default_values_in_mm is not None else 0.025
        self.af_base_widget = QtWidgets.QLineEdit(f"{self.af_base_value}")
        self.af_top_widget = QtWidgets.QLineEdit(f"{self.af_top_value}")
        self.af_step_widget = QtWidgets.QLineEdit(f"{self.af_step_value}")
        self.af_run_button = QPushButton("RUN")
        self.af_stop_button = QPushButton("STOP")
        self.af_run_button.setDisabled(False)
        self.af_stop_button.setDisabled(True)

    def init_z_scan_widget(self, default_values_in_mm: Optional[ZScanParameters] = None, options=[(3, 3, 1, 2)]):
        self.well_base_value = default_values_in_mm.well_base if default_values_in_mm is not None else 7.00
        self.well_top_value = default_values_in_mm.well_top if default_values_in_mm is not None else 7.30
        self.z_scan_step_value = default_values_in_mm.z_scan_step if default_values_in_mm is not None else 0.025
        self._z_scan_box = QtWidgets.QGroupBox("Z-Scan:")
        layout = QtWidgets.QGridLayout()
        self.z_scan_zpos_label = QtWidgets.QLabel(f"Adjust focus of row {'-'} to ")
        self.z_scan_zpos_label.setWordWrap(True)
        self.z_scan_zpos_label.setMaximumWidth(150)
        self.z_scan_zpos_widget = QtWidgets.QLineEdit('')
        self.z_scan_zpos_widget.setMaximumWidth(60)
        self.z_scan_adjust_focus_widget = guitools.BetterPushButton("Focus!")
        self.z_scan_adjust_focus_widget.setStyleSheet("font-size: 14px")
        self.z_scan_adjust_focus_widget.setMaximumWidth(60)
        self.z_scan_preview_button = guitools.BetterPushButton("Preview")  # QtWidgets.QPushButton(corrds)
        self.z_scan_preview_button.setStyleSheet("font-size: 14px")
        self.z_scan_preview_button.setMinimumWidth(100)
        self.z_scan_stop_button = guitools.BetterPushButton("Stop")  # QtWidgets.QPushButton(corrds)
        self.z_scan_stop_button.setStyleSheet("font-size: 14px")
        self.z_scan_stop_button.setMinimumWidth(30)
        # self._z_scan_box.setMinimumWidth(150)
        layout.addWidget(self.z_scan_preview_button, 0, 0, 1, 1)
        layout.addWidget(self.z_scan_stop_button, 0, 1, 1, 1)
        layout.addWidget(self.z_scan_adjust_focus_widget, 0, 2, 1, 1)
        layout.addWidget(self.z_scan_zpos_label, 1, 0, 1, 2)
        layout.addWidget(self.z_scan_zpos_widget, 1, 2, 1, 1)
        self._z_scan_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._z_scan_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
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

    def init_light_sources(self, light_sources, illumination_params: dict, options=(4, 3, 2, 1)):
        self.light_sources = light_sources
        self.illumination_params = illumination_params

    def light_intensity_change(self, ledName):
        if self.LED_selection_combobox.currentText() == ledName:
            self.sigSliderValueChanged.emit(ledName, self.light_sources_widgets[ledName].value())

    def light_intensity_config_change(self, ledName, value):
        value = self.light_sources[ledName].config.value_range_max * value / 100
        self.illumination_params[ledName].intensity = value
        self.ScanInfo.setText("Unsaved changes.")

    def get_illumination_params(self):
        return self.illumination_params

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

        exp_buttons_layout.addWidget(self.ScanStartButton, 0, 0, 1, 1)
        exp_buttons_layout.addWidget(self.ScanStopButton, 1, 0, 1, 1)

        self.ScanActionsWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                             QtWidgets.QSizePolicy.Expanding)
        self.ScanActionsWidget.setLayout(exp_buttons_layout)
        self.main_grid_layout.addWidget(self.ScanActionsWidget, *options)

    def init_focus_all_button(self, options=(3, 4, 1, 1)):
        layout = QtWidgets.QHBoxLayout()
        self.adjust_all_focus_button = guitools.BetterPushButton('Focus All')
        self.adjust_all_focus_button.setStyleSheet("font-size: 14px")
        self.adjust_all_focus_button.setFixedHeight(30)
        self.adjust_all_focus_button.setMinimumWidth(40)
        layout.addWidget(self.adjust_all_focus_button)
        self.adjust_all_focus_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                                   QtWidgets.QSizePolicy.Expanding)
        self.main_grid_layout.addWidget(self.adjust_all_focus_button, *options)

    def init_offset_buttons(self, options=(3, 4, 1, 1)):
        self.adjust_offset_button = guitools.BetterPushButton('Set!')

    def get_offset_all(self):
        return float(self.x_offset_all_value.text()), float(self.y_offset_all_value.text()), float(
            self.z_offset_all_value.text())

    def update_scan_info_text(self, text):
        self.ScanInfo.setText(text)
        self.ScanInfo.setHidden(False)

    def init_experiment_info(self, options=(8, 0, 1, 1)):
        self.ScanInfo = QtWidgets.QLabel('')
        self.ScanInfo.setWordWrap(True)
        self.sigScanInfoTextChanged.connect(self.update_scan_info_text)
        self.ScanInfo_widget = QtWidgets.QGroupBox("Scan Info")
        self.ScanInfo_widget.setMinimumWidth(200)
        ScanInfo_layout = QtWidgets.QHBoxLayout()
        ScanInfo_layout.addWidget(self.ScanInfo)
        self.ScanInfo.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                    QtWidgets.QSizePolicy.Expanding)
        self.ScanInfo_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                           QtWidgets.QSizePolicy.Expanding)
        self.ScanInfo_widget.setLayout(ScanInfo_layout)
        self.main_grid_layout.addWidget(self.ScanInfo_widget, *options)
        self.setLayout(self.main_grid_layout)

    def initialize_deck(self, deck_manager: DeckManager, options=(1, 0, 2, 4)):
        self._deck_dict = deck_manager.deck_layout
        self._labware_dict = deck_manager.labwares

        self.sigLabwareSelect.connect(partial(self.select_labware, options))
        self.sigWellSelect.connect(self.select_well)

    def init_home_button(self, row=None):
        home_button_layout = QtWidgets.QGridLayout()
        self.home_button = guitools.BetterPushButton(text="HOME")  # QtWidgets.QPushButton(corrds)
        self.home_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.home_button.setMaximumWidth(60)
        self.home_button.setMaximumHeight(20)
        self.home_button.setStyleSheet("background-color: black; font-size: 14px")
        home_button_layout.addWidget(self.home_button)
        row = self.layout_positioner.rowCount() + 1 if row is None else row
        p = (row, self.layout_positioner.columnCount() - 2, 1, 2)
        self.layout_positioner.addWidget(self.home_button, *p)
        self.setLayout(self.layout_positioner)

    def init_park_button(self, row=None):
        park_button_layout = QtWidgets.QGridLayout()
        self.park_button = guitools.BetterPushButton(text="PARK")  # QtWidgets.QPushButton(corrds)
        self.park_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.park_button.setMaximumHeight(20)
        self.park_button.setMaximumWidth(60)
        self.park_button.setStyleSheet("background-color: black; font-size: 14px")
        park_button_layout.addWidget(self.park_button)
        row = self.layout_positioner.rowCount() + 1 if row is None else row
        p = (row, self.layout_positioner.columnCount() - 4, 1, 2)
        self.layout_positioner.addWidget(self.park_button, *p)
        self.setLayout(self.layout_positioner)

    def update_scan_info(self, dict_info):
        self.ScanInfo.setText(dict_info["experiment_status"])

    def init_well_action(self, row=None):
        self.well_action_widget = QtWidgets.QLabel("Selected well: [-]")
        self.goto_btn = guitools.BetterPushButton('GO TO')
        row = self.layout_positioner.rowCount() + 1 if row is None else row
        self.layout_positioner.addWidget(self.well_action_widget, *(row, 0, 1, 4))
        self.layout_positioner.addWidget(self.goto_btn, *(row, 4, 1, 2))
        self.setLayout(self.layout_positioner)

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
        self.scan_list.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                     QtWidgets.QSizePolicy.Expanding)

        # Create a vertical layout and add the table and the buttons layout
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.scan_list)
        main_layout.addLayout(buttons_layout)
        self.scan_list_widget.setMinimumHeight(350)
        self.scan_list_widget.setMaximumHeight(700)

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


class ImSwitchConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImSwitchConfig")
        self.initUI()

    def initUI(self):
        load_dotenv()
        path = os.getenv("IMSWITCH_CONFIG_PATH", None)
        if path is not None:
            self.copy_imswitch_config_file(path)
        else:
            path = self.open_folder()
            env_path = os.path.abspath(os.sep.join([os.path.curdir, ".env"]))
            with open(env_path, 'w') as file:
                file.write(f'IMSWITCH_CONFIG_PATH="{path}"\n')
                file_path = os.path.abspath(os.sep.join([os.path.curdir, "labmaite_config.json"]))
                file.write(f'JSON_CONFIG_PATH="{file_path}"\n')
        load_dotenv()
        self.close()

    def copy_imswitch_config_file(self, directory):
        file = os.sep.join([os.path.abspath(directory), "imcontrol_setups", "btig_uc2_merged_imswitch.json"])
        if not os.path.exists(file):
            import shutil
            file_lm = os.sep.join([os.path.abspath(os.path.curdir), "btig_uc2_merged_imswitch.json"])
            shutil.copyfile(file_lm, file)
            time.sleep(0.5)

    def open_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Please select ImSwitchConfig folder")
        if directory:
            self.copy_imswitch_config_file(directory)
        self.close()
        return directory


class InitializationWizard(QObject):
    sigSaveData = pyqtSignal(dict)
    sigLoadData = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.widget = InitializationWizardWidget()
        self.widget.save_signal.connect(self.save_json_data)
        self.widget.load_signal.connect(self.load_json_data)
        self.widget.load_signal.emit()
        # self.widget.closeEvent.connect(self.load_signal.emit)  # Connect finished signal to save method

    def save_json_data(self, data):
        with open(os.getenv("JSON_CONFIG_PATH"), "w") as file:
            json.dump(data, file, indent=4)

    def load_json_data(self):
        load_dotenv()
        data = {}
        try:
            with open(os.getenv("JSON_CONFIG_PATH"), "r") as file:
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
        layout = QVBoxLayout()
        # Define input fields for each JSON key
        self.fields = {}
        self.modules_checkboxes = []  # Initialize list to store module checkboxes
        tabs = QTabWidget()
        tabs.addTab(self.user_tab(), "User Options")
        tabs.addTab(self.developer_tab(), "Developer Options")
        layout.addWidget(tabs)
        self.setLayout(layout)

    def user_tab(self):
        json_keys = ["EXPERIMENT_JSON_PATH"]
        user_tab = QWidget()
        layout = QVBoxLayout()
        for key in json_keys:
            if key == "EXPERIMENT_JSON_PATH":
                layout_ = QVBoxLayout()
                label = QLabel(key + ":")
                edit = QPushButton("Select")
                edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                layout_.setAlignment(Qt.AlignCenter)
                layout_.addWidget(label)
                layout_.addWidget(edit)
                layout.addLayout(layout_)
                self.fields[key] = edit
        user_tab.setLayout(layout)
        return user_tab

    def developer_tab(self):
        dev_tab = QWidget()
        layout = QVBoxLayout()
        json_keys = ["PROJECT_FOLDER", "DEVICE", "DEVICE_JSON_PATH", "STORAGE_PATH", "MODULES", "DEBUG", "APP"]
        modules = ExperimentModules
        for key in json_keys:
            if key == "MODULES":
                label = QLabel(key + ":")
                modules_layout = QHBoxLayout()
                self.modules = [m for m in modules]
                self.fields[key] = {}
                modules_layout.addWidget(label)
                for module in self.modules:
                    checkbox = QCheckBox(module.name)
                    modules_layout.addWidget(checkbox)
                    checkbox.stateChanged.connect(partial(self.toggle_module, module.name))
                    self.fields[key][module.name] = checkbox
                layout.addLayout(modules_layout)
            elif key == "DEBUG":
                debug_layout = QHBoxLayout()
                debug_label = QLabel("DEBUG:")
                self.debug_checkbox = QCheckBox("Mocks")
                self.debug_checkbox.stateChanged.connect(self.toggle_debug_label)
                debug_layout.addWidget(debug_label)
                debug_layout.addWidget(self.debug_checkbox)
                layout.addLayout(debug_layout)
                self.fields[key] = self.debug_checkbox.text()
            elif key == "DEVICE":
                device_layout = QHBoxLayout()
                device_label = QLabel("DEVICE:")
                self.device_checkbox = QCheckBox("UC2_INVESTIGATOR")
                self.device_checkbox.stateChanged.connect(self.toggle_device_label)
                device_layout.addWidget(device_label)
                device_layout.addWidget(self.device_checkbox)
                layout.addLayout(device_layout)
                self.fields[key] = self.device_checkbox.text()
            elif key == "APP":
                app_layout = QHBoxLayout()
                app_label = QLabel("APP:")
                self.app_selector = QComboBox()
                self.app_selector.addItems(["BCALL", "LOCAI", "ICARUS"])
                self.app_selector.setDisabled(True)
                # self.app_selector.stateChanged.connect(self.toggle_device_label)
                app_layout.addWidget(app_label)
                app_layout.addWidget(self.app_selector)
                layout.addLayout(app_layout)
                self.fields[key] = self.app_selector.currentText()
            else:
                if key == "EXPERIMENT_JSON_PATH":
                    layout_ = QVBoxLayout()
                    label = QLabel(key + ":")
                    edit = QPushButton("Select")
                    edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                    layout_.addWidget(label)
                    layout_.addWidget(edit)
                    layout.addLayout(layout_)
                    self.fields[key] = edit
                elif key == "PROJECT_FOLDER":
                    # Create a separator using QFrame
                    layout_ = QVBoxLayout()
                    label = QLabel(key + ":")
                    edit = QPushButton("Select")
                    edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                    layout_.addWidget(label)
                    layout_.addWidget(edit)
                    layout.addLayout(layout_)
                    self.fields[key] = edit
                elif key == "STORAGE_PATH":
                    # Create a separator using QFrame
                    layout_ = QVBoxLayout()
                    label = QLabel(key + ":")
                    edit = QPushButton("Select")
                    edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                    layout_.addWidget(label)
                    layout_.addWidget(edit)
                    layout.addLayout(layout_)
                    self.fields[key] = edit
                else:
                    layout_ = QVBoxLayout()
                    label = QLabel(key + ":")
                    edit = QPushButton("Select")
                    edit.clicked.connect(lambda _, key=key: self.open_file_dialog(key))
                    layout_.addWidget(label)
                    layout_.addWidget(edit)
                    layout.addLayout(layout_)
                    self.fields[key] = edit
        dev_tab.setLayout(layout)
        return dev_tab

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
        elif key == "STORAGE_PATH":
            directory = QFileDialog.getExistingDirectory(self, "Select Storage Folder")
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


def getSignal(oObject: QtCore.QObject, strSignalName: str):
    oMetaObj = oObject.metaObject()
    for i in range(oMetaObj.methodCount()):
        oMetaMethod = oMetaObj.method(i)
        if not oMetaMethod.isValid():
            continue
        if oMetaMethod.methodType() == QtCore.QMetaMethod.Signal and \
                oMetaMethod.name() == strSignalName:
            return oMetaMethod

    return None


# From https://stackoverflow.com/questions/26227885/drag-and-drop-rows-within-qtablewidget
class TableWidgetDragRows(QtWidgets.QTableWidget):
    sigGoToTableClicked = QtCore.Signal(int)
    sigAdjustFocusClicked = QtCore.Signal(int)
    sigDeleteRowClicked = QtCore.Signal(int)
    sigAdjustPositionClicked = QtCore.Signal(int)
    sigDuplicatePositionClicked = QtCore.Signal(int)
    sigRunAutofocusClicked = QtCore.Signal(int)
    sigSelectedDragRows = QtCore.Signal(list, int)  # list of selected rows, position to drag to.
    sigRowChecked = QtCore.Signal(bool, int)

    from locai_app.exp_control.scanning.scan_entities import ScanPoint

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.getSignal = getSignal
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
            run_autofocus_action = menu.addAction("Run Autofocus") if self.isSignalConnected(
                self.getSignal(self, "sigRunAutofocusClicked")) else None
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
            elif action == run_autofocus_action:
                self.run_autofocus(row)

    def go_to_action(self, row):
        self.sigGoToTableClicked.emit(row)

    def run_autofocus(self, row):
        self.sigRunAutofocusClicked.emit(row)

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
