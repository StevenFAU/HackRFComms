"""
HackRFComms — Scanner Service
Wraps scanner.sweep() for async use. Does NOT modify scanner.py.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import scanner as _scanner


async def run_sweep(
    start_mhz: int,
    end_mhz: int,
    fine: bool = False,
    num_sweeps: int = 1,
) -> list[dict]:
    """
    Run a single hackrf_sweep pass. Returns list of {freq, power} dicts.
    Runs blocking scanner.sweep() in a thread so the event loop stays free.
    """
    bin_width = 100_000 if fine else 1_000_000
    results: list[tuple[float, float]] = await asyncio.to_thread(
        _scanner.sweep,
        start_mhz,
        end_mhz,
        bin_width,
        num_sweeps,
    )
    return [{"freq": freq, "power": power} for freq, power in results]
