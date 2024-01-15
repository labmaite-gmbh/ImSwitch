import csv
from typing import Dict

from PyQt5.QtCore import Qt
from imswitch.imcommon.model import initLogger
from imswitch.imcontrol.view import guitools as guitools
from qtpy import QtCore, QtWidgets
from functools import partial

from locai_app.impl.deck.sd_deck_manager import DeckManager
from .basewidgets import Widget


class LabmaiteDeckWidget(Widget):
    """ Widget in control of the piezo movement. """
    sigStepUpClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigStepDownClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigsetSpeedClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigScanStop = QtCore.Signal(bool)  # (enabled)
    sigScanStart = QtCore.Signal(bool)  # (enabled)
    sigScanSave = QtCore.Signal()

    sigStepAbsoluteClicked = QtCore.Signal(str)
    sigHomeAxisClicked = QtCore.Signal(str, str)
    sigStopAxisClicked = QtCore.Signal(str, str)

    sigZeroZAxisClicked = QtCore.Signal(float)

    sigSliderLEDValueChanged = QtCore.Signal(float)  # (value)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.numPositioners = 0
        self.pars = {}
        self.main_grid_layout = QtWidgets.QGridLayout()
        self.scan_list = TableWidgetDragRows()  # Initialize empty table
        self.info = ""  # TODO: use QLabel...
        self.__logger = initLogger(self, instanceName="DeckWidget")

    def update_scan_list(self, scan_list):
        self.scan_list.clear_scan_list()
        self.scan_list.set_header()
        for row_i, row_values in enumerate(scan_list):
            self.scan_list.add_row_in_widget(row_i, row_values)
            self.scan_list_items += 1

    def display_save_file_window(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'JSON(*.json)')
        return path[0]

    def addPositioner(self, positionerName, axes, hasSpeed, hasHome=True, hasStop=True, options=(0, 0, 1, 1)):
        self._positioner_widget = QtWidgets.QGroupBox(f"{positionerName}")
        layout = QtWidgets.QGridLayout()
        for i in range(len(axes)):
            axis = axes[i]
            parNameSuffix = self._getParNameSuffix(positionerName, axis)
            # label = f'{positionerName} -- {axis}' if positionerName != axis else positionerName

            self.pars['Label' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{axis}</strong>')
            self.pars['Label' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['Position' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{0:.2f} mm</strong>')
            self.pars['Position' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['UpButton' + parNameSuffix] = guitools.BetterPushButton('+')
            self.pars['DownButton' + parNameSuffix] = guitools.BetterPushButton('-')
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
                self.pars['SpeedEdit' + parNameSuffix] = QtWidgets.QLineEdit('12') if axis != "Z" else QtWidgets.QLineEdit('8')

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

    def select_well(self, well):
        for well_id, btn in self.wells.items():
            if isinstance(btn, guitools.BetterPushButton):
                if well_id == well:
                    btn.setStyleSheet("background-color: green; font-size: 14px")
                else:
                    btn.setStyleSheet("background-color: grey; font-size: 14px")
        self.beacons_selected_well.setText(f"{well}")

    def select_labware(self, slot, options=(1, 1, 2, 1)):
        self.current_slot = slot
        if hasattr(self, "_wells_group_box"):
            self.main_grid_layout.removeWidget(self._wells_group_box)
        self._wells_group_box = QtWidgets.QGroupBox(f"{self._labware_dict[slot]}")
        layout = QtWidgets.QGridLayout()

        labware = self._labware_dict[slot]
        # Create dictionary to hold buttons
        self.wells = {}
        # Create grid layout for wells (buttons)
        well_buttons = {}
        rows = len(self._labware_dict[slot].rows())
        columns = len(self._labware_dict[slot].columns())
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
                # self.wells[corrds].setMaximumSize(30, 25)
                self.wells[corrds].setStyleSheet("background-color: None; font-size: 12px")
            else:
                self.wells[corrds] = guitools.BetterPushButton(corrds)  # QtWidgets.QPushButton(corrds)
                # self.wells[corrds].setMaximumSize(30, 25)
                self.wells[corrds].setStyleSheet("background-color: grey; font-size: 14px")
            self.wells[corrds].setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                             QtWidgets.QSizePolicy.Expanding)
            # Set style for empty cell
            # self.wells[corrds].setStyleSheet("background-color: none")
            # Add button/label to layout
            layout.addWidget(self.wells[corrds], pos[0], pos[1])

        # Change color of selected labware
        for slot_id, btn in self.deck_slots.items():
            if isinstance(btn, guitools.BetterPushButton):
                if slot_id == slot:
                    btn.setStyleSheet("background-color: blue; font-size: 14px")
                else:
                    btn.setStyleSheet("background-color: grey; font-size: 14px")
        # self._wells_group_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
        #                                     QtWidgets.QSizePolicy.Expanding)
        # self._wells_group_box.setMinimumSize(100,100)
        self._wells_group_box.setLayout(layout)
        self.main_grid_layout.addWidget(self._wells_group_box, *options)
        self.setLayout(self.main_grid_layout)

    def initialize_deck(self, deck_manager: DeckManager, options=[(1, 0, 1, 2), (1, 2, 1, 2)]):
        self._deck_dict = deck_manager.deck_layout
        self._labware_dict = deck_manager.labwares
        self._deck_group_box = QtWidgets.QGroupBox("Deck layout")
        layout = QtWidgets.QHBoxLayout()

        # Create dictionary to hold buttons
        slots = [slot.id for slot in deck_manager.deck_layout.locations.orderedSlots]
        used_slots = list(deck_manager.labwares.keys())
        self.deck_slots = {}

        # Create dictionary to store deck slots names (button texts)
        slots_buttons = {s: (0, i + 2) for i, s in enumerate(slots)}
        for slot_id, pos in slots_buttons.items():
            if slot_id in used_slots:
                # Do button if slot contains labware
                self.deck_slots[slot_id] = guitools.BetterPushButton(slot_id)  # QtWidgets.QPushButton(slot_id)
                # self.deck_slots[slot_id].setFixedSize(25, 20)
                self.deck_slots[slot_id].setMaximumSize(30, 25)
                self.deck_slots[slot_id].setStyleSheet("QPushButton"
                                                       "{"
                                                       "background-color : grey; font-size: 14px"
                                                       "}"
                                                       "QPushButton::pressed"
                                                       "{"
                                                       "background-color : red; font-size: 14px"
                                                       "}"
                                                       )
            else:
                self.deck_slots[slot_id] = QtWidgets.QLabel(slot_id)  # QtWidgets.QPushButton(slot_id)
                # self.deck_slots[slot_id].setFixedSize(25, 20)
                self.deck_slots[slot_id].setMaximumSize(30, 25)
                self.deck_slots[slot_id].setStyleSheet("background-color: None; font-size: 14px")
            layout.addWidget(self.deck_slots[slot_id])
        self._deck_group_box.setMaximumHeight(120)
        self._deck_group_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                           QtWidgets.QSizePolicy.Expanding)
        self._deck_group_box.setLayout(layout)
        self.select_labware(used_slots[0], options[0])
        self.main_grid_layout.addWidget(self._deck_group_box, *options[1])
        self.setLayout(self.main_grid_layout)

    def init_light_source(self, options=(3, 0, 1, 1)):
        # LED

        led_layout = QtWidgets.QHBoxLayout()
        self.LEDWidget = QtWidgets.QGroupBox()
        # valueDecimalsLED = 0
        # valueRangeLED = (0, 100)
        # tickIntervalLED = 1
        # singleStepLED = 1
        # self.sliderLED, self.LabelLED = self.setupSliderGui('Intensity (LED):', valueDecimalsLED, valueRangeLED,
        #                                                     tickIntervalLED, singleStepLED)
        self.LabelLED = QtWidgets.QLabel("LED Intensity [mA]: ")
        # self.sliderLED.valueChanged.connect(
        #     lambda value: self.sigSliderLEDValueChanged.emit(value)
        # )
        # led_layout.addWidget(self.ValueLED)
        # led_layout.addWidget(self.sliderLED, 3)
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

    def init_experiment_buttons(self, options=(7, 0, 1, 1)):
        exp_buttons_layout = QtWidgets.QGridLayout()
        self.ScanActionsWidget = QtWidgets.QGroupBox("Scan List Actions")
        self.ScanActionsWidget.setMinimumWidth(200)
        self.ScanSaveButton = guitools.BetterPushButton('Save')
        self.ScanSaveButton.setStyleSheet("font-size: 14px")
        self.ScanSaveButton.setFixedHeight(35)
        self.ScanSaveButton.setMinimumWidth(60)
        self.ScanSaveButton.setCheckable(False)
        self.ScanSaveButton.toggled.connect(self.sigScanSave)

        self.ScanStartButton = guitools.BetterPushButton('Start')
        self.ScanStartButton.setStyleSheet("background-color: black; font-size: 14px")
        self.ScanStartButton.setFixedHeight(35)
        self.ScanStartButton.setMinimumWidth(60)
        self.ScanStartButton.setCheckable(False)
        self.ScanStartButton.toggled.connect(self.sigScanStart)

        self.ScanStopButton = guitools.BetterPushButton('Stop')
        self.ScanStopButton.setStyleSheet("background-color: gray; font-size: 14px")
        self.ScanStopButton.setFixedHeight(35)
        self.ScanStopButton.setMinimumWidth(60)
        self.ScanStopButton.setCheckable(False)
        self.ScanStopButton.setEnabled(False)
        self.ScanStopButton.toggled.connect(self.sigScanStop)

        exp_buttons_layout.addWidget(self.ScanSaveButton, 0, 0, 1, 1)
        exp_buttons_layout.addWidget(self.ScanStartButton, 0, 1, 1, 1)
        exp_buttons_layout.addWidget(self.ScanStopButton, 0, 2, 1, 1)
        self.ScanActionsWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                             QtWidgets.QSizePolicy.Expanding)
        # self.ScanActionsWidget.setMaximumHeight(160)
        self.ScanActionsWidget.setLayout(exp_buttons_layout)
        self.main_grid_layout.addWidget(self.ScanActionsWidget, *options)

    def init_experiment_info(self, options=(8, 0, 1, 1)):
        self.ScanInfo = QtWidgets.QLabel('')
        self.ScanInfo_widget = QtWidgets.QGroupBox("Scan Info")
        ScanInfo_layout = QtWidgets.QGridLayout()
        ScanInfo_layout.addWidget(self.ScanInfo)
        self.ScanInfo_widget.setLayout(ScanInfo_layout)
        self.main_grid_layout.addWidget(self.ScanInfo_widget, *options)
        self.setLayout(self.main_grid_layout)

    def init_home_button(self, options=(2, 2, 1, 1)):
        self.home_button_widget = QtWidgets.QGroupBox("Stage")
        home_button_layout = QtWidgets.QGridLayout()
        self.home_button = guitools.BetterPushButton(text="HOME")  # QtWidgets.QPushButton(corrds)
        self.home_button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.home_button.setMinimumWidth(50)
        self.home_button.setMinimumHeight(50)
        self.home_button.setMaximumHeight(100)
        self.home_button.setStyleSheet("background-color: black; font-size: 14px")
        home_button_layout.addWidget(self.home_button)
        self.home_button_widget.setLayout(home_button_layout)
        self.main_grid_layout.addWidget(self.home_button_widget, *options)
        self.setLayout(self.main_grid_layout)

    def update_scan_info(self, dict_info):
        # {
        #     'experiment_status': self.state.value,
        #     'scan_info': self.shared_context.scan_info,
        #     'fluidics_info': self.shared_context.fluidic_info,
        #     'position': self.shared_context.position,
        #     'estimated_remaining_time': self.shared_context.remaining_time
        # }
        self.ScanInfo.setText(dict_info["experiment_status"])

    def init_well_action(self, options=(3, 0, 1, 1)):
        self.well_action_widget = QtWidgets.QGroupBox("Selected well")
        well_action_layout = QtWidgets.QGridLayout()
        self.beacons_selected_well = QtWidgets.QLabel("<Well>")
        well_action_layout.addWidget(self.beacons_selected_well, 0, 0, 1, 1)

        self.goto_btn = guitools.BetterPushButton('GO TO')
        self.goto_btn.setMaximumHeight(50)
        well_action_layout.addWidget(self.goto_btn, 0, 1, 1, 1)

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
        self.focusAllButton = guitools.BetterPushButton('Focus All')
        self.nextButton = guitools.BetterPushButton('Next')
        self.prevButton.clicked.connect(self.prevRow)
        self.nextButton.clicked.connect(self.nextRow)
        buttons_layout.addWidget(self.prevButton)
        buttons_layout.addWidget(self.nextButton)

        self.scan_list = TableWidgetDragRows()
        self.scan_list.set_header()
        self.scan_list_items = 0
        self.scan_list.itemPressed.connect(self.onSelectionChanged)
        # self.scan_list.itemSelectionChanged.connect(self.onSelectionChanged)
        # self.scan_list.setMaximumHeight(500)
        self.scan_list.setMinimumHeight(350)
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
            f'<strong>{position:.3f} mm</strong>')  # TODO: depends if um or mm!

    def updateSpeed(self, positionerName, axis, speed):
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        self.pars['Speed' + parNameSuffix].setText(f'<strong>{speed} um/s</strong>')

    def _getParNameSuffix(self, positionerName, axis):
        return f'{positionerName}--{axis}'


# From https://stackoverflow.com/questions/26227885/drag-and-drop-rows-within-qtablewidget
class TableWidgetDragRows(QtWidgets.QTableWidget):
    sigGoToTableClicked = QtCore.Signal(int)
    sigAdjustFocusClicked = QtCore.Signal(int)
    sigDeleteRowClicked = QtCore.Signal(int)
    sigAdjustPositionClicked = QtCore.Signal(int)
    sigSelectedDragRows = QtCore.Signal(list, int)  # list of selected rows, position to drag to.

    from locai.utils.scan_list import ScanPoint

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.columns = ["Slot", "Labware", "Well", "Index", "Offset", "Z_focus", "Absolute"]
        self.column_mapping = {
            "Slot": "slot",
            "Labware": "labware",
            "Well": "well",
            "Index": "position_in_well_index",
            "Offset": ("offset_from_center_x", "offset_from_center_y"),
            "Z_focus": "relative_focus_z",
            "Absolute": ("position_x", "position_y", "position_z"),
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

        # self.setDragEnabled(True)
        # self.setAcceptDrops(True)
        # self.viewport().setAcceptDrops(True)
        # self.setDragDropOverwriteMode(False)
        # self.setDropIndicatorShown(True)
        self.context_menu_enabled = True
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.resizeColumnsToContents()
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.onHorizontalHeaderClicked)
        # self.scan_list.setEditTriggers(self.scan_list.NoEditTriggers)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

    def set_item(self, row, col, item):
        self.setItem(row, col, QtWidgets.QTableWidgetItem(str(item)))

    def add_row_in_widget(self, row_id, current_point: ScanPoint):
        self.insertRow(row_id)
        self.set_item(row=row_id, col=self.columns.index("Slot"), item=current_point.slot)
        self.set_item(row=row_id, col=self.columns.index("Labware"), item=current_point.labware)
        self.set_item(row=row_id, col=self.columns.index("Well"), item=current_point.well)
        self.set_item(row=row_id, col=self.columns.index("Index"), item=round(current_point.position_in_well_index))
        self.set_item(row=row_id, col=self.columns.index("Offset"),
                      item=(round(current_point.offset_from_center_x),
                            round(current_point.offset_from_center_y)))
        self.set_item(row=row_id, col=self.columns.index("Z_focus"), item=round(current_point.relative_focus_z))
        self.set_item(row=row_id, col=self.columns.index("Absolute"),
                      item=(round(current_point.position_x),
                            round(current_point.position_y),
                            round(current_point.position_z)))

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
            action = menu.exec_(self.mapToGlobal(event.pos()))
            if action == goto_action:
                self.go_to_action(row)
            elif action == delete_action:
                self.deleteSelected(row)
            elif action == adjust_focus_action:
                self.adjust_focus_action(row)
            elif action == adjust_pos_action:
                self.adjust_position_action(row)

    def go_to_action(self, row):
        self.sigGoToTableClicked.emit(row)

    def adjust_focus_action(self, row):
        self.sigAdjustFocusClicked.emit(row)

    def adjust_position_action(self, row):
        self.sigAdjustPositionClicked.emit(row)

    def deleteSelected(self, row):
        self.sigDeleteRowClicked.emit(row)

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
