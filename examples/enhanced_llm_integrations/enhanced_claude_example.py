#!/usr/bin/env python3

import asyncio
import os
from typing import Optional

from fastapi import FastAPI
from vocode.streaming.models.agent import EnhancedClaudeAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import AzureSynthesizerConfig
from vocode.streaming.models.transcriber import DeepgramTranscriberConfig
from vocode.streaming.synthesizer.azure_synthesizer import AzureSynthesizer
from vocode.streaming.transcriber.deepgram_transcriber import DeepgramTranscriber
from vocode.streaming.streaming_conversation import StreamingConversation

app = FastAPI()

# Get environment variables
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

async def main():
    # Create an enhanced Claude agent config
    agent_config = EnhancedClaudeAgentConfig(
        initial_message=BaseMessage(text="Hello! I'm an AI assistant powered by Claude. How can I help you today?"),
        prompt_preamble="""You are a helpful AI assistant. 
        Be concise, friendly, and helpful in your responses.
        If you don't know something, admit it rather than making up information.""",
        model_name="claude-3-opus-20240229",  # Using Claude 3 Opus for highest quality
        temperature=0.7,
        max_tokens=1024,
        anthropic_api_key=ANTHROPIC_API_KEY,
        # Advanced parameters
        top_p=0.9,
        top_k=50,
        stop_sequences=["Human:", "USER:"],  # Stop sequences to prevent model from continuing as the user
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
        voice_name="en-US-AriaNeural",
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