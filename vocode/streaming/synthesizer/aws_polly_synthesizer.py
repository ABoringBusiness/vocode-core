import asyncio
import os
import tempfile
from typing import AsyncGenerator, Optional, Tuple, List

import boto3
import numpy as np
from loguru import logger

from vocode.streaming.agent.bot_sentiment_analyser import BotSentiment
from vocode.streaming.models.audio_encoding import AudioEncoding
from vocode.streaming.models.synthesizer import AWSPollySynthesizerConfig
from vocode.streaming.synthesizer.base_synthesizer import (
    BaseSynthesizer,
    SynthesisResult,
    encode_as_wav,
)
from vocode.streaming.utils.audio_utils import convert_wav_to_pcm


class AWSPollySynthesizer(BaseSynthesizer[AWSPollySynthesizerConfig]):
    def __init__(
        self,
        config: AWSPollySynthesizerConfig,
        logger_name: Optional[str] = None,
    ):
        super().__init__(config)
        self.aws_region = config.aws_region
        self.voice_id = config.voice_id
        self.engine = config.engine
        self.language_code = config.language_code
        self.output_format = "pcm" if self.config.audio_encoding == AudioEncoding.LINEAR16 else "mp3"
        self.sample_rate = config.sampling_rate
        
        # Initialize AWS Polly client
        self.polly_client = boto3.client(
            'polly',
            region_name=self.aws_region,
            aws_access_key_id=config.aws_access_key_id or os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=config.aws_secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
        
        # Validate voice ID
        try:
            voices = self.polly_client.describe_voices(
                Engine=self.engine,
                LanguageCode=self.language_code
            )
            available_voices = [voice['Id'] for voice in voices['Voices']]
            if self.voice_id not in available_voices:
                logger.warning(f"Voice ID {self.voice_id} not found in available voices for {self.language_code}. Available voices: {available_voices}")
        except Exception as e:
            logger.warning(f"Failed to validate voice ID: {e}")

    async def create_speech(
        self, message: str, bot_sentiment: Optional[BotSentiment] = None
    ) -> AsyncGenerator[Tuple[bytes, bool], None]:
        """
        Create speech from text using AWS Polly
        """
        try:
            # Apply SSML if needed
            if self.config.use_ssml and not message.startswith("<speak>"):
                message = f"<speak>{message}</speak>"
                
            # Prepare synthesis parameters
            synthesis_params = {
                'Engine': self.engine,
                'LanguageCode': self.language_code,
                'OutputFormat': self.output_format,
                'SampleRate': str(self.sample_rate),
                'Text': message,
                'TextType': 'ssml' if self.config.use_ssml else 'text',
                'VoiceId': self.voice_id
            }
            
            # Add neural engine specific parameters
            if self.engine == 'neural':
                if bot_sentiment and self.config.use_sentiment:
                    # Map sentiment to speaking style if supported
                    if self.voice_id in ['Matthew', 'Joanna']:
                        style = 'excited' if bot_sentiment == BotSentiment.POSITIVE else 'serious'
                        synthesis_params['Engine'] = 'neural'
                        synthesis_params['VoiceId'] = self.voice_id
                
            # Synthesize speech
            response = self.polly_client.synthesize_speech(**synthesis_params)
            
            # Process audio stream
            audio_stream = response['AudioStream'].read()
            
            # Convert to the right format if needed
            if self.config.audio_encoding == AudioEncoding.LINEAR16 and self.output_format == "pcm":
                # Already in PCM format, just yield it
                chunk_size = 4096
                for i in range(0, len(audio_stream), chunk_size):
                    chunk = audio_stream[i:i+chunk_size]
                    yield chunk, i + chunk_size >= len(audio_stream)
            elif self.config.audio_encoding == AudioEncoding.MULAW:
                # Need to convert from PCM to MULAW
                with tempfile.NamedTemporaryFile(suffix=".wav") as temp_wav:
                    # Write PCM data to WAV file
                    with open(temp_wav.name, "wb") as f:
                        f.write(encode_as_wav(audio_stream, self.sample_rate))
                    
                    # Convert to MULAW
                    mulaw_data = convert_wav_to_pcm(
                        temp_wav.name, 
                        output_sample_rate=self.sample_rate, 
                        output_encoding=AudioEncoding.MULAW
                    )
                    
                    # Yield in chunks
                    chunk_size = 4096
                    for i in range(0, len(mulaw_data), chunk_size):
                        chunk = mulaw_data[i:i+chunk_size]
                        yield chunk, i + chunk_size >= len(mulaw_data)
            else:
                # Just yield the MP3 data
                chunk_size = 4096
                for i in range(0, len(audio_stream), chunk_size):
                    chunk = audio_stream[i:i+chunk_size]
                    yield chunk, i + chunk_size >= len(audio_stream)
                
        except Exception as e:
            logger.error(f"Error in AWS Polly synthesis: {e}")
            # Return silence in case of error
            yield b"\x00" * 1024, True

    async def synthesize(
        self, message: str, bot_sentiment: Optional[BotSentiment] = None
    ) -> SynthesisResult:
        """
        Synthesize speech from text using AWS Polly
        """
        audio_chunks = []
        async for chunk, _ in self.create_speech(message, bot_sentiment):
            audio_chunks.append(chunk)
        
        return SynthesisResult(audio_chunks=audio_chunks)