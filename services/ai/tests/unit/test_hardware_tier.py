"""Unit tests for app/services/hardware_tier.py — Fase 0."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.services import hardware_tier


@pytest.fixture(autouse=True)
def _clear_cache():
    hardware_tier._tier_cache = None
    yield
    hardware_tier._tier_cache = None


def test_manual_override_wins_over_detection():
    with patch.object(hardware_tier.settings, "HARDWARE_TIER", "B"), \
         patch.object(hardware_tier, "_auto_detect", side_effect=AssertionError("should not detect")):
        assert hardware_tier.detect_tier() == "B"


def test_detect_tier_is_cached():
    with patch.object(hardware_tier.settings, "HARDWARE_TIER", ""), \
         patch.object(hardware_tier, "_auto_detect", return_value="C") as mock_detect:
        assert hardware_tier.detect_tier() == "C"
        assert hardware_tier.detect_tier() == "C"
    mock_detect.assert_called_once()


@pytest.mark.parametrize("ram_gb,expected", [(40, "A"), (20, "B"), (10, "C"), (2, "D")])
def test_apple_silicon_tiers_by_ram(ram_gb, expected):
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=True), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=ram_gb):
        assert hardware_tier._auto_detect() == expected


@pytest.mark.parametrize("vram_gb,expected", [(16, "A"), (8, "B")])
def test_nvidia_gpu_tiers_by_vram(vram_gb, expected):
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=False), \
         patch.object(hardware_tier, "_detect_nvidia_vram_gb", return_value=vram_gb), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=64):
        assert hardware_tier._auto_detect() == expected


def test_no_gpu_falls_back_to_cpu_ram_tiers():
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=False), \
         patch.object(hardware_tier, "_detect_nvidia_vram_gb", return_value=None), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=12):
        assert hardware_tier._auto_detect() == "C"


def test_no_gpu_and_low_ram_is_tier_d():
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=False), \
         patch.object(hardware_tier, "_detect_nvidia_vram_gb", return_value=None), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=4):
        assert hardware_tier._auto_detect() == "D"


def test_gpu_below_tier_b_floor_falls_back_to_ram_check():
    # A GPU exists (e.g. 4GB) but is below the tier-B floor (6GB) — the
    # machine still has plenty of RAM, so it should land on tier C rather
    # than being discarded to tier D just because the GPU is small.
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=False), \
         patch.object(hardware_tier, "_detect_nvidia_vram_gb", return_value=4), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=32):
        assert hardware_tier._auto_detect() == "C"


def test_detect_nvidia_vram_gb_returns_none_without_nvidia_smi():
    with patch.object(hardware_tier.shutil, "which", return_value=None):
        assert hardware_tier._detect_nvidia_vram_gb() is None


def test_unknown_ram_is_treated_as_below_every_floor_not_a_crash():
    # None (detection truly failed) must not raise a TypeError from `None >= 8`
    # and must land on the safest default (tier D), same as "known to be low".
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=False), \
         patch.object(hardware_tier, "_detect_nvidia_vram_gb", return_value=None), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=None):
        assert hardware_tier._auto_detect() == "D"


def test_unknown_ram_on_apple_silicon_is_tier_d_not_a_crash():
    with patch.object(hardware_tier, "_is_apple_silicon", return_value=True), \
         patch.object(hardware_tier, "_detect_total_ram_gb", return_value=None):
        assert hardware_tier._auto_detect() == "D"


def test_detect_nvidia_vram_gb_survives_non_numeric_output():
    # Some vGPU/passthrough/degraded-driver setups print "[N/A]" instead of
    # an integer for memory.total — float() on that must not crash detect_tier.
    fake_result = MagicMock(stdout="[N/A]\n")
    with patch.object(hardware_tier.shutil, "which", return_value="/usr/bin/nvidia-smi"), \
         patch.object(hardware_tier.subprocess, "run", return_value=fake_result):
        assert hardware_tier._detect_nvidia_vram_gb() is None


def test_detect_total_ram_gb_returns_none_not_zero_when_undetectable():
    with patch.dict("sys.modules", {"psutil": None}), \
         patch.object(hardware_tier.os, "sysconf", side_effect=AttributeError("no sysconf")):
        assert hardware_tier._detect_total_ram_gb() is None


def test_detect_tier_reprobes_after_ttl_expires():
    with patch.object(hardware_tier.settings, "HARDWARE_TIER", ""), \
         patch.object(hardware_tier, "_auto_detect", return_value="C") as mock_detect, \
         patch.object(hardware_tier.time, "monotonic", side_effect=[0.0, 301.0]):
        assert hardware_tier.detect_tier() == "C"
        assert hardware_tier.detect_tier() == "C"
    assert mock_detect.call_count == 2
