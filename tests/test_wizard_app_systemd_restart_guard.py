"""The managed Wizard App runtime must reject direct systemd restarts."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STARTER_PATH = ROOT / "hermesui" / "installer" / "systemd-start-owned.py"


def _load_starter():
    spec = importlib.util.spec_from_file_location("wizard_app_systemd_start_owned", STARTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_managed_runtime_refuses_direct_manual_stop_and_restart():
    starter = _load_starter()

    command = starter.build_command(
        "systemd-run",
        "hermesui.service",
        ROOT,
        Path.home(),
        8797,
    )

    assert command.count("--property=RefuseManualStop=yes") == 1
    assert "--property=Restart=on-failure" in command
    assert "--collect" in command
