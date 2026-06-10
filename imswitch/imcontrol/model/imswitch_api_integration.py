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

    Returns the base URL. If an external server is already healthy on the port,
    connects to it immediately without attempting to embed a second instance.
    Otherwise starts an in-process server via microscope_api.server.start_server_in_thread.
    """
    base = f"http://127.0.0.1:{port}"
    # If an external server is already running (e.g. launched by launch_all.bat),
    # skip the embedded-server attempt entirely to avoid port-conflict shutdown errors.
    try:
        if requests.get(base + "/health", timeout=1.0).status_code == 200:
            return base
    except Exception:
        pass
    try:
        from microscope_api.server import start_server_in_thread
        start_server_in_thread(port=port)
    except Exception as e:  # pragma: no cover - rig-only path
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
    so deck/well coordinate math works client-side without round-trips."""
    import json
    device_json_path = os.environ.get("DEVICE_JSON_PATH")
    if not device_json_path:
        return None
    try:
        with open(device_json_path) as f:
            cfg_raw = json.load(f)
        from locai_app.impl.deck.sd_deck_manager import CfgDeckManager, DeckManager
        deck_cfg = CfgDeckManager.parse_obj(cfg_raw["components"]["deck_manager"])
        deck_manager = DeckManager(config=deck_cfg)
        deck_manager.initialize(None)  # loads deck schema; device=None is fine for geometry-only use
        deck_manager.load_labwares(exp_config.slots)
        return deck_manager
    except Exception as e:
        import loguru
        loguru.logger.warning(f"Could not build local DeckManager: {e!r}; deck rendering will be limited")
        return None


def lights_from_config(exp_config):
    """Return [(key, readable_name, value_range_max), ...] for the ClientDevice light
    proxies, derived from the device config light sources."""
    import json
    device_json_path = os.environ.get("DEVICE_JSON_PATH")
    if not device_json_path:
        return []
    try:
        with open(device_json_path) as f:
            cfg_raw = json.load(f)
        result = []
        light_raw = cfg_raw.get("components", {}).get("light")
        if light_raw:
            from hardware_api.impl.tl.model_impl.tl_upled import CfgTlUpLed
            cfg = CfgTlUpLed.parse_obj(light_raw)
            result.append(("led", cfg.readable_name, cfg.value_range_max))
        return result
    except Exception as e:
        import loguru
        loguru.logger.warning(f"Could not read lights from device config: {e!r}; light sliders may not map correctly")
        return []
