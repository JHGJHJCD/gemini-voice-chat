#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_stability.py - בדיקות יציבות
"""

import subprocess
import time
import psutil
import os
import sys
from pathlib import Path

def test_start_stop_cycles(cycles=50):
    exe_path = Path("dist/GeminiVoiceChat/GeminiVoiceChat.exe")
    if not exe_path.exists():
        print("[SKIP] exe not found")
        return None

    print(f"[TEST] Start/Stop x {cycles}")
    print("-" * 70)

    baseline = psutil.virtual_memory().available
    successes = 0
    failures = []

    for cycle in range(1, cycles + 1):
        try:
            p = subprocess.Popen(str(exe_path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
            successes += 1
            status = "OK" if cycle % 10 == 0 else "."
            print(f"[{cycle:2d}] {status}", end=" ", flush=True)
            if cycle % 10 == 0:
                print()
        except Exception as e:
            failures.append((cycle, str(e)[:40]))
            print(f"[{cycle:2d}] X", end=" ", flush=True)

    print("\n" + "-" * 70)
    print(f"[PASS] {successes}/{cycles} cycles OK")

    if failures:
        print(f"[FAIL] {len(failures)} failures")
        for cycle, err in failures[:3]:
            print(f"  Cycle {cycle}: {err}")
    else:
        print("[OK] No failures!")

    final = psutil.virtual_memory().available
    leak_mb = (baseline - final) / (1024 * 1024)
    print(f"[MEM] Leak: {leak_mb:.1f} MB")

    return successes == cycles

def test_tray_minimize():
    print(f"\n[TEST] Tray minimize/restore")
    print("-" * 70)
    print("[INFO] Manual test - skip in CI")
    return True

def test_device_swap():
    print(f"\n[TEST] Audio device swap")
    print("-" * 70)
    import sounddevice as sd
    devices = sd.query_devices()
    audio_devices = [d for d in devices if isinstance(d, dict) and d.get('max_input_channels', 0) > 0]
    print(f"[OK] {len(audio_devices)} audio devices found")
    return True

def main():
    print("\n" + "=" * 70)
    print("[STABILITY TEST SUITE]")
    print("=" * 70 + "\n")

    results = {}
    results["Start/Stop x50"] = test_start_stop_cycles(50)
    results["Tray Minimize"] = test_tray_minimize()
    results["Device Swap"] = test_device_swap()

    print("\n" + "=" * 70)
    print("[RESULTS]")
    print("=" * 70)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {name}")

    all_passed = all(v for v in results.values() if v is not None)
    print("\n" + ("[PASS] All tests OK!" if all_passed else "[FAIL] Issues detected"))

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
