import dataclasses
import json
import time
from functools import partial
from typing import Optional
from itertools import product
import csv
from typing import Union, Dict, Tuple, List, Optional

import pandas as pd
import numpy as np
from imswitch.imcommon.framework import Signal
from imswitch.imcommon.model import initLogger, APIExport
from imswitch.imcontrol.view import guitools as guitools
from opentrons.types import Point

from locai.deck.deck_config import DeckConfig
from ..basecontrollers import LiveUpdatedController
from ...model.SetupInfo import OpentronsDeckInfo

_attrCategory = 'Positioner'
_positionAttr = 'Position'
_speedAttr = "Speed"
_homeAttr = "Home"
_stopAttr = "Stop"
_objectiveRadius = 21.8 / 2
_objectiveRadius = 29.0 / 2  # Olympus


@dataclasses.dataclass
class ScanPoint:
    labware: str
    slot: int
    well: str
    position_x: float
    position_y: float
    position_z: float
    offset_from_center_x: float
    offset_from_center_y: float
    relative_focus_z: float


# dict = dataclasses.asdict(ScanPoint)

class DeckController(LiveUpdatedController):
    """ Linked to OpentronsDeckWidget.
    Safely moves around the OTDeck and saves positions to be scanned with OpentronsDeckScanner."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__logger = initLogger(self, instanceName="DeckController")

        # Deck and Labwares definitions:
        self.objective_radius = _objectiveRadius
        ot_info: OpentronsDeckInfo = self._setupInfo.deck["OpentronsDeck"]
        deck_layout = json.load(open(ot_info["deck_file"], "r"))

        self.deck_definition = DeckConfig(deck_layout, ot_info["labwares"])
        self.translate_units = self._setupInfo.deck["OpentronsDeck"]["translate_units"]

        # Has control over positioner
        self.initialize_positioners()
        #
        self.selected_slot = None
        self.selected_well = None
        self.relative_focal_plane = None
        # self.scanner = LabwareScanner(self.positioner, self.deck, self.labwares, _objectiveRadius)
        self._widget.initialize_deck(self.deck_definition.deck, self.deck_definition.labwares)
        self._widget.init_scan_list()
        self._widget.init_beacons()
        self.scan_table: List[ScanPoint] = []
        # Connect widget´s buttons
        self.connect_home()
        self.connect_zero()
        self.connect_deck_slots()
        self._widget.scan_list.sigGoToTableClicked.connect(self.go_to_position_in_table)
        self._widget.scan_list.sigDeleteRowClicked.connect(self.delete_position_in_table)
        self._widget.scan_list.sigAdjustFocusClicked.connect(self.adjust_focus_in_table)
        self._widget.buttonOpen.clicked.connect(self.open_scan_table_from_file)
        self._widget.buttonSave.clicked.connect(self.save_scan_table_to_file)
        self._widget.buttonClear.clicked.connect(self.clear_scan_table)
        self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)
        self._widget.beacons_add.clicked.connect(self.add_beacons)

    def add_beacons(self):
        try:
            nx, ny = int(self._widget.beacons_nx.text()), int(self._widget.beacons_ny.text())
            dx, dy = int(self._widget.beacons_dx.text()), int(self._widget.beacons_dy.text())
            x, y, _ = self.deck_definition.get_well_position(slot=self.selected_slot, well=self.selected_well)
            _, _, z = Point(*self.positioner.get_position())
            x, y, z = self.translate_position(Point(x, y, z))  # Positioner value
            xx, yy = [dx * (i - (nx - 1) / 2) for i in range(nx)], [dy * (i - (ny - 1) / 2) for i in range(ny)]
            for xi, yi in product(xx, yy):
                point_to_scan = self.parse_position(Point(x=xi + x, y=yi + y, z=z))
                self.scan_table.append(point_to_scan)
            self.update_table_in_widget()
        except Exception as e:
            self.__logger.debug(f"No well selected: Please, select a well before adding beacons. {e}")

    def parse_position(self, current_position: Point) -> ScanPoint:
        current_position = self.retranslate_position(current_position)
        current_slot = self.deck_definition.get_slot(current_position)
        current_well = self.deck_definition.get_closest_well(current_position)
        well_position = self.deck_definition.get_well_position(current_slot, current_well)  # Deck measurement
        well_position = self.translate_position(well_position)  # Positioner value
        zero = self.translate_position(10e-4)  # Positioner value
        current_position = self.translate_position(current_position)  # Positioner value
        offset = tuple([b - a if np.abs(b - a) > zero else 0.00 for (a, b) in
                        zip(well_position,
                            current_position)][:2])
        labware = self.deck_definition.labwares[current_slot].load_name
        if not self.scan_table:  # First positions holds relative zero
            self.relative_focal_plane = current_position[2]
        z_focus = current_position[2] - self.relative_focal_plane
        return ScanPoint(labware=labware, slot=int(current_slot), well=current_well,
                         position_x=current_position[0], position_y=current_position[1],
                         position_z=current_position[2],
                         offset_from_center_x=offset[0], offset_from_center_y=offset[1],
                         relative_focus_z=z_focus)

    def add_current_position_to_scan(self):
        # self.__logger.debug(f"Adding current position: {self.current_slot}, {self.current_well}")
        current_position = Point(*self.positioner.get_position())
        try:
            current_point = self.parse_position(current_position)
            self.scan_table.append(current_point)
            self.update_table_in_widget()

        except Exception as e:
            self.__logger.debug(f"Error when updating values. {e}")

    def update_table_in_widget(self):
        self._widget.scan_list.clear()
        self._widget.scan_list.setRowCount(0)
        self._widget.scan_list_items = 0
        self._widget.scan_list.setColumnCount(len(self._widget.scan_list.columns))
        self._widget.scan_list.setHorizontalHeaderLabels(self._widget.scan_list.columns)
        for row_i, row_values in enumerate(self.scan_table):
            self.add_row_in_widget(row_i, row_values)

    def add_row_in_widget(self, row_id, current_point):
        self._widget.scan_list.insertRow(row_id)
        self._widget.set_table_item(row_id, 0, current_point.slot)
        self._widget.set_table_item(row_id, 1, current_point.well)
        self._widget.set_table_item(row_id, 2, (
        round(current_point.offset_from_center_x), round(current_point.offset_from_center_y)))
        self._widget.set_table_item(row_id, 3, round(current_point.relative_focus_z))
        self._widget.set_table_item(row_id, 4,
                                    (round(current_point.position_x), round(current_point.position_y),
                                     round(current_point.position_z)))
        self._widget.scan_list_items += 1

    def clear_scan_table(self):
        self.scan_table = []
        self._widget.scan_list.clear()
        self._widget.scan_list.setHorizontalHeaderLabels(self._widget.scan_list.columns)

    def open_scan_table_from_file(self):
        path = self._widget.display_open_file_window()
        # if not path.isEmpty():
        self.scan_table = []
        # load table from path
        with open(path[0], 'r') as csvfile:
            scan_dict = pd.read_csv(csvfile, sep=",").to_dict()

            for k, v in scan_dict.items():
                ...

            reader = csv.reader(csvfile)
            header = next(reader)
            for row, values in enumerate(reader):
                self.scan_table.append(values)

        self.update_table_in_widget()

    def save_scan_table_to_file(self):
        path = self._widget.display_save_file_window()
        [dataclasses.asdict(i) for i in self.scan_table]

        self._widget.open_in_scanner_window()

    def go_to_position_in_table(self, row):
        abs_pos = self.scan_table[row].position_x, self.scan_table[row].position_y, self.scan_table[row].position_z
        self.move(new_position=Point(*abs_pos))

    def delete_position_in_table(self, row):
        deleted_point = self.scan_table.pop(row)
        self.__logger.debug(f"Deleting row {row}: {deleted_point}")
        self.update_table_in_widget()

    def adjust_focus_in_table(self, row):
        _, _, z_new = self.positioner.get_position()
        z_old = self.scan_table[row].position_z
        if z_old == z_new:
            return
        if row == 0:
            self.scan_table[row].position_z = z_new
            self.relative_focal_plane = z_new
            for i_row, values in enumerate(self.scan_table[1:]):
                print(values)
                self.scan_table[1:][i_row].relative_focus_z = (self.scan_table[1:][i_row].position_z - self.relative_focal_plane)
            # print("Propagate values below...")
        else:
            z_old = self.scan_table[row].position_z
            self.scan_table[row].position_z = z_new
            self.scan_table[row].relative_focus_z = (z_new-self.relative_focal_plane)
        self.update_table_in_widget()


    @property
    def selected_well(self):
        return self._selected_well

    @selected_well.setter
    def selected_well(self, well):
        self._selected_well = well

    @property
    def selected_slot(self):
        return self._selected_slot

    @selected_slot.setter
    def selected_slot(self, slot):
        self._selected_slot = slot

    def connect_all_buttons(self):
        self.connect_home()
        self.connect_zero()
        self.connect_deck_slots()

    def initialize_positioners(self):
        # Has control over positioner
        self.positioner_name = self._master.positionersManager.getAllDeviceNames()[0]
        self.positioner = self._master.positionersManager[self.positioner_name]
        # Set up positioners
        for pName, pManager in self._master.positionersManager:
            if not pManager.forPositioning:
                continue
            hasSpeed = hasattr(pManager, 'speed')
            hasHome = hasattr(pManager, 'home')
            hasStop = hasattr(pManager, 'stop')
            self._widget.addPositioner(pName, pManager.axes, hasSpeed, hasHome, hasStop)
            for axis in pManager.axes:
                self.setSharedAttr(axis, _positionAttr, pManager.position[axis])
                if hasSpeed:
                    self.setSharedAttr(axis, _speedAttr, pManager.speed[axis])
                if hasHome:
                    self.setSharedAttr(axis, _homeAttr, pManager.home[axis])
                if hasStop:
                    self.setSharedAttr(axis, _stopAttr, pManager.stop[axis])

        # Connect CommunicationChannel signals
        self._commChannel.sharedAttrs.sigAttributeSet.connect(self.attrChanged)
        self._commChannel.sigSetSpeed.connect(lambda speed: self.setSpeedGUI(speed))

        # Connect PositionerWidget signals
        self._widget.sigStepUpClicked.connect(self.stepUp)
        self._widget.sigStepDownClicked.connect(self.stepDown)
        self._widget.sigsetSpeedClicked.connect(self.setSpeedGUI)
        self._widget.sigStepAbsoluteClicked.connect(self.moveAbsolute)
        self._widget.sigHomeAxisClicked.connect(self.homeAxis)
        self._widget.sigStopAxisClicked.connect(self.stopAxis)

    def stopAxis(self, positionerName, axis):
        self.__logger.debug(f"Stopping axis {axis}")
        self._master.positionersManager[positionerName].forceStop(axis)

    def homeAxis(self, positionerName, axis):
        self.__logger.debug(f"Homing axis {axis}")
        self._master.positionersManager[positionerName].doHome(axis)

    def closeEvent(self):
        self._master.positionersManager.execOnAll(
            lambda p: [p.setPosition(0, axis) for axis in p.axes]
        )

    def getPos(self):
        return self._master.positionersManager.execOnAll(lambda p: p.position)

    def getSpeed(self):
        return self._master.positionersManager.execOnAll(lambda p: p.speed)

    @APIExport(runOnUIThread=True)
    def home(self) -> None:
        # TODO: fix home in PositionerManager
        self.positioner.doHome("X")
        time.sleep(0.1)
        self.positioner.doHome("Y")
        [self.updatePosition(axis) for axis in self.positioner.axes]

    @APIExport(runOnUIThread=True)
    def zero(self):
        if not len(self.scan_table):
            self.relative_focal_plane = self.positioner.get_position()
        else:
            old_relative_focal_plane = self.scan_table[0].position_z
            if old_relative_focal_plane != self.relative_focal_plane:
                raise(f"Error: mismatch in relative focus position.")
            _, _, self.relative_focal_plane = self.positioner.get_position()
            for i_row, values in enumerate(self.scan_table):
                self.scan_table[i_row].position_z += (self.relative_focal_plane - old_relative_focal_plane)
        self.update_table_in_widget()

    @APIExport(runOnUIThread=True)
    def move(self, new_position):
        """ Moves positioner to absolute position. """
        speed = [self._widget.getSpeed(self.positioner_name, axis) for axis in self.positioner.axes]
        self.positioner.move(new_position, "XYZ", is_absolute=True, is_blocking=False, speed=speed)
        [self.updatePosition(axis) for axis in self.positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    def setPos(self, axis, position):
        """ Moves the positioner to the specified position in the specified axis. """
        self.positioner.setPosition(position, axis)
        self.updatePosition(axis)

    def moveAbsolute(self, axis):
        self.positioner.move(self._widget.getAbsPosition(self.positioner_name, axis), axis=axis, is_absolute=True,
                             is_blocking=False)
        [self.updatePosition(axis) for axis in self.positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    def stepUp(self, positionerName, axis):
        shift = self._widget.getStepSize(positionerName, axis)
        # if self.scanner.objective_collision_avoidance(axis=axis, shift=shift):
        try:
            self.positioner.move(shift, axis, is_blocking=False)
            [self.updatePosition(axis) for axis in self.positioner.axes]
            # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")

    def stepDown(self, positionerName, axis):
        shift = -self._widget.getStepSize(positionerName, axis)
        try:
            self.positioner.move(shift, axis, is_blocking=False)
            [self.updatePosition(axis) for axis in self.positioner.axes]
            # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")

    def setSpeedGUI(self, axis):
        speed = self._widget.getSpeed(self.positioner_name, axis)
        self.setSpeed(speed=speed, axis=axis)

    def setSpeed(self, axis, speed=(12, 12, 8)):
        self.positioner.setSpeed(speed, axis)
        self._widget.updateSpeed(self.positioner_name, axis, speed)

    def updatePosition(self, axis):
        newPos = self.positioner.position[axis]
        self._widget.updatePosition(self.positioner_name, axis, newPos)
        self.setSharedAttr(axis, _positionAttr, newPos)

    def attrChanged(self, key, value):
        if self.settingAttr or len(key) != 4 or key[0] != _attrCategory:
            return
        # positionerName = key[1]
        axis = key[2]
        if key[3] == _positionAttr:
            self.setPositioner(axis, value)

    def setPositioner(self, axis: str, position: float) -> None:
        """ Moves the specified positioner axis to the specified position. """
        self.setPos(axis, position)

    def setSharedAttr(self, axis, attr, value):
        self.settingAttr = True
        try:
            self._commChannel.sharedAttrs[(_attrCategory, self.positioner_name, axis, attr)] = value
        finally:
            self.settingAttr = False

    @APIExport()
    def get_labwares(self):
        return self.deck_definition.labwares

    @APIExport()
    def getAvailableLabwareSlots(self):
        return [slot for slot in self.deck_definition.labwares.keys()]

    @APIExport(runOnUIThread=True)
    def select_labware(self, slot):
        self.__logger.debug(f"Slot {slot}")
        self._widget.select_labware(slot)
        self.selected_slot = slot
        self.selected_well = None
        self.connect_wells()

    @APIExport(runOnUIThread=True)
    def select_well(self, well):
        self.__logger.debug(f"Well {well}")
        self.selected_well = well
        self._widget.select_well(well)
        self.connect_go_to()

    def retranslate_position(self, position: Point, flip_xy=False):
        if flip_xy:  # TODO: avoid this by using normal coordinate system
            position = Point(position.y, position.x, position.z)
        if self.translate_units == "mm2um":
            return position * 0.001
        elif self.translate_units == "um2mm":
            return position * 1000
        elif self.translate_units is None:
            return position
        else:
            raise NotImplementedError(f"Not recognized units.")

    def translate_position(self, position: Point, flip_xy=False):
        if flip_xy:  # TODO: avoid this by using normal coordinate system
            position = Point(position.y, position.x, position.z)
        if self.translate_units == "mm2um":
            return position * 1000
        elif self.translate_units == "um2mm":
            return position * 0.001
        elif self.translate_units is None:
            return position
        else:
            raise NotImplementedError(f"Not recognized units.")

    @APIExport(runOnUIThread=True)
    def move_to_well(self, well: str, slot: Optional[str] = None):
        """ Moves positioner to center of selecterd well keeping the current Z-axis position. """
        self.__logger.debug(f"Move to {well} ({slot})")
        speed = [self._widget.getSpeed(self.positioner_name, axis) for axis in self.positioner.axes]
        well_position = self.deck_definition.get_well_position(slot=slot, well=well)
        well_position = self.translate_position(well_position)
        self.positioner.move(well_position[:2], "XY", is_absolute=True, is_blocking=False,
                             speed=speed[:2])
        [self.updatePosition(axis) for axis in self.positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    def current_slot(self):
        return self.deck_definition.get_slot(self.positioner.get_position())

    def get_position_in_deck(self):
        return Point(*self.positioner.get_position()) + self.deck_definition.corner_offset

    def connect_deck_slots(self):
        """Connect Deck Slots (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        for slot, btn in self._widget.deck_slots.items():
            # Connect signals
            # self.pars['UpButton' + parNameSuffix].clicked.connect(
            #    lambda *args, axis=axis: self.sigStepUpClicked.emit(positionerName, axis)
            # )
            if isinstance(btn, guitools.BetterPushButton):
                btn.clicked.connect(partial(self.select_labware, slot))
        # Select default slot
        self.select_labware(list(self._widget._labware_dict.keys())[0])  # TODO: improve...

    def connect_go_to(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""
        if isinstance(self._widget.goto_btn, guitools.BetterPushButton):
            try:
                self._widget.goto_btn.clicked.disconnect()
            except Exception:
                pass
            self._widget.goto_btn.clicked.connect(partial(self.move_to_well, self.selected_well, self.selected_slot))

    def connect_home(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""
        if isinstance(self._widget.home, guitools.BetterPushButton):
            self._widget.home.clicked.connect(self.home)

    def connect_zero(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""
        if isinstance(self._widget.zero, guitools.BetterPushButton):
            self._widget.zero.clicked.connect(self.zero)

    def connect_wells(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        for well, btn in self._widget.wells.items():
            # Connect signals
            # self.pars['UpButton' + parNameSuffix].clicked.connect(
            #    lambda *args, axis=axis: self.sigStepUpClicked.emit(positionerName, axis)
            # )
            if isinstance(btn, guitools.BetterPushButton):
                btn.clicked.connect(partial(self.select_well, well))
