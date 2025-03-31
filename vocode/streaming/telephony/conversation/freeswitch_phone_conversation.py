from typing import Optional, Dict, Union

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
from vocode.streaming.telephony.conversation.freeswitch_call_transfer import (
    CallTransferManager, TransferType
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
        
        # Initialize call transfer manager
        self.transfer_manager = CallTransferManager(
            call_uuid=self.freeswitch_uuid,
            client=None,  # Will be initialized when needed
            conversation_id=self.conversation_id,
            event_publisher=events_manager
        )

    def get_telephony_config(self):
        return self.freeswitch_config
        
    async def transfer_call(
        self,
        destination: str,
        transfer_type: Union[TransferType, str] = TransferType.BLIND,
        caller_id: Optional[str] = None,
        timeout_seconds: int = 60,
        transfer_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Transfer the current call to another destination
        
        Args:
            destination: The destination number or SIP URI
            transfer_type: The type of transfer (blind, attended, warm)
            caller_id: The caller ID to use for the transfer leg
            timeout_seconds: Timeout in seconds for attended/warm transfers
            transfer_headers: Additional SIP headers for the transfer
            
        Returns:
            bool: True if transfer was successful, False otherwise
        """
        # Initialize client if needed
        if self.transfer_manager.client is None:
            from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
            self.transfer_manager.client = FreeSwitchClient(
                base_url=self.base_url,
                maybe_freeswitch_config=self.freeswitch_config
            )
            
        # Convert string to enum if needed
        if isinstance(transfer_type, str):
            transfer_type = TransferType(transfer_type)
            
        return await self.transfer_manager.transfer_call(
            destination=destination,
            transfer_type=transfer_type,
            caller_id=caller_id,
            timeout_seconds=timeout_seconds,
            transfer_headers=transfer_headers
        )
        
    async def complete_warm_transfer(self) -> bool:
        """
        Complete a warm transfer by removing the original agent from the conference
        """
        return await self.transfer_manager.complete_warm_transfer()
        
    async def cancel_transfer(self) -> bool:
        """
        Cancel an in-progress transfer
        """
        return await self.transfer_manager.cancel_transfer()
        
    async def terminate(self):
        """Terminate the conversation"""
        # Cancel any in-progress transfers before terminating
        await self.transfer_manager.cancel_transfer()
        await super().terminate()