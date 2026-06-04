"""Helper for running ImSwitch as a CLIENT of microscope_api (Architecture A).

microscope_api becomes the sole hardware owner; ImSwitch drives it over HTTP via a
ClientDevice proxy and shows live view through the RemoteCameraManager detector.

Enable the client path by setting env ``MICROSCOPE_API_CLIENT=1`` and selecting the
``btig_uc2_remote_imswitch`` setup (WidefieldCamera -> RemoteCameraManager).

ON-RIG: this module is verified on the physical microscope with ImSwitch running. The
TODOs below are the rig-specific wiring (local deck geometry, light names, API launch
mechanism) that must be completed/validated on the rig.
"""
import os
import time

import requests


def use_api_client() -> bool:
    """True when ImSwitch should run as a microscope_api client."""
    return os.environ.get("MICROSCOPE_API_CLIENT", "").strip() not in ("", "0", "false", "False")


def start_api(port: int = 9523, wait_s: float = 60.0) -> str:
    """Start microscope_api so it owns the hardware, and wait until it is healthy.

    Returns the base URL. Two launch options (pick per deployment):
      (a) in-process via microscope_api's start_server_in_thread (this function), OR
      (b) a separate process started by the launcher before ImSwitch (preferred if you
          want fully independent lifecycles) -- in that case skip this and just connect.

    ON-RIG TODO: microscope_api's start_server_in_thread lives in its repo-root main.py.
    Ensure that module is importable (microscope-api repo root on PYTHONPATH) or refactor
    start_server_in_thread into the importable ``microscope_api`` package.
    """
    base = f"http://127.0.0.1:{port}"
    try:
        import main as microscope_api_main  # microscope-api repo root must be importable
        microscope_api_main.start_server_in_thread(port=port)
    except Exception as e:  # pragma: no cover - rig-only path
        # If already running as a separate process this is fine; just wait for health.
        import loguru
        loguru.logger.warning(f"Could not start microscope_api in-process ({e!r}); "
                              f"assuming it runs as a separate process.")
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            if requests.get(base + "/health", timeout=1.0).status_code == 200:
                return base
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"microscope_api not healthy at {base} within {wait_s}s")


def build_client_device(base_url: str, exp_config, client_id: str = "imswitch"):
    """Build the ClientDevice proxy and acquire control. ImSwitch holds control during
    setup; it is released on operator hand-over to the external (microfluidics) client.

    Returns (client, device).
    """
    from imswitch.imcontrol.model.microscope_api_client import MicroscopeApiClient
    from imswitch.imcontrol.model.clientdevice import ClientDevice

    client = MicroscopeApiClient(base_url=base_url, client_id=client_id)
    try:
        client.acquire()
    except Exception as e:  # pragma: no cover - rig-only path
        import loguru
        loguru.logger.warning(f"Could not acquire control on startup: {e!r}")

    deck_manager = build_local_deck_manager(exp_config)
    lights = lights_from_config(exp_config)
    device = ClientDevice(client, deck_manager=deck_manager, lights=lights)
    return client, device


def set_external_control(client, handover: bool):
    """Operator hand-over (B4 logic). On hand-over, ImSwitch releases control so the
    external (microfluidics) client can acquire it; on take-back, ImSwitch re-acquires.
    The caller (widget handler) is responsible for enabling/disabling operator controls.
    Returns the API's reported owner dict.

    ON-RIG: wire a 'Hand over / Take back control' toggle in LabmaiteDeckWidget to this.
    """
    if handover:
        return client.release()
    return client.acquire()


def build_local_deck_manager(exp_config):
    """Build a LOCAL DeckManager (pure geometry, no hardware) from the experiment config,
    so deck/well coordinate math works client-side without round-trips.

    ON-RIG TODO: instantiate locai_app.impl.deck.sd_deck_manager.DeckManager from
    exp_config and call load_labwares(exp_config.slots). Returns None for now (the
    controller falls back to API geometry endpoints / disables deck rendering).
    """
    return None


def lights_from_config(exp_config):
    """Return [(key, readable_name, value_range_max), ...] for the ClientDevice light
    proxies, derived from the device/experiment config light sources.

    ON-RIG TODO: read the device config's light sources (led/led_matrix/laser_slot_1/2)
    and their readable_name + value_range_max so the widget light sliders map correctly.
    """
    return []
