import asyncio
import json
from typing import Dict, Optional

import ESL
from loguru import logger

from vocode.streaming.models.telephony import FreeSwitchConfig, TelephonyProviderConfig
from vocode.streaming.telephony.client.abstract_telephony_client import AbstractTelephonyClient


class FreeSwitchClient(AbstractTelephonyClient):
    def __init__(
        self,
        base_url: str,
        maybe_freeswitch_config: Optional[FreeSwitchConfig] = None,
        record_calls: bool = False,
    ):
        super().__init__(base_url)
        self.freeswitch_config = maybe_freeswitch_config
        self.record_calls = record_calls

    def get_telephony_config(self) -> TelephonyProviderConfig:
        if not self.freeswitch_config:
            raise ValueError("FreeSwitchClient not initialized with config")
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
        """Create an outbound call using FreeSWITCH ESL

        Args:
            conversation_id: The ID of the conversation
            to_phone: The phone number to call
            from_phone: The phone number to call from
            record: Whether to record the call
            digits: DTMF digits to send after the call is answered
            telephony_params: Additional parameters to pass to FreeSWITCH

        Returns:
            The UUID of the call
        """
        if not self.freeswitch_config:
            raise ValueError("FreeSwitchClient not initialized with config")

        # Connect to FreeSWITCH ESL
        con = ESL.ESLconnection(
            self.freeswitch_config.host, 
            self.freeswitch_config.port, 
            self.freeswitch_config.password
        )
        
        if not con.connected():
            raise ValueError(f"Failed to connect to FreeSWITCH at {self.freeswitch_config.host}:{self.freeswitch_config.port}")

        # Create the originate command
        originate_cmd = f"originate {{origination_caller_id_number={from_phone}"
        
        # Add recording if requested
        if record or self.record_calls:
            record_path = f"/tmp/vocode_recording_{conversation_id}.wav"
            originate_cmd += f",record_file={record_path}"
        
        # Add any additional parameters
        if telephony_params:
            for key, value in telephony_params.items():
                originate_cmd += f",{key}={value}"
        
        # Add any extra params from the config
        if self.freeswitch_config.extra_params:
            for key, value in self.freeswitch_config.extra_params.items():
                originate_cmd += f",{key}={value}"
        
        # Complete the originate command with destination and application
        originate_cmd += f"}}sofia/external/{to_phone}@example.com &socket({self.base_url}/socket/{conversation_id})"
        
        # Execute the originate command
        e = con.api("originate", originate_cmd)
        
        if e:
            result = e.getBody()
            # Extract UUID from the result
            # The result format is typically "+OK uuid" or an error message
            if result.startswith("+OK"):
                uuid = result.split(" ")[1].strip()
                logger.info(f"Created FreeSWITCH call with UUID: {uuid}")
                return uuid
            else:
                raise ValueError(f"Failed to create call: {result}")
        else:
            raise ValueError("Failed to execute originate command")

    async def end_call(self, id: str) -> bool:
        """End a call using FreeSWITCH ESL

        Args:
            id: The UUID of the call to end

        Returns:
            True if the call was ended successfully, False otherwise
        """
        if not self.freeswitch_config:
            raise ValueError("FreeSwitchClient not initialized with config")

        # Connect to FreeSWITCH ESL
        con = ESL.ESLconnection(
            self.freeswitch_config.host, 
            self.freeswitch_config.port, 
            self.freeswitch_config.password
        )
        
        if not con.connected():
            raise ValueError(f"Failed to connect to FreeSWITCH at {self.freeswitch_config.host}:{self.freeswitch_config.port}")

        # Execute the hangup command
        e = con.api("uuid_kill", id)
        
        if e:
            result = e.getBody()
            # Check if the command was successful
            if result.startswith("+OK"):
                logger.info(f"Ended FreeSWITCH call with UUID: {id}")
                return True
            else:
                logger.error(f"Failed to end call: {result}")
                return False
        else:
            logger.error("Failed to execute hangup command")
            return False

    def create_call_socket_instructions(
        self, conversation_id: str, record: bool = False
    ) -> Dict:
        """Create instructions for FreeSWITCH socket connection

        Args:
            conversation_id: The ID of the conversation
            record: Whether to record the call

        Returns:
            A dictionary with instructions for the FreeSWITCH socket connection
        """
        instructions = {
            "connect_to": f"{self.base_url}/connect_call/{conversation_id}",
            "conversation_id": conversation_id,
        }
        
        if record or self.record_calls:
            instructions["record"] = True
            
        return instructions