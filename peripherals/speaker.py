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
Supports sensorlib (on Raven devices) and, in simulator mode, simpleaudio or
the Windows-only winsound standard-library fallback.
"""

# Standard library imports
import io
import threading
import time
import wave
from typing import Callable, Optional

# Third-party imports - make simpleaudio optional
try:
    import simpleaudio as sa

    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    SIMPLEAUDIO_AVAILABLE = False
    sa = None

# winsound is a Windows-only standard-library fallback for simulator playback.
# It lets audio work on Windows without simpleaudio, which needs a C++ compiler
# to build and often fails to install there.
try:
    import winsound

    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False
    winsound = None

# True when any simulator-mode audio backend is usable (device mode uses
# sensorlib instead and doesn't depend on either of these).
SIMULATOR_AUDIO_AVAILABLE = SIMPLEAUDIO_AVAILABLE or WINSOUND_AVAILABLE

from PySide6.QtCore import QObject, Signal

# Local imports
from ..helpers.logger import get_logger
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("Speaker")


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    """Best-effort WAV duration in seconds; 0.0 if wav_bytes isn't a valid WAV."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / float(rate) if rate else 0.0
    except (wave.Error, EOFError, ValueError):
        return 0.0


class _PlaybackSignalEmitter(QObject):
    """
    Emits `finished` from a background playback thread. Qt marshals the
    connected slot onto the thread that owns this emitter (the thread that
    called play_audio), so `on_finished` callbacks never run off that thread.
    """

    finished = Signal()


class Speaker:
    """Speaker class to handle asynchronous playback of WAV audio bytes."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize speaker with optional app_id and app_key for entitlement verification."""
        self._play_obj = None
        # Tracks whether a winsound clip is currently playing, so stop_audio
        # only purges when there is something to stop (winsound has no handle).
        self._winsound_playing = False
        self._callback: Optional[Callable[[], None]] = None
        # Keeps each playback's signal emitter alive until its queued
        # cross-thread `finished` signal is actually delivered. Without this,
        # the emitter (and its underlying QObject) can be garbage-collected
        # as soon as the background thread exits, before Qt's event loop
        # processes the queued signal — silently dropping on_finished or
        # crashing.
        self._pending_emitters: list = []

        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.SPEAKER
        )
        if not self.sensorlib_client:
            if SIMPLEAUDIO_AVAILABLE:
                log.info(
                    "Speaker: Using simulator mode (simpleaudio)",
                    extra={"console": True},
                )
            elif WINSOUND_AVAILABLE:
                log.info(
                    "Speaker: Using simulator mode (winsound - Windows fallback)",
                    extra={"console": True},
                )
            else:
                log.warning(
                    "Speaker: no simulator audio backend available. Audio playback will not "
                    "work in simulator mode. Install with: pip install -e .[audio-simulator] "
                    "(on Windows the built-in winsound fallback is used automatically).",
                    extra={"console": True},
                )

    def play_audio(
        self, wav_bytes: bytes, on_finished: Optional[Callable[[], None]] = None
    ) -> None:
        """Plays WAV audio data asynchronously on a separate thread."""
        emitter = _PlaybackSignalEmitter()
        self._pending_emitters.append(emitter)

        def _on_playback_finished() -> None:
            try:
                self._pending_emitters.remove(emitter)
            except ValueError:
                pass
            if on_finished:
                on_finished()

        emitter.finished.connect(_on_playback_finished)

        if not isinstance(wav_bytes, bytes) or not wav_bytes:
            log.error(
                f"play_audio: invalid wav_bytes (type={type(wav_bytes).__name__})"
            )
            emitter.finished.emit()
            return

        self._callback = on_finished

        if self.sensorlib_client:

            def _play_sensorlib() -> None:
                try:
                    started_at = time.monotonic()
                    success = self.sensorlib_client.play_speaker(wav_bytes)
                    if not success:
                        log.error("Failed to play audio via sensorlib")
                        return
                    log.info("Audio playback started (Raven device - sensorlib)")
                    # play_speaker only confirms the daemon accepted the
                    # command, not that playback has finished — wait out the
                    # remainder of the clip's duration so on_finished fires
                    # near actual completion instead of at playback start.
                    remaining = _wav_duration_seconds(wav_bytes) - (
                        time.monotonic() - started_at
                    )
                    if remaining > 0:
                        time.sleep(remaining)
                    log.info("Audio playback finished (Raven device - sensorlib)")
                except Exception as e:
                    log.error(
                        f"Error during audio playback via sensorlib: {e}", exc_info=True
                    )
                finally:
                    emitter.finished.emit()

            thread = threading.Thread(target=_play_sensorlib, daemon=True)
            thread.start()
            log.info("Started audio playback thread (Raven device).")
        else:
            # Simulator mode: no sensorlib. Pick an available audio backend,
            # preferring simpleaudio and falling back to winsound on Windows.
            if not SIMULATOR_AUDIO_AVAILABLE:
                log.warning(
                    "Cannot play audio: no simulator audio backend available. "
                    "Install with: pip install -e .[audio-simulator] or use a Raven device.",
                    extra={"console": True},
                )
                emitter.finished.emit()
                return

            backend = (
                self._play_simpleaudio if SIMPLEAUDIO_AVAILABLE else self._play_winsound
            )

            def _play() -> None:
                try:
                    backend(wav_bytes)
                except Exception as e:
                    log.error(f"Error during audio playback: {e}", exc_info=True)
                finally:
                    emitter.finished.emit()

            thread = threading.Thread(target=_play, daemon=True)
            thread.start()
            log.info("Started audio playback thread.")

    def _play_simpleaudio(self, wav_bytes: bytes) -> None:
        """Blocking playback via simpleaudio; returns when the clip finishes."""
        wave_obj = sa.WaveObject.from_wave_read(wave.open(io.BytesIO(wav_bytes), "rb"))
        self._play_obj = wave_obj.play()
        log.info("Audio playing")
        self._play_obj.wait_done()
        log.info("Audio playback finished.")

    def _play_winsound(self, wav_bytes: bytes) -> None:
        """Blocking playback via the Windows-only winsound fallback.

        Without SND_ASYNC, PlaySound blocks until playback finishes, so this
        runs on the playback thread and returns when the clip is done (matching
        simpleaudio's wait_done). SND_MEMORY plays the WAV image directly from
        bytes; SND_NODEFAULT suppresses the system "ding" if the data is bad.
        """
        self._winsound_playing = True
        try:
            log.info("Audio playing")
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            log.info("Audio playback finished.")
        finally:
            self._winsound_playing = False

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
            if not SIMULATOR_AUDIO_AVAILABLE:
                log.warning(
                    "Cannot stop audio: no simulator audio backend available",
                    extra={"console": True},
                )
                return

            if SIMPLEAUDIO_AVAILABLE:
                if self._play_obj and self._play_obj.is_playing():
                    try:
                        self._play_obj.stop()
                        log.info("Audio stopped.")
                    except Exception as e:
                        log.error(f"Error stopping audio: {e}", exc_info=True)
            elif WINSOUND_AVAILABLE and self._winsound_playing:
                try:
                    # PlaySound(None, SND_PURGE) stops the in-progress SND_MEMORY
                    # clip, which unblocks the playback thread's PlaySound call.
                    winsound.PlaySound(None, winsound.SND_PURGE)
                    log.info("Audio stopped.")
                except Exception as e:
                    log.error(f"Error stopping audio: {e}", exc_info=True)
