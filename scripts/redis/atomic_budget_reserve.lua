-- Atomic budget reservation script for Redis
-- Inputs: KEYS[1] = tenant_budget_key (e.g., "llm_budget:tenant_123")
--         KEYS[2] = tenant_budget_limit_key (e.g., "llm_budget_limit:tenant_123")
--         ARGV[1] = amount to reserve (numeric string)
-- Returns: 1 if reservation successful, 0 if budget exceeded

local budget_key = KEYS[1]
local limit_key = KEYS[2]
local amount = tonumber(ARGV[1])

-- Get current reserved amount (default to 0 if key doesn't exist)
local current_reserved = tonumber(redis.call('GET', budget_key) or '0')

-- Get budget limit
local budget_limit = tonumber(redis.call('GET', limit_key) or '0')

-- Check if reservation would exceed budget
if current_reserved + amount > budget_limit then
    return 0  -- Budget exceeded
end

-- Atomically increment the reserved amount
redis.call('INCRBYFLOAT', budget_key, amount)
return 1  -- Success