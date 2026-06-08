import numpy as np

from imswitch.imcommon.model import initLogger
from .DetectorManager import DetectorManager, DetectorNumberParameter


class RemoteCameraManager(DetectorManager):
    """DetectorManager that serves live frames from a remote ``microscope_api`` MJPEG
    stream instead of opening a local camera. Used when ``microscope_api`` is the sole
    hardware owner and ImSwitch is a client (Architecture A).

    Manager properties (setup JSON ``managerProperties``):

    - ``base_url`` -- microscope_api base URL (default ``http://127.0.0.1:9523``)
    - ``client_id`` -- X-Client-Id sent to the API (default ``imswitch``)
    - ``image_width`` / ``image_height`` -- full frame shape (default 0 -> probed lazily)
    - ``pixelSizeUm`` -- optional [Z, Y, X] pixel size (default [1, 1, 1])

    NOTE: This is verified ON THE RIG with ImSwitch running. The live stream and
    camera-parameter forwarding require microscope_api to be up and owning the camera.
    """

    def __init__(self, detectorInfo, name, **_lowLevelManagers):
        self.__logger = initLogger(self, instanceName=name)

        props = detectorInfo.managerProperties
        self._base_url = props.get('base_url', 'http://127.0.0.1:9523')
        self._client_id = props.get('client_id', 'imswitch')
        self._pixel_size = props.get('pixelSizeUm', [1, 1, 1])
        width = int(props.get('image_width', 0) or 0)
        height = int(props.get('image_height', 0) or 0)

        # Lightweight client (HTTP only) + the MJPEG-backed camera interface.
        from imswitch.imcontrol.model.microscope_api_client import MicroscopeApiClient
        from imswitch.imcontrol.model.interfaces.remotecamera import RemoteCamera
        self._client = MicroscopeApiClient(base_url=self._base_url, client_id=self._client_id)
        self._camera = RemoteCamera(stream_url=self._client.stream_url(),
                                    model='RemoteCamera',
                                    sensor_width=width, sensor_height=height)
        self._running = False

        fullShape = (width or 0, height or 0)

        parameters = {
            'exposure': DetectorNumberParameter(group='Misc', value=10, valueUnits='ms', editable=True),
            'gain': DetectorNumberParameter(group='Misc', value=1, valueUnits='arb.u.', editable=True),
            'blacklevel': DetectorNumberParameter(group='Misc', value=1, valueUnits='arb.u.', editable=True),
            'image_width': DetectorNumberParameter(group='Misc', value=fullShape[0], valueUnits='px', editable=False),
            'image_height': DetectorNumberParameter(group='Misc', value=fullShape[1], valueUnits='px', editable=False),
        }

        super().__init__(detectorInfo, name, fullShape=fullShape, supportedBinnings=[1],
                         model='RemoteCamera', parameters=parameters, actions={}, croppable=True)

    def getLatestFrame(self, is_save=False):
        return self._camera.getLast()

    def getChunk(self):
        return np.expand_dims(self._camera.getLast(), 0)

    def flushBuffers(self):
        pass

    def setParameter(self, name, value):
        """Set a parameter and forward the camera trio (exposure/gain/blacklevel) to
        microscope_api. The API requires all three, so we push the current values of
        all three whenever any one changes."""
        super().setParameter(name, value)
        params = self._DetectorManager__parameters
        if name in ('exposure', 'gain', 'blacklevel'):
            try:
                self._client.set_camera_parameters(
                    exposure_time=params['exposure'].value,
                    gain=params['gain'].value,
                    black_level=params['blacklevel'].value,
                )
            except Exception as e:
                self.__logger.warning(f'Failed to set camera parameters via API: {e!r}')
        return value

    def setBinning(self, binning):
        super().setBinning(binning)

    def startAcquisition(self):
        if not self._running:
            self._camera.start_live()
            self._running = True
            self.__logger.debug('Started remote live stream')

    def stopAcquisition(self):
        if self._running:
            self._running = False
            self._camera.stop_live()
            self.__logger.debug('Stopped remote live stream')

    def crop(self, hpos, vpos, hsize, vsize):
        # The API serves full frames; cropping is a no-op beyond recording the shape.
        self._frameStart = (hpos, vpos)
        self._shape = (hsize, vsize)

    @property
    def pixelSizeUm(self):
        return self._pixel_size

    def finalize(self) -> None:
        super().finalize()
        self._camera.close()


# Copyright (C) ImSwitch developers 2021
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
