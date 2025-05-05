# Enhanced LLM Integrations for Vocode

This directory contains examples of enhanced integrations with popular LLM providers:

- **OpenAI**: Enhanced integration with GPT models including GPT-4o
- **Groq**: Enhanced integration with Llama 3 and other models
- **Claude**: Enhanced integration with Anthropic's Claude 3 models

## Features

These enhanced integrations provide several advantages over the standard integrations:

1. **Advanced Parameters**: Fine-tune model behavior with parameters like top_p, frequency_penalty, presence_penalty, etc.
2. **Improved Error Handling**: Better error handling and retry logic for more reliable conversations
3. **Vector DB Integration**: Built-in support for retrieving context from vector databases
4. **Backchannels**: Support for natural conversation backchannels like "hmm," "I see," etc.
5. **Configurable Timeouts**: Set custom request timeouts to handle long-running requests
6. **Custom Base URLs**: Support for custom API endpoints and self-hosted models

## Prerequisites

Before running these examples, make sure you have the necessary API keys:

- **OpenAI**: Get an API key from [OpenAI](https://platform.openai.com/)
- **Groq**: Get an API key from [Groq](https://console.groq.com/)
- **Anthropic**: Get an API key from [Anthropic](https://console.anthropic.com/)
- **Azure Speech**: Get a key from [Azure](https://portal.azure.com/)
- **Deepgram**: Get an API key from [Deepgram](https://console.deepgram.com/)

## Installation

1. Install the required dependencies:

```bash
pip install "vocode[all]"
```

2. Set up your environment variables:

```bash
export OPENAI_API_KEY="your_openai_api_key"
export GROQ_API_KEY="your_groq_api_key"
export ANTHROPIC_API_KEY="your_anthropic_api_key"
export AZURE_SPEECH_KEY="your_azure_speech_key"
export AZURE_SPEECH_REGION="your_azure_region"
export DEEPGRAM_API_KEY="your_deepgram_api_key"
```

## Running the Examples

### OpenAI Example

```bash
python enhanced_openai_example.py
```

### Groq Example

```bash
python enhanced_groq_example.py
```

### Claude Example

```bash
python enhanced_claude_example.py
```

## Configuration Options

### Enhanced OpenAI Agent

```python
agent_config = EnhancedOpenAIAgentConfig(
    # Basic parameters
    model_name="gpt-4o",  # or "gpt-4", "gpt-3.5-turbo", etc.
    temperature=0.7,
    max_tokens=1024,
    openai_api_key="your_api_key",  # Optional, can use environment variable
    
    # Advanced parameters
    organization_id="your_org_id",  # Optional
    base_url_override="https://your-custom-endpoint.com",  # Optional
    request_timeout=30.0,  # Optional, in seconds
    seed=42,  # Optional, for reproducible responses
    top_p=0.9,  # Optional
    frequency_penalty=0.5,  # Optional
    presence_penalty=0.5,  # Optional
    logit_bias={"50256": -100},  # Optional
    response_format={"type": "json_object"},  # Optional
    
    # Conversation features
    use_backchannels=True,
    backchannel_probability=0.6,
    first_response_filler_message="Let me think about that...",
)
```

### Enhanced Groq Agent

```python
agent_config = EnhancedGroqAgentConfig(
    # Basic parameters
    model_name="llama3-70b-8192",  # or "mixtral-8x7b-32768", etc.
    temperature=0.7,
    max_tokens=1024,
    groq_api_key="your_api_key",  # Optional, can use environment variable
    
    # Advanced parameters
    base_url_override="https://your-custom-endpoint.com",  # Optional
    request_timeout=30.0,  # Optional, in seconds
    top_p=0.9,  # Optional
    frequency_penalty=0.5,  # Optional
    presence_penalty=0.5,  # Optional
    stop_sequences=["Human:", "USER:"],  # Optional
    
    # Conversation features
    use_backchannels=True,
    backchannel_probability=0.6,
    first_response_filler_message="Let me think about that...",
)
```

### Enhanced Claude Agent

```python
agent_config = EnhancedClaudeAgentConfig(
    # Basic parameters
    model_name="claude-3-opus-20240229",  # or "claude-3-haiku-20240307", etc.
    temperature=0.7,
    max_tokens=1024,
    anthropic_api_key="your_api_key",  # Optional, can use environment variable
    
    # Advanced parameters
    base_url_override="https://your-custom-endpoint.com",  # Optional
    request_timeout=30.0,  # Optional, in seconds
    top_p=0.9,  # Optional
    top_k=50,  # Optional
    stop_sequences=["Human:", "USER:"],  # Optional
    
    # Conversation features
    use_backchannels=True,
    backchannel_probability=0.6,
    first_response_filler_message="Let me think about that...",
)
```

## Vector Database Integration

All enhanced agents support integration with vector databases for retrieval-augmented generation:

```python
from vocode.streaming.models.vector_db import PineconeVectorDBConfig

agent_config = EnhancedOpenAIAgentConfig(
    # ... other parameters ...
    vector_db_config=PineconeVectorDBConfig(
        api_key="your_pinecone_api_key",
        environment="your_environment",
        index_name="your_index_name",
    ),
)
```

## Contributing

Feel free to contribute to these integrations by submitting pull requests or opening issues for bugs and feature requests.