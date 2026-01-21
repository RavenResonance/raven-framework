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
Microphone sensor for Raven Framework.

This module provides microphone functionality for audio input, recording, and
level detection. Supports both sensorlib (on Raven devices) and Qt audio
(in simulator mode).
"""

# Standard library imports
import io
import json
import wave
from pathlib import Path
from typing import Optional, Tuple

# Third-party imports
import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioInput, QAudioSource, QMediaDevices

# Local imports
from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("Microphone")

# Load configuration
_config = load_config()

# Constants
AUDIO_READ_INTERVAL_MS = _config["peripherals"][
    "AUDIO_READ_INTERVAL_MS"
]  # Read audio data every 50ms


class Microphone(QObject):
    """
    Microphone class to handle audio input, recording, and level detection.

    Emits:
        levelChanged(float): Signal emitted when audio level changes (range 0.0 to 1.0).
    """

    levelChanged = Signal(float)

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize microphone with optional app_id and app_key for entitlement verification."""
        super().__init__()
        self.level: float = 0.0
        self.audio_input: Optional[QAudioInput] = None
        self.audio_buffer: QByteArray = QByteArray()
        self.buffer_device: Optional[QBuffer] = None
        self.audio_device: Optional[QIODevice] = None
        self.audio_source = None
        self.audio_format = None
        self.recording: bool = False
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self._read_audio_data)

        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.MICROPHONE
        )

        if not self.sensorlib_client:
            log.info("Microphone: Using simulator mode (Qt audio)")
            try:
                fmt = QAudioFormat()
                fmt.setSampleRate(44100)
                fmt.setChannelCount(1)
                fmt.setSampleFormat(QAudioFormat.Int16)

                device = QMediaDevices.defaultAudioInput()

                if device is None:
                    log.error("No audio input device available!")
                    return

                if not device.isFormatSupported(fmt):
                    log.warning(
                        "Requested audio format not supported, using default format."
                    )
                    fmt = QAudioFormat()
                    fmt.setSampleRate(44100)
                    fmt.setChannelCount(1)
                    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

                self.audio_source = QAudioSource(device, fmt)
                self.audio_format = fmt
                log.info("Audio source initialized successfully.")
            except Exception as e:
                log.error(f"Failed to set up audio input: {e}", exc_info=True)

    def start_recording(self) -> Optional[QIODevice]:
        """Start audio recording and return audio device or None."""
        if self.sensorlib_client:
            try:
                success = self.sensorlib_client.start_microphone()
                if success:
                    self.recording = True
                    return None
                return None
            except Exception as e:
                log.error(
                    f"Error starting microphone via sensorlib: {e}", exc_info=True
                )
                return None

        if self.recording:
            log.warning("Recording already in progress.")
            return self.audio_device
        try:
            self.audio_buffer.clear()
            self.buffer_device = QBuffer(self.audio_buffer)
            self.buffer_device.open(QIODevice.WriteOnly)

            if not hasattr(self, "audio_source") or self.audio_source is None:
                log.error("Audio source device is not initialized.")
                return None

            self.audio_device = self.audio_source.start()
            if self.audio_device is None:
                log.error("Failed to start audio device.")
                return None

            self.read_timer.start(AUDIO_READ_INTERVAL_MS)
            self.recording = True
            log.info("Recording started.")
            return self.audio_device
        except Exception as e:
            log.error(f"Failed to start recording: {e}", exc_info=True)

    def stop_recording(self) -> bytes:
        """Stop audio recording and return WAV formatted audio data."""
        if not self.recording:
            log.warning("No active recording to stop.")
            return b""

        if self.sensorlib_client:
            try:
                wav_bytes = self.sensorlib_client.stop_microphone()
                self.recording = False
                return wav_bytes
            except Exception as e:
                log.error(
                    f"Error stopping microphone via sensorlib: {e}", exc_info=True
                )
                self.recording = False
                return b""

        try:
            self.recording = False
            self.read_timer.stop()
            if hasattr(self, "audio_source") and self.audio_source is not None:
                self.audio_source.stop()
            if self.buffer_device is not None and self.buffer_device.isOpen():
                self.buffer_device.close()

            wav_bytes = self._create_wav_from_raw(bytes(self.audio_buffer.data()))
            if wav_bytes:
                log.info("Recording stopped and WAV created successfully.")
                return wav_bytes
            else:
                log.error("Recording stopped but WAV creation failed.")
                return b""
        except Exception as e:
            log.error(f"Error while stopping recording: {e}", exc_info=True)
            return b""

    ## Utils
    ## =====
    def _read_audio_data(self) -> None:
        """Read audio data from device and update level."""
        if not self.recording:
            return
        try:
            if self.audio_device is None:
                log.error("Audio device is None during read.")
                return

            data = self.audio_device.readAll()
            raw_bytes = data.data()
            if self.buffer_device is None:
                log.error("Buffer device is None during audio read.")
                return

            if len(raw_bytes) > 0:
                self.buffer_device.write(raw_bytes)

            samples = np.frombuffer(raw_bytes, dtype=np.int16)
            if samples.size > 0:
                peak = float(np.abs(samples).max()) / 32768.0
                self.level = min(max(float(peak), 0.0), 1.0)
                self.levelChanged.emit(self.level)
        except Exception as e:
            log.error(f"Error reading audio data: {e}", exc_info=True)

    def _create_wav_from_raw(self, raw_data: bytes) -> Optional[bytes]:
        """Convert raw PCM audio bytes into WAV format bytes."""
        if not raw_data:
            log.error("No raw data provided for WAV creation.")
            return None
        try:
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(raw_data)
            return buffer.getvalue()
        except Exception as e:
            log.error(f"Error creating WAV: {e}", exc_info=True)
            return None

    def stop_and_download(self, output_file_path: str) -> Tuple[bool, bytes]:
        """Stop recording and save WAV file to specified path.

        Returns:
            tuple[bool, bytes]: A tuple containing:
                - bool: True if file was saved successfully, False otherwise
                - bytes: The WAV file bytes (empty bytes if save failed)
        """
        wav_bytes = self.stop_recording()
        try:
            with open(output_file_path, "wb") as f:
                f.write(wav_bytes)
            log.info(f"WAV file saved successfully at: {output_file_path}")
            return True, wav_bytes
        except Exception as e:
            log.error(f"Failed to save WAV file: {e}", exc_info=True)
            return False, b""
