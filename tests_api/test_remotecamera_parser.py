import importlib.util
import os
import numpy as np
import cv2

_HERE = os.path.dirname(__file__)
_MOD = os.path.normpath(os.path.join(_HERE, "..", "imswitch", "imcontrol", "model", "interfaces", "remotecamera.py"))


def _load():
    spec = importlib.util.spec_from_file_location("remotecamera", _MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mod = _load()
decode_jpeg_frames = mod.decode_jpeg_frames
RemoteCamera = mod.RemoteCamera


def _jpeg(value):
    img = np.full((8, 8), value, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def test_parses_two_concatenated_frames():
    buf = _jpeg(10) + _jpeg(200)
    frames, remainder = decode_jpeg_frames(buf)
    assert len(frames) == 2
    assert all(f.shape == (8, 8) for f in frames)
    assert remainder == b""


def test_keeps_incomplete_trailing_bytes_as_remainder():
    complete = _jpeg(50)
    partial = _jpeg(99)[:20]  # truncated second frame (no end marker)
    frames, remainder = decode_jpeg_frames(complete + partial)
    assert len(frames) == 1
    assert remainder == partial


def test_no_complete_frame_returns_empty():
    frames, remainder = decode_jpeg_frames(b"\xff\xd8 not a full frame")
    assert frames == []
    assert remainder == b"\xff\xd8 not a full frame"


def test_getlast_returns_zeros_before_any_frame():
    cam = RemoteCamera("http://x/stream", sensor_width=4, sensor_height=4)
    out = cam.getLast()
    assert out.shape == (4, 4)
    assert out.dtype == np.uint8
    assert out.max() == 0
