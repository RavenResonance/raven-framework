# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================

"""
Speaker sensor for Raven Framework.

This module provides speaker functionality for asynchronous playback of WAV audio.
Supports both sensorlib (on Raven devices) and simpleaudio (in simulator mode).
"""

# Standard library imports
import io
import threading
import wave
from typing import Callable, Optional

# Third-party imports - make simpleaudio optional
try:
    import simpleaudio as sa

    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    SIMPLEAUDIO_AVAILABLE = False
    sa = None

# Local imports
from ..helpers.logger import get_logger
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("Speaker")


class Speaker:
    """Speaker class to handle asynchronous playback of WAV audio bytes."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize speaker with optional app_id and app_key for entitlement verification."""
        self._play_obj = None
        self._callback: Optional[Callable[[], None]] = None

        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.SPEAKER
        )
        if not self.sensorlib_client:
            if SIMPLEAUDIO_AVAILABLE:
                log.info(
                    "Speaker: Using simulator mode (simpleaudio)",
                    extra={"console": True},
                )
            else:
                log.warning(
                    "Speaker: simpleaudio not available. Audio playback will not work in simulator mode. "
                    "Install with: pip install -e .[audio-simulator]",
                    extra={"console": True},
                )

    def play_audio(
        self, wav_bytes: bytes, on_finished: Optional[Callable[[], None]] = None
    ) -> None:
        """Plays WAV audio data asynchronously on a separate thread."""
        if self.sensorlib_client:

            def _play_sensorlib() -> None:
                try:
                    success = self.sensorlib_client.play_speaker(wav_bytes)
                    if success:
                        log.info("Audio playback started (Raven device - sensorlib)")
                        if on_finished:
                            on_finished()
                    else:
                        log.error("Failed to play audio via sensorlib")
                except Exception as e:
                    log.error(
                        f"Error during audio playback via sensorlib: {e}", exc_info=True
                    )

            self._callback = on_finished
            thread = threading.Thread(target=_play_sensorlib, daemon=False)
            thread.start()
            log.info("Started audio playback thread (Raven device).")
        else:
            # Check if simpleaudio is available
            if not SIMPLEAUDIO_AVAILABLE:
                log.warning(
                    "Cannot play audio: simpleaudio is not available. "
                    "Install with: pip install -e .[audio-simulator] or use a Raven device.",
                    extra={"console": True},
                )
                if on_finished:
                    on_finished()
                return

            def _play() -> None:
                try:
                    wave_obj = sa.WaveObject.from_wave_read(
                        wave.open(io.BytesIO(wav_bytes), "rb")
                    )
                    self._play_obj = wave_obj.play()
                    log.info("Audio playing")
                    self._play_obj.wait_done()
                    log.info("Audio playback finished.")
                    if on_finished:
                        on_finished()
                except Exception as e:
                    log.error(f"Error during audio playback: {e}", exc_info=True)
                    if on_finished:
                        on_finished()

            self._callback = on_finished
            thread = threading.Thread(target=_play, daemon=False)
            thread.start()
            log.info("Started audio playback thread.")

    def stop_audio(self) -> None:
        """Stop currently playing audio if any."""
        if self.sensorlib_client:
            try:
                success = self.sensorlib_client.stop_speaker()
                if success:
                    log.info("Audio stopped (Raven device - sensorlib)")
                else:
                    log.warning("Failed to stop audio via sensorlib")
            except Exception as e:
                log.error(f"Error stopping audio via sensorlib: {e}", exc_info=True)
        else:
            if not SIMPLEAUDIO_AVAILABLE:
                log.warning(
                    "Cannot stop audio: simpleaudio is not available",
                    extra={"console": True},
                )
                return

            if self._play_obj and self._play_obj.is_playing():
                try:
                    self._play_obj.stop()
                    log.info("Audio stopped.")
                except Exception as e:
                    log.error(f"Error stopping audio: {e}", exc_info=True)
