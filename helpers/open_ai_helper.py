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
OpenAI API helper for Raven Framework.

This module provides a wrapper around OpenAI API calls for transcription,
chat completions, text-to-speech, and multimodal image + text prompts.
"""

from typing import Any, Optional, Type

import numpy as np
from openai import OpenAI

from .logger import get_logger
from .utils import convert_ndarray_to_base64_image

log = get_logger("OpenAiHelper")


class OpenAiHelper:
    """
    Helper class wrapping OpenAI API calls for transcription, chat completions,
    text-to-speech, and multimodal image + text prompts.

    Args:
        open_ai_key (str): API key for OpenAI. Defaults to "".
    """

    def __init__(self, open_ai_key: str = "") -> None:
        """
        Initialize the OpenAI helper with API key.

        See class docstring for parameter descriptions.
        """
        try:
            if open_ai_key == "":
                log.error("No OpenAI key available", exc_info=True)
                self.client = None
                return
            self.client: Optional[OpenAI] = OpenAI(api_key=open_ai_key)
            log.info("OpenAI client initialized.")
        except Exception as e:
            log.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            self.client = None

    def transcribe_audio(
        self,
        wav_bytes: bytes,
        model: str = "whisper-1",
        audio_filename: str = "audio.wav",
        audio_mime_type: str = "audio/wav",
    ) -> str:
        """
        Transcribe audio bytes using Whisper model.

        Args:
            wav_bytes (bytes): Audio data in WAV format.
            model (str): Model to use for transcription. Defaults to "whisper-1".
            audio_filename (str): Filename identifier for the audio file. Defaults to "audio.wav".
            audio_mime_type (str): MIME type specifying the audio format. Defaults to "audio/wav".

        Returns:
            str: Transcribed text or empty string on failure.
        """
        if not self.client:
            log.error("OpenAI client not initialized")
            return ""
        try:
            response = self.client.audio.transcriptions.create(
                model=model,
                file=(audio_filename, wav_bytes, audio_mime_type),
            )
            text = response.text.strip()
            log.info(f"Transcribed text: {text}")
            return text
        except Exception as e:
            log.error(f"Audio transcription failed: {e}", exc_info=True)
            return ""

    def get_text_response(self, prompt: str, model: str = "gpt-4o") -> str:
        """
        Get a text completion from GPT based on a prompt.

        Args:
            prompt (str): Input prompt text.
            model (str): Model to use.

        Returns:
            str: Completion text or empty string on failure.
        """
        if not self.client:
            log.error("OpenAI client not initialized")
            return ""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content.strip()
            log.info(f"Text response: {text}")
            return text
        except Exception as e:
            log.error(f"Text response failed: {e}", exc_info=True)
            return ""

    def generate_tts(
        self,
        text: str,
        model: str = "tts-1",
        voice: str = "alloy",
        response_format: str = "wav",
    ) -> bytes:
        """
        Generate speech audio from text using TTS model.

        Args:
            text (str): Input text to convert to speech.
            model (str): TTS model to use. Defaults to "tts-1".
            voice (str): Voice to use for TTS. Defaults to "alloy".
            response_format (str): Audio output format. Defaults to "wav".

        Returns:
            bytes: Audio data in WAV format or empty bytes on failure.
        """
        if not self.client:
            log.error("OpenAI client not initialized")
            return b""
        try:
            response = self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format=response_format,
            )
            audio_bytes = response.read()
            log.info("TTS generation successful")
            return audio_bytes
        except Exception as e:
            log.error(f"TTS generation failed: {e}", exc_info=True)
            return b""

    def process_multimodal_with_image(
        self, prompt: str, image: np.ndarray, model: str = "gpt-4o"
    ) -> str:
        """
        Send a multimodal prompt including text and an image to GPT.

        Args:
            prompt (str): Text prompt.
            image (np.ndarray): Image as a NumPy array (BGR or RGB).
            model (str): Model to use

        Returns:
            str: Model's response text or empty string on failure.
        """
        if not self.client:
            log.error("OpenAI client not initialized")
            return ""
        try:
            base64_image = convert_ndarray_to_base64_image(image)
            log.debug("Image converted to base64.")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
            )
            reply = response.choices[0].message.content.strip()
            log.info(f"Multimodal response: {reply}")
            return reply
        except Exception as e:
            log.error(f"Multimodal processing failed: {e}", exc_info=True)
            return ""

    def structured_text_response(
        self,
        content_prompt: str,
        prompt: str,
        structure: Type[Any],
        model: str = "gpt-4o-2024-08-06",
    ) -> Any:
        """
        Get a structured text response with a specified format type.

        Uses OpenAI's structured output feature to parse responses into a specific type.
        Currently configured for recipe generation with steps, timers, and labels.

        Args:
            content_prompt (str): System prompt content for the model.
            prompt (str): User input prompt text.
            structure (Type[Any]): Python type or Pydantic model to parse the response into.
            model (str): Model to use for structured outputs. Defaults to "gpt-4o-2024-08-06".

        Returns:
            Any: Parsed structured response matching the provided structure type, or empty string on failure.
                  The actual return type depends on the structure parameter (e.g., dict, Pydantic model, etc.).
        """
        if not self.client:
            log.error("OpenAI client not initialized")
            return ""
        try:
            response = self.client.responses.parse(
                model=model,
                input=[
                    {"role": "system", "content": content_prompt},
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                text_format=structure,
            )
            output = response.output_parsed
            log.info(f"Structured response received: {output}")
            return output
        except Exception as e:
            log.warning(f"Structured text response failed: {e}", exc_info=True)
            return ""
