#!/usr/bin/env python3
"""Receive-only PICO diagnostics. Never creates ZMQ/DDS or robot command publishers."""
import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import signal
import time

import numpy as np
import xrobotoolkit_sdk as sdk
from gear_sonic.utils.teleop.body_freshness import (
    BodyFreshnessGate, FreshnessConfig, read_body_snapshot, valid_body_pose,
)
from gear_sonic.utils.teleop.xrt_runtime import XrtSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--timeout', type=float, default=60, help='Retained SDK setup timeout; measurement runs even when freshness fails')
    parser.add_argument('--stale-ms', type=float, default=None)
    parser.add_argument('--max-skew-ms', type=float, default=None)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.seconds < 10:
        parser.error('Use at least 10 seconds for a live read-only acceptance probe')
    defaults = FreshnessConfig.from_env()
    config = FreshnessConfig(stale_s=args.stale_ms / 1000 if args.stale_ms is not None else defaults.stale_s,
                             max_skew_s=args.max_skew_ms / 1000 if args.max_skew_ms is not None else defaults.max_skew_s)
    gate = BodyFreshnessGate(config)
    session = XrtSession(sdk, timeout=args.timeout, freshness_config=config)
    result = {'status': 'FAIL', 'sdk_close_returned': False}
    errors = Counter()
    try:
        # Diagnostic open does not claim readiness: sample the full duration even if every frame is rejected.
        session.open()
        start = time.monotonic()
        deadline = start + args.seconds
        first_ready = None
        last_raw_timestamps = None
        last_raw_change_at = None
        raw_gaps = []
        raw_changes = position_changes = pose_valid_polls = body_available_polls = polls = 0
        overall_zero = 0
        last_pose = None
        longest_outage = 0.0
        outage_start = start
        faults_after_ready = Counter()
        while time.monotonic() < deadline:
            polls += 1
            try:
                pose, timestamps, available = read_body_snapshot(sdk)
                now = time.monotonic()
                body_available_polls += int(available)
                overall_zero += int(sdk.get_body_timestamp_ns() == 0)  # diagnostic only, never used by gate
                if available and valid_body_pose(pose):
                    pose_valid_polls += 1
                    p = np.asarray(pose)
                    if last_pose is not None and np.any(np.linalg.norm(p[:, :3] - last_pose[:, :3], axis=1) > .001):
                        position_changes += 1
                    last_pose = p.copy()
                if timestamps is not None:
                    t = tuple(timestamps)
                    if last_raw_timestamps is not None and t != last_raw_timestamps:
                        raw_changes += 1
                        if last_raw_change_at is not None:
                            raw_gaps.append(now - last_raw_change_at)
                        last_raw_change_at = now
                    last_raw_timestamps = t
                frame = gate.update(pose, timestamps, available=available, now=now)
                latest = gate.latest(now=now)
                if frame is not None and first_ready is None:
                    first_ready = now
                if latest is not None:
                    if outage_start is not None:
                        longest_outage = max(longest_outage, now - outage_start)
                        outage_start = None
                else:
                    if outage_start is None:
                        outage_start = now
                    if first_ready is not None:
                        faults_after_ready[gate.reason] += 1
            except Exception as exc:
                errors[type(exc).__name__ + ':' + str(exc)] += 1
                gate.invalidate('sdk_snapshot_error:' + str(exc))
                if outage_start is None:
                    outage_start = time.monotonic()
                if first_ready is not None:
                    faults_after_ready[gate.reason] += 1
            time.sleep(.002)
        end = time.monotonic()
        if outage_start is not None:
            longest_outage = max(longest_outage, end - outage_start)
        stats = gate.stats()
        passed = (stats['accepted_frames'] >= 2 and first_ready is not None
                  and not faults_after_ready and not errors and gate.latest(now=end) is not None)
        result.update(status='PASS' if passed else 'FAIL', seconds=end - start,
                      sdk_overall_timestamp_zero_polls=overall_zero, polls=polls,
                      body_available_polls=body_available_polls, pose_valid_polls=pose_valid_polls,
                      pose_validity_ratio=pose_valid_polls / polls if polls else 0,
                      raw_timestamp_vector_changes=raw_changes,
                      raw_timestamp_max_gap_s=max(raw_gaps) if raw_gaps else None,
                      raw_position_changes_over_1mm=position_changes,
                      longest_no_valid_full_body_interval_s=longest_outage,
                      first_valid_frame_after_s=first_ready - start if first_ready is not None else None,
                      faults_after_ready=dict(faults_after_ready), sdk_errors=dict(errors), freshness=stats,
                      note='Raw timestamp/pose changes are diagnostic observations, not accepted full-body frames. No head/max fallback.')
    finally:
        session.close()
        result['sdk_close_returned'] = True
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    def interrupt(*args):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        raise SystemExit(main())
    except (RuntimeError, TimeoutError) as exc:
        logging.error('%s', exc)
        raise SystemExit(2)
    except KeyboardInterrupt:
        raise SystemExit(130)
