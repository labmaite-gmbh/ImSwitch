import importlib.util
import os
import io
import numpy as np
import tifffile

_HERE = os.path.dirname(__file__)
_MOD = os.path.normpath(os.path.join(_HERE, "..", "imswitch", "imcontrol", "model", "clientdevice.py"))


def _load():
    spec = importlib.util.spec_from_file_location("clientdevice", _MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mod = _load()
ClientDevice = mod.ClientDevice
from locai_app.generics import Point


class FakeClient:
    def __init__(self):
        self.calls = []
        self._pos = {"x": 1.0, "y": 2.0, "z": 3.0}
        self._meta = {"timestamp": "t", "camera_metadata": {}}

    def get_position(self):
        self.calls.append(("get_position",))
        return self._pos

    def move_absolute(self, x, y, z):
        self.calls.append(("move_absolute", x, y, z))

    def shift(self, x, y, z):
        self.calls.append(("shift", x, y, z))

    def move_from_well(self, slot, well, x, y, z):
        self.calls.append(("move_from_well", slot, well, x, y, z))

    def home(self, axis):
        self.calls.append(("home", axis))

    def park(self):
        self.calls.append(("park",))

    def stop(self):
        self.calls.append(("stop",))

    def set_light_enabled(self, name, state):
        self.calls.append(("set_light_enabled", name, state))

    def set_light_intensity(self, name, frac):
        self.calls.append(("set_light_intensity", name, frac))

    def set_camera_parameters(self, e, g, b):
        self.calls.append(("set_camera_parameters", e, g, b))

    def camera_metadata(self):
        return self._meta

    def raw_frame_bytes(self):
        bio = io.BytesIO()
        tifffile.imwrite(bio, np.full((4, 4), 7, dtype=np.uint16))
        return bio.getvalue()


def test_position_returns_point():
    c = FakeClient()
    dev = ClientDevice(c)
    p = dev.stage.position()
    assert (p.x, p.y, p.z) == (1.0, 2.0, 3.0)


def test_move_absolute_and_relative_forward():
    c = FakeClient()
    dev = ClientDevice(c)
    dev.stage.move_absolute(Point(x=4.0, y=5.0, z=6.0))
    dev.stage.move_relative(Point(x=1.0, y=0.0, z=0.0))
    assert ("move_absolute", 4.0, 5.0, 6.0) in c.calls
    assert ("shift", 1.0, 0.0, 0.0) in c.calls


def test_move_from_well_forwards():
    c = FakeClient()
    dev = ClientDevice(c)
    dev.stage.move_from_well("1", "A1", Point(x=7.0, y=0.0, z=0.0))
    assert ("move_from_well", "1", "A1", 7.0, 0.0, 0.0) in c.calls


def test_wait_is_noop():
    c = FakeClient()
    dev = ClientDevice(c)
    dev.stage.wait()
    assert c.calls == []


def test_capture_decodes_raw_tiff():
    c = FakeClient()
    dev = ClientDevice(c)
    img, meta = dev.camera.capture()
    assert img.shape == (4, 4) and img.dtype == np.uint16 and img.max() == 7
    assert meta == c._meta


def test_set_camera_parameters_forwards_attributes():
    from types import SimpleNamespace
    c = FakeClient()
    dev = ClientDevice(c)
    dev.camera.set_parameters(SimpleNamespace(exposure_time=10.0, gain=2.0, black_level=1.0))
    assert ("set_camera_parameters", 10.0, 2.0, 1.0) in c.calls


def test_light_enable_and_intensity_conversion():
    c = FakeClient()
    dev = ClientDevice(c, lights=[("led", "LED", 100.0)])
    light = dev.light_sources["led"]
    assert light.config.readable_name == "LED"
    light.set_enabled(True)
    light.set_intensity(50.0)  # raw value in [0, 100] -> 0.5 fraction for the API
    assert ("set_light_enabled", "LED", True) in c.calls
    assert ("set_light_intensity", "LED", 0.5) in c.calls
    assert light.get_intensity() == 50.0
