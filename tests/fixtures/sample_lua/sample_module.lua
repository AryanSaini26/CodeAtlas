-- Lua sample module for CodeAtlas tests

local M = {}

-- Format a greeting message
function M.greet(name)
    return "Hello, " .. name .. "!"
end

-- Compute the sum of two numbers
function M.add(a, b)
    return a + b
end

-- Top-level helper function
function process(items)
    M.greet("world")
    M.add(1, 2)
end

-- Local helper function
local function helper(x)
    return x * 2
end

-- Variable assigned to a function
local transform = function(data)
    return helper(data)
end

-- Configuration table (not a function)
local config = {
    debug = false,
    version = "1.0.0",
}

return M
