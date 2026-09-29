--[[ Sewars -- talking between clients and the server.

    pz_trekship's TREK_Net.lua, whose findings stand (checked against the
    bytecode there):

      * sendClientCommand reaches OnClientCommand on the server -- and in
        single player too, through the game's in-process server. So a client
        always sends and the server always handles.
      * sendServerCommand does nothing in single player. The reply path is the
        one place that needs a branch, and it lives here.

    Commands are plain tables of numbers, strings and booleans. The server
    validates every one: a client is a request, never a fact.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"

SEW = SEW or {}
local U = SEW.Util

local Net = {}
SEW.Net = Net

Net.MODULE = "Sewars"
Net.serverHandlers = {}
Net.clientHandlers = {}

function Net.send(player, cmd, args)
    if not player then return false end
    return U.try("send:" .. tostring(cmd), function()
        sendClientCommand(player, Net.MODULE, cmd, args or {})
        return true
    end) == true
end

--- One handler per message, and a second registration is a bug, not a
--- replacement: it would silently disconnect the first (it nearly did, the map's
--- `found` and the journal's).
function Net.onServer(cmd, fn)
    if Net.serverHandlers[cmd] then U.warnOnce("dupServer:" .. cmd, "second server handler for " .. cmd) end
    Net.serverHandlers[cmd] = Net.serverHandlers[cmd] or fn
end
function Net.onClient(cmd, fn)
    if Net.clientHandlers[cmd] then U.warnOnce("dupClient:" .. cmd, "second client handler for " .. cmd) end
    Net.clientHandlers[cmd] = Net.clientHandlers[cmd] or fn
end

local function runClient(cmd, args)
    local handler = Net.clientHandlers[cmd]
    if handler then U.try("reply:" .. tostring(cmd), handler, args or {}) end
end

--- Tells one player's client something. In single player there is no network
--- to send over, so the handler runs directly.
function Net.toClient(player, cmd, args)
    if isServer() then
        U.try("sendServerCommand:" .. tostring(cmd), function()
            sendServerCommand(player, Net.MODULE, cmd, args or {})
        end)
    else
        runClient(cmd, args)
    end
end

Events.OnClientCommand.Add(function(module, cmd, player, args)
    if module ~= Net.MODULE or isClient() then return end
    local handler = Net.serverHandlers[cmd]
    if not handler then
        U.warnOnce("unknownCommand:" .. tostring(cmd), "unknown command " .. tostring(cmd))
        return
    end
    U.try("command:" .. tostring(cmd), handler, player, args or {})
end)

Events.OnServerCommand.Add(function(module, cmd, args)
    if module ~= Net.MODULE then return end
    runClient(cmd, args)
end)

return Net
