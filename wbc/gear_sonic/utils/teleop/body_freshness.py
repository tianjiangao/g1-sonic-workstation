"""Strict 24-joint freshness gate. Device clocks are compared only to themselves."""
from collections import Counter
from dataclasses import asdict, dataclass
import math
from numbers import Integral
import os
import time


@dataclass(frozen=True)
class FreshnessConfig:
    stale_s: float = .250
    max_skew_s: float = .050
    quaternion_norm_tolerance: float = .1

    def __post_init__(self):
        if not (math.isfinite(self.stale_s) and 0 < self.stale_s <= 1):
            raise ValueError('Body stale threshold must be finite and in (0, 1] seconds')
        if not (math.isfinite(self.max_skew_s) and 0 <= self.max_skew_s <= self.stale_s):
            raise ValueError('Joint timestamp skew must be finite and between 0 and stale threshold')
        if not 0 < self.quaternion_norm_tolerance <= .1:
            raise ValueError('Quaternion norm tolerance must be in (0, .1]')

    @classmethod
    def from_env(cls):
        return cls(stale_s=float(os.environ.get('SONIC_BODY_STALE_MS', '250')) / 1000,
                   max_skew_s=float(os.environ.get('SONIC_BODY_MAX_SKEW_MS', '50')) / 1000)


def valid_body_pose(pose, tolerance=.1):
    try:
        return len(pose) == 24 and all(
            len(row) == 7 and all(math.isfinite(float(v)) for v in row)
            and abs(math.sqrt(sum(float(v)**2 for v in row[3:])) - 1) <= tolerance
            for row in pose)
    except (ValueError, TypeError, OverflowError):
        return False


def read_body_snapshot(sdk):
    """Separate SDK getters are not atomic: bracket pose with identical timestamp vectors."""
    if not sdk.is_body_data_available():
        return None, None, False
    for _ in range(3):
        before = tuple(sdk.get_body_joints_timestamp())
        pose = sdk.get_body_joints_pose()
        after = tuple(sdk.get_body_joints_timestamp())
        if before == after and sdk.is_body_data_available():
            return pose, after, True
    raise ValueError('unstable_snapshot: timestamps changed across SDK getters')


class BodyFreshnessGate:
    def __init__(self, config=None):
        self.config = config or FreshnessConfig.from_env()
        self.reason = 'warming_up'
        self._previous = self._committed = self._floor = None
        self._changed_at = None
        self._latest = None
        self._raw_previous = self._first_raw = self._last_raw = None
        self._changes = [0] * 24
        self._backwards = [0] * 24
        self._missing = set()
        self._reasons = Counter()
        self._polls = self._valid_polls = self._frames = 0
        self._last_frame_at = None
        self._max_gap = 0.0
        self._max_skew = 0
        self._last_skew = None

    def invalidate(self, reason, now=None):
        if self._committed is not None:
            self._floor = self._committed
        self._latest = None
        self._previous = self._committed = self._changed_at = None
        self.reason = reason
        self._reasons[reason] += 1

    def _observe_timestamps(self, t):
        self._last_raw = t
        if self._first_raw is None:
            self._first_raw = t
        for i, v in enumerate(t):
            if v <= 0:
                self._missing.add(i)
            if self._raw_previous is not None:
                self._changes[i] += int(v > self._raw_previous[i])
                self._backwards[i] += int(v < self._raw_previous[i])
        self._raw_previous = t

    def update(self, pose, timestamps, available=True, now=None):
        now = time.monotonic() if now is None else now
        self._polls += 1
        if not available:
            self.invalidate('body_unavailable', now)
            return None
        try:
            if len(timestamps) != 24 or any(isinstance(t, bool) or not isinstance(t, Integral) for t in timestamps):
                raise ValueError()
            t = tuple(int(v) for v in timestamps)
            if any(v > 2**63 - 1 for v in t):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            self.invalidate('invalid_joint_timestamp_shape_or_type', now)
            return None
        self._observe_timestamps(t)
        missing = [i for i, v in enumerate(t) if v <= 0]
        if missing:
            self.invalidate('missing_joint_timestamps:' + ','.join(map(str, missing)), now)
            return None
        if not valid_body_pose(pose, self.config.quaternion_norm_tolerance):
            self.invalidate('invalid_body_pose_or_quaternion', now)
            return None
        skew = max(t) - min(t)
        self._last_skew = skew
        self._max_skew = max(self._max_skew, skew)
        if skew > self.config.max_skew_s * 1e9:
            self.invalidate('joint_timestamp_skew', now)
            return None
        self._valid_polls += 1
        if self._previous is None:
            if self._floor is not None and any(v <= p for v, p in zip(t, self._floor)):
                self.reason = 'awaiting_new_all_joint_frame_after_fault'
                return None
            self._previous = self._committed = t
            self._changed_at = [now] * 24
            self.reason = 'warming_up'
            return None
        backward = [i for i, (v, p) in enumerate(zip(t, self._previous)) if v < p]
        if backward:
            self.invalidate('joint_timestamp_backward:' + ','.join(map(str, backward)), now)
            return None
        for i, (v, p) in enumerate(zip(t, self._previous)):
            if v > p:
                self._changed_at[i] = now
        self._previous = t
        stale = [i for i, at in enumerate(self._changed_at) if now - at >= self.config.stale_s]
        if stale:
            self.invalidate('stale_joints:' + ','.join(map(str, stale)), now)
            return None
        if not all(v > p for v, p in zip(t, self._committed)):
            self.reason = 'awaiting_complete_joint_update'
            return None
        # Stream resampling uses host monotonic time, never device time vs wall clock.
        dt = now - self._last_frame_at if self._last_frame_at is not None else 0.0
        if dt > 0:
            self._max_gap = max(self._max_gap, dt)
        self._last_frame_at = now
        self._committed = t
        self._floor = None
        self._frames += 1
        import numpy as np
        self._latest = {
            'body_poses_np': np.array(pose, dtype=np.float64, copy=True),
            'joint_timestamps_ns': t,
            'joint_received_monotonic': tuple(self._changed_at),
            'timestamp_ns': int(now * 1e9),
            'timestamp_monotonic': now,
            'timestamp_realtime': time.time(),
            'dt': dt,
            'fps': 1 / dt if dt > 0 else 0.0,
        }
        self.reason = 'ready'
        return self._latest

    def latest(self, now=None):
        now = time.monotonic() if now is None else now
        if self._latest is not None and now - self._latest['timestamp_monotonic'] >= self.config.stale_s:
            self.invalidate('stale_complete_frame', now)
        return self._latest

    def stats(self):
        return {
            'config': asdict(self.config), 'required_joint_indices': list(range(24)),
            'timestamp_source': 'all 24 per-joint SDK timestamps; no overall/head fallback',
            'receipt_clock': 'host time.monotonic', 'snapshots': self._polls,
            'valid_schema_snapshots': self._valid_polls,
            'schema_validity_ratio': self._valid_polls / self._polls if self._polls else 0,
            'accepted_frames': self._frames, 'reason': self.reason,
            'invalid_reasons': dict(self._reasons), 'missing_timestamp_indices': sorted(self._missing),
            'joint_first_timestamps_ns': self._first_raw, 'joint_last_timestamps_ns': self._last_raw,
            'joint_change_counts': self._changes.copy(), 'joint_backward_counts': self._backwards.copy(),
            'max_valid_vector_skew_ns': self._max_skew, 'last_valid_vector_skew_ns': self._last_skew,
            'max_accepted_frame_gap_s': self._max_gap,
        }
