import threading

import cv2
import numpy as np
import requests


def decode_jpeg_frames(buffer: bytes):
    """Extract complete JPEG frames from an MJPEG byte buffer.
    Returns (frames, remainder): frames is a list of decoded grayscale ndarrays,
    remainder is the leftover bytes (an incomplete trailing frame)."""
    frames = []
    while True:
        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9", start + 2) if start != -1 else -1
        if start == -1 or end == -1:
            break
        jpg = buffer[start:end + 2]
        buffer = buffer[end + 2:]
        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            frames.append(img)
    return frames, buffer


class RemoteCamera:
    """Pulls the microscope_api MJPEG stream in a background thread and keeps the
    latest decoded frame. getLast() is fast (returns the cached frame)."""

    def __init__(self, stream_url, model="RemoteCamera", sensor_width=0, sensor_height=0, timeout=5.0):
        self.stream_url = stream_url
        self.model = model
        self.SensorWidth = sensor_width
        self.SensorHeight = sensor_height
        self.timeout = timeout
        self._latest = None
        self._running = False
        self._thread = None

    def start_live(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True, name="remote-camera")
        self._thread.start()

    def stop_live(self):
        self._running = False

    def _consume(self):
        try:
            with requests.get(self.stream_url, stream=True, timeout=self.timeout) as r:
                buf = b""
                for chunk in r.iter_content(chunk_size=4096):
                    if not self._running:
                        break
                    buf += chunk
                    frames, buf = decode_jpeg_frames(buf)
                    if frames:
                        self._latest = frames[-1]
        except Exception:
            # Best-effort live stream: on any error, stop. Live view shows the last
            # frame (or zeros); the operator/poller recovers.
            self._running = False

    def getLast(self):
        if self._latest is None:
            return np.zeros((self.SensorHeight or 2, self.SensorWidth or 2), dtype=np.uint8)
        return self._latest

    def close(self):
        self.stop_live()
