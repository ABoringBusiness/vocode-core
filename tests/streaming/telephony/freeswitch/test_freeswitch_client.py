import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.client.freeswitch_client import (
    FreeSwitchClient,
    FreeSwitchBadRequestException,
    FreeSwitchException,
)


class TestFreeSwitchClient(unittest.TestCase):
    def setUp(self):
        self.base_url = "test.example.com"
        self.freeswitch_config = FreeSwitchConfig(
            api_url="http://freeswitch:8080",
            auth_username="freeswitch",
            auth_password="password",
            record=True,
        )
        self.client = FreeSwitchClient(
            base_url=self.base_url,
            maybe_freeswitch_config=self.freeswitch_config,
        )
        
    def test_get_telephony_config(self):
        config = self.client.get_telephony_config()
        self.assertEqual(config, self.freeswitch_config)
        
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_create_call_success(self, mock_post):
        # Mock the response
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value={"uuid": "test-uuid-123"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
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
        self.assertEqual(result, "test-uuid-123")
        
        # Verify the API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0][0]
        call_kwargs = mock_post.call_args[1]
        
        self.assertEqual(call_args, f"{self.freeswitch_config.api_url}/originate")
        self.assertEqual(call_kwargs["json"]["to"], f"+{to_phone}")
        self.assertEqual(call_kwargs["json"]["from"], f"+{from_phone}")
        self.assertEqual(call_kwargs["json"]["conversation_id"], conversation_id)
        self.assertEqual(call_kwargs["json"]["callback_url"], f"{self.base_url}/connect_call/{conversation_id}")
        self.assertEqual(call_kwargs["json"]["record"], True)
        
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_create_call_bad_request(self, mock_post):
        # Mock the response
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 400
        mock_response.reason = "Bad Request"
        mock_response.json = AsyncMock(return_value={"error": "Invalid phone number"})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test parameters
        conversation_id = "conv-123"
        to_phone = "invalid"
        from_phone = "9876543210"
        
        # Call the method and expect an exception
        with self.assertRaises(FreeSwitchBadRequestException):
            await self.client.create_call(
                conversation_id=conversation_id,
                to_phone=to_phone,
                from_phone=from_phone,
            )
            
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_create_call_server_error(self, mock_post):
        # Mock the response
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test parameters
        conversation_id = "conv-123"
        to_phone = "1234567890"
        from_phone = "9876543210"
        
        # Call the method and expect an exception
        with self.assertRaises(FreeSwitchException):
            await self.client.create_call(
                conversation_id=conversation_id,
                to_phone=to_phone,
                from_phone=from_phone,
            )
            
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_end_call_success(self, mock_post):
        # Mock the response
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test parameters
        call_uuid = "test-uuid-123"
        
        # Call the method
        result = await self.client.end_call(call_uuid)
        
        # Verify the result
        self.assertTrue(result)
        
        # Verify the API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0][0]
        call_kwargs = mock_post.call_args[1]
        
        self.assertEqual(call_args, f"{self.freeswitch_config.api_url}/hangup")
        self.assertEqual(call_kwargs["json"]["uuid"], call_uuid)
        
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_end_call_failure(self, mock_post):
        # Mock the response
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 404
        mock_response.reason = "Not Found"
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test parameters
        call_uuid = "nonexistent-uuid"
        
        # Call the method and expect an exception
        with self.assertRaises(RuntimeError):
            await self.client.end_call(call_uuid)


if __name__ == "__main__":
    unittest.main()