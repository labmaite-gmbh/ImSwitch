import requests


class MicroscopeApiError(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"microscope_api error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class MicroscopeApiClient:
    """Thin HTTP client for microscope_api. Sends X-Client-Id on every request so the
    server's control-owner guard can attribute calls to this client."""

    def __init__(self, base_url="http://127.0.0.1:9523", client_id="imswitch",
                 session=None, timeout=10.0):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.timeout = timeout
        self._session = session or requests.Session()

    def _request(self, method, path, *, json=None, params=None, raw=False, stream=False):
        url = self.base_url + path
        headers = {"X-Client-Id": self.client_id}
        resp = self._session.request(method, url, json=json, params=params,
                                     headers=headers, timeout=self.timeout, stream=stream)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = getattr(resp, "text", "")
            raise MicroscopeApiError(resp.status_code, detail)
        if raw:
            return resp.content
        if resp.status_code == 204 or not getattr(resp, "content", b""):
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # --- control ---
    def acquire(self):
        return self._request("POST", "/api/control/acquire", json={"client_id": self.client_id})

    def release(self):
        return self._request("POST", "/api/control/release")

    def owner(self):
        return self._request("GET", "/api/control/owner")

    # --- stage ---
    def get_position(self):
        return self._request("GET", "/api/stage/position")

    def move_absolute(self, x, y, z):
        return self._request("PUT", "/api/stage/position/move", json={"x": x, "y": y, "z": z})

    def shift(self, x, y, z):
        return self._request("PUT", "/api/stage/position/shift", json={"x": x, "y": y, "z": z})

    def move_from_well(self, slot, well, x, y, z):
        return self._request("PUT", "/api/stage/position/move_from_well",
                             params={"slot": slot, "well": well}, json={"x": x, "y": y, "z": z})

    def home(self, axis="ALL"):
        return self._request("PUT", "/api/stage/position/home", json={"axis": axis})

    def park(self):
        return self._request("PUT", "/api/stage/position/park")

    def stop(self):
        return self._request("PUT", "/api/stage/position/stop")

    # --- lights ---
    def set_light_enabled(self, readable_name, state):
        path = "/api/lights/enable" if state else "/api/lights/disable"
        return self._request("PUT", path, json={"readable_name": readable_name})

    def set_light_intensity(self, readable_name, intensity):
        return self._request("PUT", "/api/lights/intensity",
                             json={"readable_name": readable_name, "intensity": intensity})

    def intensities(self):
        return self._request("GET", "/api/lights/intensities")

    # --- camera / imaging ---
    def take_image(self):
        return self._request("PUT", "/api/imaging/camera/take_image")

    def snapshot_bytes(self):
        return self._request("GET", "/api/imaging/camera/snapshot", raw=True)

    def raw_frame_bytes(self):
        return self._request("GET", "/api/imaging/camera/frame.tiff", raw=True)

    def stream_url(self):
        return self.base_url + "/api/imaging/camera/stream"

    def set_camera_parameters(self, exposure_time, gain, black_level):
        return self._request("PUT", "/api/imaging/camera/parameters",
                             json={"exposure_time": exposure_time, "gain": gain, "black_level": black_level})

    def camera_metadata(self):
        return self._request("GET", "/api/imaging/camera/metadata")

    # --- scan / autofocus / well-preview (server-side execution) ---
    def run_scan(self, exp_config_dict, custom_parent_dir=None, experiment_dir_name=None):
        return self._request("PUT", "/api/imaging/scan/iteration",
                             json={"exp_config": exp_config_dict,
                                   "custom_parent_dir": custom_parent_dir,
                                   "experiment_dir_name": experiment_dir_name})

    def cancel_scan(self):
        return self._request("PUT", "/api/imaging/scan/iteration/cancel")

    def point_autofocus(self, af_params_dict):
        return self._request("PUT", "/api/imaging/camera/point_autofocus",
                             json=af_params_dict)

    def take_well(self, slot, well, rois, z_params_dict):
        return self._request("PUT", "/api/imaging/camera/take_well",
                             json={"slot": slot, "well": well,
                                   "rois": rois, "z_params": z_params_dict})
