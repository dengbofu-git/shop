"""Versioned cart rows: monotonic cursors make delayed consumption idempotent."""
import json
import uuid

LUA_STATE = r'''
local function normalize(row, generation)
    local count = tonumber(row.count)
    if not count or count < 0 or count ~= math.floor(count) then error('INVALID_CART') end
    if not row.generation then
        row.generation = generation
        row.version = 1
        row.added = count
        row.removed = 0
    end
    if type(row.generation) ~= 'string' or not tonumber(row.version)
       or not tonumber(row.added) or not tonumber(row.removed)
       or row.added < row.removed or row.removed < 0
       or row.added - row.removed ~= count then error('INVALID_CART') end
    row.count = count
    return row
end
'''

SNAPSHOT_SCRIPT = LUA_STATE + r'''
local values = redis.call('HGETALL', KEYS[1])
local result = {}
local updates = {}
for i=1,#values,2 do
    local row = normalize(cjson.decode(values[i+1]), ARGV[1] .. '-' .. values[i])
    local encoded = cjson.encode(row)
    table.insert(updates, {values[i],encoded})
    result[values[i]] = encoded
end
for _,entry in ipairs(updates) do redis.call('HSET',KEYS[1],entry[1],entry[2]) end
return cjson.encode(result)
'''


def checkout_snapshot(conn, username):
    # Validate legacy values before entering Lua; malformed requests never mutate rows.
    for raw in conn.hgetall('carts_' + username).values():
        row = json.loads(raw)
        if not isinstance(row, dict) or isinstance(row.get('count'), bool) or not isinstance(row.get('status', True), bool):
            raise ValueError('Invalid cart')
        count = str(row.get('count', ''))
        if not count.isascii() or not count.isdigit() or not 1 <= int(count) <= 999999999:
            raise ValueError('Invalid cart')
    return json.loads(conn.eval(SNAPSHOT_SCRIPT, 1, 'carts_' + username, uuid.uuid4().hex))


def edit_row(before, after):
    original = json.loads(before)
    updated = json.loads(after)
    count = int(original['count'])
    if not original.get('generation'):
        original.update(generation=uuid.uuid4().hex, version=0, added=count, removed=0)
    delta = int(updated['count']) - count
    original['added'] += max(0, delta)
    original['removed'] += max(0, -delta)
    original.update(count=int(updated['count']), status=updated.get('status', True),
                    version=int(original['version']) + 1)
    return json.dumps(original)


CLEAN_SCRIPT = LUA_STATE + r'''
local raw = redis.call('HGET',KEYS[1],ARGV[1])
if not raw then return 'missing' end
local row = cjson.decode(raw)
if row.generation ~= ARGV[2] then return 'superseded' end
row = normalize(row,ARGV[2])
local target = tonumber(ARGV[3])
if target > row.added then error('INVALID_CONSUMPTION') end
if row.removed >= target then return 'already_applied' end
row.removed = target
row.count = row.added - row.removed
row.version = row.version + 1
if row.count == 0 then redis.call('HDEL',KEYS[1],ARGV[1])
else redis.call('HSET',KEYS[1],ARGV[1],cjson.encode(row)) end
return 'consumed'
'''
