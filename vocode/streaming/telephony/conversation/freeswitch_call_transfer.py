import asyncio
from enum import Enum
from typing import Dict, List, Optional, Union
import uuid
import time
from loguru import logger

from vocode.streaming.models.events import PhoneCallTransferredEvent
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.telephony.client.freeswitch_esl_client import FreeSwitchESLClient


class TransferType(str, Enum):
    BLIND = "blind"
    ATTENDED = "attended"
    WARM = "warm"


class CallTransferManager:
    """
    Manages call transfers for FreeSWITCH conversations.
    Supports different types of transfers:
    - Blind transfer: Immediately transfers the call without waiting
    - Attended transfer: Calls the destination first, then transfers when answered
    - Warm transfer: Calls the destination, allows conversation, then completes transfer
    """

    def __init__(
        self,
        call_uuid: str,
        client: Union[FreeSwitchClient, FreeSwitchESLClient],
        conversation_id: str,
        event_publisher=None,
    ):
        self.call_uuid = call_uuid
        self.client = client
        self.conversation_id = conversation_id
        self.event_publisher = event_publisher
        self.transfer_in_progress = False
        self.transfer_destination = None
        self.transfer_type = None
        self.transfer_start_time = None
        self.transfer_leg_uuid = None

    async def transfer_call(
        self,
        destination: str,
        transfer_type: TransferType = TransferType.BLIND,
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
        if self.transfer_in_progress:
            logger.warning(f"Transfer already in progress for call {self.call_uuid}")
            return False
            
        self.transfer_in_progress = True
        self.transfer_destination = destination
        self.transfer_type = transfer_type
        self.transfer_start_time = time.time()
        
        headers = transfer_headers or {}
        if caller_id:
            headers["origination_caller_id_number"] = caller_id
            
        try:
            if transfer_type == TransferType.BLIND:
                # Blind transfer - just send the call to the destination
                success = await self._execute_blind_transfer(destination, headers)
                
            elif transfer_type == TransferType.ATTENDED:
                # Attended transfer - call destination first, then transfer
                success = await self._execute_attended_transfer(
                    destination, headers, timeout_seconds
                )
                
            elif transfer_type == TransferType.WARM:
                # Warm transfer - call destination, allow conversation, then complete transfer
                success = await self._execute_warm_transfer(
                    destination, headers, timeout_seconds
                )
                
            else:
                logger.error(f"Unknown transfer type: {transfer_type}")
                self.transfer_in_progress = False
                return False
                
            # Publish transfer event
            if success and self.event_publisher:
                await self.event_publisher.publish(
                    PhoneCallTransferredEvent(
                        conversation_id=self.conversation_id,
                        destination=destination,
                        transfer_type=transfer_type,
                        success=success,
                    )
                )
                
            return success
            
        except Exception as e:
            logger.error(f"Error transferring call {self.call_uuid}: {e}")
            self.transfer_in_progress = False
            return False
            
    async def _execute_blind_transfer(
        self, destination: str, headers: Dict[str, str]
    ) -> bool:
        """Execute a blind transfer"""
        try:
            # For FreeSWITCH, we use the transfer API command
            if isinstance(self.client, FreeSwitchESLClient):
                # ESL client - use direct ESL command
                result = await self.client.execute_esl_command(
                    f"uuid_transfer {self.call_uuid} {destination} inline"
                )
                success = "success" in result.lower() or "ok" in result.lower()
            else:
                # HTTP client - use API endpoint
                result = await self.client.execute_api_command(
                    "uuid_transfer",
                    [self.call_uuid, destination, "inline"],
                    headers
                )
                success = result.get("success", False)
                
            logger.info(f"Blind transfer to {destination}: {'Success' if success else 'Failed'}")
            self.transfer_in_progress = False
            return success
            
        except Exception as e:
            logger.error(f"Error in blind transfer: {e}")
            self.transfer_in_progress = False
            return False
            
    async def _execute_attended_transfer(
        self, destination: str, headers: Dict[str, str], timeout_seconds: int
    ) -> bool:
        """Execute an attended transfer"""
        try:
            # Create a new call leg to the destination
            self.transfer_leg_uuid = str(uuid.uuid4())
            
            # Originate a call to the destination
            if isinstance(self.client, FreeSwitchESLClient):
                # ESL client - use direct ESL command
                originate_cmd = (
                    f"originate {{origination_uuid={self.transfer_leg_uuid}"
                )
                
                # Add any custom headers
                for key, value in headers.items():
                    originate_cmd += f",{key}={value}"
                    
                originate_cmd += f"}}user/{destination} &park()"
                
                result = await self.client.execute_esl_command(originate_cmd)
                success = self.transfer_leg_uuid in result
                
            else:
                # HTTP client - use API endpoint
                originate_params = {
                    "origination_uuid": self.transfer_leg_uuid,
                    **headers
                }
                result = await self.client.execute_api_command(
                    "originate",
                    [f"user/{destination}", "&park()"],
                    originate_params
                )
                success = result.get("success", False)
                
            if not success:
                logger.error(f"Failed to originate call to {destination}")
                self.transfer_in_progress = False
                return False
                
            # Wait for the destination to answer
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                # Check if the call was answered
                if isinstance(self.client, FreeSwitchESLClient):
                    result = await self.client.execute_esl_command(
                        f"uuid_getvar {self.transfer_leg_uuid} answer_state"
                    )
                    if "answered" in result.lower():
                        break
                else:
                    result = await self.client.execute_api_command(
                        "uuid_getvar",
                        [self.transfer_leg_uuid, "answer_state"]
                    )
                    if result.get("result") == "answered":
                        break
                        
                await asyncio.sleep(0.5)
            else:
                # Timeout waiting for answer
                logger.warning(f"Timeout waiting for {destination} to answer")
                
                # Hangup the transfer leg
                if isinstance(self.client, FreeSwitchESLClient):
                    await self.client.execute_esl_command(
                        f"uuid_kill {self.transfer_leg_uuid}"
                    )
                else:
                    await self.client.execute_api_command(
                        "uuid_kill",
                        [self.transfer_leg_uuid]
                    )
                    
                self.transfer_in_progress = False
                return False
                
            # Destination answered, now bridge the calls
            if isinstance(self.client, FreeSwitchESLClient):
                result = await self.client.execute_esl_command(
                    f"uuid_bridge {self.call_uuid} {self.transfer_leg_uuid}"
                )
                success = "success" in result.lower() or "ok" in result.lower()
            else:
                result = await self.client.execute_api_command(
                    "uuid_bridge",
                    [self.call_uuid, self.transfer_leg_uuid]
                )
                success = result.get("success", False)
                
            logger.info(f"Attended transfer to {destination}: {'Success' if success else 'Failed'}")
            self.transfer_in_progress = False
            return success
            
        except Exception as e:
            logger.error(f"Error in attended transfer: {e}")
            self.transfer_in_progress = False
            return False
            
    async def _execute_warm_transfer(
        self, destination: str, headers: Dict[str, str], timeout_seconds: int
    ) -> bool:
        """Execute a warm transfer (three-way call then transfer)"""
        try:
            # Create a new call leg to the destination
            self.transfer_leg_uuid = str(uuid.uuid4())
            
            # Originate a call to the destination
            if isinstance(self.client, FreeSwitchESLClient):
                # ESL client - use direct ESL command
                originate_cmd = (
                    f"originate {{origination_uuid={self.transfer_leg_uuid}"
                )
                
                # Add any custom headers
                for key, value in headers.items():
                    originate_cmd += f",{key}={value}"
                    
                originate_cmd += f"}}user/{destination} &conference({self.conversation_id})"
                
                result = await self.client.execute_esl_command(originate_cmd)
                success = self.transfer_leg_uuid in result
                
            else:
                # HTTP client - use API endpoint
                originate_params = {
                    "origination_uuid": self.transfer_leg_uuid,
                    **headers
                }
                result = await self.client.execute_api_command(
                    "originate",
                    [f"user/{destination}", f"&conference({self.conversation_id})"],
                    originate_params
                )
                success = result.get("success", False)
                
            if not success:
                logger.error(f"Failed to originate call to {destination}")
                self.transfer_in_progress = False
                return False
                
            # Add the original call to the conference
            if isinstance(self.client, FreeSwitchESLClient):
                result = await self.client.execute_esl_command(
                    f"uuid_transfer {self.call_uuid} conference:{self.conversation_id} inline"
                )
                success = "success" in result.lower() or "ok" in result.lower()
            else:
                result = await self.client.execute_api_command(
                    "uuid_transfer",
                    [self.call_uuid, f"conference:{self.conversation_id}", "inline"]
                )
                success = result.get("success", False)
                
            if not success:
                logger.error(f"Failed to add original call to conference")
                
                # Hangup the transfer leg
                if isinstance(self.client, FreeSwitchESLClient):
                    await self.client.execute_esl_command(
                        f"uuid_kill {self.transfer_leg_uuid}"
                    )
                else:
                    await self.client.execute_api_command(
                        "uuid_kill",
                        [self.transfer_leg_uuid]
                    )
                    
                self.transfer_in_progress = False
                return False
                
            logger.info(f"Warm transfer to {destination} successful - in conference {self.conversation_id}")
            
            # The transfer is technically successful at this point, but we keep it marked as in progress
            # since the agent needs to complete the transfer by calling complete_warm_transfer()
            return True
            
        except Exception as e:
            logger.error(f"Error in warm transfer: {e}")
            self.transfer_in_progress = False
            return False
            
    async def complete_warm_transfer(self) -> bool:
        """
        Complete a warm transfer by removing the original agent from the conference
        and leaving just the caller and the transfer destination
        """
        if not self.transfer_in_progress or self.transfer_type != TransferType.WARM:
            logger.warning("No warm transfer in progress to complete")
            return False
            
        try:
            # Remove the original call from the conference
            if isinstance(self.client, FreeSwitchESLClient):
                result = await self.client.execute_esl_command(
                    f"conference {self.conversation_id} kick {self.call_uuid}"
                )
                success = "success" in result.lower() or "ok" in result.lower()
            else:
                result = await self.client.execute_api_command(
                    "conference",
                    [self.conversation_id, "kick", self.call_uuid]
                )
                success = result.get("success", False)
                
            logger.info(f"Completed warm transfer: {'Success' if success else 'Failed'}")
            self.transfer_in_progress = False
            return success
            
        except Exception as e:
            logger.error(f"Error completing warm transfer: {e}")
            self.transfer_in_progress = False
            return False
            
    async def cancel_transfer(self) -> bool:
        """
        Cancel an in-progress transfer
        """
        if not self.transfer_in_progress:
            return True  # Nothing to cancel
            
        try:
            if self.transfer_leg_uuid:
                # Hangup the transfer leg
                if isinstance(self.client, FreeSwitchESLClient):
                    await self.client.execute_esl_command(
                        f"uuid_kill {self.transfer_leg_uuid}"
                    )
                else:
                    await self.client.execute_api_command(
                        "uuid_kill",
                        [self.transfer_leg_uuid]
                    )
                    
            # If it was a warm transfer, make sure the original call is taken out of the conference
            if self.transfer_type == TransferType.WARM:
                if isinstance(self.client, FreeSwitchESLClient):
                    await self.client.execute_esl_command(
                        f"uuid_transfer {self.call_uuid} 'hangup:NORMAL_CLEARING' inline"
                    )
                else:
                    await self.client.execute_api_command(
                        "uuid_transfer",
                        [self.call_uuid, "hangup:NORMAL_CLEARING", "inline"]
                    )
                    
            self.transfer_in_progress = False
            return True
            
        except Exception as e:
            logger.error(f"Error canceling transfer: {e}")
            self.transfer_in_progress = False
            return False