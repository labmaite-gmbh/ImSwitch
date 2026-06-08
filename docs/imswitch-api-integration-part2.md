# ImSwitch↔microscope_api Integration — Part 2 (ImSwitch side) Implementation Plan

**Goal:** Turn ImSwitch into a CLIENT of `microscope_api` (Architecture A): the API owns the hardware; ImSwitch drives it over HTTP via a device-shaped proxy and shows live view via a remote-camera detector that consumes the API's MJPEG stream.

**Status of dependencies:** Part 1 (microscope-api side) is merged into `scc_dev` and pushed as branch `imswitch-api-integration` — it provides `/api/imaging/camera/{stream,snapshot,frame.tiff,parameters,metadata}`, `/api/control/{owner,acquire,release}` + `X-Client-Id` guard, and the existing `/api/stage`, `/api/lights`, `/api/imaging/{take_image,take_zstack,point_autofocus,take_well,scan/iteration}`.

**Branch:** `imswitch_api_integration` in the ImSwitch fork (off `bcall_sturdy`).

> **Verifiability split (important):** Phase A (client + proxy + remote-camera interface/manager) is environment-independent and unit-tested here with mocked HTTP. **Phase B (setup-JSON swap, startup wiring, controller cutover, handover UI) is GUI/hardware-coupled and CANNOT be verified in this environment** — there is no camera/ESP32/Qt display. Phase B tasks give precise implementation specs but MUST be executed and verified on the actual rig with ImSwitch running. Exact setup-JSON edits depend on the live setup file selected on the rig.

**Test runner:** `C:/Users/Matias/anaconda3/envs/uc2i_env/python.exe -m pytest <path> -v` from `uc2i_conda/ImSwitch`.

---

## Exact contracts (from exploration)

- **DetectorManager** (`imswitch/imcontrol/model/managers/detectors/DetectorManager.py`): abstract `__init__(detectorInfo, name, fullShape, supportedBinnings, model, *, parameters=None, actions=None, croppable=True, isRGB=False)`; abstract `pixelSizeUm` (property, `[Z,Y,X]`), `crop(hpos,vpos,hsize,vsize)`, `getLatestFrame()->ndarray`, `getChunk()->ndarray(n,h,w)`, `flushBuffers()`, `startAcquisition()`, `stopAcquisition()`. Live view: `DetectorsManager.LVWorker` polls `updateLatestFrame()`→`getLatestFrame()` every `updatePeriod` ms and emits `sigImageUpdated`. Auto-discovered by `managerName` via `importlib` from `imswitch.imcontrol.model.managers.detectors.<managerName>`. Template: `ESP32CamManager.py` + `interfaces/esp32camera.py` (already has an MJPEG consumer parsing `\xff\xd8`/`\xff\xd9`).
- **locai device interface** the proxy must mirror (`locai-impl`): stage `CollisionAvoidance` — `position()->Point`, `move_absolute(Point)`, `move_relative(Point)`, `move_from_well(slot,well,Point)`, `home()`, `park()`, `stop()`, `wait()`, attr `deck_manager` (`get_well_position`, `get_slot`, `get_closest_well`, `labwares`); camera (`hardware_api.core.abcs.Camera`) — `capture()->(ndarray,dict)`, `stream_switch(bool)`, `set_parameters(obj)`, `get_metadata()`, `compression`; light sources dict keyed `led/led_matrix/laser_slot_1/laser_slot_2`, each `set_enabled(bool)`, `set_intensity(value)`, `get_intensity()`, `.config.readable_name`, `.config.value_range_max`. `DeckManager` (`locai_app/impl/deck/sd_deck_manager.py`) builds labware geometry from config via `load_labwares(slots)` — buildable LOCALLY, no hardware.
- **microscope_api**: `main.start_server_in_thread(port=9523)`. ImSwitch startup: `imswitch/__main__.py` → `ImConMainController` (already spawns its own `ImSwitchServer` thread); `MasterController` builds managers from setup JSON; `LabmaiteDeckController.__init__` calls `init_device()` (builds the locai `UC2Device`) and wraps `_master.detectorsManager["WidefieldCamera"]` in `CameraWrapper`.

---

## File Structure

**Create (Phase A — testable):**
- `imswitch/imcontrol/model/microscope_api_client.py` — `MicroscopeApiClient` (requests; `X-Client-Id`).
- `imswitch/imcontrol/model/interfaces/remotecamera.py` — `RemoteCamera` (MJPEG bg consumer; `getLast`/`start_live`/`stop_live`).
- `imswitch/imcontrol/model/managers/detectors/RemoteCameraManager.py` — `RemoteCameraManager(DetectorManager)`.
- `imswitch/imcontrol/model/clientdevice.py` — `ClientDevice`/`ClientStage`/`ClientCamera`/`ClientLight` (+ local `deck_manager`).
- Tests: `tests_api/test_microscope_api_client.py`, `tests_api/test_remotecamera_parser.py`, `tests_api/test_clientdevice.py` (new `tests_api/` dir to avoid clashing with ImSwitch's own tests).

**Modify (Phase B — on-rig):**
- The live ImSwitch setup JSON (swap `WidefieldCamera`→`RemoteCameraManager`; neutralize ImSwitch-owned positioners/LEDs that open hardware).
- ImSwitch startup (launch `microscope_api` before managers build).
- `imswitch/imcontrol/controller/controllers/LabmaiteDeckController.py`, `DeckLocaiController.py` (use `ClientDevice` proxy instead of `init_device`).
- `imswitch/imcontrol/view/widgets/LabmaiteDeckWidget.py` (handover toggle).

---

## Phase A — testable foundation

### Task A1: `MicroscopeApiClient`
**Files:** Create `imswitch/imcontrol/model/microscope_api_client.py`; Test `tests_api/test_microscope_api_client.py`.

TDD. The client wraps `requests.Session`, prefixes `base_url` (default `http://127.0.0.1:9523`), sends `X-Client-Id` on every request, and exposes typed methods mapping to the API routes. Tests monkeypatch the session's `request` to capture method/url/json/headers and return canned responses (no real network).

Methods (map to Part 1 + existing routes):
- control: `acquire()` → POST `/api/control/acquire {client_id}`; `release()` → POST `/api/control/release`; `owner()` → GET `/api/control/owner`.
- stage: `get_position()` GET `/api/stage/position`; `move_absolute(x,y,z)` PUT `/api/stage/position/move`; `shift(x,y,z)` PUT `/api/stage/position/shift`; `move_from_well(slot,well,x,y,z)` PUT `/api/stage/position/move_from_well`; `home(axis)` PUT `/api/stage/position/home`; `park()` PUT `/api/stage/position/park`; `stop()` PUT `/api/stage/position/stop`.
- lights: `set_enabled(name,state)` PUT `/api/lights/{enable|disable}`; `set_intensity(name,intensity)` PUT `/api/lights/intensity`; `intensities()` GET `/api/lights/intensities`.
- camera/imaging: `take_image()` PUT `/api/imaging/camera/take_image`; `snapshot_bytes()` GET `/api/imaging/camera/snapshot`; `raw_frame()` GET `/api/imaging/camera/frame.tiff`; `stream_url()` → f"{base}/api/imaging/camera/stream"; `set_camera_parameters(exposure_time,gain,black_level)` PUT `/api/imaging/camera/parameters`; `camera_metadata()` GET `/api/imaging/camera/metadata`; `take_zstack(...)`, `point_autofocus(...)`, `take_well(...)`, `run_scan(...)`.

(Full method code + tests are written task-by-task during execution; each method is one-liner over `self._session.request`. Tests assert URL/verb/json/`X-Client-Id` header and 423/409 handling — a non-2xx raises a `MicroscopeApiError` carrying status code.)

### Task A2: `RemoteCamera` MJPEG interface
**Files:** Create `imswitch/imcontrol/model/interfaces/remotecamera.py`; Test `tests_api/test_remotecamera_parser.py`.
- A background thread reads the MJPEG `stream_url` and parses JPEG frames (`\xff\xd8`…`\xff\xd9`), `cv2.imdecode` → grayscale ndarray stored as `self._latest`. `getLast()` returns latest (or zeros until first frame). `start_live()/stop_live()` manage the thread. `model`, `SensorWidth/Height` from a `/api/imaging/camera/metadata` call or config.
- **Unit-test the frame PARSER** (the testable core): feed a synthetic byte buffer containing two concatenated JPEGs and assert it yields two decoded frames. Mirror `esp32camera.getframes` parsing. (The live thread itself is exercised on-rig.)

### Task A3: `RemoteCameraManager(DetectorManager)`
**Files:** Create `imswitch/imcontrol/model/managers/detectors/RemoteCameraManager.py`.
- Mirror `ESP32CamManager`: build `fullShape`, `supportedBinnings=[1]`, `parameters` (exposure/gain as `DetectorNumberParameter`), call `super().__init__`. `getLatestFrame()`→`self._camera.getLast()`; `getChunk()`→`np.expand_dims(getLast(),0)`; `start/stopAcquisition`→camera `start_live/stop_live`; `crop` stores frame start/shape; `pixelSizeUm` from `managerProperties` (default `[1,1,1]`). `managerProperties`: `{base_url, client_id}`.
- **Verification: on-rig** (instantiating a `DetectorManager` needs ImSwitch's Qt `SignalInterface`; a smoke import test may run headless but live frames need the rig). Mark accordingly.

### Task A4: `ClientDevice` proxy
**Files:** Create `imswitch/imcontrol/model/clientdevice.py`; Test `tests_api/test_clientdevice.py`.
- `ClientStage` implements the `CollisionAvoidance` surface by forwarding to `MicroscopeApiClient` (`position/move_absolute/move_relative/move_from_well/home/park/stop/wait`; `wait()` is a no-op because the API blocks server-side). `deck_manager` is a REAL local `DeckManager` built from the experiment config (geometry only, no hardware).
- `ClientCamera` implements `capture()` (via `/snapshot` or `raw_frame` → ndarray), `stream_switch`, `set_parameters`, `get_metadata`, `compression`.
- `ClientLight` objects + `light_sources` dict mirror the locai light interface, forwarding `set_enabled/set_intensity/get_intensity`; `.config.readable_name`/`.value_range_max` from the device/experiment config.
- `ClientDevice` aggregates `.stage`, `.camera`, `.light_sources` and exposes the few attrs controllers read.
- **Unit-test** stage/camera/light proxies forward the right client calls (mock `MicroscopeApiClient`); test the local `deck_manager` returns geometry from a config without hardware.

---

## Phase B — on-rig wiring (specify; VERIFY ON HARDWARE)

### Task B1: Launch microscope_api at ImSwitch startup
Start `microscope_api.main.start_server_in_thread(port)` early in ImSwitch startup (before `MasterController` builds managers), configured so the API owns the hardware (its own `MicroscopeDevice()` standalone). Ensure the API has finished opening hardware before ImSwitch tries to use it (health poll). **Verify:** API boots, owns camera+stage; ImSwitch process hosts it.

### Task B2: Setup-JSON cutover (sole-owner)
In the LIVE ImSwitch setup JSON: swap the `WidefieldCamera` detector `managerName`→`RemoteCameraManager` (`managerProperties: {base_url, client_id}`); and **neutralize any ImSwitch-owned managers that open the same hardware** (positioners/LEDs that drive the UC2 stage/lights) so only the API opens hardware. Exact keys depend on the live file (candidates seen: `example_locai.json` with `CameraGXIPY`/`StandaStage`/`TLUP`). **Verify on rig:** no double-open errors; live view shows API frames.

### Task B3: Controller cutover
In `LabmaiteDeckController.init_device` (and `DeckLocaiController`), replace construction of the locai `UC2Device` + `CameraWrapper(imswitch detector)` with a `ClientDevice` proxy (built from `MicroscopeApiClient` + experiment config for deck geometry). `self.exp_context`/device usages then hit the proxy. Remove the local hardware-open path. Long-running flows (`run_experiment`, autofocus, well-preview) call the API's `/scan/iteration`, `/point_autofocus`, `/take_well` and report progress via the existing webhooks. **Verify on rig:** jog/move/home/light/snap and a scan all work through the API.

### Task B4: Handover UI
In `LabmaiteDeckWidget`, add "Hand over to external control" / "Take back control". On hand-over: `client.release()` (or transfer) so the microfluidics client can `acquire()`, and disable operator controls; on take-back: `client.acquire()` and re-enable. Reflect `/api/control/owner` in the UI. **Verify on rig:** operator hand-off → microfluidics drives; reads still work; take-back reclaims.

---

## Verification
- **Phase A (here):** `pytest tests_api/ -v` green (client routes/headers, MJPEG parser, proxy forwarding, local deck geometry).
- **Phase B (on rig):** boot ImSwitch → live view via API (no gxipy double-open); operator control via proxy; scan/autofocus/well-preview server-side with webhook progress; handover to a separate `X-Client-Id` client and back. Use Part 1's `smoke_part1.py` against the running API as a sanity check.

## Self-review notes
- Deck geometry deliberately stays local (no new API endpoints). Long-running flows stay server-side (no chatty HTTP loops). Reads (frames/status) never gated. Phase B exact edits are rig-specific by necessity — flagged, not hidden.
