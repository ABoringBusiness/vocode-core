import os
from typing import Dict, Optional

import aiohttp
from loguru import logger

from vocode.streaming.models.telephony import TelephonyProviderConfig
from vocode.streaming.telephony.client.abstract_telephony_client import AbstractTelephonyClient


class FreeSwitchConfig(TelephonyProviderConfig):
    type: str = "freeswitch"
    api_url: str
    auth_username: str
    auth_password: str
    record: bool = False


class FreeSwitchBadRequestException(ValueError):
    pass


class FreeSwitchException(ValueError):
    pass


class FreeSwitchClient(AbstractTelephonyClient):
    def __init__(
        self,
        base_url: str,
        maybe_freeswitch_config: Optional[FreeSwitchConfig] = None,
    ):
        self.freeswitch_config = maybe_freeswitch_config or FreeSwitchConfig(
            api_url=os.environ["FREESWITCH_API_URL"],
            auth_username=os.environ["FREESWITCH_AUTH_USERNAME"],
            auth_password=os.environ["FREESWITCH_AUTH_PASSWORD"],
        )
        self.auth = aiohttp.BasicAuth(
            login=self.freeswitch_config.auth_username,
            password=self.freeswitch_config.auth_password,
        )
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
        """
        Initiates a call using FreeSWITCH API
        Returns the UUID of the call
        """
        data = {
            "to": f"+{to_phone}",
            "from": f"+{from_phone}",
            "conversation_id": conversation_id,
            "callback_url": f"{self.base_url}/connect_call/{conversation_id}",
            "record": record,
            **(telephony_params or {}),
        }
        
        if digits:
            data["send_digits"] = digits
            
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.freeswitch_config.api_url}/originate",
                auth=self.auth,
                json=data,
            ) as response:
                if not response.ok:
                    if response.status == 400:
                        logger.warning(
                            f"Failed to create call: {response.status} {response.reason} {await response.json()}"
                        )
                        raise FreeSwitchBadRequestException(
                            "Telephony provider rejected call; this is usually due to a bad/malformed number."
                        )
                    else:
                        raise FreeSwitchException(
                            f"FreeSWITCH failed to create call: {response.status} {response.reason}"
                        )
                response_json = await response.json()
                return response_json["uuid"]

    async def end_call(self, call_uuid):
        """
        Ends a call using FreeSWITCH API
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.freeswitch_config.api_url}/hangup",
                auth=self.auth,
                json={"uuid": call_uuid},
            ) as response:
                if not response.ok:
                    raise RuntimeError(f"Failed to end call: {response.status} {response.reason}")
                response_json = await response.json()
                return response_json.get("success", False)