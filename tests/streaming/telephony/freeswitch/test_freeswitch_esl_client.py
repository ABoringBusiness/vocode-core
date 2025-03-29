import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocode.streaming.models.telephony import FreeSwitchESLConfig
from vocode.streaming.telephony.client.freeswitch_esl_client import FreeSwitchESLClient


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
        if command.startswith("originate"):
            return MockESLEvent(body="uuid-123")
        elif command.startswith("uuid_kill"):
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


@patch("vocode.streaming.telephony.client.freeswitch_esl_client.ESL", MagicMock())
@patch("vocode.streaming.telephony.client.freeswitch_esl_client.ESL.ESLconnection", MockESLConnection)
class TestFreeSwitchESLClient(unittest.TestCase):
    def setUp(self):
        self.base_url = "test.example.com"
        self.freeswitch_config = FreeSwitchESLConfig(
            api_url="http://freeswitch:8080",
            auth_username="freeswitch",
            auth_password="password",
            esl_host="freeswitch",
            esl_port=8021,
            esl_password="ClueCon",
            record=True,
        )
        self.client = FreeSwitchESLClient(
            base_url=self.base_url,
            maybe_freeswitch_config=self.freeswitch_config,
        )
        
    def test_get_telephony_config(self):
        config = self.client.get_telephony_config()
        self.assertEqual(config, self.freeswitch_config)
        
    @pytest.mark.asyncio
    async def test_get_esl_connection(self):
        # Test getting a new connection
        self.client._esl_con = None
        conn = await self.client._get_esl_connection()
        self.assertIsNotNone(conn)
        self.assertTrue(conn.connected())
        
        # Test reusing an existing connection
        conn2 = await self.client._get_esl_connection()
        self.assertEqual(conn, conn2)
        
    @pytest.mark.asyncio
    async def test_execute_esl_command(self):
        # Test executing a command
        result = await self.client._execute_esl_command("test_command")
        self.assertTrue(result["success"])
        self.assertEqual(result["body"], "Unknown command")
        
    @pytest.mark.asyncio
    async def test_create_call(self):
        # Test parameters
        conversation_id = "conv-123"
        to_phone = "1234567890"
        from_phone = "9876543210"
        
        # Call the method
        result = await self.client.create_call(
            conversation_id=conversation_id,
            to_phone=to_phone,
            from_phone=from_phone,
            record=True,
        )
        
        # Verify the result
        self.assertEqual(result, conversation_id)
        
    @pytest.mark.asyncio
    async def test_end_call(self):
        # Test parameters
        call_uuid = "test-uuid-123"
        
        # Call the method
        result = await self.client.end_call(call_uuid)
        
        # Verify the result
        self.assertTrue(result)
        
    @pytest.mark.asyncio
    @patch("asyncio.create_task")
    async def test_subscribe_to_call_events(self, mock_create_task):
        # Mock callback
        callback = AsyncMock()
        
        # Call the method
        result = await self.client.subscribe_to_call_events(callback)
        
        # Verify the result
        self.assertTrue(result)
        
        # Verify that create_task was called
        mock_create_task.assert_called_once()


if __name__ == "__main__":
    unittest.main()