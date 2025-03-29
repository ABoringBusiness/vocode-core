from typing import Optional

from loguru import logger

from vocode.streaming.agent.abstract_factory import AbstractAgentFactory
from vocode.streaming.agent.default_factory import DefaultAgentFactory
from vocode.streaming.models.agent import AgentConfig
from vocode.streaming.models.synthesizer import SynthesizerConfig
from vocode.streaming.models.telephony import FreeSwitchConfig, PhoneCallDirection
from vocode.streaming.models.transcriber import TranscriberConfig
from vocode.streaming.synthesizer.abstract_factory import AbstractSynthesizerFactory
from vocode.streaming.synthesizer.default_factory import DefaultSynthesizerFactory
from vocode.streaming.telephony.config_manager.base_config_manager import BaseConfigManager
from vocode.streaming.telephony.conversation.abstract_phone_conversation import (
    AbstractPhoneConversation,
)
from vocode.streaming.telephony.constants import FREESWITCH_AUDIO_ENCODING, MULAW_SILENCE_BYTE
from vocode.streaming.transcriber.abstract_factory import AbstractTranscriberFactory
from vocode.streaming.transcriber.default_factory import DefaultTranscriberFactory
from vocode.streaming.utils.events_manager import EventsManager


class FreeSwitchPhoneConversation(AbstractPhoneConversation):
    def __init__(
        self,
        to_phone: str,
        from_phone: str,
        base_url: str,
        config_manager: BaseConfigManager,
        agent_config: AgentConfig,
        transcriber_config: TranscriberConfig,
        synthesizer_config: SynthesizerConfig,
        freeswitch_config: FreeSwitchConfig,
        freeswitch_uuid: str,
        conversation_id: str,
        transcriber_factory: AbstractTranscriberFactory = DefaultTranscriberFactory(),
        agent_factory: AbstractAgentFactory = DefaultAgentFactory(),
        synthesizer_factory: AbstractSynthesizerFactory = DefaultSynthesizerFactory(),
        events_manager: Optional[EventsManager] = None,
        output_to_speaker: bool = False,
        direction: PhoneCallDirection = "inbound",
    ):
        super().__init__(
            to_phone=to_phone,
            from_phone=from_phone,
            base_url=base_url,
            config_manager=config_manager,
            agent_config=agent_config,
            transcriber_config=transcriber_config,
            synthesizer_config=synthesizer_config,
            conversation_id=conversation_id,
            transcriber_factory=transcriber_factory,
            agent_factory=agent_factory,
            synthesizer_factory=synthesizer_factory,
            events_manager=events_manager,
            direction=direction,
        )
        self.freeswitch_config = freeswitch_config
        self.freeswitch_uuid = freeswitch_uuid
        self.output_to_speaker = output_to_speaker
        self.audio_encoding = FREESWITCH_AUDIO_ENCODING
        self.silence_byte = MULAW_SILENCE_BYTE

    def get_telephony_config(self):
        return self.freeswitch_config