import csv
from typing import Dict

from PyQt5.QtCore import Qt
from imswitch.imcommon.model import initLogger
from imswitch.imcontrol.view import guitools as guitools
from qtpy import QtCore, QtWidgets

from .basewidgets import Widget
from ...controller.controllers.DeckController import ScanPoint


class DeckWidget(Widget):
    """ Widget in control of the piezo movement. """
    sigStepUpClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigStepDownClicked = QtCore.Signal(str, str)  # (positionerName, axis)
    sigsetSpeedClicked = QtCore.Signal(str, str)  # (positionerName, axis)

    sigStepAbsoluteClicked = QtCore.Signal(str)
    sigHomeAxisClicked = QtCore.Signal(str, str)
    sigStopAxisClicked = QtCore.Signal(str, str)

    sigZeroZAxisClicked = QtCore.Signal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.numPositioners = 0
        self.pars = {}
        self.main_grid_layout = QtWidgets.QGridLayout()
        self.current_slot = None
        self.current_well = None
        self.current_offset = (None, None)
        self.current_z_focus = None
        self.current_absolute_position = (None, None, None)
        self.first_z_focus = 0.0

        self.__logger = initLogger(self, instanceName="DeckWidget")

    # https://stackoverflow.com/questions/12608830/writing-a-qtablewidget-to-a-csv-or-xls
    # Extra blank row issue: https://stackoverflow.com/questions/3348460/csv-file-written-with-python-has-blank-lines-between-each-row
    def handleSave_(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'CSV(*.csv)')
        # if not path[0] != "":
        with open(path[0], 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            for row in range(self.scan_list.rowCount()):
                rowdata = []
                for column in range(self.scan_list.columnCount()):
                    item = self.scan_list.item(row, column)
                    if item is not None:
                        rowdata.append(
                            item.text())
                    else:
                        rowdata.append('')
                writer.writerow(rowdata)
        # else:
        #     self.__logger.debug("Empty path: handleSave")
        self.open_in_scanner_window()

    def handleSave(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'CSV(*.csv)')
        # if not path[0] != "":
        columns = range(self.scan_list.columnCount())
        header = [self.scan_list.horizontalHeaderItem(column).text()
                  for column in columns]
        with open(path[0], 'w') as csvfile:
            writer = csv.writer(
                csvfile, dialect='excel', lineterminator='\n')
            writer.writerow(header)
            for row in range(self.scan_list.rowCount()):
                writer.writerow(
                    self.scan_list.item(row, column).text()
                    for column in columns)
        # else:
        #     self.__logger.debug("Empty path: handleSave")
        self.open_in_scanner_window()

    def open_in_scanner_window(self):
        choice = QtWidgets.QMessageBox.question(self, 'Next action',
                                                "Do you want to load the current scan list in the Deck Scanner?",
                                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if choice == QtWidgets.QMessageBox.Yes:
            print("Open table in DeckScanner")
            QtWidgets.QMessageBox.information(self, "Scan list loaded in DeckScanner.",
                                              'Scan list loaded. Open the DeckScanner.',
                                              QtWidgets.QMessageBox.Ok)
            print("Click DeckScanner")
        else:
            pass

    def handleOpen_(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'CSV(*.csv)')
        # if not path.isEmpty():
        with open(path[0], 'r') as csvfile:
            self.scan_list.clear()
            self.scan_list.setHorizontalHeaderLabels(["Slot", "Well", "Offset", "Z_focus", "Absolute"])
            self.scan_list.setRowCount(0)
            self.scan_list_items = 0
            for rowdata in csv.reader(csvfile):
                self.scan_list.insertRow(self.scan_list_items)
                for column, data in enumerate(rowdata):
                    item = QtWidgets.QTableWidgetItem(data)
                    self.scan_list.setItem(self.scan_list_items, column, item)
                self.scan_list_items += 1

    def handleOpen(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'CSV(*.csv)')
        # if not path.isEmpty():
        self.scan_list.clear()
        self.scan_list.setRowCount(0)
        self.scan_list_items = 0
        with open(path[0], 'r') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)
            self.scan_list.setColumnCount(len(header))
            self.scan_list.setHorizontalHeaderLabels(header)
            for row, values in enumerate(reader):
                self.scan_list.insertRow(row)
                for column, value in enumerate(values):
                    self.scan_list.setItem(
                        row, column, QtWidgets.QTableWidgetItem(value))

    def handleClear(self):
        self.scan_list.clearContents()
        self.scan_list.setRowCount(0)
        self.scan_list_items = 0

    def display_open_file_window(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open File', '', 'CSV(*.csv)')
        return path

    def display_save_file_window(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save File', '', 'CSV(*.csv)')
        return path

    def select_well(self, well):
        for well_id, btn in self.wells.items():
            if isinstance(btn, guitools.BetterPushButton):
                if well_id == well:
                    btn.setStyleSheet("background-color: green; font-size: 14px")
                else:
                    btn.setStyleSheet("background-color: grey; font-size: 14px")
        self.beacons_selected_well.setText(f"{well}")

    def select_labware(self, slot):
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
                self.wells[corrds].setFixedSize(25, 20)
                self.wells[corrds].setStyleSheet("background-color: None; font-size: 12px")
            else:
                self.wells[corrds] = guitools.BetterPushButton(corrds)  # QtWidgets.QPushButton(corrds)
                self.wells[corrds].setFixedSize(25, 20)
                self.wells[corrds].setStyleSheet("background-color: grey; font-size: 14px")
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
        #                         QtWidgets.QSizePolicy.Expanding)
        self._wells_group_box.setLayout(layout)
        self.main_grid_layout.addWidget(self._wells_group_box, 2, 5, 4, 9)
        self.setLayout(self.main_grid_layout)

    def add_home(self, layout):
        self.home = guitools.BetterPushButton(text="HOME")  # QtWidgets.QPushButton(corrds)
        self.home.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                QtWidgets.QSizePolicy.Expanding)
        self.home.setMinimumWidth(120)
        self.home.setMinimumHeight(40)
        self.home.setMaximumHeight(60)
        self.home.setStyleSheet("background-color: black; font-size: 14px")
        layout.addWidget(self.home)

    def add_zero(self, layout):
        # self.zero = guitools.BetterPushButton(text="ZERO")  # QtWidgets.QPushButton(corrds)
        # TODO: implement ZERO -> solve ESP32StageManager/Motor issue with set_motor
        self.zero = guitools.BetterPushButton(text="ZERO\nZ-AXIS")  # QtWidgets.QPushButton(corrds)
        self.zero.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                QtWidgets.QSizePolicy.Expanding)
        self.zero.setMinimumWidth(120)
        self.zero.setMinimumHeight(40)
        self.zero.setMaximumHeight(60)
        # self.zero.setStyleSheet("background-color: black; font-size: 14px")
        self.zero.setStyleSheet("background-color: white; color: black; font-size: 14px")
        layout.addWidget(self.zero)

    def initialize_deck(self, deck_dict: Dict, labwares_dict: Dict):
        self._deck_dict = deck_dict
        self._labware_dict = labwares_dict

        self._deck_group_box = QtWidgets.QGroupBox("Deck layout")
        layout = QtWidgets.QHBoxLayout()

        # Add home and zero buttons
        self.add_home(layout)
        self.add_zero(layout)
        # self.add_slot(layout)

        # Create dictionary to hold buttons
        slots = [slot["id"] for slot in deck_dict["locations"]["orderedSlots"]]
        used_slots = list(labwares_dict.keys())
        self.deck_slots = {}

        # Create dictionary to store deck slots names (button texts)
        slots_buttons = {s: (0, i + 2) for i, s in enumerate(slots)}
        for slot_id, pos in slots_buttons.items():
            if slot_id in used_slots:
                # Do button if slot contains labware
                self.deck_slots[slot_id] = guitools.BetterPushButton(slot_id)  # QtWidgets.QPushButton(slot_id)
                self.deck_slots[slot_id].setFixedSize(25, 20)
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
                self.deck_slots[slot_id].setFixedSize(25, 20)
                self.deck_slots[slot_id].setStyleSheet("background-color: None; font-size: 14px")
            layout.addWidget(self.deck_slots[slot_id])
        self._deck_group_box.setMaximumHeight(120)
        self._deck_group_box.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                           QtWidgets.QSizePolicy.Expanding)
        self._deck_group_box.setLayout(layout)
        self.select_labware(used_slots[0])
        if len(used_slots) == 1 and "1" in self.deck_slots.keys():
            self.deck_slots["1"].setHidden(True)
        self.main_grid_layout.addWidget(self._deck_group_box, 1, 5, 1, 9)
        self.setLayout(self.main_grid_layout)

    def set_table_item(self, row, col, item):
        self.scan_list.setItem(row, col, QtWidgets.QTableWidgetItem(str(item)))

    def init_beacons(self):
        self.beacons_widget = QtWidgets.QGroupBox("Beacons")
        beacons_layout = QtWidgets.QGridLayout()
        self.beacons_nx = QtWidgets.QLineEdit("1")
        self.beacons_ny = QtWidgets.QLineEdit("1")
        self.beacons_dx = QtWidgets.QLineEdit("300")
        self.beacons_dy = QtWidgets.QLineEdit("300")
        self.beacons_add = guitools.BetterPushButton('ADD')
        self.beacons_selected_well = QtWidgets.QLabel("<Well>")
        # beacons_layout.addWidget(QtWidgets.QLabel("# Positions in well"), 0, 0, 1, 1)
        beacons_layout.addWidget(QtWidgets.QLabel("Nx x Ny"), 0, 0, 1, 1)
        beacons_layout.addWidget(QtWidgets.QLabel("Dx x Dy [um]"), 1, 0, 1, 1)
        # beacons_layout.addWidget(self.pos_in_well_lined, 0, 2, 1, 1)
        beacons_layout.addWidget(self.beacons_nx, 0, 1, 1, 1)
        beacons_layout.addWidget(self.beacons_ny, 0, 2, 1, 1)
        beacons_layout.addWidget(self.beacons_dx, 1, 1, 1, 1)
        beacons_layout.addWidget(self.beacons_dy, 1, 2, 1, 1)
        beacons_layout.addWidget(self.beacons_selected_well, 0, 3, 1, 1)
        beacons_layout.addWidget(self.beacons_add, 1, 3, 1, 1)
        self.beacons_widget.setMaximumHeight(120)
        self.beacons_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                          QtWidgets.QSizePolicy.Expanding)
        self.beacons_widget.setLayout(beacons_layout)
        self.main_grid_layout.addWidget(self.beacons_widget, 1, 0, 3, 5)


    def init_scan_list(self):
        # , detectorName, detectorModel, detectorParameters, detectorActions,supportedBinnings, roiInfos):
        self.scan_list = TableWidgetDragRows()
        self.scan_list.setColumnCount(5)
        self.scan_list.setHorizontalHeaderLabels(self.scan_list.columns)
        self.scan_list_items = 0
        self.scan_list.setColumnHidden(0, True)
        # self.scan_list.setEditTriggers(self.scan_list.NoEditTriggers)
        self.scan_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self._actions_widget = QtWidgets.QGroupBox("Actions")
        self.scan_list_actions_widget = QtWidgets.QGroupBox("Scan List Actions")

        actions_layout = QtWidgets.QHBoxLayout()
        scan_list_actions_layout = QtWidgets.QHBoxLayout()

        self.goto_btn = guitools.BetterPushButton('GO TO')
        self.add_current_btn = guitools.BetterPushButton('ADD CURRENT')


        self.buttonOpen = guitools.BetterPushButton('Open')
        self.buttonOpen.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Expanding)
        self.buttonOpen.setStyleSheet("background-color : gray; color: black")
        self.buttonSave = guitools.BetterPushButton('Save')
        self.buttonSave.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Expanding)
        self.buttonSave.setStyleSheet("background-color : gray; color: black")
        self.buttonClear = guitools.BetterPushButton('Clear')
        self.buttonClear.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                       QtWidgets.QSizePolicy.Expanding)
        self.buttonClear.setStyleSheet("background-color : gray; color: black")

        actions_layout.addWidget(self.goto_btn)
        actions_layout.addWidget(self.add_current_btn)
        scan_list_actions_layout.addWidget(self.buttonOpen)
        scan_list_actions_layout.addWidget(self.buttonSave)
        scan_list_actions_layout.addWidget(self.buttonClear)

        self.scan_list_actions_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                                    QtWidgets.QSizePolicy.Expanding)
        self.scan_list_actions_widget.setMaximumHeight(60)
        self._actions_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                           QtWidgets.QSizePolicy.Expanding)
        # self._actions_widget.setMaximumWidth(140)
        self._actions_widget.setMaximumHeight(60)
        self._actions_widget.setLayout(actions_layout)
        self.scan_list_actions_widget.setLayout(scan_list_actions_layout)

        self.scan_list.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                     QtWidgets.QSizePolicy.Expanding)
        # self.scan_list.setMaximumHeight(500)
        # self.scan_list.setMinimumWidth(500)

        self.main_grid_layout.addWidget(self.scan_list, 6, 0, 1, 14)
        self.main_grid_layout.addWidget(self._actions_widget, 4, 0, 1, 5)
        self.main_grid_layout.addWidget(self.scan_list_actions_widget, 5, 0, 1, 5)

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

    def add_current_position_to_scan_(self):
        self.__logger.debug(f"Adding current position: {self.current_slot}, {self.current_well}")
        row_id = len(self._get_items())

        self.scan_list.insertRow(row_id)
        if row_id == 0:
            self.first_z_focus = self.current_z_focus
            self.set_table_item(row_id, 3, 0)
        else:
            relative_z_focus = self.current_absolute_position[2] - self.first_z_focus
            self.set_table_item(row_id, 3, relative_z_focus)

        self.set_table_item(row_id, 0, self.current_slot)
        self.set_table_item(row_id, 1, self.current_well)
        self.set_table_item(row_id, 2, self.current_offset)
        self.set_table_item(row_id, 4, self.current_absolute_position)
        self.scan_list_items = row_id

        for row in range(self.scan_list.rowCount()):
            rowdata = []
            for column in range(self.scan_list.columnCount()):
                item = self.scan_list.item(row, column)
                if item is not None:
                    rowdata.append(
                        item.text())
                else:
                    rowdata.append('')
            self.__logger.debug(rowdata)

    def getAbsPosition(self, positionerName, axis):
        """ Returns the absolute position of the  specified positioner axis in
        micrometers. """
        parNameSuffix = self._getParNameSuffix(positionerName, axis)
        return float(self.pars['AbsolutePosEdit' + parNameSuffix].text())

    def addPositioner(self, positionerName, axes, hasSpeed, hasHome=True, hasStop=True):
        self._positioner_widget = QtWidgets.QGroupBox(f"{positionerName}")
        layout = QtWidgets.QGridLayout()
        for i in range(len(axes)):
            axis = axes[i]
            parNameSuffix = self._getParNameSuffix(positionerName, axis)
            # label = f'{positionerName} -- {axis}' if positionerName != axis else positionerName

            self.pars['Label' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{axis}</strong>')
            self.pars['Label' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['Position' + parNameSuffix] = QtWidgets.QLabel(f'<strong>{0:.2f} µm</strong>')
            self.pars['Position' + parNameSuffix].setTextFormat(QtCore.Qt.RichText)
            self.pars['UpButton' + parNameSuffix] = guitools.BetterPushButton('+')
            self.pars['DownButton' + parNameSuffix] = guitools.BetterPushButton('-')
            self.pars['StepEdit' + parNameSuffix] = QtWidgets.QLineEdit('1000')

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
                self.pars['SpeedEdit' + parNameSuffix] = QtWidgets.QLineEdit('15000')

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
        self.main_grid_layout.addWidget(self._positioner_widget, 0, 0, 1, 14)

    @property
    def current_slot(self):
        return self._current_slot

    @current_slot.setter
    def current_slot(self, current_slot):
        self._current_slot = current_slot

    @property
    def current_well(self):
        return self._current_well

    @current_well.setter
    def current_well(self, current_well):
        self._current_well = current_well

    @property
    def current_offset(self):
        return self._current_offset

    @current_offset.setter
    def current_offset(self, current_offset):
        self._current_offset = current_offset

    @property
    def current_z_focus(self):
        return self._current_z_focus

    @current_z_focus.setter
    def current_z_focus(self, current_z_focus):
        self._current_z_focus = current_z_focus

    @property
    def current_absolute_position(self):
        return self._current_absolute_position

    @current_absolute_position.setter
    def current_absolute_position(self, current_absolute_position):
        self._current_absolute_position = current_absolute_position

    # @property
    # def positions_in_well(self):
    #     try:
    #         if int(self.pos_in_well_lined.text()) > 4:
    #             return 4
    #         else:
    #             return int(self.pos_in_well_lined.text())
    #     except ValueError:
    #         return 1

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
            f'<strong>{round(position)} um</strong>')  # TODO: depends if um or mm!

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
    sigSelectedDragRows = QtCore.Signal(list, int) # list of selected rows, position to drag to.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.columns = ["Slot", "Well", "Offset", "Z_focus", "Absolute", "Pos_idx"]
        self.columns_map_dict = {
            "Slot": 0, "Well": 1, "Offset": 3, "Z_focus":4, "Absolute":5, "Pos_idx":2
        }
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.scan_list_items = 0
        self.setColumnHidden(0, True)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)

        self.horizontalHeader().sectionClicked.connect(self.onHorizontalHeaderClicked)

        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.onHorizontalHeaderClicked)

    def onHorizontalHeaderClicked(self, column_index):
        if self.selectionModel().selection().indexes():
            for i in self.selectionModel().selection().indexes():
                column = i.column()
            menu = QtWidgets.QMenu()
            goto_action = menu.addAction("Go To")
            delete_action = menu.addAction("Delete")
            adjust_focus_action = menu.addAction("Adjust Focus")

            action = menu.exec_(column_index)
            if action == goto_action:
                self.go_to_action(row)
                print(f"{row}, {column}")
            elif action == delete_action:
                self.deleteSelected(row)
            elif action == adjust_focus_action:
                self.adjust_focus_action(row)



    def get_first_z_focus(self):
        return float(self.item(0, 3).text())

    def contextMenuEvent(self, event):
        if self.selectionModel().selection().indexes():
            for i in self.selectionModel().selection().indexes():
                row, column = i.row(), i.column()
            menu = QtWidgets.QMenu()
            goto_action = menu.addAction("Go To")
            delete_action = menu.addAction("Delete")
            adjust_focus_action = menu.addAction("Adjust Focus")

            action = menu.exec_(self.mapToGlobal(event.pos()))
            if action == goto_action:
                self.go_to_action(row)
                print(f"{row}, {column}")
            elif action == delete_action:
                self.deleteSelected(row)
            elif action == adjust_focus_action:
                self.adjust_focus_action(row)

    def go_to_action(self, row):
        self.sigGoToTableClicked.emit(row)

    def adjust_focus_action(self, row):
        self.sigAdjustFocusClicked.emit(row)

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
