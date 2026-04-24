"""基于响度与频谱的嘴型姿态分析。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from livestudio.services.audio_stream import AudioChunk

from ..models import MouthSyncControllerConfig
from .models import MouthPose


@dataclass(frozen=True, slots=True)
class AudioSpectrumFeatures:
    """单个音频块的基础声学特征。"""

    rms: float
    normalized_level: float
    low_ratio: float
    high_ratio: float


class SpectralMouthPoseAnalyzer:
    """使用响度、频段能量和轻微活性动态估计三参数嘴型。"""

    _LOW_BAND = (80.0, 500.0)
    _HIGH_BAND = (1800.0, 5000.0)

    def __init__(self, config: MouthSyncControllerConfig) -> None:
        self._config = config
        self._previous_level = 0.0
        self._phase = 0.0

    def analyze(self, chunk: AudioChunk) -> MouthPose:
        """分析音频块并返回目标嘴型。"""

        samples = self._to_mono_float32(chunk)
        if samples.size == 0:
            return self._closed_pose()

        features = self._calculate_features(samples, chunk.samplerate)
        if features.normalized_level <= 0.0:
            self._previous_level = 0.0
            return self._closed_pose()

        smile = self._calculate_smile(features)
        mouth_open = self._calculate_open(features.normalized_level, smile)
        mouth_x = self._calculate_x(features.normalized_level)
        self._previous_level = features.normalized_level
        return MouthPose(open=mouth_open, smile=smile, x=mouth_x).clamp()

    def _closed_pose(self) -> MouthPose:
        return MouthPose(
            open=self._config.closed_pose.open,
            smile=self._config.closed_pose.smile,
            x=self._config.closed_pose.x,
        ).clamp()

    def _calculate_features(
        self,
        samples: NDArray[np.float32],
        samplerate: int,
    ) -> AudioSpectrumFeatures:
        rms = float(np.sqrt(np.mean(np.square(samples))))
        normalized_level = self._normalize_level(rms)
        if normalized_level <= 0.0:
            return AudioSpectrumFeatures(
                rms=rms,
                normalized_level=0.0,
                low_ratio=0.0,
                high_ratio=0.0,
            )

        windowed = samples * np.hanning(samples.size)
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(samples.size, d=1.0 / samplerate)
        total_energy = float(np.sum(spectrum))
        if total_energy <= 0.0:
            return AudioSpectrumFeatures(
                rms=rms,
                normalized_level=normalized_level,
                low_ratio=0.0,
                high_ratio=0.0,
            )

        low_ratio = self._band_energy_ratio(
            freqs,
            spectrum,
            self._LOW_BAND,
            total_energy,
        )
        high_ratio = self._band_energy_ratio(
            freqs,
            spectrum,
            self._HIGH_BAND,
            total_energy,
        )
        return AudioSpectrumFeatures(
            rms=rms,
            normalized_level=normalized_level,
            low_ratio=low_ratio,
            high_ratio=high_ratio,
        )

    def _calculate_smile(self, features: AudioSpectrumFeatures) -> float:
        if self._config.mode == "loudness":
            return self._config.neutral_smile

        smile = self._config.neutral_smile
        smile += features.high_ratio * self._config.high_band_smile_gain
        smile -= features.low_ratio * self._config.low_band_smile_gain
        return max(self._config.min_smile, min(self._config.max_smile, smile))

    def _calculate_open(self, normalized_level: float, smile: float) -> float:
        raw_open = self._config.open_min + normalized_level * (
            self._config.open_max - self._config.open_min
        )
        if smile > self._config.neutral_smile:
            raw_open -= (
                smile - self._config.neutral_smile
            ) * self._config.smile_open_compensation
        elif smile < self._config.neutral_smile:
            raw_open += (
                self._config.neutral_smile - smile
            ) * self._config.low_smile_open_boost
        return max(0.0, min(1.0, raw_open))

    def _calculate_x(self, normalized_level: float) -> float:
        if not self._config.x_enabled:
            return self._config.closed_pose.x

        level_delta = normalized_level - self._previous_level
        self._phase = math.fmod(self._phase + 0.37, math.tau)
        activity = math.sin(self._phase) * normalized_level * self._config.x_max_offset
        activity += level_delta * self._config.x_activity_gain
        return max(-self._config.x_max_offset, min(self._config.x_max_offset, activity))

    def _normalize_level(self, rms: float) -> float:
        if rms <= self._config.noise_floor:
            return 0.0
        normalized = (rms - self._config.noise_floor) / (
            self._config.voice_ceiling - self._config.noise_floor
        )
        return min(1.0, max(0.0, normalized))

    @staticmethod
    def _to_mono_float32(chunk: AudioChunk) -> NDArray[np.float32]:
        samples = np.asarray(chunk.data, dtype=np.float32)
        if samples.size == 0:
            return np.asarray([], dtype=np.float32)
        if samples.ndim == 1:
            return samples.reshape(-1)
        return np.mean(samples, axis=1, dtype=np.float32).reshape(-1)

    @staticmethod
    def _band_energy_ratio(
        freqs: NDArray[np.floating[Any]],
        spectrum: NDArray[np.floating[Any]],
        band: tuple[float, float],
        total_energy: float,
    ) -> float:
        lower, upper = band
        mask = (freqs >= lower) & (freqs < upper)
        if not np.any(mask):
            return 0.0
        return float(np.sum(spectrum[mask]) / total_energy)
