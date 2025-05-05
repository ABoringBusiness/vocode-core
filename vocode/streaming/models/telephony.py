from enum import Enum
from typing import Any, Dict, Literal, Optional, Union

from vocode.streaming.models.agent import AgentConfig
from vocode.streaming.models.model import BaseModel, TypedModel
from vocode.streaming.models.synthesizer import AzureSynthesizerConfig, SynthesizerConfig
from vocode.streaming.models.transcriber import (
    DeepgramTranscriberConfig,
    PunctuationEndpointingConfig,
    TranscriberConfig,
)
from vocode.streaming.telephony.constants import (
    DEFAULT_AUDIO_ENCODING,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_SAMPLING_RATE,
    VONAGE_AUDIO_ENCODING,
    VONAGE_CHUNK_SIZE,
    VONAGE_SAMPLING_RATE,
)


class TelephonyProviderConfig(BaseModel):
    record: bool = False


class TwilioConfig(TelephonyProviderConfig):
    account_sid: str
    auth_token: str
    extra_params: Optional[Dict[str, Any]] = {}
    account_supports_any_caller_id: bool = True


class VonageConfig(TelephonyProviderConfig):
    api_key: str
    api_secret: str
    application_id: str
    private_key: str


class FreeSwitchConfig(TelephonyProviderConfig):
    server_url: str  # URL of the FreeSwitch server
    api_key: str  # API key for authentication
    gateway: Optional[str] = None  # Optional gateway to use for outbound calls
    sip_domain: Optional[str] = None  # SIP domain for call routing
    ws_endpoint: Optional[str] = None  # WebSocket endpoint for streaming
    extra_params: Optional[Dict[str, Any]] = {}
    
    # Audio configuration
    input_format: str = "mulaw"  # Input audio format (mulaw, pcm, opus)
    output_format: str = "mulaw"  # Output audio format (mulaw, pcm, opus)
    sample_rate: int = 8000  # Sample rate in Hz
    channels: int = 1  # Number of audio channels
    
    # Call handling options
    max_call_duration: Optional[int] = None  # Maximum call duration in seconds
    call_timeout: int = 60  # Timeout for call setup in seconds
    retry_attempts: int = 2  # Number of retry attempts for failed calls
    
    # Streaming options
    chunk_size: int = 320  # Audio chunk size (20ms at 8kHz)
    use_websocket: bool = True  # Use WebSocket for audio streaming
    stream_timeout: int = 10  # Timeout for stream connection in seconds


class CallEntity(BaseModel):
    phone_number: str


class CreateInboundCall(BaseModel):
    recipient: CallEntity
    caller: CallEntity
    transcriber_config: Optional[TranscriberConfig] = None
    agent_config: AgentConfig
    synthesizer_config: Optional[SynthesizerConfig] = None
    vonage_uuid: Optional[str] = None
    twilio_sid: Optional[str] = None
    freeswitch_call_id: Optional[str] = None
    conversation_id: Optional[str] = None
    twilio_config: Optional[TwilioConfig] = None
    vonage_config: Optional[VonageConfig] = None
    freeswitch_config: Optional[FreeSwitchConfig] = None


class EndOutboundCall(BaseModel):
    call_id: str
    vonage_config: Optional[VonageConfig] = None
    twilio_config: Optional[TwilioConfig] = None
    freeswitch_config: Optional[FreeSwitchConfig] = None


class CreateOutboundCall(BaseModel):
    recipient: CallEntity
    caller: CallEntity
    transcriber_config: Optional[TranscriberConfig] = None
    agent_config: AgentConfig
    synthesizer_config: Optional[SynthesizerConfig] = None
    conversation_id: Optional[str] = None
    vonage_config: Optional[VonageConfig] = None
    twilio_config: Optional[TwilioConfig] = None
    freeswitch_config: Optional[FreeSwitchConfig] = None
    # TODO add IVR/etc.


class DialIntoZoomCall(BaseModel):
    recipient: CallEntity
    caller: CallEntity
    zoom_meeting_id: str
    zoom_meeting_password: Optional[str]
    transcriber_config: Optional[TranscriberConfig] = None
    agent_config: AgentConfig
    synthesizer_config: Optional[SynthesizerConfig] = None
    conversation_id: Optional[str] = None
    vonage_config: Optional[VonageConfig] = None
    twilio_config: Optional[TwilioConfig] = None
    freeswitch_config: Optional[FreeSwitchConfig] = None


class CallConfigType(str, Enum):
    BASE = "call_config_base"
    TWILIO = "call_config_twilio"
    VONAGE = "call_config_vonage"
    FREESWITCH = "call_config_freeswitch"


PhoneCallDirection = Literal["inbound", "outbound"]


class BaseCallConfig(TypedModel, type=CallConfigType.BASE.value):  # type: ignore
    transcriber_config: TranscriberConfig
    agent_config: AgentConfig
    synthesizer_config: SynthesizerConfig
    from_phone: str
    to_phone: str
    sentry_tags: Dict[str, str] = {}
    conference: bool = False
    telephony_params: Optional[Dict[str, str]] = None
    direction: PhoneCallDirection

    @staticmethod
    def default_transcriber_config():
        raise NotImplementedError

    @staticmethod
    def default_synthesizer_config():
        raise NotImplementedError


class TwilioCallConfig(BaseCallConfig, type=CallConfigType.TWILIO.value):  # type: ignore
    twilio_config: TwilioConfig
    twilio_sid: str

    @staticmethod
    def default_transcriber_config():
        return DeepgramTranscriberConfig(
            sampling_rate=DEFAULT_SAMPLING_RATE,
            audio_encoding=DEFAULT_AUDIO_ENCODING,
            chunk_size=DEFAULT_CHUNK_SIZE,
            model="phonecall",
            tier="nova",
            endpointing_config=PunctuationEndpointingConfig(),
        )

    @staticmethod
    def default_synthesizer_config():
        return AzureSynthesizerConfig(
            sampling_rate=DEFAULT_SAMPLING_RATE,
            audio_encoding=DEFAULT_AUDIO_ENCODING,
        )


class VonageCallConfig(BaseCallConfig, type=CallConfigType.VONAGE.value):  # type: ignore
    vonage_config: VonageConfig
    vonage_uuid: str
    output_to_speaker: bool = False

    @staticmethod
    def default_transcriber_config():
        return DeepgramTranscriberConfig(
            sampling_rate=VONAGE_SAMPLING_RATE,
            audio_encoding=VONAGE_AUDIO_ENCODING,
            chunk_size=VONAGE_CHUNK_SIZE,
            model="phonecall",
            tier="nova",
            endpointing_config=PunctuationEndpointingConfig(),
        )

    @staticmethod
    def default_synthesizer_config():
        return AzureSynthesizerConfig(
            sampling_rate=VONAGE_SAMPLING_RATE,
            audio_encoding=VONAGE_AUDIO_ENCODING,
        )


class FreeSwitchCallConfig(BaseCallConfig, type=CallConfigType.FREESWITCH.value):  # type: ignore
    freeswitch_config: FreeSwitchConfig
    freeswitch_call_id: str
    output_to_speaker: bool = False
    call_status: Optional[str] = None  # Current call status
    call_start_time: Optional[float] = None  # Call start time (Unix timestamp)
    call_duration: Optional[int] = None  # Call duration in seconds
    
    # Audio streaming settings
    use_websocket: bool = True  # Use WebSocket for audio streaming
    stream_id: Optional[str] = None  # Stream ID for WebSocket connection
    
    # Call metadata
    sip_headers: Optional[Dict[str, str]] = None  # SIP headers for the call
    call_variables: Optional[Dict[str, Any]] = None  # Custom call variables

    @staticmethod
    def default_transcriber_config():
        return DeepgramTranscriberConfig(
            sampling_rate=8000,
            audio_encoding=AudioEncoding.MULAW,
            chunk_size=320,  # 20ms at 8kHz
            model="phonecall",
            tier="nova",
            endpointing_config=PunctuationEndpointingConfig(),
        )

    @staticmethod
    def default_synthesizer_config():
        return AzureSynthesizerConfig(
            sampling_rate=8000,
            audio_encoding=AudioEncoding.MULAW,
        )


TelephonyConfig = Union[TwilioConfig, VonageConfig, FreeSwitchConfig]
