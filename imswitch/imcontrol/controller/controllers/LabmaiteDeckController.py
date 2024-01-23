import datetime
import os
import threading

import time
from qtpy import QtCore, QtWidgets, QtGui
from functools import partial
from typing import Union, Dict, Tuple, List, Optional, Callable
import numpy as np

from exp_control.scanning.scan_manager import get_array_from_list
from imswitch.imcommon.model import initLogger, APIExport
from imswitch.imcontrol.view import guitools as guitools
from imswitch.imcontrol.model.interfaces.tiscamera_mock import MockCameraTIS
from imswitch.imcontrol.model.interfaces.gxipycamera import CameraGXIPY
from imswitch.imcontrol.controller.basecontrollers import LiveUpdatedController
from imswitch.imcommon.framework.qt import Thread

_attrCategory = 'Positioner'
_positionAttr = 'Position'
_speedAttr = "Speed"
_homeAttr = "Home"
_stopAttr = "Stop"
_objectiveRadius = 21.8 / 2
_objectiveRadius = 29.0 / 2  # Olympus

# PROJECT FOLDER:
PROJECT_FOLDER = r"C:\Users\matia_n97ktw5\Documents\LABMaiTE\BMBF-LOCai\locai-impl"

# MODE:
os.environ["DEBUG"] = "2"  # 1 for debug/Mocks, 2 for real device
# MODULES:
MODULES = ['scan']
# DEVICE AND EXPERIMENT:
DEVICE: str = "UC2_INVESTIGATOR"  # "BTIG_A" or "UC2_INVESTIGATOR"
if DEVICE == "BTIG_A":
    DEVICE_JSON_PATH = os.sep.join([PROJECT_FOLDER, r"\config\locai_device_config.json"])
    EXPERIMENT_JSON_PATH = os.sep.join([PROJECT_FOLDER, r"\config\btig_small_experiment_config_TEST.json"])
    EXPERIMENT_JSON_PATH_ = os.sep.join(
        [PROJECT_FOLDER, r"\config\updated_locai_experiment_config_TEST_multislot.json"])
elif DEVICE == "UC2_INVESTIGATOR":
    DEVICE_JSON_PATH = os.sep.join([PROJECT_FOLDER, r"\config\uc2_device_config.json"])
    EXPERIMENT_JSON_PATH_ = os.sep.join([PROJECT_FOLDER, r"\config\uc2_stage_experiment_config_TEST.json"])
    EXPERIMENT_JSON_PATH = os.sep.join([PROJECT_FOLDER, r"\config\bcall_experiment_config_TEST.json"])
    EXPERIMENT_JSON_PATH_ = os.sep.join([PROJECT_FOLDER, r"\config\grid_test_repeat.json"])
# APPLICATION SPECIFIC FEATURES
os.environ["APP"] = "BCALL"  # BCALL only for now

from hardware_api.core.abcs import Camera
from imswitch.imcontrol.model.managers.detectors.GXPIPYManager import GXPIPYManager
from locai_app.generics import Point
from config.config_definitions import ExperimentConfig
from locai_app.exp_control.experiment_context import ExperimentState, ExperimentContext
from locai_app.exp_control.scanning.scan_entities import ScanPoint


class CameraWrapper(Camera):
    camera_: Union[MockCameraTIS, CameraGXIPY]
    camera: GXPIPYManager

    def __init__(self, camera: GXPIPYManager):
        super(CameraWrapper, self).__init__()
        self.camera = camera
        self.metadata = {"frame_rate": self.camera.getParameter("frame_rate"),
                         "exposure_time": self.camera.getParameter("exposure") / 1000,
                         "black_level": self.camera.getParameter("blacklevel"),
                         "gain": self.camera.getParameter("gain")}

    def get_metadata(self):
        return {"timestamp": datetime.datetime.now().strftime('%Y%m%d_%H%M%S'), "camera_metadata": self.metadata}

    def capture(self):
        return self.camera.getLatestFrame(), self.get_metadata()

    def stream_switch(self, stream: bool):
        if stream:
            self.camera.startAcquisition()
        else:
            self.camera.stopAcquisition()

    def disconnect(self):
        self.camera.finalize()


class WorkerThread(Thread):
    finished_signal = QtCore.Signal(list)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        # Execute the specified task
        result = self.task_func(*self.args, **self.kwargs)
        self.finished_signal.emit(result)


# class PositionerThread(threading.Thread):
#     def __init__(self, positioner, update_position_callback):
#         super().__init__()
#         self.positioner = positioner
#         self.position = positioner.position()
#         self.update_position_callback = update_position_callback
#
#     def home(self):
#         self.positioner.home()
#         self.position = self.positioner.position()
#         return self.position
#
#     def home_axis(self, axis: str):
#         self.positioner.positioner.home_axis(axis)
#         self.position = self.positioner.position()
#         return self.position
#
#     def move_absolute(self, new_position: Point):
#         self.positioner.move_absolute(new_position)
#         self.position = self.positioner.position()
#         return self.position
#
#     def move_relative(self, shift: Point):
#         self.positioner.move_relative(shift)
#         self.position = self.positioner.position()
#         return self.position
#
#     def move_from_well(self, slot: str, well: str, offset: Point):
#         self.positioner.move_from_well(slot, well, offset)
#         self.update_position_callback(self.positioner)


class LabmaiteDeckController(LiveUpdatedController):
    """ Linked to OpentronsDeckWidget.
    Safely moves around the OTDeck and saves positions to be scanned with OpentronsDeckScanner."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__logger = initLogger(self, instanceName="DeckController")
        start = time.time()
        self.exp_config = self.load_experiment_config_from_json(EXPERIMENT_JSON_PATH)
        dev = self.init_device()
        self.exp_context = ExperimentContext(dev, callback=self.experiment_finished,
                                             callback_info=self.update_scan_info)
        self.exp_context.cfg_experiment_path = EXPERIMENT_JSON_PATH
        self.load_scan_list_from_cfg(self.exp_config)
        print(f"init LabmaiteDeck {time.time() - start:.3f} seconds")
        # Deck and Labwares definitions:
        self.objective_radius = _objectiveRadius
        self.selected_well = None
        self.selected_slot = None
        self.relative_focal_plane = None
        self.initialize_widget()
        self.update_list_in_widget()
        self._widget.sigSliderValueChanged.connect(self.value_light_changed)

    def init_device(self):
        if DEVICE == "UC2_INVESTIGATOR":
            from locai_app.impl.uc2_device import CfgDevice, UC2Device, create_device
            cfg_device = CfgDevice.parse_file(DEVICE_JSON_PATH)
            device: UC2Device = create_device(cfg_device)
        elif DEVICE == "BTIG_A":
            from locai_app.impl.btig_a import create_device, BTIGDevice, CfgBTIGDevice
            cfg_device = CfgBTIGDevice.parse_file(DEVICE_JSON_PATH)
            device: BTIGDevice = create_device(cfg_device)
        else:
            raise ValueError(f"Unrecognized device {DEVICE}")
        device.initialize()
        device.load_labwares(self.exp_config.slots)
        start = time.time()
        imswitch_camera = self._master.detectorsManager._subManagers["WidefieldCamera"]
        camera = CameraWrapper(imswitch_camera)
        device.attach_camera(camera)
        print(f"init camera {time.time() - start:.3f} seconds")
        device.stage.home()
        return device

    def update_scan_info(self, dict_info):
        formated_info = self.format_info(dict_info)
        self._widget.ScanInfo.setText(formated_info)
        self._widget.ScanInfo.setHidden(False)

    def format_info(self, info: dict):
        # TODO: improve, use pydantic model
        exp_time = f"Experiment started at {info['start_time']}" if hasattr(info, "start_time") else ""
        scan_info = f"STATUS: {info['experiment_status']}\t{exp_time}\n" \
                    f"SCAN {info['scan_info'].status.value} started at {info['scan_info'].current_scan_start_date}\n" \
                    f"\tRound: {info['scan_info'].current_scan_number + 1}/{self.exp_config.scan_params.number_scans}\n" \
                    f"\tSlot: {info['scan_info'].current_slot}, Well: {info['scan_info'].current_well}\n" \
                    f"\tPosition: ({info['position'].x:.2f}, {info['position'].y:.2f}, {info['position'].z:.3f})\n\n" \
                    f"\tRemaining: {info['estimated_remaining_time']} \n\tNext in: {info['next_scan_time']}\n\n"
        light_sources_intensity = f"Light sources: {info['light_sources_intensity']}\n"
        # f" Index: {info['scan_info'].current_pos_index}" \
        if info['fluidics_info'] and 'fluidics' in self.exp_context.modules:
            fluidics_info = f"FLUIDICS: Current pressure = {info['fluidics_info'].pressure}\n" \
                            f"\tCurrent flow rate = {info['fluidics_info'].flow_rate}" \
                            f"\tValue = {info['fluidics_info'].status.value}\n" \
                            f"\tAction {info['fluidics_info'].current_action_number}:\n"
            action = info['fluidics_info'].current_action
        else:
            fluidics_info = '\n\n\n'
            action = None
        if action is not None:
            action_info = f"\tMux Channel: {action.mux_group_channel}({action.ob1_channel}) (Slot: {action.slot_number})\n" \
                          f"\tFlow rate: {action.flow_rate} ul/min, Duration: {action.duration_seconds} seconds\n"
            reservoir_info = f"\tReservoir: {action.reservoir.reagent_id}@{action.reservoir.mux_channel}({action.reservoir.ob1_channel})" if action.reservoir is not None else "\n\n"
        else:
            action_info = "\n\n"
            reservoir_info = "\n\n"
        event_info = f"EVENT: {info['event']}\n"

        return scan_info + light_sources_intensity + fluidics_info + action_info + reservoir_info + event_info

    def value_light_changed(self, light_source, value):
        try:
            [light.set_intensity(value=value * light.config.value_range_max / 100) for light in
             self.exp_context.device.light_sources if
             light.config.readable_name == light_source]
            time.sleep(0.1)
        except Exception as e:
            raise e

    def load_experiment_config_from_json(self, file=EXPERIMENT_JSON_PATH):
        return ExperimentConfig.parse_file(file)

    def closeEvent(self):
        self.stop_scan()

    def load_scan_list_from_cfg(self, cfg: ExperimentConfig):
        deck_manager = self.exp_context.device.stage.deck_manager
        self.scan_list: List[ScanPoint] = []
        for slot in cfg.slots:
            slot_number = slot.slot_number
            labware_id = slot.labware_id
            for group_id, group in enumerate(slot.groups):
                # First delete empty wells
                wells_to_delete = [k for k, w in group.wells.items() if not w]
                [group.wells.pop(w) for w in wells_to_delete]
                for well_id, (well, positions) in enumerate(group.wells.items()):
                    if well_id == 0 and group_id == 0:
                        first_position = slot.groups[0].wells[well][0]  # First position in the well
                    for idx, position in enumerate(positions):
                        if position:
                            well_position = deck_manager.get_well_position(str(slot_number), well)
                            relative_focus_z = position.z - first_position.z
                            scanpoint = ScanPoint(
                                point=position,
                                labware=labware_id,
                                slot=slot_number,
                                well=well,
                                position_in_well_index=idx,
                                position_x=well_position.x,
                                position_y=well_position.y,
                                position_z=position.z,
                                offset_from_center_x=position.x,
                                offset_from_center_y=position.y,
                                relative_focus_z=relative_focus_z
                            )
                            self.scan_list.append(scanpoint)
                        else:
                            self.__logger.warning(f"Ignoring empty position in well {well} ")

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
        print(f"Info dict: {info_dict}")
        return

    def initialize_widget(self):
        self.initialize_positioners(options=(0, 0, 1, 5))
        self._widget.init_experiment_buttons((4, 4, 1, 1))
        self._widget.init_experiment_info((4, 0, 2, 3))
        self._widget.init_home_button((1, 4, 1, 1))
        # self._widget.init_light_source((3, 3, 1, 2))
        self._widget.init_well_action((1, 3, 2, 1))
        self._widget.initialize_deck(self.exp_context.device.stage.deck_manager, [(1, 0, 3, 3), (2, 4, 1, 1)])
        self._widget.init_light_sources(self.exp_context.device.light_sources, (4, 3, 2, 1))
        self._widget.init_scan_list((7, 0, 2, 5))
        if "BCALL" in os.environ["APP"]:
            self._widget.init_z_scan((3, 3, 1, 2))
            self._widget.z_scan_preview_button.clicked.connect(self.z_scan_preview)
        else:
            pass
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

    def go_to_position_in_list(self, row):
        positioner = self.exp_context.device.stage
        well = self.scan_list[row].well
        slot = self.scan_list[row].slot
        focus_plane = self.scan_list[row].position_z
        offset = Point(x=self.scan_list[row].offset_from_center_x, y=self.scan_list[row].offset_from_center_y,
                       z=focus_plane)
        # TODO: use single thread
        threading.Thread(target=positioner.move_from_well, args=(str(slot), well, offset), daemon=True).start()
        self.update_position(positioner)
        self.select_labware(slot=str(slot))
        self.select_well(well=well)
        self.__logger.debug(
            f"Moving to position in row {row}: slot={str(slot)}, well={well}, offset={offset}, focus={focus_plane}")

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
        positioner = self.exp_context.device.stage
        p = positioner.position()
        closest_well = positioner.deck_manager.get_closest_well(p)
        x_old, y_old, _ = positioner.deck_manager.get_well_position(str(self.scan_list[row].slot),
                                                                    self.scan_list[row].well).as_tuple()
        _, _, z_old = self.scan_list[row].get_absolute_position()
        if closest_well != self.scan_list[row].well:
            self.__logger.warning(
                f"Adjusting Position: can only adjust position within the same well ({self.scan_list[row].well}) -> new position is within well {closest_well}. ")
            return
        if (x_old, y_old, z_old) == p.as_tuple():
            self.__logger.warning(f"Adjusting Position: same position selected.")
            return
        self.exp_config.update_pos_by_index(row)
        self.update_row_from_point(row=row, point=p)
        self.__logger.debug(f"Adjusting Position: {(x_old, y_old, z_old)} -> {p.as_tuple()}")
        self.update_beacons_index()
        self.update_list_in_widget()
        self._widget.ScanInfo.setText("Unsaved changes.")
        self._widget.ScanInfo.setHidden(False)

    def update_row_from_point(self, row: int, point: Point):
        positioner = self.exp_context.device.stage
        if row == 0:
            self.relative_focal_plane = point.z
            self.propagate_relative_focus()
        else:
            if self.relative_focal_plane is None:
                self.relative_focal_plane = self.scan_list[0].position_z
            self.scan_list[row].relative_focus_z = (point.z - self.relative_focal_plane)
        self.scan_list[row].position_x = point.x
        self.scan_list[row].position_y = point.y
        self.scan_list[row].position_z = point.z
        slot_new = positioner.deck_manager.get_slot(point)
        well_new = positioner.deck_manager.get_closest_well(point)
        center_of_closest_well_new = positioner.deck_manager.get_well_position(slot_new, well_new)
        offset_new = point - center_of_closest_well_new
        if self.scan_list[row].slot != slot_new:
            self.scan_list[row].slot = slot_new
        if self.scan_list[row].well != well_new:
            self.scan_list[row].well = well_new
        self.scan_list[row].offset_from_center_x = offset_new.x
        self.scan_list[row].offset_from_center_y = offset_new.y
        self.scan_list[row].point.x = offset_new.x  # TODO: this one modifies the exp_config as intended.
        self.scan_list[row].point.y = offset_new.y  # TODO: this one modifies the exp_config as intended.
        self.scan_list[row].point.z = point.z  # TODO: this one modifies the exp_config as intended.

    def propagate_relative_focus(self):
        for i_row, values in enumerate(self.scan_list[1:]):
            self.scan_list[1:][i_row].relative_focus_z = (
                    self.scan_list[1:][i_row].position_z - self.relative_focal_plane)

    def adjust_focus_in_list(self, row):
        positioner = self.exp_context.device.stage
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

    def adjust_all_focus(self):
        positioner = self.exp_context.device.stage
        p = positioner.position()
        _, _, z_new = p.as_tuple()
        for row in range(len(self.scan_list)):
            if row == 0:
                self.relative_focal_plane = z_new
                self.propagate_relative_focus()
            else:
                if self.relative_focal_plane is None:
                    self.relative_focal_plane = self.scan_list[0].position_z
                self.scan_list[row].relative_focus_z = (z_new - self.relative_focal_plane)
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
        self._widget.sigStepAbsoluteClicked.connect(self.moveAbsolute)
        self._widget.sigHomeAxisClicked.connect(self.home_axis)
        self._widget.sigStopAxisClicked.connect(self.stop_axis)

    def stop_axis(self, positionerName, axis):
        self.__logger.debug(f"Stopping axis {axis}")
        positioner = self.exp_context.device.stage
        if axis == "X":
            positioner.positioner.x_axis.stop()
        if axis == "Y":
            positioner.positioner.y_axis.stop()
        if axis == "Z":
            positioner.positioner.z_axis.stop()

    def home_axis(self, positionerName, axis):
        self.__logger.debug(f"Homing axis {axis}")
        self._master.positionersManager[positionerName].doHome(axis)
        positioner = self.exp_context.device.stage
        # TODO: use single thread
        threading.Thread(target=positioner.positioner.home_axis, args=(axis,), daemon=True).start()
        self.update_position(positioner)

    def getPos(self):
        return self._master.positionersManager.execOnAll(lambda p: p.position)

    def getSpeed(self):
        return self._master.positionersManager.execOnAll(lambda p: p.speed)

    def home(self) -> None:
        positioner = self.exp_context.device.stage
        # TODO: use single thread
        threading.Thread(target=positioner.home, daemon=True).start()
        self.update_position(positioner)

    def zero(self):
        positioner = self.exp_context.device.stage
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

    def move(self, new_position: Point):
        """ Moves positioner to absolute position. """
        positioner = self.exp_context.device.stage
        # TODO: use single thread
        threading.Thread(target=positioner.move_absolute, args=(new_position,), daemon=True).start()
        self.update_position(positioner)

    def setPos(self, axis, position):
        """ Moves the positioner to the specified position in the specified axis. """
        # positioner.setPosition(position, axis)
        self._update_position(axis)

    def moveAbsolute(self, axis):
        positioner = self.exp_context.device.stage
        p_positioner = positioner.position()
        p_axis = self._widget.getAbsPosition(self.positioner_name, axis)
        setattr(p_positioner, axis.lower(), p_axis)
        # TODO: use single thread
        threading.Thread(target=positioner.move_absolute, args=(p_positioner,), daemon=True).start()
        self.update_position(positioner)

    def stepUp(self, positionerName, axis):
        shift = self._widget.getStepSize(positionerName, axis)
        positioner = self.exp_context.device.stage
        try:
            point = Point(**{axis.lower(): shift})
            # TODO: use single thread
            threading.Thread(target=positioner.move_relative, args=(point,), daemon=True).start()
            self.update_position(positioner)
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.ScanInfo.setText("Avoiding objective collision.")

    def stepDown(self, positionerName, axis):
        shift = -self._widget.getStepSize(positionerName, axis)
        positioner = self.exp_context.device.stage
        try:
            point = Point(**{axis.lower(): shift})
            # TODO: use single thread
            threading.Thread(target=positioner.move_relative, args=(point,), daemon=True).start()
            self.update_position(positioner)
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.ScanInfo.setText("Avoiding objective collision.")

    def setSpeedGUI(self, axis):
        speed = self._widget.getSpeed(self.positioner_name, axis)
        self.setSpeed(speed=speed, axis=axis)

    def setSpeed(self, axis, speed=(12, 12, 8)):
        positioner = self.exp_context.device.stage
        # positioner.setSpeed(speed, axis)
        # TODO: Fix speed
        self._widget.updateSpeed(self.positioner_name, axis, speed)

    def update_position(self, positioner):
        [self._update_position(axis) for axis in positioner.axes]

    def _update_position(self, axis):
        positioner = self.exp_context.device.stage

        def update_pos():
            pos = positioner.position()
            newPos = pos.__getattribute__(axis.lower())
            self._widget.updatePosition(self.positioner_name, axis, newPos)
            self.setSharedAttr(axis, _positionAttr, newPos)

        t = threading.Thread(target=update_pos, daemon=True)
        t.start()

    def attrChanged(self, key, value):
        # TODO: check if needed.
        if self.settingAttr or len(key) != 4 or key[0] != _attrCategory:
            return
        # positionerName = key[1]
        axis = key[2]
        if key[3] == _positionAttr:
            # self.setPositioner(axis, value)
            pass

    def setPositioner(self, axis: str, position: float) -> None:
        """ Moves the specified positioner axis to the specified position. """
        self.setPos(axis, position)

    def setSharedAttr(self, axis, attr, value):
        self.settingAttr = True
        try:
            self._commChannel.sharedAttrs[(_attrCategory, self.positioner_name, axis, attr)] = value
        finally:
            self.settingAttr = False

    def select_labware(self, slot: str):
        self.__logger.debug(f"Slot {slot}")
        self._widget.select_labware(slot)
        self.selected_slot = slot
        self.selected_well = None
        self.connect_wells()

    def move_to_well(self, well: str, slot: str):
        """ Moves positioner to center of selecterd well keeping the current Z-axis position. """
        positioner = self.exp_context.device.stage
        self.__logger.debug(f"Move to {well} ({slot})")
        # TODO: use single thread
        position = Point(z=positioner.position().z)
        threading.Thread(target=positioner.move_from_well, args=(slot, well, position,), daemon=True).start()
        self.update_position(positioner)

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
        self._widget.home_button.clicked.connect(self.home)
        self._widget.adjust_all_focus_button.clicked.connect(self.adjust_all_focus)

    def set_preview_images(self, images):
        # images = well_previewer.preview_well(imager=imager, device=self.exp_context.device)
        imgs = get_array_from_list(images)
        name = f"{self.selected_well}"
        # for im in images:
        self._widget.set_preview(imgs, name=name, pixelsize=(1, 0.45, 0.45))  # TODO: fix hardcode

    def z_scan_preview(self):
        from exp_control.imaging.imagers import get_preview_imager
        from exp_control.scanning.scan_manager import WellPreviewer

        z_start = float(self._widget.well_base_widget.text())
        z_end = float(self._widget.well_top_widget.text())
        z_step = float(self._widget.z_scan_step_widget.text())

        exp = ExperimentConfig.parse_file(self.exp_context.cfg_experiment_path)
        imager = get_preview_imager(exp.scan_params.illumination_params)

        well_previewer = WellPreviewer(z_start=z_start, z_end=z_end, z_step=z_step,
                                       callback_finish=self.set_preview_images)
        args = (imager, self.exp_context.device)
        kwargs = {}
        thread_preview = WorkerThread(well_previewer.preview_well, *args, **kwargs)
        thread_preview.finished_signal.connect(self.set_preview_images)
        thread_preview.start()
        thread_preview.wait()
        del thread_preview

    def start_scan(self):
        self.exp_context.load_experiment(self.exp_config, modules=MODULES)
        # Start the experiment in a separate thread
        if self.exp_context.state != ExperimentState.CREATED:
            self.exp_context.state = ExperimentState.CREATED
        if self.exp_context.thread_experiment is not None:
            del self.exp_context.thread_experiment
        thread_experiment = threading.Thread(target=self.exp_context.run_experiment)
        thread_experiment.start()
        # TODO: improve check
        self._widget.ScanStartButton.setEnabled(False)
        self._widget.ScanSaveButton.setEnabled(False)
        self._widget.ScanStopButton.setEnabled(True)
        self._widget._positioner_widget.hide()
        self._widget._wells_group_box.hide()
        self._widget._deck_group_box.hide()
        self._widget.LEDWidget.hide()
        self._widget.home_button_widget.hide()
        self._widget.well_action_widget.hide()
        self._widget.scan_list.context_menu_enabled = False

    def stop_scan(self):
        # if hasattr(self.exp_context, "shared_context"):
        if self.exp_context.state in [ExperimentState.RUNNING]:
            self.exp_context.stop_experiment()
        else:
            print(f"No running experiment to stop.")

    def experiment_finished(self):
        self._widget.ScanStartButton.setEnabled(True)
        self._widget.ScanSaveButton.setEnabled(True)
        self._widget.ScanStopButton.setEnabled(False)
        self._widget._positioner_widget.show()
        self._widget._wells_group_box.show()
        self._widget._deck_group_box.show()
        self._widget.LEDWidget.show()
        self._widget.home_button_widget.show()
        self._widget.well_action_widget.show()
        self._widget.scan_list.context_menu_enabled = True

    def save_experiment_config(self):
        self.save_scan_list_to_json()

    def connect_deck_slots(self):
        """Connect Deck Slots (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        self._widget.slots_combobox.currentTextChanged.connect(self.select_labware)
        # for slot, btn in self._widget.deck_slots.items():
        #     # Connect signals
        #     if isinstance(btn, guitools.BetterPushButton):
        #         btn.clicked.connect(partial(self.select_labware, slot))
        # Select default slot -> done in init
        positioner = self.exp_context.device.stage
        self.select_labware(list(positioner.deck_manager.labwares.keys())[0])  # TODO: improve...

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
            if isinstance(btn, guitools.BetterPushButton):
                btn.clicked.connect(partial(self.select_well, well))

    def select_well(self, well):
        self.__logger.debug(f"Well {well} in slot {self.selected_slot}")
        self.selected_well = well
        self._widget.select_well(well)
        self.connect_go_to()
