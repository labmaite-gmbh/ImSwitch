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
1. Ensure `microscope_api` is importable and configured to own the hardware standalone
   (its own `MicroscopeDevice()` from `labmaite_config.json`, `DEBUG=2` real device).
   Confirm `start_server_in_thread` is reachable — either put the microscope-api repo
   root on `PYTHONPATH` (so `import main` works) or refactor `start_server_in_thread`
   into the importable `microscope_api` package (preferred).
2. `set MICROSCOPE_API_CLIENT=1` in the environment that launches ImSwitch.
3. Select the **`btig_uc2_remote_imswitch`** setup in the ImSwitch setup picker.
4. Launch ImSwitch. `init_device` starts the API, acquires control as `imswitch`, and
   returns the `ClientDevice` proxy; the `RemoteCameraManager` shows live view.

## Remaining wiring (do on the rig)

### 1. Local deck geometry + light names (`imswitch_api_integration.py` TODOs)
- `build_local_deck_manager(exp_config)`: instantiate `locai_app.impl.deck.sd_deck_manager.DeckManager` from `exp_config` and `load_labwares(exp_config.slots)` so deck/well math works client-side (no round-trips). Until done, deck rendering that relies on `device.stage.deck_manager` will be limited.
- `lights_from_config(exp_config)`: return `[(key, readable_name, value_range_max), ...]` from the device config light sources so the widget light sliders map to the right names/ranges.

### 2. Redirect scan / autofocus / well-preview to the API (the key B3 follow-up)
Under client mode, do **not** run a local `ExperimentContext` against the proxy (it would
drive the hardware over per-call HTTP in tight loops). Instead, in the controller flows
that currently call `self.exp_context.run_experiment()` / the local `Autofocus` /
`WellPreviewer`, branch on `use_api_client()` and call the API:
- scan iteration → `self.api_client` POST `/api/imaging/scan/iteration` (see `MicroscopeApiClient`; add a `run_scan(...)` method mapping to it).
- autofocus → `/api/imaging/camera/point_autofocus`.
- well preview → `/api/imaging/camera/take_well`.
Progress/ताcompletion arrives via the existing **webhooks** (microfluidics + ImSwitch can both subscribe). Keep the local path for non-client mode.

### 3. Handover toggle in `LabmaiteDeckWidget` (B4)
Add a "Hand over to external control" / "Take back control" button. Wire its handler to:
```python
from imswitch.imcontrol.model.imswitch_api_integration import set_external_control
set_external_control(self.api_client, handover=True)   # release -> external can acquire
# ... and disable operator controls while handed over;
set_external_control(self.api_client, handover=False)  # re-acquire on take-back
```
Reflect `self.api_client.owner()` in the UI. Disable jog/scan/light controls when not the owner.

## Verification checklist (on the rig)
- [ ] API boots and owns the camera+stage (no `gxipy`/serial double-open errors).
- [ ] ImSwitch live view (napari) shows frames via `RemoteCameraManager` ← `/api/imaging/camera/stream`.
- [ ] Operator jog/move/home/park/stop, light intensity, and single snapshot work through the proxy (stage actually moves; frame updates).
- [ ] A scan / autofocus / well-preview runs **server-side** (after wiring item 2) with progress via webhooks; output lands under `STORAGE_PATH`.
- [ ] Hand-over: operator clicks "Hand over"; ImSwitch controls disable; a separate client (`curl`/microfluidics) with its `X-Client-Id` acquires control and drives a move; state-changing calls from the wrong id get 423; reads (frames/status) still work; "Take back" reclaims.
- [ ] Run `smoke_part1.py` (microscope-api) against the running API as a sanity check.

## Notes / risks
- Camera params: `RemoteCameraManager.setParameter` pushes exposure/gain/blacklevel together to `/api/imaging/camera/parameters` (the API requires all three). Confirm units match the rig.
- MJPEG preview is 8-bit; raw 16-bit is available via `/api/imaging/camera/frame.tiff` and the API saves captures/scans to `STORAGE_PATH`.
- `RemoteCamera` has no reconnect/backoff; if the stream drops, live view freezes on the last frame until re-acquired. Add a reconnect loop if needed in production.
