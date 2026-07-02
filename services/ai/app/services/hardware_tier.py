"""Hardware tier detection — docs/agent-memory-plan.md, Fase 0.

Determines which local-model tier (A/B/C/D) this machine can run, so
app.services.qvac_router can pick a local model for gradino 2/3 (chat fast
path / agent path) without a manual per-deploy config value.

Tiers (docs/agent-memory-plan.md § Tier hardware e assegnazione modelli):
  A - GPU >= 12GB VRAM (RTX 4070+) or Apple Silicon with >= 32GB unified memory
  B - GPU 6-8GB VRAM (RTX 3060/4060) or Apple Silicon with >= 16GB unified memory
  C - CPU-only, 8-16GB RAM
  D - below the tier-C floor (thin client — every local-tier task delegates to the server)
"""
import logging
import os
import platform
import shutil
import subprocess
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

VALID_TIERS = ("A", "B", "C", "D")

_APPLE_SILICON_TIER_A_RAM_GB = 32
_APPLE_SILICON_TIER_B_RAM_GB = 16
_GPU_TIER_A_VRAM_GB = 12
_GPU_TIER_B_VRAM_GB = 6
_TIER_C_MIN_RAM_GB = 8


def _detect_nvidia_vram_gb() -> Optional[float]:
    """Largest NVIDIA GPU's VRAM in GiB, or None (no GPU / driver / nvidia-smi)."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("nvidia-smi query failed: %s", exc)
        return None
    try:
        values = [float(line.strip()) for line in out.stdout.splitlines() if line.strip()]
    except ValueError as exc:
        # Some vGPU/passthrough/degraded-driver setups print a non-numeric
        # line (e.g. "[N/A]") for memory.total instead of an integer.
        logger.warning("nvidia-smi returned non-numeric memory.total: %s", exc)
        return None
    return max(values) / 1024 if values else None  # MiB -> GiB


def _detect_total_ram_gb() -> Optional[float]:
    """Total RAM in GiB, or None if it truly can't be determined."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        logger.warning("psutil not installed — falling back to os.sysconf for RAM detection")
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024 ** 3)
    except (ValueError, OSError, AttributeError) as exc:
        # os.sysconf doesn't exist on Windows; psutil (a hard dependency) is
        # the real detection path there, so this only fires if psutil is
        # somehow missing/broken on a POSIX-incompatible platform.
        logger.warning("Could not determine total RAM: %s", exc)
        return None


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _auto_detect() -> str:
    ram_gb = _detect_total_ram_gb()

    if _is_apple_silicon():
        # Unified memory: no discrete VRAM query, RAM is the usable ceiling.
        # ram_gb is None only if detection truly failed — treat that the
        # same as "below the tier-C floor" (thin client, safest default).
        if ram_gb is not None and ram_gb >= _APPLE_SILICON_TIER_A_RAM_GB:
            return "A"
        if ram_gb is not None and ram_gb >= _APPLE_SILICON_TIER_B_RAM_GB:
            return "B"
        return "C" if ram_gb is not None and ram_gb >= _TIER_C_MIN_RAM_GB else "D"

    vram_gb = _detect_nvidia_vram_gb()
    if vram_gb is not None:
        if vram_gb >= _GPU_TIER_A_VRAM_GB:
            return "A"
        if vram_gb >= _GPU_TIER_B_VRAM_GB:
            return "B"
        # A GPU exists but sits below tier B's floor — fall through to the
        # CPU-RAM check rather than assuming tier D outright.

    return "C" if ram_gb is not None and ram_gb >= _TIER_C_MIN_RAM_GB else "D"


# TTL (not a permanent cache): detection depends on nvidia-smi/driver state
# that can be transiently unavailable at cold-start (container just booted,
# GPU driver still initializing). A permanent cache would freeze that bad
# first reading for the process's entire lifetime; re-probing periodically
# lets it self-heal. Full cross-process persistence ("tier rilevato e
# persistito" per docs/agent-memory-plan.md) is a later-phase follow-up —
# this only fixes in-process staleness.
_TIER_CACHE_TTL_SECONDS = 300
_tier_cache: Optional[tuple] = None  # (tier, detected_at_monotonic)


def detect_tier() -> str:
    """Return this machine's hardware tier ('A'|'B'|'C'|'D').

    HARDWARE_TIER overrides detection entirely (pin a known dev machine or a
    CI runner where probing would be noisy). Auto-detected results are
    cached for _TIER_CACHE_TTL_SECONDS — long enough that nvidia-smi/psutil
    calls aren't repeated on every request, short enough that a transient
    detection failure doesn't stick around for the process's whole life.
    """
    global _tier_cache

    if settings.HARDWARE_TIER:
        logger.info("Hardware tier: %s (manual override)", settings.HARDWARE_TIER)
        return settings.HARDWARE_TIER

    now = time.monotonic()
    if _tier_cache is not None and (now - _tier_cache[1]) < _TIER_CACHE_TTL_SECONDS:
        return _tier_cache[0]

    tier = _auto_detect()
    logger.info("Hardware tier: %s (auto-detected)", tier)
    _tier_cache = (tier, now)
    return tier
