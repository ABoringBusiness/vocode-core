import os
import unittest
import queue
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchESLConfig, FreeSwitchESLCallConfig
from vocode.streaming.telephony.conversation.freeswitch_esl_conversation import (
    FreeSwitchESLConversation,
)


# Mock the ESL module since it might not be available during tests
class MockESLConnection:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self._connected = True
        
    def connected(self):
        return self._connected
        
    def api(self, command):
        # Mock response for different commands
        if command.startswith("uuid_audio_start"):
            return MockESLEvent(body="OK")
        elif command.startswith("uuid_audio_stop"):
            return MockESLEvent(body="OK")
        elif command.startswith("uuid_displace"):
            return MockESLEvent(body="OK")
        else:
            return MockESLEvent(body="Unknown command")
            
    def events(self, event_type, event_name):
        pass
        
    def recvEvent(self):
        return None


class MockESLEvent:
    def __init__(self, body="", headers=None):
        self.body = body
        self.headers = headers or {}
        
    def getBody(self):
        return self.body
        
    def getHeader(self, name):
        return self.headers.get(name)


@patch("vocode.streaming.telephony.conversation.freeswitch_esl_conversation.ESL", MagicMock())
@patch("vocode.streaming.telephony.conversation.freeswitch_esl_conversation.ESL.ESLconnection", MockESLConnection)
class TestFreeSwitchESLConversation(unittest.TestCase):
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
        
        # Create FreeSwitchESLConfig
        self.freeswitch_config = FreeSwitchESLConfig(
            api_url="http://freeswitch:8080",
            auth_username="freeswitch",
            auth_password="password",
            esl_host="freeswitch",
            esl_port=8021,
            esl_password="ClueCon",
            record=True,
        )
        
        # Create call config
        self.call_config = FreeSwitchESLCallConfig(
            transcriber_config=FreeSwitchESLCallConfig.default_transcriber_config(),
            agent_config=self.agent_config,
            synthesizer_config=FreeSwitchESLCallConfig.default_synthesizer_config(),
            freeswitch_config=self.freeswitch_config,
            freeswitch_uuid=self.freeswitch_uuid,
            to_phone=self.to_phone,
            from_phone=self.from_phone,
            direction="inbound",
        )
        
        # Create conversation
        self.conversation = FreeSwitchESLConversation(
            to_phone=self.to_phone,
            from_phone=self.from_phone,
            base_url=self.base_url,
            config_manager=self.config_manager,
            agent_config=self.agent_config,
            transcriber_config=FreeSwitchESLCallConfig.default_transcriber_config(),
            synthesizer_config=FreeSwitchESLCallConfig.default_synthesizer_config(),
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
    async def test_connect_esl(self):
        # Call the method
        result = await self.conversation._connect_esl()
        
        # Verify the result
        self.assertTrue(result)
        self.assertIsNotNone(self.conversation._esl_con)
        
    @pytest.mark.asyncio
    @patch("vocode.streaming.telephony.conversation.freeswitch_esl_conversation.threading.Thread")
    @patch("vocode.streaming.telephony.conversation.abstract_phone_conversation.AbstractPhoneConversation.attach_ws_and_start")
    @patch("vocode.streaming.telephony.conversation.freeswitch_esl_conversation.FreeSwitchESLConversation._connect_esl")
    async def test_attach_ws_and_start(self, mock_connect_esl, mock_parent_attach, mock_thread):
        # Mock websocket
        websocket = MagicMock()
        
        # Mock thread
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        # Mock queue
        self.conversation._audio_queue = MagicMock(spec=queue.Queue)
        self.conversation._audio_queue.get = MagicMock(side_effect=queue.Empty)
        
        # Set up the running flag to stop after one iteration
        self.conversation._running = True
        
        def stop_running(*args, **kwargs):
            self.conversation._running = False
            return AsyncMock()()
            
        # Mock asyncio.sleep to stop the loop
        with patch("asyncio.sleep", side_effect=stop_running):
            # Call the method
            await self.conversation.attach_ws_and_start(websocket)
            
            # Verify ESL connection was established
            mock_connect_esl.assert_called_once()
            
            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            
            # Verify parent method was called
            mock_parent_attach.assert_called_once_with(websocket)
            
    @pytest.mark.asyncio
    @patch("tempfile.NamedTemporaryFile")
    async def test_send_audio_to_freeswitch(self, mock_temp_file):
        # Mock temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.raw"
        mock_temp_file.return_value.__enter__.return_value = mock_file
        
        # Set up ESL connection
        self.conversation._esl_con = MockESLConnection("localhost", 8021, "ClueCon")
        
        # Call the method
        audio_data = b"test audio data"
        result = await self.conversation._send_audio_to_freeswitch(audio_data)
        
        # Verify the result
        self.assertTrue(result)
        
        # Verify file was written
        mock_file.write.assert_called_once_with(audio_data)
        
    @pytest.mark.asyncio
    async def test_send_audio(self):
        # Mock _send_audio_to_freeswitch
        self.conversation._send_audio_to_freeswitch = AsyncMock(return_value=True)
        
        # Call the method
        audio_chunk = b"test audio chunk"
        await self.conversation.send_audio(audio_chunk)
        
        # Verify _send_audio_to_freeswitch was called
        self.conversation._send_audio_to_freeswitch.assert_called_once_with(audio_chunk)
        
    @pytest.mark.asyncio
    @patch("vocode.streaming.telephony.conversation.abstract_phone_conversation.AbstractPhoneConversation.terminate")
    async def test_terminate(self, mock_parent_terminate):
        # Call the method
        await self.conversation.terminate()
        
        # Verify running flag was set to False
        self.assertFalse(self.conversation._running)
        
        # Verify parent method was called
        mock_parent_terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()