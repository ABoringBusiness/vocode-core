import os
import json
import asyncio
from typing import Dict, Optional, List, Any
import uuid

import aiohttp
from loguru import logger

from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.client.abstract_telephony_client import AbstractTelephonyClient
from vocode.streaming.utils.async_requester import AsyncRequestor


class FreeSwitchBadRequestException(ValueError):
    pass


class FreeSwitchException(ValueError):
    pass


class FreeSwitchClient(AbstractTelephonyClient):
    def __init__(
        self,
        base_url: str,
        maybe_freeswitch_config: Optional[FreeSwitchConfig] = None,
        record_calls: bool = False,
    ):
        self.freeswitch_config = maybe_freeswitch_config or FreeSwitchConfig(
            server_url=os.environ["FREESWITCH_SERVER_URL"],
            api_key=os.environ["FREESWITCH_API_KEY"],
            sip_domain=os.environ.get("FREESWITCH_SIP_DOMAIN", ""),
            ws_endpoint=os.environ.get("FREESWITCH_WS_ENDPOINT", ""),
        )
        self.headers = {
            "Authorization": f"Bearer {self.freeswitch_config.api_key}",
            "Content-Type": "application/json",
        }
        self.record_calls = record_calls
        super().__init__(base_url=base_url)

    def get_telephony_config(self):
        return self.freeswitch_config

    async def create_call(
        self,
        conversation_id: str,
        to_phone: str,
        from_phone: str,
        record: bool = False,
        digits: Optional[str] = None,
        telephony_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create an outbound call using FreeSwitch"""
        
        # Prepare the request data
        data = {
            "to": to_phone,
            "from": from_phone,
            "webhook_url": f"{self.base_url}/calls/{conversation_id}/events",
            "stream_url": f"{self.base_url}/calls/{conversation_id}/stream",
            "record": record or self.record_calls,
            "conversation_id": conversation_id,
            **(telephony_params or {}),
        }
        
        # Add SIP domain if specified in config
        if self.freeswitch_config.sip_domain:
            data["sip_domain"] = self.freeswitch_config.sip_domain
            
        # Add gateway if specified in config
        if self.freeswitch_config.gateway:
            data["gateway"] = self.freeswitch_config.gateway
            
        # Add DTMF digits if specified
        if digits:
            data["dtmf"] = digits
            
        # Add any extra parameters from the config
        if self.freeswitch_config.extra_params:
            data.update(self.freeswitch_config.extra_params)
        
        # Configure audio settings
        data["audio_settings"] = {
            "input_format": self.freeswitch_config.input_format,
            "output_format": self.freeswitch_config.output_format,
            "sample_rate": self.freeswitch_config.sample_rate,
            "channels": self.freeswitch_config.channels,
        }
        
        # Make the API request to FreeSwitch
        try:
            async with AsyncRequestor().get_session().post(
                f"{self.freeswitch_config.server_url}/api/calls",
                headers=self.headers,
                json=data,
                timeout=30,  # Increased timeout for call setup
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(
                        f"Failed to create call: {response.status} {response.reason} {error_text}"
                    )
                    if response.status == 400:
                        raise FreeSwitchBadRequestException(
                            f"FreeSwitch rejected call: {error_text}"
                        )
                    else:
                        raise FreeSwitchException(
                            f"FreeSwitch failed to create call: {response.status} {response.reason} - {error_text}"
                        )
                
                response_data = await response.json()
                logger.info(f"Successfully initiated call with ID: {response_data['call_id']}")
                return response_data["call_id"]
        except asyncio.TimeoutError:
            raise FreeSwitchException("Timeout while connecting to FreeSwitch server")
        except aiohttp.ClientError as e:
            raise FreeSwitchException(f"Connection error to FreeSwitch server: {str(e)}")

    async def end_call(self, call_id: str) -> bool:
        """End an active call on FreeSwitch"""
        try:
            async with AsyncRequestor().get_session().post(
                f"{self.freeswitch_config.server_url}/api/calls/{call_id}/hangup",
                headers=self.headers,
                timeout=10,
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(f"Failed to end call: {response.status} {response.reason} {error_text}")
                    return False
                
                response_data = await response.json()
                success = response_data.get("success", False)
                if success:
                    logger.info(f"Successfully ended call with ID: {call_id}")
                return success
        except Exception as e:
            logger.error(f"Error ending call {call_id}: {str(e)}")
            return False
            
    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """Get the status of an active call"""
        try:
            async with AsyncRequestor().get_session().get(
                f"{self.freeswitch_config.server_url}/api/calls/{call_id}",
                headers=self.headers,
                timeout=10,
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(f"Failed to get call status: {response.status} {response.reason} {error_text}")
                    return {"status": "unknown", "error": error_text}
                
                return await response.json()
        except Exception as e:
            logger.error(f"Error getting call status for {call_id}: {str(e)}")
            return {"status": "error", "error": str(e)}
            
    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF tones to an active call"""
        try:
            async with AsyncRequestor().get_session().post(
                f"{self.freeswitch_config.server_url}/api/calls/{call_id}/dtmf",
                headers=self.headers,
                json={"digits": digits},
                timeout=10,
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(f"Failed to send DTMF: {response.status} {response.reason} {error_text}")
                    return False
                
                response_data = await response.json()
                return response_data.get("success", False)
        except Exception as e:
            logger.error(f"Error sending DTMF to call {call_id}: {str(e)}")
            return False
            
    async def get_active_calls(self) -> List[Dict[str, Any]]:
        """Get a list of all active calls"""
        try:
            async with AsyncRequestor().get_session().get(
                f"{self.freeswitch_config.server_url}/api/calls",
                headers=self.headers,
                timeout=10,
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(f"Failed to get active calls: {response.status} {response.reason} {error_text}")
                    return []
                
                response_data = await response.json()
                return response_data.get("calls", [])
        except Exception as e:
            logger.error(f"Error getting active calls: {str(e)}")
            return []