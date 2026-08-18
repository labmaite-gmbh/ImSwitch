import importlib.util
import os

_HERE = os.path.dirname(__file__)
_MOD = os.path.normpath(os.path.join(_HERE, "..", "imswitch", "imcontrol", "model", "microscope_api_client.py"))


def _load():
    spec = importlib.util.spec_from_file_location("microscope_api_client", _MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mod = _load()
MicroscopeApiClient = mod.MicroscopeApiClient
MicroscopeApiError = mod.MicroscopeApiError


class _Resp:
    def __init__(self, status_code=200, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json = json_data
        # If json_data is provided but no explicit content, use a non-empty sentinel
        # so _request does not treat the response as empty/204.
        self.content = content if content else (b"{}" if json_data is not None else b"")
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _Session:
    def __init__(self, resp=None):
        self.calls = []
        self._resp = resp or _Resp(204)

    def request(self, method, url, json=None, params=None, files=None, headers=None, timeout=None, stream=False):
        self.calls.append({"method": method, "url": url, "json": json, "params": params,
                           "files": files, "headers": headers, "stream": stream})
        return self._resp


def test_move_absolute_sends_put_with_body_and_header():
    s = _Session(_Resp(204))
    c = MicroscopeApiClient(base_url="http://h:9523", client_id="imswitch", session=s)
    c.move_absolute(1.0, 2.0, 3.0)
    call = s.calls[-1]
    assert call["method"] == "PUT"
    assert call["url"] == "http://h:9523/api/stage/position/move"
    assert call["json"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert call["headers"]["X-Client-Id"] == "imswitch"


def test_acquire_posts_client_id():
    s = _Session(_Resp(200, {"control_owner": "imswitch"}))
    c = MicroscopeApiClient(session=s, client_id="imswitch")
    assert c.acquire() == {"control_owner": "imswitch"}
    assert s.calls[-1]["url"].endswith("/api/control/acquire")
    assert s.calls[-1]["json"] == {"client_id": "imswitch"}


def test_move_from_well_uses_query_and_body():
    s = _Session(_Resp(204))
    c = MicroscopeApiClient(session=s)
    c.move_from_well("1", "A1", 1.0, 2.0, 3.0)
    call = s.calls[-1]
    assert call["params"] == {"slot": "1", "well": "A1"}
    assert call["json"] == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_light_enable_vs_disable_path():
    s = _Session(_Resp(204))
    c = MicroscopeApiClient(session=s)
    c.set_light_enabled("LED", True)
    assert s.calls[-1]["url"].endswith("/api/lights/enable")
    c.set_light_enabled("LED", False)
    assert s.calls[-1]["url"].endswith("/api/lights/disable")


def test_snapshot_returns_raw_bytes():
    s = _Session(_Resp(200, content=b"\xff\xd8jpeg"))
    c = MicroscopeApiClient(session=s)
    assert c.snapshot_bytes() == b"\xff\xd8jpeg"


def test_error_status_raises_with_detail():
    s = _Session(_Resp(423, {"detail": "control held"}))
    c = MicroscopeApiClient(session=s, client_id="other")
    try:
        c.move_absolute(0, 0, 0)
        assert False, "should have raised"
    except MicroscopeApiError as e:
        assert e.status_code == 423
        assert "control held" in e.detail


def test_load_experiment_uploads_json_as_file():
    s = _Session(_Resp(204))
    c = MicroscopeApiClient(session=s, client_id="imswitch")
    c.load_experiment('{"slots": []}')
    call = s.calls[-1]
    assert call["method"] == "PUT"
    assert call["url"] == "http://127.0.0.1:9523/api/general/experiment"
    assert call["json"] is None
    name, content, content_type = call["files"]["file"]
    assert content == b'{"slots": []}'
    assert content_type == "application/json"
    assert call["headers"]["X-Client-Id"] == "imswitch"


def test_stream_url_normalizes_trailing_slash():
    c = MicroscopeApiClient(base_url="http://h:9523/")
    assert c.stream_url() == "http://h:9523/api/imaging/camera/stream"
