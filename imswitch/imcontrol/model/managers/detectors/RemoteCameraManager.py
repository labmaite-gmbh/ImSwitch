import io

import numpy as np
import requests
import tifffile

from imswitch.imcommon.model import initLogger
from .DetectorManager import DetectorManager, DetectorNumberParameter


class RemoteCameraManager(DetectorManager):
    """DetectorManager that proxies camera operations to a running microscope-api server.

    Manager properties:
        - ``base_url``: Base URL of the microscope-api (e.g. 'http://127.0.0.1:9523')
        - ``client_id``: Client ID used to acquire the control lock
        - ``image_width``: Sensor width in pixels
        - ``image_height``: Sensor height in pixels
        - ``pixelSizeUm``: [z, y, x] pixel size list
    """

    def __init__(self, detectorInfo, name, **_lowLevelManagers):
        self.__logger = initLogger(self, instanceName=name)

        props = detectorInfo.managerProperties
        self._base_url = props['base_url'].rstrip('/')
        self._client_id = props.get('client_id', 'imswitch')
        self._pixel_size_um = props.get('pixelSizeUm', [1, 1, 1])

        self._image_width = int(props.get('image_width', 1920))
        self._image_height = int(props.get('image_height', 1080))
        fullShape = (self._image_width, self._image_height)

        self._running = False
        self._exposure_ms = 100.0
        self._gain = 1.0
        self._black_level = 0.0

        self._session = requests.Session()
        self._session.headers['X-Client-Id'] = self._client_id

        self._acquire_control()

        parameters = {
            'exposure': DetectorNumberParameter(group='Misc', value=self._exposure_ms,
                                                valueUnits='ms', editable=True),
            'gain': DetectorNumberParameter(group='Misc', value=self._gain,
                                            valueUnits='arb.u.', editable=True),
            'blacklevel': DetectorNumberParameter(group='Misc', value=self._black_level,
                                                  valueUnits='arb.u.', editable=True),
            'frame_rate': DetectorNumberParameter(group='Misc', value=10.0,
                                                  valueUnits='fps', editable=True),
            'image_width': DetectorNumberParameter(group='Misc', value=self._image_width,
                                                   valueUnits='px', editable=False),
            'image_height': DetectorNumberParameter(group='Misc', value=self._image_height,
                                                    valueUnits='px', editable=False),
        }

        super().__init__(detectorInfo, name, fullShape=fullShape, supportedBinnings=[1],
                         model='RemoteCamera', parameters=parameters, croppable=False)

    # ------------------------------------------------------------------
    # Control lock helpers
    # ------------------------------------------------------------------

    def _acquire_control(self):
        try:
            resp = self._session.post(
                f'{self._base_url}/api/control/acquire',
                json={'client_id': self._client_id},
                timeout=3,
            )
            if resp.ok:
                self.__logger.info(f'Control acquired as "{self._client_id}"')
            else:
                self.__logger.warning(f'Control acquire returned {resp.status_code}: {resp.text}')
        except Exception as e:
            self.__logger.warning(f'microscope-api not reachable, running in offline mode: {e}')

    def _release_control(self):
        try:
            self._session.post(f'{self._base_url}/api/control/release', timeout=3)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Camera parameter sync
    # ------------------------------------------------------------------

    def _push_camera_params(self):
        try:
            self._session.put(
                f'{self._base_url}/api/imaging/camera/parameters',
                json={
                    'exposure_time': self._exposure_ms,
                    'gain': self._gain,
                    'black_level': self._black_level,
                },
                timeout=3,
            )
        except Exception as e:
            self.__logger.warning(f'Failed to push camera params: {e}')

    def _blank_frame(self):
        return np.zeros((self._image_height, self._image_width), dtype=np.uint16)

    # ------------------------------------------------------------------
    # DetectorManager abstract interface
    # ------------------------------------------------------------------

    def getLatestFrame(self, is_save=False):
        try:
            resp = self._session.get(
                f'{self._base_url}/api/imaging/camera/frame.tiff',
                timeout=10,
            )
            resp.raise_for_status()
            return tifffile.imread(io.BytesIO(resp.content))
        except Exception as e:
            self.__logger.debug(f'Frame fetch failed (offline?): {e}')
            return self._blank_frame()

    def getChunk(self):
        """Returns the latest frame as a single-frame chunk (numFrames, height, width)."""
        frame = self.getLatestFrame()
        return frame[np.newaxis, ...]

    def flushBuffers(self):
        pass

    def setParameter(self, name, value):
        super().setParameter(name, value)
        if name == 'exposure':
            self._exposure_ms = float(value)
            self._push_camera_params()
        elif name == 'gain':
            self._gain = float(value)
            self._push_camera_params()
        elif name == 'blacklevel':
            self._black_level = float(value)
            self._push_camera_params()
        return value

    def getParameter(self, name):
        if name not in self.parameters:
            raise AttributeError(f'Non-existent parameter "{name}" specified')
        return self.parameters[name].value

    def startAcquisition(self, liveView=False):
        if not self._running:
            try:
                self._session.put(f'{self._base_url}/api/imaging/camera/enable', timeout=3)
            except Exception as e:
                self.__logger.debug(f'Camera enable skipped (offline?): {e}')
            self._running = True
            self.__logger.debug('Remote camera acquisition started')

    def stopAcquisition(self):
        if self._running:
            self._running = False
            try:
                self._session.put(f'{self._base_url}/api/imaging/camera/disable', timeout=3)
            except Exception as e:
                self.__logger.debug(f'Camera disable skipped (offline?): {e}')
            self.__logger.debug('Remote camera acquisition stopped')

    def stopAcquisitionForROIChange(self):
        self.stopAcquisition()

    def crop(self, hpos, vpos, hsize, vsize):
        pass  # cropping not supported via REST

    @property
    def pixelSizeUm(self):
        return self._pixel_size_um

    def finalize(self) -> None:
        super().finalize()
        self._release_control()
        self._session.close()
        self.__logger.debug('RemoteCameraManager finalized')

    def closeEvent(self):
        self.finalize()
