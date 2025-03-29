import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig, FreeSwitchCallConfig
from vocode.streaming.telephony.conversation.freeswitch_phone_conversation import (
    FreeSwitchPhoneConversation,
)


class TestFreeSwitchPhoneConversation(unittest.TestCase):
    def setUp(self):
        self.to_phone = "1234567890"
        self.from_phone = "9876543210"
        self.base_url = "test.example.com"
        self.conversation_id = "conv-123"
        self.freeswitch_uuid = "uuid-123"
        
        # Mock config manager
        self.config_manager = MagicMock()
        self.config_manager.get_config = AsyncMock()
        self.config_manager.save_config = AsyncMock()
        
        # Create agent config
        self.agent_config = ChatGPTAgentConfig(
            initial_message=BaseMessage(text="Hello! How can I help you?"),
            prompt_preamble="You are a helpful assistant.",
            model="gpt-3.5-turbo",
        )
        
        # Create FreeSwitchConfig
        self.freeswitch_config = FreeSwitchConfig(
            api_url="http://freeswitch:8080",
            auth_username="freeswitch",
            auth_password="password",
            record=True,
        )
        
        # Create call config
        self.call_config = FreeSwitchCallConfig(
            transcriber_config=FreeSwitchCallConfig.default_transcriber_config(),
            agent_config=self.agent_config,
            synthesizer_config=FreeSwitchCallConfig.default_synthesizer_config(),
            freeswitch_config=self.freeswitch_config,
            freeswitch_uuid=self.freeswitch_uuid,
            to_phone=self.to_phone,
            from_phone=self.from_phone,
            direction="inbound",
        )
        
        # Create conversation
        self.conversation = FreeSwitchPhoneConversation(
            to_phone=self.to_phone,
            from_phone=self.from_phone,
            base_url=self.base_url,
            config_manager=self.config_manager,
            agent_config=self.agent_config,
            transcriber_config=FreeSwitchCallConfig.default_transcriber_config(),
            synthesizer_config=FreeSwitchCallConfig.default_synthesizer_config(),
            freeswitch_config=self.freeswitch_config,
            freeswitch_uuid=self.freeswitch_uuid,
            conversation_id=self.conversation_id,
        )
        
        # Mock the parent class methods
        self.conversation.attach_ws_and_start = AsyncMock()
        self.conversation.receive_audio = AsyncMock()
        self.conversation.terminate = AsyncMock()
        
    def test_get_telephony_config(self):
        config = self.conversation.get_telephony_config()
        self.assertEqual(config, self.freeswitch_config)
        
    def test_audio_encoding(self):
        self.assertEqual(self.conversation.audio_encoding.name, "MULAW")
        
    def test_silence_byte(self):
        self.assertEqual(self.conversation.silence_byte, b"\xff")
        
    @pytest.mark.asyncio
    @patch("vocode.streaming.telephony.conversation.abstract_phone_conversation.AbstractPhoneConversation.attach_ws_and_start")
    async def test_attach_ws_and_start(self, mock_parent_attach):
        # Mock websocket
        websocket = MagicMock()
        
        # Call the method
        await self.conversation.attach_ws_and_start(websocket)
        
        # Verify parent method was called
        mock_parent_attach.assert_called_once_with(websocket)


if __name__ == "__main__":
    unittest.main()