#!/usr/bin/env python3

import asyncio
import os
from typing import Optional

from fastapi import FastAPI
from vocode.streaming.models.agent import EnhancedOpenAIAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import AzureSynthesizerConfig
from vocode.streaming.models.transcriber import DeepgramTranscriberConfig
from vocode.streaming.synthesizer.azure_synthesizer import AzureSynthesizer
from vocode.streaming.transcriber.deepgram_transcriber import DeepgramTranscriber
from vocode.streaming.streaming_conversation import StreamingConversation

app = FastAPI()

# Get environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

async def main():
    # Create an enhanced OpenAI agent config
    agent_config = EnhancedOpenAIAgentConfig(
        initial_message=BaseMessage(text="Hello! I'm an AI assistant powered by OpenAI. How can I help you today?"),
        prompt_preamble="""You are a helpful AI assistant. 
        Be concise, friendly, and helpful in your responses.
        If you don't know something, admit it rather than making up information.""",
        model_name="gpt-4o",  # Using the latest GPT-4o model
        temperature=0.7,
        max_tokens=1024,
        openai_api_key=OPENAI_API_KEY,
        # Advanced parameters
        seed=42,  # For reproducible responses
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        # Enable backchannels for more natural conversation
        use_backchannels=True,
        backchannel_probability=0.6,
        first_response_filler_message="Let me think about that...",
    )
    
    # Create a transcriber config
    transcriber_config = DeepgramTranscriberConfig(
        sampling_rate=16000,
        api_key=DEEPGRAM_API_KEY,
        model="nova-2",
    )
    
    # Create a synthesizer config
    synthesizer_config = AzureSynthesizerConfig(
        azure_speech_key=AZURE_SPEECH_KEY,
        azure_speech_region=AZURE_SPEECH_REGION,
        voice_name="en-US-JennyNeural",
        sampling_rate=16000,
    )
    
    # Create the conversation components
    transcriber = DeepgramTranscriber(transcriber_config)
    agent = agent_config.create_agent()
    synthesizer = AzureSynthesizer(synthesizer_config)
    
    # Create the streaming conversation
    conversation = StreamingConversation(
        transcriber=transcriber,
        agent=agent,
        synthesizer=synthesizer,
    )
    
    # Start the conversation
    await conversation.start()
    
    # Keep the conversation running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Conversation ended by user")
    finally:
        await conversation.terminate()

if __name__ == "__main__":
    asyncio.run(main())