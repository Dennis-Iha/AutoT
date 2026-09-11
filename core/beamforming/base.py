"""Multi-microphone beamforming interface.

AT's target hardware (Phase 29/30 of the product architecture) has 2-4 MEMS
microphones per earbud specifically to enable this. No real multi-mic
hardware exists yet (Phase 13+), so today this is validated entirely with
synthetic multi-channel signals - honest about that rather than assuming
results will transfer directly to a real microphone array's geometry,
coupling and self-noise characteristics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Beamformer(ABC):
    @abstractmethod
    def process(self, multi_channel: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        """Combine a multi-microphone buffer into one enhanced channel.

        Args:
            multi_channel: shape (n_samples, n_channels).

        Returns:
            shape (n_samples,) single-channel output.
        """
        raise NotImplementedError

    def reset(self) -> None:
        return None
