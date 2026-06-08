# ImSwitch ↔ microscope_api — ON-RIG integration guide (Part 2, Phase B)

This guide covers the steps that **must be completed and verified on the physical
microscope** (no camera/ESP32/Qt display in CI). The testable foundation (client,
RemoteCamera parser, ClientDevice proxy — `tests_api/`, 18 passing) and the on-rig
scaffolding (RemoteCameraManager, helper, opt-in controller branch, remote setup,
handover helper) are committed; the items below are the remaining wiring + validation.

## What's already in place
- `imswitch/imcontrol/model/managers/detectors/RemoteCameraManager.py` — detector serving the API MJPEG stream (auto-discovered by `managerName`).
- `imswitch/imcontrol/model/interfaces/remotecamera.py` — `RemoteCamera` MJPEG consumer.
- `imswitch/imcontrol/model/microscope_api_client.py` — `MicroscopeApiClient`.
- `imswitch/imcontrol/model/clientdevice.py` — `ClientDevice` proxy.
- `imswitch/imcontrol/model/imswitch_api_integration.py` — `use_api_client()`, `start_api()`, `build_client_device()`, `set_external_control()`, + `build_local_deck_manager`/`lights_from_config` (TODOs).
- `btig_uc2_remote_imswitch.json` — setup variant: `WidefieldCamera` → `RemoteCameraManager` (positioner already mock; nothing else opens hardware in ImSwitch).
- `LabmaiteDeckController.init_device` — opt-in branch: when `MICROSCOPE_API_CLIENT` is set, starts the API and returns a `ClientDevice` proxy instead of building the local `UC2Device`.

## Enabling client mode (on the rig)
1. Ensure the `microscope_api` package is importable (microscope-api repo installed or
   on `PYTHONPATH`). The server is started in-process via
   `from microscope_api.server import start_server_in_thread` — no separate `main.py`
   import needed. Configure `labmaite_config.json` with `DEBUG=2` (real device).
2. Set `MICROSCOPE_API_CLIENT=1` and `DEVICE_JSON_PATH=<path/to/device.json>` in the
   environment that launches ImSwitch.
3. Select the **`btig_uc2_remote_imswitch`** setup in the ImSwitch setup picker.
4. Launch ImSwitch. `init_device` starts the API, acquires control as `imswitch`, and
   returns the `ClientDevice` proxy; the `RemoteCameraManager` shows live view.

## Remaining wiring (do on the rig)

### 1. Local deck geometry + light names (`imswitch_api_integration.py` TODOs) ✅ DONE
- `build_local_deck_manager(exp_config)`: reads from `DEVICE_JSON_PATH`; returns None with a warning if unavailable.
- `lights_from_config(exp_config)`: reads `CfgTlUpLed` from `DEVICE_JSON_PATH`; returns `[]` with a warning if unavailable.
- Both functions gracefully degrade — verify on rig that `DEVICE_JSON_PATH` resolves correctly.

### 2. Redirect scan / autofocus / well-preview to the API ✅ DONE
`LabmaiteDeckController` now branches on `use_api_client()` in `start_scan`, `run_autofocus`, and `z_scan_preview`:
- `start_scan` → calls `_start_scan_via_api()` → `self.api_client.run_scan(exp_config.dict())` in a daemon thread.
- `stop_scan` → calls `self.api_client.cancel_scan()` in client mode.
- `run_autofocus` → calls `_run_autofocus_via_api()` → `self.api_client.point_autofocus(params_dict)` in a daemon thread; moves stage to returned `z` on completion.
- `z_scan_preview` → calls `_run_well_preview_via_api()` → `self.api_client.take_well(slot, well, rois, z_params)` using the selected slot/well and z-scan widget values.
- `MicroscopeApiClient` has four new methods: `run_scan`, `cancel_scan`, `point_autofocus`, `take_well`.
- `imswitch_api_integration.start_api` now imports `from microscope_api.server import start_server_in_thread` (resolves the old `main` import ambiguity).

### 3. Handover toggle in `LabmaiteDeckWidget` ✅ DONE
- `LabmaiteDeckWidget` has a new `HandOverButton` (checkable, orange/red) and `sigHandOverToggled` signal.
- Button is hidden by default; shown only when `use_api_client()` is true (set in `connect_widget_buttons`).
- `_on_handover_toggled(handover)` calls `set_external_control`, updates button label/style, and toggles operator controls via `toggle_widgets`.

## Verification checklist (on the rig)

### Startup
- [ ] `MICROSCOPE_API_CLIENT=1` and `DEVICE_JSON_PATH` are set before launching ImSwitch.
- [ ] API boots cleanly — no `gxipy`/serial double-open errors in the log.
- [ ] `GET /health` returns `"OK"` at `http://127.0.0.1:9523/health`.
- [ ] `GET /api/control/owner` shows `{"client_id": "imswitch"}` — control acquired on init.
- [ ] `DEVICE_JSON_PATH` resolves; loguru shows no "Could not build local DeckManager" or "Could not read lights" warnings (if it does, fix the path).

### Live view & camera
- [ ] ImSwitch live view (napari) shows frames via `RemoteCameraManager` ← `/api/imaging/camera/stream`.
- [ ] Adjusting exposure/gain/blacklevel in the ImSwitch camera panel pushes to `/api/imaging/camera/parameters` without error; confirm units match the rig.
- [ ] Single snapshot (`PUT /api/imaging/camera/take_image`) saves a file under `STORAGE_PATH`.

### Operator controls (proxy round-trips)
- [ ] Jog / step buttons move the stage; `/api/stage/position` position updates.
- [ ] Home (`PUT /api/stage/position/home`) and Park work without errors.
- [ ] Stop (`PUT /api/stage/position/stop`) halts motion mid-move.
- [ ] Light intensity slider calls `/api/lights/intensity`; LED brightness changes on the rig.

### Server-side long-running flows
- [ ] **Scan**: press Start in the Scan List Actions group; status label shows "Scan running via API…"; output directory appears under `STORAGE_PATH`; status updates to "Scan complete: <dir>" when done. Stop button calls `cancel_scan` and halts early if pressed mid-scan.
- [ ] **Autofocus**: run autofocus from the autofocus dialog; `PUT /api/imaging/camera/point_autofocus` is called; stage moves to the returned `z`; status label confirms completion.
- [ ] **Well preview**: open the Z-scan dialog with a slot/well selected; press Preview; `PUT /api/imaging/camera/take_well` is called with the correct slot, well, ROI offset, and z-params; output lands under `STORAGE_PATH`.

### Hand-over / take-back
- [ ] "Hand over" button is **visible** in the Scan Actions group when `MICROSCOPE_API_CLIENT=1`.
- [ ] Click "Hand over": button turns red and reads "Take back"; operator controls (jog/scan/home/park) are hidden; status shows current owner.
- [ ] While handed over: a second client (e.g. `curl -H "X-Client-Id: external" -X POST .../api/control/acquire`) acquires control and can drive a move; state-changing calls from `imswitch` client-id return 423; reads (frames, `/api/stage/position`) still work from any client.
- [ ] Click "Take back": button returns orange; controls reappear; `imswitch` re-acquires ownership; external calls get 423.

### Smoke test
- [ ] Run `smoke_test.py` (microscope-api repo) against the running API as a final sanity check — all assertions pass.

## Notes / risks
- Camera params: `RemoteCameraManager.setParameter` pushes exposure/gain/blacklevel together to `/api/imaging/camera/parameters` (the API requires all three). Confirm units match the rig.
- MJPEG preview is 8-bit; raw 16-bit is available via `/api/imaging/camera/frame.tiff` and the API saves captures/scans to `STORAGE_PATH`.
- `RemoteCamera` has no reconnect/backoff; if the stream drops, live view freezes on the last frame until re-acquired. Add a reconnect loop if needed in production.
