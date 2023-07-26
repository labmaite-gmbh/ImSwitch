import dataclasses
import json
import os
import threading
import time
from datetime import datetime, timedelta
from queue import Queue
from typing import Optional, NamedTuple, Tuple, List
from functools import partial

import numpy as np
import pydantic
import tifffile as tif
from imswitch.imcommon.framework import Signal
from imswitch.imcommon.model import dirtools
from imswitch.imcommon.model import initLogger, APIExport

from locai.deck.deck_config import DeckConfig
from locai.utils.utils import strfdelta
from ..basecontrollers import LiveUpdatedController
from ...model.SetupInfo import OpentronsDeckInfo
from opentrons.types import Point
from locai.utils.scan_list import ScanPoint, open_scan_list, save_scan_list

_attrCategory = 'Positioner'
_positionAttr = 'Position'
_speedAttr = "Speed"
_objectiveRadius = 21.8 / 2
_objectiveRadius = 29.0 / 2  # Olympus


class ImageI(pydantic.BaseModel):
    slot: str
    well: str
    offset: Tuple[float, float]
    z_focus: float
    pos_abs: Point


@dataclasses.dataclass
class ImageInfo:
    slot: Optional[int]
    labware: Optional[str]
    well: str
    position_in_well_index: int
    offset: Tuple[float, float]
    z_focus: float
    pos_abs: Point
    illu_mode: str
    timestamp: str

    def get_filename(self):
        # TODO: fix hardcode in self.position_idx
        # <Experiment name>_<Slot>_<Well>_<Image in Well Index+Z>_<Channel>_<Channel Index>_<00dd00hh00mm>
        if self.slot is None:
            return f"{self.well}_{self.position_in_well_index}_z{round(self.z_focus)}_{self.illu_mode}_{self.timestamp}"
        else:
            return f"{int(self.slot)}_{self.well}_{int(self.position_in_well_index)}_z{round(self.z_focus)}_{self.illu_mode}_{self.timestamp}"


class DeckScanController(LiveUpdatedController):
    """ Linked to OpentronsDeckScanWidget."""
    sigImageReceived = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__logger = initLogger(self, instanceName="DeckScanController")
        self.objective_radius = _objectiveRadius
        ot_info: OpentronsDeckInfo = self._setupInfo.deck["OpentronsDeck"]
        # Init desk and labware
        deck_layout = json.load(open(ot_info["deck_file"], "r"))
        self.deck_definition = DeckConfig(deck_layout, ot_info["labwares"])
        self.translate_units = self._setupInfo.deck["OpentronsDeck"]["translate_units"]

        self.scan_list: List[ScanPoint] = []
        # Has control over positioners/detector/camera/LED
        self.initialize_positioners()
        self.initialize_detectors()
        self.initialize_leds()
        # Time to settle image (stage vibrations)
        self.tUnshake = 0.2
        # From MCT:
        # mct parameters
        self.nRounds = 0
        self.timePeriod = 60  # seconds
        self.zStackEnabled = False
        self.zStackMax = 0
        self.zStackStep = 0
        self.pixelsize = (10, 1, 1)  # zxy
        # connect XY Stagescanning live update  https://github.com/napari/napari/issues/1110
        # autofocus related
        self.isAutofocusRunning = False
        self.isScanrunning = False

        self.connect_signals()
        self.connect_widget_buttons()
        self.ScanThread: Optional[threading.Thread] = None

    def connect_widget_buttons(self):
        self._widget.ScanStartButton.clicked.connect(self.startScan)
        self._widget.ScanStopButton.clicked.connect(self.stopScan)
        self._widget.ScanShowLastButton.clicked.connect(self.showLast)
        self._widget.ScanShowLastButton.setEnabled(False)

    def connect_signals(self):
        self._widget.scan_list.sigGoToTableClicked.connect(self.go_to_position_in_list)
        self._commChannel.sigInitialFocalPlane.connect(self.update_z_focus)
        self._commChannel.sigAutoFocusRunning.connect(self.setAutoFocusIsRunning)
        self._commChannel.sigOpenInScannerClicked.connect(self.open_scan_list_from_file)
        self.sigImageReceived.connect(self.displayImage)

    def update_list_in_widget(self):
        self._widget.update_scan_list(self.scan_list)

    def open_scan_list_from_file(self, path=False):
        if path is False:
            path = self._widget.display_open_file_window()
        self.scan_list = []
        try:
            self.scan_list = open_scan_list(path)
            self.update_list_in_widget()
            self._widget.scan_list_actions_info.setText(f"Opened file: {os.path.split(path)[1]}")
            self._widget.scan_list_actions_info.setHidden(False)
        except Exception as e:
            self.__logger.debug(f"No file selected. {e}")

    def save_scan_list_to_file(self):
        path = self._widget.display_save_file_window()
        try:
            save_scan_list(self.scan_list, path)
            self._widget.scan_list_actions_info.setText(f"Saved changes to {os.path.split(path)[1]}")
            self._widget.scan_list_actions_info.setHidden(False)
        except Exception as e:
            self.__logger.debug(f"No file selected. {e}")

    def delete_position_in_list(self, row):
        deleted_point = self.scan_list.pop(row)
        self.__logger.debug(f"Deleting row {row}: {deleted_point}")
        self.update_list_in_widget()
        self._widget.scan_list_actions_info.setText("Unsaved changes.")
        self._widget.scan_list_actions_info.setHidden(False)

    @APIExport(runOnUIThread=True)
    def go_to_position_in_list(self, row):
        abs_pos = self.scan_list[row].get_absolute_position()
        self.move(new_position=Point(*abs_pos))
        self.__logger.debug(f"Moving to position in row {row}: {abs_pos}")

    # Scan Logic
    def setAutoFocusIsRunning(self, isRunning):
        # this is set by the AutofocusController once the AF is finished/initiated
        self.isAutofocusRunning = isRunning

    def update_z_focus(self, value: float):
        self.z_focus = value
        self._widget.update_z_autofocus(value)

    def displayImage(self):
        # a bit weird, but we cannot update outside the main thread
        name = "Last Frame"
        self._widget.setImage(self.detector.getLatestFrame(), colormap="gray", name=name, pixelsize=(1, 1),
                              translation=(0, 0))

    def displayStack(self, im):
        """ Displays the image in the view. """
        self._widget.setImage(im)

    def cleanStack(self, input):
        try:
            import NanoImagingPack as nip
            mBackground = nip.gaussf(np.mean(input, 0), 10)
            moutput = input / mBackground
            mFluctuations = np.mean(moutput, (1, 2))
            moutput /= np.expand_dims(np.expand_dims(mFluctuations, -1), -1)
            return np.uint8(moutput)
        except:
            return np.uint8(input)

    def showLast(self):
        isCleanStack = True
        try:
            if isCleanStack:
                LastStackLEDArrayLast = self.cleanStack(self.LastStackLEDArrayLast)
            else:
                LastStackLEDArrayLast = self.LastStackLEDArrayLast
            self._widget.setImage(LastStackLEDArrayLast, colormap="gray", name="Brightfield", pixelsize=self.pixelsize)
        except  Exception as e:
            self._logger.error(e)

    def get_scan_list_queue_(self):
        queue = Queue(maxsize=self._widget.scan_list_items)
        for row in range(self._widget.scan_list.rowCount()):
            rowdata = []
            for column in range(self._widget.scan_list.columnCount()):
                item = self._widget.scan_list.item(row, column)
                if item is not None:
                    rowdata.append(
                        item.text())
                else:
                    rowdata.append('')
            queue.put(rowdata)
        return queue

    def startScan(self):
        # initilaze setup
        # this is not a thread!
        self._widget.ScanStartButton.setEnabled(False)
        # start the timelapse
        # get parameters from GUI
        self.zStackDepth, self.zStackStep, self.zStackEnabled = self._widget.getZStackValues()
        # positions_list = self._widget.get_all_positions()
        self.timePeriod, self.nDuration = self._widget.getTimelapseValues()
        valid_start = True
        if len(self.scan_list) < 1:
            self.__logger.debug("Scan list empty: please load a valid .csv file before starting the scan.")
            self._widget.show_info("Scan list empty: please load a valid .csv file before starting the scan.")
            valid_start = False
        if not self.LEDValue:
            self.__logger.debug("LED intensity needs to be set before starting scan.")
            self._widget.show_info("LED intensity needs to be set before starting scan.")
            valid_start = False
        if self.zStackEnabled and self.zStackDepth <= 0:
            self.__logger.debug("Z-Stack enabled: sample depth must be positive.")
            self._widget.show_info("Z-Stack enabled: sample depth must be positive.")
            valid_start = False
        if not self.timePeriod:
            self.__logger.debug("Scan Period needs to be set before starting scan.")
            self._widget.show_info("Scan Period needs to be set before starting scan.")
            valid_start = False
        if not self.isScanrunning and valid_start:
            self.nRounds = 0
            self._widget.show_info("Starting timelapse...")
            self.switchOffIllumination()

            self.experiment_name = self._widget.getFilename()
            self.ScanDate = datetime.now().strftime("%Y%m%d_%H%M%S")
            # store old values for later
            if len(self.leds) > 0:
                self.LEDValueOld = self.leds[0].getValue()
            # reserve space for the stack
            self._widget.ScanShowLastButton.setEnabled(False)
            # TODO: freeze scan_list -> edit shouldn´t be available while running.
            # start the timelapse - otherwise we have to wait for the first run after timePeriod to take place..
            self.takeTimelapse(self.timePeriod, self.scan_list)
        else:
            self.isScanrunning = False
            self._widget.ScanStartButton.setEnabled(True)

    def takeTimelapse(self, tperiod, positions_list):
        # this is called periodically by the timer
        if self.isScanrunning:
            self.stopScan()
            # this should decouple the hardware-related actions from the GUI
        self.isScanrunning = True
        self.ScanThread = threading.Thread(target=self.takeTimelapseThread, args=(tperiod, positions_list,),
                                           daemon=True)
        self.__logger.debug("Starting Thread: takeTimelapse().")
        self.ScanThread.start()

    def takeTimelapseThread(self, tperiod=1, positions_list=[]):
        # this wil run i nthe background
        self.timeLast = 0
        self.timeStart = datetime.now()
        self._widget.setNImages(self.nRounds)
        # run as long as the Scan is active
        while self.isScanrunning:
            # stop measurement once done
            if self.nDuration <= self.nRounds:
                self.isScanrunning = False
                self._logger.debug("Done with timelapse.")
                self._widget.show_info("Done with timelapse.")
                self._widget.ScanStartButton.setEnabled(True)
                break
            # initialize a run
            if time.time() - self.timeLast >= tperiod:
                # TODO: include estimation of one run (Autofocus * Z-Stack * Positions * Speed)
                # run an event
                self.timeLast = time.time()  # makes sure that the period is measured from launch to launch
                self._widget.ScanInfoStartTime.setText(
                    f"Started scan at {self.timeStart.strftime('%H:%M (%d.%m.%Y)')}.")
                self._widget.update_widget_text(self._widget.ScanInfoRoundStartTime,
                                f"Round {self.nRounds+1} strated at {datetime.fromtimestamp(self.timeLast).strftime('%H:%M (%d.%m.%Y)')}")

                # reserve and free space for displayed stacks
                self.LastStackLED = []
                try:
                    # want to do autofocus? -> No!
                    # if False:
                    #     autofocusParams = self._widget.getAutofocusValues() or None
                    #     if self._widget.isAutofocus() and np.mod(self.nRounds, int(autofocusParams['valuePeriod'])) == 0:
                    #         self._widget.setNImages("Autofocusing...")
                    #         if self.nRounds == 0:
                    #             self.z_focus = float(autofocusParams["valueInitial"])
                    #         else:
                    #             autofocusParams["valueInitial"] = self.z_focus
                    #         self.doAutofocus(autofocusParams)

                    if self.LEDValue > 0:
                        timestamp_ = strfdelta(datetime.now() - self.timeStart,
                                               "{days}dd{hours}hh{minutes}mm")
                        self.z_focus = float(self._widget.autofocusInitial.text())
                        illu_mode = "Brightfield"
                        self._logger.debug("Take images in " + illu_mode + ": " + str(self.LEDValue) + " A")
                        self._widget.show_info("Timelapse progress: ")
                        for pos_id, row_info, frame in self.takeImageIllu(illuMode=illu_mode,
                                                                          intensity=self.LEDValue,
                                                                          timestamp=timestamp_):
                            self.update_time_to_next_round(tperiod)
                            if not self.isScanrunning:
                                break
                    self.nRounds += 1
                    self._widget.update_widget_text(self._widget.ScanInfoCurrentWell, "-")
                    self._widget.setNImages(self.nRounds)
                    self.LastStackLEDArrayLast = np.array(self.LastStackLED)
                    self._widget.ScanShowLastButton.setEnabled(True)
                except Exception as e:
                    self._logger.error(f"Thread closes with Error: {e}")
                    self.positioner.move(value=0, axis="Z", is_blocking=True)
                    raise e
                    # close the controller ina nice way
            else:
                self.update_time_to_next_round(tperiod, True)
            self.positioner.move(value=0, axis="Z", is_blocking=True)
            # pause to not overwhelm the CPU
        time.sleep(0.1)
        self.stopScan()

    def display_current_position(self, scan_position: ScanPoint):
        self._widget.update_widget_text(self._widget.ScanInfoCurrentWell,
                                        f"Scanning: Slot {int(scan_position.slot)}, Well {scan_position.well}, Index {int(scan_position.position_in_well_index)}")

    def update_time_to_next_round(self, tperiod, sleep=False):
        delta = timedelta(seconds=tperiod) + datetime.fromtimestamp(self.timeLast) - datetime.now()
        time_to_next = strfdelta(delta, "{hours}:{minutes}:{seconds}")
        self.__logger.info(f"Time to next: {time_to_next}")
        self._widget.update_widget_text(self._widget.ScanInfoTimeToNextRound, f"Next round in: {time_to_next}")
        if sleep:
            if delta.seconds < 60:
                time.sleep(1)
            elif delta.seconds < 600:
                time.sleep(60)
            elif delta.seconds < 3600:
                time.sleep(300)
            else:
                time.sleep(600)

    def switchOnIllumination(self, intensity):
        self.__logger.info(f"Turning on Leds: {intensity} A")
        if self.leds:
            self.leds[0].setValue(intensity)
            self.leds[0].setEnabled(True)
        elif self.led_matrixs:
            self.led_matrixs[0].setAll(state=(1, 1, 1))
            # time.sleep(0.1)
            # for LEDid in [12, 13, 14]:  # TODO: these LEDs generate artifacts
            #     self.led_matrixs[0].setLEDSingle(indexled=int(LEDid), state=0)
            #     time.sleep(0.1)
        time.sleep(self.tUnshake * 3)  # unshake + Light

    def switchOffIllumination(self):
        # switch off all illu sources
        self.__logger.info(f"Turning off Leds")
        if len(self.leds) > 0:
            self.leds[0].setEnabled(False)
            self.leds[0].setValue(0)
            # self.illu.setAll((0,0,0))
        elif self.led_matrixs:
            self.led_matrixs[0].setAll(state=(0, 0, 0))
        time.sleep(self.tUnshake * 3)  # unshake + Light

    # TODO: move to scan_list
    def get_first_row(self):
        slot = self._widget.scan_list.item(0, 0).text()
        well = self._widget.scan_list.item(0, 1).text()
        first_position_offset = self._widget.scan_list.item(0, 2).text()
        # z_focus = float(self._widget.scan_list.item(0, 3).text())
        abs_pos = self._widget.scan_list.item(0, 4).text()
        first_position_offset = tuple(map(float, first_position_offset.strip('()').split(',')))
        abs_pos = tuple(map(float, abs_pos.strip('()').split(',')))
        z_focus = abs_pos[2] + float(self._widget.scan_list.item(0, 3).text())
        return slot, well, first_position_offset, z_focus, abs_pos

    def doAutofocus(self, params):
        self._logger.info("Autofocusing at first position...")
        self._widget.show_info("Autofocusing...")
        slot, well, first_position_offset, first_z_focus, first_pos = self.get_first_row()
        self.positioner.move(value=first_pos, axis="XYZ", is_absolute=True, is_blocking=True)
        self._commChannel.sigAutoFocus.emit(float(params["valueRange"]), float(params["valueSteps"]),
                                            float(params["valueInitial"]))
        self.isAutofocusRunning = True
        while self.isAutofocusRunning:
            time.sleep(0.1)
            if not self.isAutofocusRunning:
                self._logger.info("Autofocusing done.")
                _, _, z_focus = self.positioner.get_position()  # Once done, update focal point
                self.z_focus = z_focus
                return
            # # For Mock AutoFocus I need to break somehow:
            # for i in range(10000):
            #     pass
            # return

    def parse_scan_list_row(self, queue_item):
        scan_item_dict = {}
        for c, col_key, item in enumerate(self._widget.scan_list.column_mapping.items()):
            if isinstance(item, tuple):
                for c_, item_ in enumerate(item):
                    scan_item_dict[item_] = queue_item[c][c_]
            scan_item_dict[item] = queue_item[c]
        return ScanPoint(**scan_item_dict)

    # def get_current_scan_row(self):
    #     queue_item = self.scan_queue.get()
    #     if queue_item is None:
    #         self.__logger.debug(f"Queue is empty upon scanning")
    #         raise ValueError("Queue is empty upon scanning.")
    #     elif None not in queue_item:
    #         self.current_scanning_row = queue_item
    #         self.current_scanning_row[2] = tuple(map(float, queue_item[2].strip('()').split(',')))
    #         self.current_scanning_row[3] = float(queue_item[3])
    #         self.current_scanning_row[4] = Point(*tuple(map(float, queue_item[4].strip('()').split(','))))
    #         return self.current_scanning_row
    #     else:
    #         raise ValueError("Get rid of None values in the list before scanning.")

    def take_single_image_at_position(self, current_position: Point, intensity):
        self.__logger.info(f"Moving to {current_position}.")
        self.positioner.move(value=current_position, axis="XYZ", is_absolute=True, is_blocking=True)
        time.sleep(self.tUnshake)

        self.switchOnIllumination(intensity)

        self.__logger.info(f"Taking image.")
        last_frame = self.detector.getLatestFrame()
        return last_frame

    def take_z_stack_at_position(self, current_position: Point, intensity):
        self.positioner.move(value=current_position, axis="XYZ", is_absolute=True, is_blocking=True)
        time.sleep(self.tUnshake * 3)
        # for zn, iZ in enumerate(np.arange(self.zStackMin, self.zStackMax, self.zStackStep)):
        # Array of displacements from center point (z_focus) -/+ z_depth/2
        self.switchOnIllumination(
            intensity)  # Lights stay on during Z-stack. Ideally it shouldn't, but we don't care so much about phototoxicity with brightfield
        for zn, iZ in enumerate(np.linspace(-self.zStackDepth / 2 + current_position.z,
                                            self.zStackDepth / 2 + current_position.z, int(self.zStackStep))):
            self.__logger.info(f"Z-stack : {iZ}")
            # move to each position
            self.positioner.move(value=iZ, axis="Z", is_absolute=True, is_blocking=True)  # , is_absolute=False
            time.sleep(self.tUnshake)  # unshake + Light
            # self.switchOnIllumination(intensity)
            last_frame = self.detector.getLatestFrame()

            yield iZ, last_frame

    # TODO: merge or clean img saving and file path getting
    def get_save_file_path(self, date, filename, extension):
        # <Experiment name>_<Slot>_<Well>_<Image in Well Index+Z>_<Channel>_<Channel Index>_<00dd00hh00mm>
        # mFilename = f"{self.experiment_name}_{filename}_{self.nRounds}.{extension}"
        mFilename = f"{self.experiment_name}_{filename}.{extension}"
        dirPath = os.path.join(dirtools.UserFileDirs.Root, 'recordings', date)
        newPath = os.path.join(dirPath, mFilename)
        if not os.path.exists(dirPath):
            os.makedirs(dirPath)
        return newPath

    def save_image(self, image, info: ImageInfo):
        img_filename = info.get_filename()
        # <Experiment name>_<Slot>_<Well>_<Image in Well Index+Z>_<Channel>_<Channel Index>_<00dd00hh00mm>
        filePath = self.get_save_file_path(date=self.ScanDate, filename=img_filename, extension='tif')
        self._logger.debug(filePath)
        tif.imwrite(filePath, image)

    def takeImageIllu(self, illuMode, intensity, timestamp: str = "", positions_list=[]):
        # TODO: include exit/stop logic inside this loop: if I want to stop after 1 well, it need to complete the whole run before deleting the thread.
        image_index = 0
        self._widget.gridLayer = None
        for pos_i, pos_row in enumerate(self.scan_list):
            self.__logger.info(f"Scanning position {pos_i}/{len(self.scan_list)}: {pos_row}")
            # Get position to scan
            current_pos = Point(*pos_row.get_absolute_position())
            z_focus = pos_row.relative_focus_z
            current_pos = current_pos + Point(0, 0, self.z_focus + z_focus - current_pos.z)
            # Z-position calculated with z_focus column and self.z_focus
            img_info = ImageInfo(slot=pos_row.slot, well=pos_row.well, labware=pos_row.labware,
                                 offset=pos_row.get_offset(), z_focus=z_focus, pos_abs=current_pos,
                                 illu_mode=illuMode,
                                 position_in_well_index=pos_row.position_in_well_index,
                                 timestamp=timestamp)

            self.display_current_position(pos_row)

            if self.zStackEnabled:
                for z_index, (z_pos, frame) in enumerate(
                        self.take_z_stack_at_position(current_pos, intensity)):  # Will yield image and iZ
                    img_info.z_focus = z_index
                    self.save_image(frame, img_info)
                    if img_info.illu_mode == "Brightfield":  # store frames for displaying
                        self.LastStackLED.append(frame.copy())
                    self.sigImageReceived.emit()  # => displays image
            else:
                frame = self.take_single_image_at_position(current_pos, intensity)
                self.save_image(frame, img_info)
                self.LastStackLED = (frame.copy())
                self.sigImageReceived.emit()  # => displays image
                time.sleep(self.tUnshake * 2)  # Time to see image

            self.switchOffIllumination()
            image_index += 1

            yield pos_i, pos_row, frame

    def stopScan(self):
        # # delete any existing timer
        # try:
        #     del self.timer
        # except:
        #     pass
        # delete any existing thread
        try:
            # make sure there is no exisiting thread
            # del self.ScanThread
            self._widget.show_info("Stopping timelapse...")
            self.isScanrunning = False
            if self.ScanThread is not None:
                self.ScanThread.join(timeout=10)  # wait 10 seconds for the thread to exit
                self.ScanThread = None
            print("Deleted Scan Thread")
        except Exception as e:
            print(f"Error deleting existing Thread: {e}")
            pass
        self._widget.show_info("Done wit timelapse...")

        self.positioner.move(value=0, axis="Z", is_blocking=True)
        # store old values for later
        for axis in self.positioner.axes:
            self.positioner.forceStop(axis)
            time.sleep(self.tUnshake)
        self.positioner.doHome("X")
        time.sleep(self.tUnshake)
        self.positioner.doHome("Y")
        time.sleep(self.tUnshake)

        if len(self.leds) > 0:
            self.leds[0].setValue(self.LEDValueOld)
        self.switchOffIllumination()

        self._widget.ScanStartButton.setEnabled(True)

    # Detectors Logic
    def initialize_detectors(self):
        # select detectors
        self.detector_names = self._master.detectorsManager.getAllDeviceNames()
        self.detector = self._master.detectorsManager[self.detector_names[0]]
        self.detector.startAcquisition()

    # LED Logic
    def initialize_leds(self):
        self.led_names = self._master.LEDsManager.getAllDeviceNames()
        self.ledMatrix_names = self._master.LEDMatrixsManager.getAllDeviceNames()

        self.leds = []
        self.led_matrixs = []
        for led_name in self.led_names:
            self.leds.append(self._master.LEDsManager[led_name])
        for led_matrix_name in self.ledMatrix_names:
            self.led_matrixs.append(self._master.LEDMatrixsManager[led_matrix_name])
        self.LEDValueOld = 0
        self.LEDValue = 0
        self._widget.sigSliderLEDValueChanged.connect(self.valueLEDChanged)
        if len(self.leds) >= 1:
            self._widget.sliderLED.setMaximum(self.leds[0].valueRangeMax)
        elif len(self.led_matrixs) >= 1:
            #        self._widget.sliderLED.setMaximum(self.led_matrixs[0].valueRangeMax)
            self._widget.sliderLED.setMaximum(100)  # TODO: Implement in LEDMatrix
        if len(self.leds) >= 1:
            self._widget.autofocusLED1Checkbox.setText(self.led_names[0])
            self._widget.autofocusLED1Checkbox.setCheckState(False)
        elif len(self.led_matrixs) >= 1:
            self._widget.autofocusLED1Checkbox.setText(self.ledMatrix_names[0])
            self._widget.autofocusLED1Checkbox.setCheckState(False)

    def valueLEDChanged(self, value):
        self.LEDValue = value
        self._widget.ValueLED.setText(f'{str(value)} %')
        try:
            if len(self.leds) and not self.leds[0].enabled:
                self.leds[0].setEnabled(1)
        except Exception as e:
            raise e
        if len(self.leds):
            try:
                self.leds[0].setValue(self.LEDValue)
            except Exception as e:
                self.leds[0].setIntensity(self.LEDValue)

    # Positioner Logic
    def initialize_positioners(self):
        # Has control over positioner
        self.positioner_name = self._master.positionersManager.getAllDeviceNames()[0]
        self.positioner = self._master.positionersManager[self.positioner_name]
        # Set up positioners
        for pName, pManager in self._master.positionersManager:
            if not pManager.forPositioning:
                continue
            hasSpeed = hasattr(pManager, 'speed')
            # self._widget.addPositioner(pName, pManager.axes, hasSpeed, pManager.position, pManager.speed)
            for axis in pManager.axes:
                self.setSharedAttr(pName, axis, _positionAttr, pManager.position[axis])
                if hasSpeed:
                    self.setSharedAttr(pName, axis, _speedAttr, pManager.speed[axis])
        # Connect CommunicationChannel signals
        self._commChannel.sharedAttrs.sigAttributeSet.connect(self.attrChanged)

        time.sleep(1)
        self.positioner.move(value=0, axis="Z")
        time.sleep(0.1)
        self.positioner.doHome("X")
        time.sleep(0.1)
        self.positioner.doHome("Y")
        time.sleep(0.1)

    def setPositioner(self, positionerName: str, axis: str, position: float) -> None:
        """ Moves the specified positioner axis to the specified position. """
        self.setPos(positionerName, axis, position)

    def setPos(self, positionerName, axis, position):
        """ Moves the positioner to the specified position in the specified axis. """
        self._master.positionersManager[positionerName].setPosition(position, axis)
        self.updatePosition(positionerName, axis)

    def updatePosition(self, positionerName, axis):
        newPos = self._master.positionersManager[positionerName].position[axis]
        self.setSharedAttr(positionerName, axis, _positionAttr, newPos)

    def attrChanged(self, key, value):
        if self.settingAttr or len(key) != 4 or key[0] != _attrCategory:
            return
        positionerName = key[1]
        axis = key[2]
        if key[3] == _positionAttr:
            self.setPositioner(positionerName, axis, value)

    def setSharedAttr(self, positionerName, axis, attr, value):
        self.settingAttr = True
        try:
            self._commChannel.sharedAttrs[(_attrCategory, positionerName, axis, attr)] = value
        finally:
            self.settingAttr = False

    def move(self, new_position):
        """ Moves positioner to absolute position. """
        self.positioner.move(new_position, "XYZ", is_absolute=True, is_blocking=False)
        # [self.updatePosition(self.positioner_name, axis) for axis in self.positioner.axes] # TODO: check if this breaks the focus.


class mTimer(object):
    def __init__(self, waittime, mFunc) -> None:
        self.waittime = waittime
        self.starttime = time.time()
        self.running = False
        self.isStop = False
        self.mFunc = mFunc

    def start(self):
        self.starttime = time.time()
        self.running = True

        ticker = threading.Event(daemon=True)
        self.waittimeLoop = 0  # make sure first run runs immediately
        while not ticker.wait(self.waittimeLoop) and self.isStop == False:
            self.waittimeLoop = self.waittime
            self.mFunc()
        self.running = False

    def stop(self):
        self.running = False
        self.isStop = True
