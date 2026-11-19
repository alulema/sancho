"""Presence with hysteresis (T6): turns per-frame detections into one entry and one exit.

Simple tracking for E0: the studio has one presence at a time. Somebody enters when
there are detections for at least `enter_ms` (with at least `min_hits` frames and no
gap longer than `max_gap_ms`); they leave after `leave_ms` without any detection, so a
few missed frames while walking do not end the visit.

Pure logic, no camera or bus: times come from the caller (monotonic seconds for the
rules, UTC timestamps for the messages).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Detection:
    score: float
    bbox: tuple[float, float, float, float]  # x, y, w, h, normalized to the frame


@dataclass(frozen=True)
class Entered:
    track_id: str
    first_seen_ts: datetime  # capture of the first frame with a detection
    frame_ts: datetime  # capture of the frame that confirmed the entry
    detection: Detection  # the best detection of that frame


@dataclass(frozen=True)
class Left:
    track_id: str
    duration_s: float  # from the first to the last frame with a detection


@dataclass
class _Candidate:
    first_t: float
    first_ts: datetime
    last_t: float
    hits: int


@dataclass
class _Present:
    track_id: str
    first_t: float
    last_t: float


class Presence:
    def __init__(self, *, enter_ms: int = 500, min_hits: int = 2, max_gap_ms: int = 1000,
                 leave_ms: int = 3000, new_track_id=lambda: uuid.uuid4().hex[:8]):  # fmt: skip
        if min(enter_ms, max_gap_ms, leave_ms) < 0 or min_hits < 1:
            raise ValueError("times must be >= 0 and min_hits >= 1")
        self.enter_s, self.min_hits = enter_ms / 1000, min_hits
        self.max_gap_s, self.leave_s = max_gap_ms / 1000, leave_ms / 1000
        self._new_track_id = new_track_id
        self._state: _Candidate | _Present | None = None

    @property
    def present(self) -> bool:
        return isinstance(self._state, _Present)

    def update(self, t: float, ts: datetime, detections: list[Detection]) -> Entered | Left | None:
        """One frame: `t` monotonic seconds and `ts` UTC, both of its capture."""
        state = self._state
        if detections:
            best = max(detections, key=lambda d: d.score)
            if state is None:
                state = self._state = _Candidate(t, ts, t, 0)
            if isinstance(state, _Candidate):
                if t - state.last_t > self.max_gap_s:  # too long a gap: start again
                    state = self._state = _Candidate(t, ts, t, 0)
                state.hits += 1
                state.last_t = t
                if state.hits >= self.min_hits and t - state.first_t >= self.enter_s:
                    track = self._new_track_id()
                    self._state = _Present(track, state.first_t, t)
                    return Entered(track, state.first_ts, ts, best)
                return None
            state.last_t = t
            return None
        if isinstance(state, _Candidate) and t - state.last_t > self.max_gap_s:
            self._state = None
        elif isinstance(state, _Present) and t - state.last_t >= self.leave_s:
            self._state = None
            return Left(state.track_id, round(state.last_t - state.first_t, 3))
        return None

    def pause(self, seconds: float) -> None:
        """Time without looking (detection paused while speaking) is not absence: the
        pending timers move forward by `seconds`, so nobody leaves or expires for it."""
        state = self._state
        if state is not None and seconds > 0:
            state.last_t += seconds

    def close(self) -> Left | None:
        """On shutdown: whoever is present leaves, so no entry stays open."""
        state, self._state = self._state, None
        if isinstance(state, _Present):
            return Left(state.track_id, round(state.last_t - state.first_t, 3))
        return None
