import asyncio
import hashlib
import os
import time
from typing import Optional, List, Dict, Any

from elevenlabs import Voice, VoiceSettings, voices, clone, generate
from elevenlabs.client import AsyncElevenLabs
from loguru import logger

from vocode.streaming.models.audio import AudioEncoding, SamplingRate
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import ElevenLabsSynthesizerConfig, ElevenLabsVoiceSettings
from vocode.streaming.synthesizer.base_synthesizer import BaseSynthesizer, SynthesisResult
from vocode.streaming.utils.create_task import asyncio_create_task

ELEVEN_LABS_BASE_URL = "https://api.elevenlabs.io/v1/"
STREAMED_CHUNK_SIZE = 16000 * 2 // 4  # 1/8 of a second of 16kHz audio with 16-bit samples


class ElevenlabsException(Exception):
    pass


class ElevenLabsSynthesizer(BaseSynthesizer[ElevenLabsSynthesizerConfig]):
    def __init__(
        self,
        synthesizer_config: ElevenLabsSynthesizerConfig,
    ):
        super().__init__(synthesizer_config)

        assert synthesizer_config.api_key is not None, "API key must be set"
        self.api_key = synthesizer_config.api_key

        self.elevenlabs_client = AsyncElevenLabs(
            api_key=self.api_key,
        )

        # Handle voice cloning if enabled
        if synthesizer_config.voice_cloning_enabled:
            self._setup_cloned_voice(synthesizer_config)
        else:
            assert synthesizer_config.voice_id is not None, "Voice ID must be set when not using voice cloning"
            self.voice_id = synthesizer_config.voice_id

        # Set up voice settings
        if synthesizer_config.voice_settings:
            self.voice_settings = VoiceSettings(
                stability=synthesizer_config.voice_settings.stability,
                similarity_boost=synthesizer_config.voice_settings.similarity_boost,
                style=synthesizer_config.voice_settings.style,
                use_speaker_boost=synthesizer_config.voice_settings.use_speaker_boost,
            )
        else:
            # For backward compatibility
            stability = getattr(synthesizer_config, "stability", None)
            similarity_boost = getattr(synthesizer_config, "similarity_boost", None)
            
            if stability is not None and similarity_boost is not None:
                self.voice_settings = VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity_boost,
                )
            else:
                self.voice_settings = None

        self.model_id = synthesizer_config.model_id
        self.language = synthesizer_config.language
        self.optimize_streaming_latency = synthesizer_config.optimize_streaming_latency
        self.max_retries = synthesizer_config.max_retries
        self.retry_delay = synthesizer_config.retry_delay
        self.words_per_minute = 150
        self.upsample = None
        self.sample_rate = self.synthesizer_config.sampling_rate

        # Configure output format based on audio encoding and sampling rate
        self._configure_output_format()
        
    def _setup_cloned_voice(self, config: ElevenLabsSynthesizerConfig) -> None:
        """Set up a cloned voice using provided audio samples"""
        try:
            # Check if samples exist
            for sample_path in config.voice_cloning_samples:
                if not os.path.exists(sample_path):
                    raise ValueError(f"Voice cloning sample not found: {sample_path}")
            
            # Generate a deterministic name based on the samples
            sample_hash = hashlib.md5(
                "".join(config.voice_cloning_samples).encode()
            ).hexdigest()[:8]
            voice_name = f"cloned_voice_{sample_hash}"
            
            # Check if we already have this voice
            available_voices = voices()
            for voice in available_voices:
                if voice.name == voice_name:
                    logger.info(f"Using existing cloned voice: {voice_name}")
                    self.voice_id = voice.voice_id
                    return
            
            # Clone the voice
            logger.info(f"Cloning new voice: {voice_name}")
            description = config.voice_cloning_description or "Cloned voice for Vocode"
            cloned_voice = clone(
                name=voice_name,
                description=description,
                files=config.voice_cloning_samples,
            )
            self.voice_id = cloned_voice.voice_id
            logger.info(f"Successfully cloned voice with ID: {self.voice_id}")
            
        except Exception as e:
            logger.error(f"Voice cloning failed: {str(e)}")
            raise ElevenlabsException(f"Voice cloning failed: {str(e)}")
    
    def _configure_output_format(self) -> None:
        """Configure the output format based on audio encoding and sampling rate"""
        if self.synthesizer_config.audio_encoding == AudioEncoding.LINEAR16:
            match self.synthesizer_config.sampling_rate:
                case SamplingRate.RATE_16000:
                    self.output_format = "pcm_16000"
                case SamplingRate.RATE_22050:
                    self.output_format = "pcm_22050"
                case SamplingRate.RATE_24000:
                    self.output_format = "pcm_24000"
                case SamplingRate.RATE_44100:
                    self.output_format = "pcm_44100"
                case SamplingRate.RATE_48000:
                    self.output_format = "pcm_44100"
                    self.upsample = SamplingRate.RATE_48000.value
                    self.sample_rate = SamplingRate.RATE_44100.value
                case _:
                    raise ValueError(
                        f"Unsupported sampling rate: {self.synthesizer_config.sampling_rate}. Elevenlabs only supports 16000, 22050, 24000, and 44100 Hz."
                    )
        elif self.synthesizer_config.audio_encoding == AudioEncoding.MULAW:
            self.output_format = "ulaw_8000"
        else:
            raise ValueError(
                f"Unsupported audio encoding: {self.synthesizer_config.audio_encoding}"
            )

    async def create_speech_uncached(
        self,
        message: BaseMessage,
        chunk_size: int,
        is_first_text_chunk: bool = False,
        is_sole_text_chunk: bool = False,
    ) -> SynthesisResult:
        self.total_chars += len(message.text)
        
        # Create voice with settings
        voice = Voice(
            voice_id=self.voice_id,
            settings=self.voice_settings,
        )
        
        # Build URL with parameters
        url = (
            ELEVEN_LABS_BASE_URL
            + f"text-to-speech/{self.voice_id}/stream?output_format={self.output_format}"
        )
        if self.optimize_streaming_latency is not None:
            url += f"&optimize_streaming_latency={self.optimize_streaming_latency}"
            
        # Prepare headers and request body
        headers = {"xi-api-key": self.api_key}
        body = {
            "text": message.text,
            "voice_settings": voice.settings.dict() if voice.settings else None,
        }
        
        # Add model ID if specified
        if self.model_id:
            body["model_id"] = self.model_id
            
        # Add language if specified (for multilingual models)
        if self.language:
            body["language"] = self.language

        # Create queue for chunks and start getting chunks
        chunk_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        asyncio_create_task(
            self.get_chunks(url, headers, body, chunk_size, chunk_queue),
        )

        return SynthesisResult(
            self.chunk_result_generator_from_queue(chunk_queue),
            lambda seconds: self.get_message_cutoff_from_voice_speed(message, seconds, 150),
        )

    @classmethod
    def get_voice_identifier(cls, synthesizer_config: ElevenLabsSynthesizerConfig):
        hashed_api_key = hashlib.sha256(f"{synthesizer_config.api_key}".encode("utf-8")).hexdigest()
        
        # Include voice settings in the identifier if present
        voice_settings_str = ""
        if synthesizer_config.voice_settings:
            voice_settings_str = f"{synthesizer_config.voice_settings.stability}:{synthesizer_config.voice_settings.similarity_boost}"
            if synthesizer_config.voice_settings.style is not None:
                voice_settings_str += f":{synthesizer_config.voice_settings.style}"
            if synthesizer_config.voice_settings.use_speaker_boost is not None:
                voice_settings_str += f":{synthesizer_config.voice_settings.use_speaker_boost}"
        
        return ":".join(
            (
                "eleven_labs",
                hashed_api_key,
                str(synthesizer_config.voice_id),
                str(synthesizer_config.model_id),
                voice_settings_str,
                str(synthesizer_config.optimize_streaming_latency),
                str(synthesizer_config.language or ""),
                synthesizer_config.audio_encoding,
            )
        )

    async def get_chunks(
        self,
        url: str,
        headers: dict,
        body: dict,
        chunk_size: int,
        chunk_queue: asyncio.Queue[Optional[bytes]],
    ):
        retries = 0
        
        while retries <= self.max_retries:
            try:
                async_client = self.async_requestor.get_client()
                stream = await async_client.send(
                    async_client.build_request(
                        "POST",
                        url,
                        headers=headers,
                        json=body,
                    ),
                    stream=True,
                )

                if not stream.is_success:
                    error = await stream.aread()
                    error_message = f"ElevenLabs API returned {stream.status_code} status code and the following details: {error.decode('utf-8')}"
                    
                    # Check if we should retry
                    if retries < self.max_retries and stream.status_code >= 500:
                        retries += 1
                        logger.warning(f"ElevenLabs API error (attempt {retries}/{self.max_retries}): {error_message}")
                        await asyncio.sleep(self.retry_delay * retries)  # Exponential backoff
                        continue
                    else:
                        raise ElevenlabsException(error_message)
                
                # Process the stream
                async for chunk in stream.aiter_bytes(chunk_size):
                    if self.upsample:
                        chunk = self._resample_chunk(
                            chunk,
                            self.sample_rate,
                            self.upsample,
                        )
                    chunk_queue.put_nowait(chunk)
                
                # If we get here, we've successfully processed the stream
                break
                
            except (asyncio.CancelledError, ElevenlabsException):
                # Don't retry on cancellation or specific ElevenLabs exceptions
                raise
            except Exception as e:
                if retries < self.max_retries:
                    retries += 1
                    logger.warning(f"Error in ElevenLabs streaming (attempt {retries}/{self.max_retries}): {str(e)}")
                    await asyncio.sleep(self.retry_delay * retries)  # Exponential backoff
                else:
                    logger.error(f"Failed to stream from ElevenLabs after {self.max_retries} attempts: {str(e)}")
                    raise ElevenlabsException(f"Failed to stream from ElevenLabs: {str(e)}")
        finally:
            chunk_queue.put_nowait(None)  # treated as sentinel
