import datetime
import os
import threading

import time
from copy import deepcopy

from qtpy import QtCore, QtWidgets, QtGui
from functools import partial
from typing import Union, Dict, Tuple, List, Optional, Callable
import numpy as np

from locai_app.exp_control.common.shared_context import ScanState
from locai_app.exp_control.scanning.scan_manager import get_array_from_list
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
# PROJECT_FOLDER = r"/home/worker5/Documents/repositories/locai-impl"
# MODE:
os.environ["DEBUG"] = "1"  # 1 for debug/Mocks, 2 for real device
# MODULES:
MODULES = ['scan']
# DEVICE AND EXPERIMENT:
DEVICE: str = "UC2_INVESTIGATOR"  # "BTIG_A" or "UC2_INVESTIGATOR"
if DEVICE == "BTIG_A":
    DEVICE_JSON_PATH = os.sep.join([PROJECT_FOLDER, 'config', 'locai_device_config.json'])
    EXPERIMENT_JSON_PATH = os.sep.join([PROJECT_FOLDER, 'config', 'btig_small_experiment_config_TEST.json'])
    EXPERIMENT_JSON_PATH_ = os.sep.join(
        [PROJECT_FOLDER, 'config', 'updated_locai_experiment_config_TEST_multislot.json'])
elif DEVICE == "UC2_INVESTIGATOR":
    # DEVICE_JSON_PATH = os.sep.join([PROJECT_FOLDER, r"\config\uc2_device_config.json"])
    DEVICE_JSON_PATH = os.sep.join([PROJECT_FOLDER, 'config', 'uc2_device_config.json'])
# APPLICATION SPECIFIC FEATURES
os.environ["APP"] = "BCALL"  # BCALL only for now
if os.environ["APP"] == "BCALL":
    exp_name = r"bcall_K562_test.json"
    EXPERIMENT_JSON_PATH = os.sep.join([PROJECT_FOLDER, "config", exp_name])

from hardware_api.core.abcs import Camera
from imswitch.imcontrol.model.managers.detectors.GXPIPYManager import GXPIPYManager
from config.config_definitions import ExperimentConfig
from locai_app.exp_control.experiment_context import ExperimentState, ExperimentContext, ExperimentLiveInfo
from locai_app.exp_control.scanning.scan_entities import ScanPoint
from locai_app.exp_control.imaging.imagers import get_preview_imager
from locai_app.exp_control.scanning.scan_manager import WellPreviewer
from locai_app.generics import Point


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


class LabmaiteDeckController(LiveUpdatedController):
    """ Linked to OpentronsDeckWidget.
    Safely moves around the OTDeck and saves positions to be scanned with OpentronsDeckScanner."""
    sigZScanStart = QtCore.Signal()

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
        self.preview_z_pos = None
        self.preview_images = None
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
        device.stage.home() if DEVICE == "UC2_INVESTIGATOR" else ...
        return device

    def update_scan_info(self, dict_info):
        formated_info = self.format_info(dict_info)
        self._widget.sigScanInfoTextChanged.emit(formated_info)

    def format_info_scan(self, info):
        if info.scan_info is not None:
            current_scan = info.scan_info.current_scan_number + 1
            date_format = "%Y-%m-%d %H:%M:%S"
            text = f"SCAN {current_scan}/{self.exp_config.scan_params.number_scans} - {info.scan_info.status.value}\n"
            if info.scan_info.status != ScanState.INITIALIZING:
                start_time = info.scan_info.scan_start_time if info.scan_info.scan_start_time is not None else "-"
                text = text + f"  Start:\t\t{start_time}\n" \
                              f"  Slot:\t\t{info.scan_info.current_slot}\n" \
                              f"  Well:\t\t{info.scan_info.current_well}\n" \
                              f"  Position:\t({info.pos_info.x:.2f}, {info.pos_info.y:.2f}, {info.pos_info.z:.3f})\n"
            else:
                text = text + f"  Start:\t\t---\n" \
                              f"  Slot:\t\t---\n" \
                              f"  Well:\t\t---\n" \
                              f"  Position:\t---\n"
            if info.scan_info.status == ScanState.WAITING:
                text = text + f"  Next:\t\t{'NotImplementedYet'}\n"
            else:
                text = text + f"  Next:\t\t---\n"
        else:
            text = f"SCAN - {ScanState.INITIALIZING}\n"
        return text

    def format_fluid_info(self, info):
        if info.fluid_info is None:
            return ''
        fluid_text = f"FLUIDICS - {info.fluid_info.status.value}\n"
        act = info.fluid_info.current_action
        if act is not None:
            action_text = f"  Mux Channel:\t{act.mux_group_channel}({act.ob1_channel}) (Slot: {act.slot_number})\n" \
                          f"  Flow Rate:\t{act.flow_rate} μl/min\n" \
                          f"  Duration:\t{act.duration_seconds} seconds\n" \
                          f"  Reservoir:\t{act.reservoir.reagent_id}@{act.reservoir.mux_channel}({act.reservoir.ob1_channel})\n"
        else:
            action_text = f"  Mux Channel:\t---\n" \
                          f"  Flow Rate:\t0 μl/min\n" \
                          f"  Duration:\t---\n" \
                          f"  Reservoir:\t---\n"
        if info.fluid_info.mux_in:
            action_text = action_text + f"  Current Mux in:\t{info.fluid_info.mux_in}\n"
        else:
            action_text = action_text + f"  Current Mux in:\t---\n"
        if info.fluid_info.mux_out:
            action_text = action_text + f"  Current Mux out:\t{info.fluid_info.mux_out}\n"
        else:
            action_text = action_text + f"  Current Mux out:\t---\n"
        return fluid_text + action_text

    def format_info(self, info: ExperimentLiveInfo):
        date_format = "%Y-%m-%d %H:%M:%S"
        general_info = f"STATUS: {info.experiment_status.value}\n" \
                       f"  Started at:\t{info.start_time.strftime(date_format)}\n" \
                       f"  Estimated left:\t{info.estimated_remaining_time}\n"
        scan_text = self.format_info_scan(info)
        fluid_info = self.format_fluid_info(info)
        # # f" Index: {info.scan_info.current_pos_index}" \
        # fluidics_info = f"FLUIDICS: {info.fluid_info.status.value}\n" \
        #                 f"\tAction {info.fluid_info.current_action_number}:\n"
        # action = info.fluid_info.current_action
        # if action is not None:
        #     action_info = f"\tMux Channel: {action.mux_group_channel}({action.ob1_channel}) (Slot: {action.slot_number})\n" \
        #                   f"\tFlow rate: {action.flow_rate} ul/min, Duration: {action.duration_seconds} seconds\n"
        #     reservoir_info = f"\tReservoir: {action.reservoir.reagent_id}@{action.reservoir.mux_channel}({action.reservoir.ob1_channel})\n"
        # else:
        #     action_info = ""
        #     reservoir_info = ""
        # # event_info = f"EVENT: {info.event}\n"
        # return scan_info + fluidics_info + action_info + reservoir_info
        return general_info + scan_text + fluid_info

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
                                position_x=well_position.x + position.x,
                                position_y=well_position.y + position.y,
                                position_z=position.z,
                                offset_from_center_x=position.x,
                                offset_from_center_y=position.y,
                                relative_focus_z=relative_focus_z,
                                checked=False
                            )
                            self.scan_list.append(scanpoint)
                        else:
                            self.__logger.warning(f"Ignoring empty position in well {well} ")

    def save_scan_list_to_json(self):
        path = self._widget.display_save_file_window()
        try:
            with open(path, "w") as file:
                file.write(self.exp_config.json(indent=4))
            self._widget.sigScanInfoTextChanged.emit(f"Saved changes to {os.path.split(path)[1]}")
            self.__logger.debug(f"Saved file to {path}")
            self.__logger.debug(f"Experiment Config: {self.exp_config}")
        except Exception as e:
            self.__logger.debug(f"No file selected. {e}")

    def open_experiment_config(self):
        path = self._widget.display_open_file_window()
        try:
            self.exp_config = self.load_experiment_config_from_json(path)
            dev = self.init_device()
            self.exp_context = ExperimentContext(dev, callback=self.experiment_finished,
                                                 callback_info=self.update_scan_info)
            self.exp_context.cfg_experiment_path = EXPERIMENT_JSON_PATH
            self.load_scan_list_from_cfg(self.exp_config)
            # Deck and Labwares definitions:
            self.objective_radius = _objectiveRadius
            self.selected_well = None
            self.selected_slot = None
            self.relative_focal_plane = None
            self.preview_z_pos = None
            self.preview_images = None
            self.initialize_widget()
            self.update_list_in_widget()
            self._widget.sigSliderValueChanged.connect(self.value_light_changed)
            self._widget.sigScanInfoTextChanged.emit(f"Opened {os.path.split(path)[1]}")
            self.__logger.debug(f"Experiment Config: {self.exp_config}")
        except Exception as e:
            self.__logger.debug(f"No file selected. {e}")

    def get_scan_info(self, info_dict):
        # self.exp_context
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
            self._widget.init_z_scan_widget((3, 3, 1, 2))
            self._widget.init_experiment_info((4, 0, 2, 2))
            self._widget.init_zstack_config_widget(default_values_in_mm=self.exp_config.scan_params.z_stack_params,
                                                   options=(4, 2, 2, 1))
            self._widget.z_scan_preview_button.clicked.connect(self.z_scan_preview)
            # self._widget.z_stack_checkbox_widget.clicked.connect(self.z_scan_preview) # TODO: change
            # TODO: connect change in enabled Z-stack widget
            self._widget.scan_list.sigRowChecked.connect(self.checked_row)
            try:
                self._widget.scan_list.setColumnHidden(self._widget.scan_list.columns.index("Slot"), True)
                self._widget.scan_list.setColumnHidden(self._widget.scan_list.columns.index("Labware"), True)
                self._widget.scan_list.setColumnHidden(self._widget.scan_list.columns.index("Done"), False)
            except ValueError as e:
                self.__logger.warning(f"Error when initializing LabmaiteDeckWidget's Scan List. Exception: {e} ")
        else:
            pass
        # Connect widget´s buttons
        self.connect_signals()
        self.connect_widget_buttons()

    def checked_row(self, state, row):
        self.scan_list[row].checked = state

    def update_beacons_index(self, row=None):
        if row is None:
            count_dict = {}
            for row in self.scan_list:
                slot = row.slot
                well = row.well
                unique_id = row.position_x, row.position_y, row.position_z
                key = (slot, well)
                if key not in count_dict:
                    count_dict[key] = set()
                count_dict[key].add(unique_id)
                row.position_in_well_index = len(count_dict[key]) - 1
        else:
            key = (self.scan_list[row].slot, self.scan_list[row].well)
            while key == (self.scan_list[row + 1].slot, self.scan_list[row + 1].well):
                self.scan_list[row + 1].position_in_well_index += 1
                row += 1

    def update_list_in_widget(self):
        self._widget.update_scan_list(self.scan_list)

    def go_to_position_in_list(self, row):
        positioner = self.exp_context.device.stage
        well = self.scan_list[row].well
        slot = self.scan_list[row].slot
        focus_plane = self.scan_list[row].position_z
        offset = Point(x=self.scan_list[row].offset_from_center_x, y=self.scan_list[row].offset_from_center_y,
                       z=focus_plane)

        def move_from_well_update():
            positioner.move_from_well(str(slot), well, offset)
            self.update_position(positioner)
            self.select_labware(slot=str(slot))
            self.select_well(well=well)

        threading.Thread(target=move_from_well_update, daemon=True).start()
        self.__logger.debug(
            f"Moving to position in row {row}: slot={str(slot)}, well={well}, offset={offset}, focus={focus_plane}")

    def delete_position_in_list(self, row):
        deleted_point = self.scan_list.pop(row)
        self.exp_config.remove_pos_by_index(row)
        self.__logger.debug(f"Deleting row {row}: {deleted_point}")
        self.update_beacons_index()
        self.update_list_in_widget()
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

    def duplicate_position_in_list(self, row):
        selected_scan_point = deepcopy(self.scan_list[row])
        self.exp_config.duplicate_pos_by_index(row)
        self.scan_list.insert(row, selected_scan_point)
        self.__logger.debug(f"Duplicating Position in row {row}: {self.scan_list[row]}")
        self.update_beacons_index(row)
        self.update_list_in_widget()
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

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
        self.update_row_from_point(row=row, point=p)
        self.exp_config.update_pos_by_index(row, p)
        self.__logger.debug(f"Adjusting Position: {(x_old, y_old, z_old)} -> {p.as_tuple()}")
        self.update_beacons_index(row)
        self.update_list_in_widget()
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

    def update_row_from_point(self, row: int, point: Point):
        positioner = self.exp_context.device.stage

        if row == 0:
            self.relative_focal_plane = point.z
            self.propagate_relative_focus()
        else:
            if self.relative_focal_plane is None:
                self.relative_focal_plane = self.scan_list[0].position_z
            self.scan_list[row].relative_focus_z = (point.z - self.relative_focal_plane)
        self.scan_list[row].point = point
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
        self.scan_list[row].point.x = offset_new.x
        self.scan_list[row].point.y = offset_new.y
        self.scan_list[row].point.z = point.z

    def propagate_relative_focus(self):
        for i_row, values in enumerate(self.scan_list[1:]):
            self.scan_list[1:][i_row].relative_focus_z = (
                    self.scan_list[1:][i_row].position_z - self.relative_focal_plane)

    def adjust_focus_from_preview(self, row):
        try:
            z_new = float(self._widget.z_scan_zpos_widget.text())
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
            self.scan_list[row].point.z = z_new
            self.update_list_in_widget()
            self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")
        except Exception as e:
            self.__logger.warning(f"Invalid value to set focus. Please use '.' as comma. {e}")

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
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

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
            self.scan_list[row].point.z = p.z
        self.update_list_in_widget()
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

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

        try:
            def home_axis_update():
                positioner.positioner.home_axis(axis)
                self.update_position(positioner)
                self.select_labware(slot=self.selected_slot)
                self.select_well(well=None) if axis != "Z" else self.select_well(well=self.selected_well)

            threading.Thread(target=home_axis_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

    def getPos(self):
        return self._master.positionersManager.execOnAll(lambda p: p.position)

    def getSpeed(self):
        return self._master.positionersManager.execOnAll(lambda p: p.speed)

    def home(self) -> None:
        positioner = self.exp_context.device.stage
        try:
            def home_update():
                positioner.home()
                self.update_position(positioner)
                self.select_labware(slot=self.selected_slot)
                self.select_well(well=None)

            threading.Thread(target=home_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

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
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

    def move(self, new_position: Point):
        """ Moves positioner to absolute position. """
        positioner = self.exp_context.device.stage
        try:
            def move_absolute_update():
                positioner.move_absolute(new_position)
                pos = self.update_position(positioner)
                slot = positioner.deck_manager.get_slot(pos)
                well = positioner.deck_manager.get_closest_well(pos)
                self.select_labware(slot=str(slot))
                self.select_well(well=well)

            threading.Thread(target=move_absolute_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

    def setPos(self, axis, position):
        """ Moves the positioner to the specified position in the specified axis. """
        # positioner.setPosition(position, axis)
        # self._update_position(axis)
        pass

    def moveAbsolute(self, axis):
        positioner = self.exp_context.device.stage
        try:
            p_positioner = positioner.position()
            p_axis = self._widget.getAbsPosition(self.positioner_name, axis)
            setattr(p_positioner, axis.lower(), p_axis)

            def move_absolute_update():
                positioner.move_absolute(p_positioner)
                pos = self.update_position(positioner)
                slot = positioner.deck_manager.get_slot(pos)
                well = positioner.deck_manager.get_closest_well(pos)
                self.select_labware(slot=str(slot))
                self.select_well(well=well)

            threading.Thread(target=move_absolute_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

    def stepUp(self, positionerName, axis):
        shift = self._widget.getStepSize(positionerName, axis)
        positioner = self.exp_context.device.stage
        try:
            point = Point(**{axis.lower(): shift})

            def step_up_update():
                positioner.move_relative(point)
                pos = self.update_position(positioner)
                slot = positioner.deck_manager.get_slot(pos)
                well = positioner.deck_manager.get_closest_well(pos)
                self.select_labware(slot=str(slot))
                self.select_well(well=well)

            threading.Thread(target=step_up_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

    def stepDown(self, positionerName, axis):
        shift = -self._widget.getStepSize(positionerName, axis)
        positioner = self.exp_context.device.stage
        try:
            point = Point(**{axis.lower(): shift})

            def step_down_update():
                positioner.move_relative(point)
                pos = self.update_position(positioner)
                slot = positioner.deck_manager.get_slot(pos)
                well = positioner.deck_manager.get_closest_well(pos)
                self.select_labware(slot=str(slot))
                self.select_well(well=well)

            threading.Thread(target=step_down_update, daemon=True).start()
        except Exception as e:
            self.__logger.info(f"Avoiding objective collision. {e}")
            self._widget.sigScanInfoTextChanged.emit("Avoiding objective collision.")

    def setSpeedGUI(self, axis):
        speed = self._widget.getSpeed(self.positioner_name, axis)
        self.setSpeed(speed=speed, axis=axis)

    def setSpeed(self, axis, speed=(12, 12, 8)):
        positioner = self.exp_context.device.stage
        # positioner.setSpeed(speed, axis)
        # TODO: Fix speed
        self._widget.updateSpeed(self.positioner_name, axis, speed)

    def update_position(self, positioner):
        pos = positioner.position()
        self._widget.sigPositionUpdate.emit(self.positioner_name, pos.x, pos.y, pos.z)
        return pos

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

    def select_labware(self, slot: str = None):
        self.__logger.debug(f"Slot {slot}")
        self.selected_slot = slot
        self.selected_well = None
        self._widget.sigLabwareSelect.emit(self.selected_slot)
        self._widget.sigWellSelect.emit(self.selected_well)

    def move_to_well(self, well: str, slot: str):
        """ Moves positioner to center of selecterd well keeping the current Z-axis position. """
        positioner = self.exp_context.device.stage
        self.__logger.debug(f"Move to {well} ({slot})")
        position = Point(z=positioner.position().z)

        def move_from_well_update():
            positioner.move_from_well(str(slot), well, position)
            self.update_position(positioner)
            self.select_labware(slot=str(slot))
            self.select_well(well=well)

        threading.Thread(target=move_from_well_update, daemon=True).start()

    def connect_signals(self):
        self.sigZScanStart.connect(self.set_images)
        self._widget.sigTableSelect.connect(self.selected_row)
        self._widget.scan_list.sigGoToTableClicked.connect(self.go_to_position_in_list)
        self._widget.scan_list.sigDeleteRowClicked.connect(self.delete_position_in_list)
        self._widget.scan_list.sigAdjustFocusClicked.connect(self.adjust_focus_in_list)
        self._widget.scan_list.sigAdjustPositionClicked.connect(self.adjust_position_in_list)
        self._widget.scan_list.sigDuplicatePositionClicked.connect(self.duplicate_position_in_list)

    def connect_widget_buttons(self):
        self.connect_deck_slots()
        self._widget.ScanStartButton.clicked.connect(self.start_scan)
        self._widget.ScanStopButton.clicked.connect(self.stop_scan)
        self._widget.ScanSaveButton.clicked.connect(self.save_experiment_config)
        self._widget.ScanOpenButton.clicked.connect(self.open_experiment_config)
        self._widget.adjust_offset_button.clicked.connect(self.adjust_all_offsets)
        self._widget.home_button.clicked.connect(self.home)
        self._widget.adjust_all_focus_button.clicked.connect(self.adjust_all_focus)
        self.connect_wells()
        self.connect_go_to()

    def set_images(self):
        if len(self._widget.viewer.dims.events.current_step.callbacks) > 3:  # TODO: a bit hacky...
            self._widget.viewer.dims.events.current_step.disconnect(
                self._widget.viewer.dims.events.current_step.callbacks[0])
        # TODO: hardcoded pixelsize
        name = f"Preview {self.selected_well}"
        self._widget.set_preview(self.preview_images, name=name, pixelsize=(1, 0.45, 0.45))  # TODO: fix hardcode
        self._widget.viewer.dims.events.current_step.connect(
            partial(self._widget.update_slider, self.preview_z_pos, name))
        self._widget.sigZScanValue.connect(self.set_z_slice_value)

    def set_z_slice_value(self, value):
        try:
            value = float(value)
            self._widget.z_scan_zpos_widget.setText(f"{value:.3f}")
        except Exception as e:
            self.__logger.warning(f"Exception set_z_slice_value: {e}")

    def set_preview_images(self, images, z_pos):
        self.preview_images = get_array_from_list(images)
        self.preview_z_pos = z_pos
        self.sigZScanStart.emit()

    def selected_row(self, row):
        self._widget.z_scan_zpos_label.setText(f"Adjust focus of row {row} to ")
        if isinstance(self._widget.z_scan_adjust_focus_widget, guitools.BetterPushButton):
            try:
                self._widget.z_scan_adjust_focus_widget.clicked.disconnect()
            except Exception:
                pass
            self._widget.z_scan_adjust_focus_widget.clicked.connect(partial(self.adjust_focus_from_preview, row))
            print(f"Selected row: {row}. \n {self.scan_list[row]}")

    def z_scan_preview(self):
        z_start = float(self._widget.well_base_widget.text())
        z_end = float(self._widget.well_top_widget.text())
        z_step = float(self._widget.z_scan_step_widget.text())

        exp = ExperimentConfig.parse_file(self.exp_context.cfg_experiment_path)
        imager = get_preview_imager(exp.scan_params.illumination_params)

        well_previewer = WellPreviewer(z_start=z_start, z_end=z_end, z_step=z_step,
                                       callback_finish=self.set_preview_images)
        well_previewer.preview_well(imager, self.exp_context.device)

    def confirm_start_run(self):
        return self._widget.confirm_start_run()

    def start_scan(self):
        if self._widget.ScanInfo.text() == "Unsaved changes.":
            if not self.confirm_start_run():
                return
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
        self._widget.ScanSaveButton.setEnabled(False)
        self._widget.adjust_all_focus_button.setEnabled(False)
        self.hide_widgets()

    def hide_widgets(self):
        self._widget._positioner_widget.hide()
        self._widget._wells_group_box.hide()
        self._widget._deck_group_box.hide()
        self._widget.LEDWidget.hide()
        self._widget.home_button_widget.hide()
        self._widget.well_action_widget.hide()
        self._widget.scan_list.context_menu_enabled = False
        if os.environ["APP"] == "BCALL":
            self._widget._z_scan_box.hide()
            self._widget.z_stack_config_widget.hide()

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
        self._widget.ScanSaveButton.setEnabled(True)
        self._widget.adjust_all_focus_button.setEnabled(True)
        self.show_widgets()

    def show_widgets(self):
        self._widget._positioner_widget.show()
        self._widget._wells_group_box.show()
        self._widget._deck_group_box.show()
        self._widget.LEDWidget.show()
        self._widget.home_button_widget.show()
        self._widget.well_action_widget.show()
        self._widget.scan_list.context_menu_enabled = True
        if os.environ["APP"] == "BCALL":
            self._widget._z_scan_box.show()
            self._widget.z_stack_config_widget.show()

    def save_experiment_config(self):
        if os.environ["APP"] == "BCALL":
            self.save_zstack_params()
        self.save_scan_list_to_json()

    def adjust_all_offsets(self):
        x, y = self._widget.get_offset_all()
        self._adjust_all_offsets(x, y)
        self.update_list_in_widget()
        self.__logger.debug(f"Adjusting Offsets: X_offset = {x} mm, Y_offset = {y} mm")
        self._widget.sigScanInfoTextChanged.emit("Unsaved changes.")

    def _adjust_all_offsets(self, x: float = 0, y: float = 0):
        for row in range(len(self.scan_list)):
            self.scan_list[row].offset_from_center_x += x
            self.scan_list[row].offset_from_center_y += y
            self.scan_list[row].point.x += x
            self.scan_list[row].point.y += y
            self.scan_list[row].position_x += x
            self.scan_list[row].position_y += y


    def save_zstack_params(self):
        z_height, z_sep, z_slices, _ = self._widget.get_z_stack_values_in_um()
        self.exp_config.scan_params.z_stack_params.z_sep = z_sep / 1000
        self.exp_config.scan_params.z_stack_params.z_slices = z_slices
        self.exp_config.scan_params.z_stack_params.z_height = z_height / 1000

    def connect_deck_slots(self):
        """Connect Deck Slots (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        self._widget.slots_combobox.currentTextChanged.connect(self.select_labware)
        positioner = self.exp_context.device.stage
        self.select_labware(list(positioner.deck_manager.labwares.keys())[0])  # TODO: improve...

    def connect_go_to(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""

        def on_go_to_clicked():
            self.move_to_well(self.selected_well, self.selected_slot)

        self._widget.goto_btn.clicked.connect(on_go_to_clicked)

    def connect_wells(self):
        """Connect Wells (Buttons) to the Sample Pop-Up Method"""
        # Connect signals for all buttons
        for well, btn in self._widget.wells.items():
            # Connect signals
            if isinstance(btn, guitools.BetterPushButton):
                btn.clicked.connect(partial(self.select_well, well))

    def select_well(self, well: str = None):
        self.__logger.debug(f"Well {well} in slot {self.selected_slot}")
        self.selected_well = well
        self._widget.sigWellSelect.emit(well)
