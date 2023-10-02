import dataclasses
import json
import os
import threading

import time
from functools import partial
from typing import Optional

from itertools import product
import csv
from typing import Union, Dict, Tuple, List, Optional
import re

import pandas as pd
import numpy as np
from imswitch.imcommon.framework import Signal
from imswitch.imcommon.model import initLogger, APIExport
from imswitch.imcontrol.view import guitools as guitools
# from opentrons.types import Point

from locai.deck.deck_config import DeckConfig
from ..basecontrollers import LiveUpdatedController
from ...model.SetupInfo import OpentronsDeckInfo
from locai.utils.scan_list import ScanPoint, open_scan_list, save_scan_list

# os.environ["DEBUG"] = "1"
from locai_app.generics import Point
from locai_app.impl.locai_device_impl import LocaiDevice, create_object, CfgLocaiDevice
from locai_app.exp_control.locai_context import LocaiContext, ExperimentState
from config.config_definitions import ExperimentConfig

_attrCategory = 'Positioner'
_positionAttr = 'Position'
_speedAttr = "Speed"
_homeAttr = "Home"
_stopAttr = "Stop"
_objectiveRadius = 21.8 / 2
_objectiveRadius = 29.0 / 2  # Olympus

# DEVICE_JSON_PATH = os.path.join(os.path.dirname(__file__), r'config\locai_device_config.json')
DEVICE_JSON_PATH = r"C:\Users\matia_n97ktw5\Documents\LABMaiTE\BMBF-LOCai\locai-impl\config\locai_device_config.json"
# EXPERIMENT_JSON_PATH = os.path.join(os.path.dirname(__file__), r'config\test_locai_experiment_config.json')
EXPERIMENT_JSON_PATH = r"C:\Users\matia_n97ktw5\Documents\LABMaiTE\BMBF-LOCai\locai-impl\config\locai_experiment_config.json"

from hardware_api.core.abcs import Camera
from imswitch.imcontrol.model.interfaces.tiscamera_mock import MockCameraTIS
from imswitch.imcontrol.model.interfaces.gxipycamera import CameraGXIPY
from ...model.managers.detectors.GXPIPYManager import GXPIPYManager


class CameraWrapper(Camera):
    camera_: Union[MockCameraTIS, CameraGXIPY]
    camera: GXPIPYManager

    def capture(self):
        return self.camera.getLatestFrame()

    def stream_switch(self, stream: bool):
        if stream:
            self.camera.startAcquisition()
        else:
            self.camera.stopAcquisition()

    def disconnect(self):
        self.camera.finalize()


class DeckLocaiController(LiveUpdatedController):
    """ Linked to OpentronsDeckWidget.
    Safely moves around the OTDeck and saves positions to be scanned with OpentronsDeckScanner."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__logger = initLogger(self, instanceName="DeckController")

        self.exp_config = self.load_experiment_config_from_json(EXPERIMENT_JSON_PATH)
        self.load_scan_list_from_cfg(self.exp_config)
        dev = self.init_device()
        self.locai_context = LocaiContext(dev, self.experiment_finished)
        self.locai_context.cfg_experiment_path = EXPERIMENT_JSON_PATH

        # Deck and Labwares definitions:
        self.objective_radius = _objectiveRadius
        # TODO: load deck info from EXPerimentConfig and do not provide it to ImSwitch!
        ot_info: OpentronsDeckInfo = self._setupInfo.deck["OpentronsDeck"]
        deck_layout = json.load(open(ot_info["deck_file"], "r"))
        self.deck_definition = DeckConfig(deck_layout, ot_info["labwares"])
        self.translate_units = self._setupInfo.deck["OpentronsDeck"]["translate_units"]

        self.initialize_widget(deck=self.deck_definition.deck, labware=self.deck_definition.labwares)
        self.update_list_in_widget()

        self.selected_well = None
        self.relative_focal_plane = None

        self._widget.sigInfoUpdated.connect(self.get_scan_info)
        self._widget.sigSliderLEDValueChanged.connect(self.valueLEDChanged)

        self.locai_context.device.light.set_enabled(True)

    def valueLEDChanged(self, value):
        self.LEDValue = value
        self._widget.ValueLED.setText(f'{str(value)} %')
        try:
            max_value = self.locai_context.device.light.get_max_intensity()
            self.locai_context.device.light.set_intensity(value=value*max_value/100)
            print(f"Led value: {value*max_value/100} (Max.: {max_value})")
        except Exception as e:
            raise e

    def init_device(self):
        cfg_device = CfgLocaiDevice.parse_file(DEVICE_JSON_PATH)
        locai_device: LocaiDevice = create_object(cfg_device)
        locai_device.initialize()
        # Load the current labwares
        locai_device.load_labwares(self.exp_config.slots)
        imswitch_camera = self._master.detectorsManager._subManagers["WidefieldCamera"]
        camera = CameraWrapper()
        camera.camera = imswitch_camera
        locai_device.attach_camera(camera)  # TODO: get imswitch camera
        # TODO: HOME
        return locai_device

    def load_experiment_config_from_json(self, file=EXPERIMENT_JSON_PATH):
        return ExperimentConfig.parse_file(file)

    def load_scan_list_from_cfg(self, cfg: ExperimentConfig):
        # self.exp_config = ExperimentConfig.parse_file(EXPERIMENT_JSON_PATH)
        self.scan_list: List[ScanPoint] = []
        for slot in cfg.slots:
            slot_number = slot.slot_number
            labware_id = slot.labware_id
            for group_id, group in enumerate(slot.groups):
                for well_id, (well, positions) in enumerate(group.wells.items()):

                    if well_id == 0 and group_id == 0:
                        first_position = slot.groups[0].wells[well][0]  # First position in the well
                    for idx, position in enumerate(positions):
                        relative_focus_z = position.z - first_position.z
                        scanpoint = ScanPoint(
                            point=position,
                            labware=labware_id,
                            slot=slot_number,
                            well=well,
                            position_in_well_index=idx,
                            position_x=-1,
                            position_y=-1,
                            position_z=position.z,
                            offset_from_center_x=position.x,
                            offset_from_center_y=position.y,
                            relative_focus_z=relative_focus_z
                        )

                        self.scan_list.append(scanpoint)

    def save_scan_list_to_json(self):
        path = self._widget.display_save_file_window()
        try:
            with open(path, "w") as file:
                file.write(self.exp_config.json(indent=4))
            self._widget.ScanInfo.setText(f"Saved changes to {os.path.split(path)[1]}")
            self._widget.ScanInfo.setHidden(False)
            self.__logger.debug(f"Saved file to {path}")
            self.__logger.debug(f"Experiment Config: {self.exp_config}")
        except Exception as e:
            self.__logger.debug(f"No file selected. {e}")

    def get_scan_info(self, info_dict):
        # self.locai_context
        print(f"Info dict: {info_dict}")
        return

    def initialize_widget(self, deck, labware):
        self.initialize_positioners(options=(0, 0, 1, 4))
        self._widget.init_well_action((2, 2, 1, 2))
        self._widget.initialize_deck(deck, labware, [(1, 0, 1, 2), (1, 2, 1, 2)])
        self._widget.init_experiment_buttons((4, 2, 1, 2))
        self._widget.init_experiment_info((3, 0, 2, 2))
        self._widget.init_light_source((3, 2, 1, 2))
        self._widget.init_scan_list((6, 0, 2, 4))
        # Connect widget´s buttons
        self.connect_signals()
        self.connect_widget_buttons()

    def update_beacons_index(self):
        count_dict = {}
        for row in self.scan_list:
            slot = row.slot
            well = row.well
            unique_id = row.position_x, row.position_y, row.position_z
            key = (slot, well)
            if key not in count_dict:
                count_dict[key] = set()
            count_dict[key].add(unique_id)
            row.position_in_well_index = len(count_dict[key])

    def update_list_in_widget(self):
        self._widget.update_scan_list(self.scan_list)
        # self._widget.update_scan_list(ExperimentConfig)

    # @APIExport(runOnUIThread=True)
    def go_to_position_in_list(self, row):
        positioner = self.locai_context.device.stage
        well = self.scan_list[row].well
        slot = self.scan_list[row].slot
        point = self.scan_list[row].point
        # abs_pos = self.scan_list[row].get_absolute_position()
        positioner.move_from_well(slot=str(slot), well=well, position=point)
        [self.updatePosition(axis) for axis in positioner.axes]
        self.select_labware(slot=str(slot))
        self.select_well(well=well)
        self.__logger.debug(f"Moving to position in row {row}: slot={str(slot)}, well={well}, offset+focus={point}")

    def delete_position_in_list(self, row):
        deleted_point = self.scan_list.pop(row)
        self.exp_config.remove_pos_by_index(row)

        # TODO: delete point from ExperimentConfig.
        self.__logger.debug(f"Deleting row {row}: {deleted_point}")
        self.update_beacons_index()
        self.update_list_in_widget()
        self._widget.ScanInfo.setText("Unsaved changes.")
        self._widget.ScanInfo.setHidden(False)

    def adjust_position_in_list(self, row):
        positioner = self.locai_context.device.stage
        p = positioner.position()
        slot = positioner.deck_manager.get_slot(p)
        well = positioner.deck_manager.get_closest_well(p)
        x_new, y_new, z_new = p.as_tuple()
        x_old, y_old, z_old = self.scan_list[row].get_absolute_position()
        if (x_old, y_old, z_old) == p.as_tuple():
            self.__logger.debug(f"Adjusting Position: same position selected.")
            return
        if row == 0:
            self.relative_focal_plane = z_new
            self.propagate_relative_focus()
        else:
            if self.relative_focal_plane is None:
                self.relative_focal_plane = self.scan_list[0].position_z
            self.scan_list[row].relative_focus_z = (z_new - self.relative_focal_plane)
        self.__logger.debug(f"Adjusting Position: {(x_old, y_old, z_old)} -> {p.as_tuple()}")
        self.update_position_in_row(row=row, point=p)
        self.update_slot_well_in_row(row=row, slot=slot, well=well)
        self.update_beacons_index()
        self.update_list_in_widget()
        self._widget.ScanInfo.setText("Unsaved changes.")
        self._widget.ScanInfo.setHidden(False)

    def update_position_in_row(self, row: int, point: Point):
        self.scan_list[row].point = point  # TODO: this one modifies the exp_config as intended.
        self.scan_list[row].position_x = point.x
        self.scan_list[row].position_y = point.y
        self.scan_list[row].position_z = point.z

    def update_slot_well_in_row(self, row: int, slot: str, well: str):
        if self.scan_list[row].slot != slot:
            self.scan_list[row].slot = slot
        if self.scan_list[row].well != well:
            self.scan_list[row].well = well

    def propagate_relative_focus(self):
        for i_row, values in enumerate(self.scan_list[1:]):
            self.scan_list[1:][i_row].relative_focus_z = (
                    self.scan_list[1:][i_row].position_z - self.relative_focal_plane)

    def adjust_focus_in_list(self, row):
        positioner = self.locai_context.device.stage
        p = positioner.position()
        _, _, z_new = p.as_tuple()
        z_old = self.scan_list[row].position_z
        if z_old == z_new:
            self.__logger.debug(f"Adjusting focus: same focus selected.")
            return
        if row == 0:
            self.relative_focal_plane = z_new
            self.propagate_relative_focus()
            self.__logger.debug(f"Adjusting focus: changing relative focal plane. {z_old} um->{z_new} um")
        else:
            if self.relative_focal_plane is None:
                self.relative_focal_plane = self.scan_list[0].position_z
            self.scan_list[row].relative_focus_z = (z_new - self.relative_focal_plane)
            self.__logger.debug(f"Adjusting focus: Row {row} - {z_old} um->{z_new} um")
        self.scan_list[row].position_z = z_new
        self.scan_list[row].point.z = p.z  # TODO: this one modifies the exp_config as intended.
        self.update_list_in_widget()
        self._widget.ScanInfo.setText("Unsaved changes.")
        self._widget.ScanInfo.setHidden(False)

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

    def initialize_positioners(self, options=(0, 0, 1, 1)):
        # Has control over positioner
        self.positioner_name = self._master.positionersManager.getAllDeviceNames()[0]
        # self.positioner = self._master.positionersManager[self.positioner_name]
        # self.positioner = self.locai_device.stage

        # Set up positioners
        for pName, pManager in self._master.positionersManager:
            if not pManager.forPositioning:
                continue
            hasSpeed = hasattr(pManager, 'speed')
            hasHome = hasattr(pManager, 'home')
            hasStop = hasattr(pManager, 'stop')
            self._widget.addPositioner(pName, pManager.axes, hasSpeed, hasHome, hasStop, options)
            for axis in pManager.axes:
                self.setSharedAttr(axis, _positionAttr, pManager.position[axis])
                if hasSpeed:
                    self.setSharedAttr(axis, _speedAttr, pManager.speed[axis])
                if hasHome:
                    if axis != "Z":  # Z-axis doesn´t have Home
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
        # self._widget.sigStepAbsoluteClicked.connect(self.moveAbsolute)
        self._widget.sigHomeAxisClicked.connect(self.homeAxis)
        self._widget.sigStopAxisClicked.connect(self.stopAxis)

    def stopAxis(self, positionerName, axis):
        self.__logger.debug(f"Stopping axis {axis}")
        positioner = self.locai_context.device.stage
        if axis == "X":
            positioner.positioner.x_axis.stop()
        if axis == "Y":
            positioner.positioner.y_axis.stop()
        if axis == "Z":
            positioner.positioner.z_axis.stop()
        # self._master.positionersManager[positionerName].forceStop(axis)

    def homeAxis(self, positionerName, axis):
        if axis != "Z":
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
        positioner = self.locai_context.device.stage
        positioner.home()
        # # TODO: fix home in PositionerManager
        # positioner.doHome("X")
        # time.sleep(0.1)
        # positioner.doHome("Y")
        # [self.updatePosition(axis) for axis in positioner.axes]

    @APIExport(runOnUIThread=True)
    def zero(self):
        positioner = self.locai_context.device.stage
        if not len(self.scan_list):
            _, _, self.relative_focal_plane = positioner.position().as_tuple()
        else:
            old_relative_focal_plane = self.scan_list[0].position_z
            _, _, self.relative_focal_plane = positioner.position().as_tuple()
            for i_row, values in enumerate(self.scan_list):
                self.scan_list[i_row].position_z += (self.relative_focal_plane - old_relative_focal_plane)
        self.update_list_in_widget()
        self._widget.scan_list_actions_info.setText("Unsaved changes.")
        self._widget.scan_list_actions_info.setHidden(False)

    @APIExport(runOnUIThread=True)
    def move(self, new_position: Point):
        """ Moves positioner to absolute position. """
        positioner = self.locai_context.device.stage
        # speed = [self._widget.getSpeed(self.positioner_name, axis) for axis in positioner.axes]
        positioner.move_absolute(new_position)
        # positioner.move(new_position, "XYZ", is_absolute=True, is_blocking=False, speed=speed)
        for (ax, p) in zip(positioner.axes, new_position.as_tuple()):
            self._widget.updatePosition(self.positioner_name, ax, p)
            self.setSharedAttr(ax, _positionAttr, p)
        # [self.updatePosition(axis) for axis in positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    def setPos(self, axis, position):
        """ Moves the positioner to the specified position in the specified axis. """
        positioner = self.locai_context.device.stage
        # positioner.setPosition(position, axis)
        self.updatePosition(axis)

    @APIExport(runOnUIThread=True)
    def moveAbsolute(self, axis):
        positioner = self.locai_context.device.stage

        point = self._widget.getAbsPosition(self.positioner_name, axis)
        positioner.move_absolute(Point.model_validate({axis.lower(): point}))
        # positioner.move(self._widget.getAbsPosition(self.positioner_name, axis), axis=axis, is_absolute=True,
        #                 is_blocking=False)
        p = self._master.positionersManager[self.positioner_name]
        # p.setPosition(shift, axis)
        [self.updatePosition(axis) for axis in positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    @APIExport(runOnUIThread=True)
    def stepUp(self, positionerName, axis):
        shift = self._widget.getStepSize(positionerName, axis)
        positioner = self.locai_context.device.stage
        try:
            point = Point()
            point.__setattr__(name=axis.lower(), value=shift)
            positioner.move_relative(point)
            [self.updatePosition(axis) for axis in positioner.axes]
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")

    @APIExport(runOnUIThread=True)
    def stepDown(self, positionerName, axis):
        shift = -self._widget.getStepSize(positionerName, axis)
        positioner = self.locai_context.device.stage
        try:
            point = Point()
            point.__setattr__(name=axis.lower(), value=shift)
            positioner.move_relative(point)
            [self.updatePosition(axis) for axis in positioner.axes]
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")

    def setSpeedGUI(self, axis):
        speed = self._widget.getSpeed(self.positioner_name, axis)
        self.setSpeed(speed=speed, axis=axis)

    def setSpeed(self, axis, speed=(12, 12, 8)):
        positioner = self.locai_context.device.stage
        positioner.setSpeed(speed, axis)
        self._widget.updateSpeed(self.positioner_name, axis, speed)

    def updatePosition(self, axis):
        positioner = self.locai_context.device.stage
        newPos = positioner.position().__getattribute__(axis.lower())
        # newPos = positioner.position[axis]
        self._widget.updatePosition(self.positioner_name, axis, newPos)
        self.setSharedAttr(axis, _positionAttr, newPos)

    def attrChanged(self, key, value):
        if self.settingAttr or len(key) != 4 or key[0] != _attrCategory:
            return
        # positionerName = key[1]
        axis = key[2]
        if key[3] == _positionAttr:
            p = self.locai_context.device.stage.position()
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

    @APIExport(runOnUIThread=True)
    def select_labware(self, slot: str):
        self.__logger.debug(f"Slot {slot}")
        self._widget.select_labware(slot, options=(1, 1, 2, 1))
        self.selected_slot = slot
        self.selected_well = None
        self.connect_wells()

    @APIExport(runOnUIThread=True)
    def move_to_well(self, well: str, slot: str):
        """ Moves positioner to center of selecterd well keeping the current Z-axis position. """
        positioner = self.locai_context.device.stage
        self.__logger.debug(f"Move to {well} ({slot})")
        # speed = [self._widget.getSpeed(self.positioner_name, axis) for axis in positioner.axes]
        positioner.move_from_well(slot=slot, well=well, position=Point())
        [self.updatePosition(axis) for axis in positioner.axes]
        # self._widget.add_current_btn.clicked.connect(self.add_current_position_to_scan)

    def connect_signals(self):
        self._widget.scan_list.sigGoToTableClicked.connect(self.go_to_position_in_list)
        self._widget.scan_list.sigDeleteRowClicked.connect(self.delete_position_in_list)
        self._widget.scan_list.sigAdjustFocusClicked.connect(self.adjust_focus_in_list)
        self._widget.scan_list.sigAdjustPositionClicked.connect(self.adjust_position_in_list)

    def connect_widget_buttons(self):
        self.connect_deck_slots()
        self._widget.ScanStartButton.clicked.connect(self.start_scan)
        self._widget.ScanStopButton.clicked.connect(self.stop_scan)
        self._widget.ScanSaveButton.clicked.connect(self.save_experiment_config)

    @APIExport(runOnUIThread=True)
    def start_scan(self):
        self.locai_context.load_experiment(self.exp_config)
        # Start the experiment in a separate thread
        thread_experiment = threading.Thread(target=self.locai_context.run_experiment)
        thread_experiment.start()
        # TODO: improve check
        self._widget.ScanStartButton.setEnabled(False)
        self._widget.ScanSaveButton.setEnabled(False)
        self._widget.ScanStopButton.setEnabled(True)

    @APIExport(runOnUIThread=True)
    def stop_scan(self):
        # if hasattr(self.locai_context, "shared_context"):
        if self.locai_context.state in [ExperimentState.RUNNING]:
            self.locai_context.stop_experiment()
        else:
            print(f"No running experiment to stop.")

    def experiment_finished(self):
        print("experiment_finished: End End End End End End End End")
        self._widget.ScanStartButton.setEnabled(True)
        self._widget.ScanSaveButton.setEnabled(True)
        self._widget.ScanStopButton.setEnabled(False)

    def save_experiment_config(self):
        self.save_scan_list_to_json()

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

    @APIExport(runOnUIThread=True)
    def select_well(self, well):
        self.__logger.debug(f"Well {well} in slot {self.selected_slot}")
        self.selected_well = well
        self._widget.select_well(well)
        self.connect_go_to()
