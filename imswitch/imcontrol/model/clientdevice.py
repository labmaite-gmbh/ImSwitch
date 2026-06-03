import io
from types import SimpleNamespace

import numpy as np
import tifffile

from locai_app.generics import Point


class ClientStage:
    """Forwards the locai stage interface to microscope_api. deck_manager (pure
    geometry, no hardware) is injected and used locally by the controllers."""

    def __init__(self, client, deck_manager=None):
        self._client = client
        self.deck_manager = deck_manager

    def position(self) -> Point:
        d = self._client.get_position()
        return Point(x=d["x"], y=d["y"], z=d["z"])

    def move_absolute(self, point):
        self._client.move_absolute(point.x, point.y, point.z)

    def move_relative(self, point):
        self._client.shift(point.x, point.y, point.z)

    def move_from_well(self, slot, well, point):
        self._client.move_from_well(slot, well, point.x, point.y, point.z)

    def home(self):
        self._client.home("ALL")

    def park(self):
        self._client.park()

    def stop(self):
        self._client.stop()

    def wait(self):
        # No-op: the API blocks server-side until the move completes.
        pass


class ClientCamera:
    compression = None

    def __init__(self, client):
        self._client = client

    def capture(self):
        data = self._client.raw_frame_bytes()
        img = tifffile.imread(io.BytesIO(data))
        return np.asarray(img), self._client.camera_metadata()

    def stream_switch(self, state):
        # Streaming is owned by the API + RemoteCamera detector; nothing to do here.
        pass

    def set_parameters(self, params):
        # params is an object with .exposure_time/.gain/.black_level (mirrors CfgGxCamera).
        self._client.set_camera_parameters(params.exposure_time, params.gain, params.black_level)

    def get_metadata(self):
        return self._client.camera_metadata()


class ClientLight:
    def __init__(self, client, readable_name, value_range_max=1.0):
        self._client = client
        self.config = SimpleNamespace(readable_name=readable_name, value_range_max=value_range_max)
        self._intensity = 0.0

    def set_enabled(self, state):
        self._client.set_light_enabled(self.config.readable_name, state)

    def set_intensity(self, value):
        # Controllers pass a raw value in [0, value_range_max]; the API expects [0, 1].
        self._intensity = value
        frac = value / self.config.value_range_max if self.config.value_range_max else value
        self._client.set_light_intensity(self.config.readable_name, frac)

    def get_intensity(self):
        return self._intensity


class ClientDevice:
    """Device-shaped proxy: stands in for the locai UC2Device but forwards hardware
    actions to microscope_api. Long-running flows (scan/autofocus/well-preview) are
    triggered via the client's scan/autofocus endpoints by the controllers, not here."""

    def __init__(self, client, deck_manager=None, lights=None):
        self.client = client
        self.stage = ClientStage(client, deck_manager)
        self.camera = ClientCamera(client)
        # lights: list of (key, readable_name, value_range_max)
        self.light_sources = {
            key: ClientLight(client, readable_name, value_range_max)
            for (key, readable_name, value_range_max) in (lights or [])
        }
