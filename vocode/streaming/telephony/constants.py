from vocode.streaming.models.audio import AudioEncoding, SamplingRate

# TODO(EPD-186): namespace as Twilio
DEFAULT_SAMPLING_RATE: int = SamplingRate.RATE_8000.value
DEFAULT_AUDIO_ENCODING = AudioEncoding.MULAW
DEFAULT_CHUNK_SIZE = 20 * 160
MULAW_SILENCE_BYTE = b"\xff"

VONAGE_SAMPLING_RATE: int = SamplingRate.RATE_16000.value
VONAGE_AUDIO_ENCODING = AudioEncoding.LINEAR16
VONAGE_CHUNK_SIZE = 640  # 20ms at 16kHz with 16bit samples
VONAGE_CONTENT_TYPE = "audio/l16;rate=16000"
PCM_SILENCE_BYTE = b"\x00"

# FreeSwitch constants
FREESWITCH_SAMPLING_RATE: int = SamplingRate.RATE_8000.value
FREESWITCH_AUDIO_ENCODING = AudioEncoding.MULAW
FREESWITCH_CHUNK_SIZE = 20 * 160  # 20ms at 8kHz with 8bit samples
FREESWITCH_CONTENT_TYPE = "audio/basic"
FREESWITCH_WEBSOCKET_PING_INTERVAL = 10  # Seconds between WebSocket ping messages
FREESWITCH_RECONNECT_ATTEMPTS = 3  # Number of reconnection attempts for WebSocket
FREESWITCH_RECONNECT_DELAY = 2  # Seconds between reconnection attempts

# FreeSwitch audio formats
FREESWITCH_AUDIO_FORMATS = {
    "mulaw": {
        "content_type": "audio/basic",
        "encoding": AudioEncoding.MULAW,
        "sample_rate": 8000,
        "silence_byte": MULAW_SILENCE_BYTE,
    },
    "pcm": {
        "content_type": "audio/l16",
        "encoding": AudioEncoding.LINEAR16,
        "sample_rate": 8000,
        "silence_byte": PCM_SILENCE_BYTE,
    },
    "opus": {
        "content_type": "audio/opus",
        "encoding": AudioEncoding.OPUS,
        "sample_rate": 16000,
        "silence_byte": PCM_SILENCE_BYTE,
    },
}
