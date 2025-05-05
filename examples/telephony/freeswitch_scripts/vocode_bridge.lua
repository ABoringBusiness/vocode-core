--[[
  vocode_bridge.lua - FreeSwitch script for integrating with Vocode
  
  This script handles the integration between FreeSwitch and Vocode for AI-powered calls.
  
  Usage in dialplan:
  <extension name="vocode_inbound">
    <condition field="destination_number" expression="^(your-number)$">
      <action application="set" data="hangup_after_bridge=true"/>
      <action application="set" data="continue_on_fail=true"/>
      <action application="set" data="vocode_url=https://your-vocode-server/inbound/freeswitch"/>
      <action application="lua" data="vocode_bridge.lua"/>
    </condition>
  </extension>
]]

-- Load required modules
require("json")
require("socket")

-- Get session variables
local vocode_url = session:getVariable("vocode_url")
local caller_id = session:getVariable("caller_id_number")
local destination = session:getVariable("destination_number")
local call_uuid = session:getVariable("uuid")
local record = session:getVariable("record") or "false"

-- Log the call information
freeswitch.consoleLog("info", "Vocode Bridge: Handling call from " .. caller_id .. " to " .. destination .. " (UUID: " .. call_uuid .. ")\n")
freeswitch.consoleLog("info", "Vocode URL: " .. vocode_url .. "\n")

-- Answer the call
session:answer()

-- Play a welcome message
session:streamFile("ivr/ivr-connecting_your_call.wav")

-- Prepare the request to Vocode
local request = {
    call_id = call_uuid,
    from = caller_id,
    to = destination,
    event = "answer",
    record = record == "true"
}

-- Function to handle DTMF
function on_dtmf(session, type, obj, arg)
    freeswitch.consoleLog("info", "DTMF received: " .. obj.digit .. "\n")
    
    -- Send DTMF to Vocode via WebSocket
    if ws then
        local dtmf_json = json.encode({
            type = "dtmf",
            digit = obj.digit,
            call_id = call_uuid
        })
        ws:send(dtmf_json)
    end
    
    -- Special handling for # key (hangup)
    if obj.digit == "#" then
        freeswitch.consoleLog("info", "Hangup requested via DTMF\n")
        session:hangup()
    end
    
    return "true"
end

-- Set DTMF callback
session:setInputCallback("on_dtmf", "")

-- Send the request to Vocode
local request_json = json.encode(request)
freeswitch.consoleLog("debug", "Sending request to Vocode: " .. request_json .. "\n")

local api = freeswitch.API()
local response = api:execute("curl", vocode_url .. " -X POST -d '" .. request_json .. "' -H 'Content-Type: application/json'")

freeswitch.consoleLog("debug", "Received response from Vocode: " .. response .. "\n")

-- Parse the response
local response_data = json.decode(response)

if response_data and response_data.success then
    -- Get the WebSocket URL
    local websocket_url = response_data.websocket_url
    freeswitch.consoleLog("info", "WebSocket URL: " .. websocket_url .. "\n")
    
    -- Connect to the WebSocket for audio streaming
    local audio_fork_cmd = websocket_url .. " mono"
    if record == "true" then
        audio_fork_cmd = audio_fork_cmd .. " record"
    end
    
    session:execute("audio_fork", audio_fork_cmd)
    freeswitch.consoleLog("info", "Audio fork started\n")
    
    -- Wait for the call to end
    while session:ready() do
        session:sleep(1000)
    end
else
    freeswitch.consoleLog("error", "Failed to connect to Vocode\n")
    session:streamFile("ivr/ivr-call_cannot_be_completed_as_dialed.wav")
    session:hangup()
end

-- Log call end
freeswitch.consoleLog("info", "Call ended\n")