import os
from typing import Dict, Optional, List, Any
import asyncio
import uuid

import aiohttp
from loguru import logger

from vocode.streaming.models.telephony import TelephonyProviderConfig
from vocode.streaming.telephony.client.abstract_telephony_client import AbstractTelephonyClient
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchConfig

try:
    import ESL
except ImportError:
    logger.warning("ESL module not found. Install with 'pip install python-ESL' to use FreeSwitchESLClient.")
    ESL = None


class FreeSwitchESLConfig(FreeSwitchConfig):
    """Configuration for FreeSwitchESLClient"""
    esl_host: str = "localhost"
    esl_port: int = 8021
    esl_password: str = "ClueCon"
    esl_timeout: int = 30


class FreeSwitchESLClient(AbstractTelephonyClient):
    """
    FreeSWITCH client using Event Socket Library (ESL) for direct communication
    with FreeSWITCH server.
    """
    def __init__(
        self,
        base_url: str,
        maybe_freeswitch_config: Optional[FreeSwitchESLConfig] = None,
    ):
        if ESL is None:
            raise ImportError("ESL module not found. Install with 'pip install python-ESL'")
            
        self.freeswitch_config = maybe_freeswitch_config or FreeSwitchESLConfig(
            api_url=os.environ.get("FREESWITCH_API_URL", "http://localhost:8080"),
            auth_username=os.environ.get("FREESWITCH_AUTH_USERNAME", "freeswitch"),
            auth_password=os.environ.get("FREESWITCH_AUTH_PASSWORD", "password"),
            esl_host=os.environ.get("FREESWITCH_ESL_HOST", "localhost"),
            esl_port=int(os.environ.get("FREESWITCH_ESL_PORT", 8021)),
            esl_password=os.environ.get("FREESWITCH_ESL_PASSWORD", "ClueCon"),
        )
        super().__init__(base_url=base_url)
        self._esl_con = None

    def get_telephony_config(self):
        return self.freeswitch_config

    async def _get_esl_connection(self):
        """Get an ESL connection, creating one if needed"""
        if self._esl_con is None or not self._esl_con.connected():
            self._esl_con = ESL.ESLconnection(
                self.freeswitch_config.esl_host,
                self.freeswitch_config.esl_port,
                self.freeswitch_config.esl_password
            )
            
            if not self._esl_con.connected():
                raise ConnectionError(
                    f"Failed to connect to FreeSWITCH ESL at {self.freeswitch_config.esl_host}:{self.freeswitch_config.esl_port}"
                )
                
            logger.info(f"Connected to FreeSWITCH ESL at {self.freeswitch_config.esl_host}:{self.freeswitch_config.esl_port}")
            
        return self._esl_con

    async def _execute_esl_command(self, command: str) -> Dict[str, Any]:
        """Execute a command via ESL and return the result"""
        esl_con = await self._get_esl_connection()
        
        # Execute the command
        e = esl_con.api(command)
        if not e:
            raise RuntimeError(f"Failed to execute ESL command: {command}")
            
        # Parse the result
        result = {
            "body": e.getBody(),
            "success": e.getBody().strip().lower() != "-err"
        }
        
        return result

    async def create_call(
        self,
        conversation_id: str,
        to_phone: str,
        from_phone: str,
        record: bool = False,
        digits: Optional[str] = None,
        telephony_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Initiates a call using FreeSWITCH ESL
        Returns the UUID of the call
        """
        # Format the originate command
        callback_url = f"ws://{self.base_url}/connect_call/{conversation_id}"
        
        # Build the originate command
        originate_cmd = (
            f"originate {{origination_uuid={conversation_id},origination_caller_id_number=+{from_phone},"
            f"ignore_early_media=true,absolute_codec_string=PCMU,record={str(record).lower()}"
        )
        
        # Add any additional telephony parameters
        if telephony_params:
            for key, value in telephony_params.items():
                originate_cmd += f",{key}={value}"
                
        # Complete the command with destination and socket info
        originate_cmd += f"}}sofia/external/+{to_phone}@your-sip-provider.com "
        originate_cmd += f"&socket('{callback_url}')"
        
        # Add digits if specified
        if digits:
            originate_cmd += f" {digits}"
            
        logger.info(f"Executing originate command: {originate_cmd}")
        
        try:
            result = await self._execute_esl_command(originate_cmd)
            
            if not result["success"]:
                error_msg = result["body"]
                logger.error(f"Failed to create call: {error_msg}")
                raise RuntimeError(f"Failed to create call: {error_msg}")
                
            # The UUID should be in the response or we use the conversation_id
            call_uuid = conversation_id
            logger.info(f"Call created with UUID: {call_uuid}")
            return call_uuid
            
        except Exception as e:
            logger.error(f"Error creating call: {str(e)}")
            raise

    async def end_call(self, call_uuid: str) -> bool:
        """
        Ends a call using FreeSWITCH ESL
        """
        try:
            result = await self._execute_esl_command(f"uuid_kill {call_uuid}")
            return result["success"]
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}")
            raise

    async def subscribe_to_call_events(self, callback):
        """
        Subscribe to call events from FreeSWITCH
        
        Args:
            callback: Async function to call with event data
        """
        esl_con = await self._get_esl_connection()
        
        # Subscribe to relevant events
        events = [
            "CHANNEL_CREATE", 
            "CHANNEL_ANSWER", 
            "CHANNEL_HANGUP", 
            "CHANNEL_HANGUP_COMPLETE",
            "DTMF"
        ]
        
        for event in events:
            esl_con.events("plain", event)
        
        # Start event listener loop
        async def event_listener():
            while True:
                e = esl_con.recvEvent()
                if e:
                    event_name = e.getHeader("Event-Name")
                    event_data = {
                        "name": event_name,
                        "uuid": e.getHeader("Unique-ID"),
                        "timestamp": e.getHeader("Event-Date-Timestamp"),
                    }
                    
                    # Add event-specific data
                    if event_name == "DTMF":
                        event_data["digit"] = e.getHeader("DTMF-Digit")
                    elif event_name in ["CHANNEL_HANGUP", "CHANNEL_HANGUP_COMPLETE"]:
                        event_data["hangup_cause"] = e.getHeader("Hangup-Cause")
                    
                    # Call the callback with the event data
                    await callback(event_data)
                
                # Small sleep to prevent CPU hogging
                await asyncio.sleep(0.01)
        
        # Start the listener in the background
        asyncio.create_task(event_listener())
        
        return True