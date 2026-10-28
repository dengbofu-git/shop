"""Redis原子追加：先校验全部行，再写入；幂等只绑定当前买家和请求内容。"""
import hashlib
import json


class CartError(ValueError):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


def request_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def receipt_key(username, operation):
    return 'cart-add-receipt:%s:%s' % (username, operation)


def previous_receipt(conn, username, operation, fingerprint):
    value = conn.get(receipt_key(username, operation))
    if not value:
        return None
    record = json.loads(value)
    if record['fingerprint'] != fingerprint:
        raise CartError('同一操作标识不能用于不同商品或数量')
    return dict(record['result'], replayed=True)


ADD_SCRIPT = r'''
local previous = redis.call('GET', KEYS[2])
if previous then
    local old = cjson.decode(previous)
    if old.fingerprint ~= ARGV[1] then return cjson.encode({error='REQUEST_CONFLICT'}) end
    old.result.replayed = true
    return cjson.encode(old.result)
end
local kind = redis.call('TYPE', KEYS[1]).ok
if kind ~= 'none' and kind ~= 'hash' then return cjson.encode({error='INVALID_CART'}) end
local items = cjson.decode(ARGV[2])
local updates = {}
for _, item in ipairs(items) do
    local old = redis.call('HGET', KEYS[1], item.sku_id)
    local count = 0
    local selected = true
    if old then
        local ok, decoded = pcall(cjson.decode, old)
        if not ok or type(decoded) ~= 'table' or not tonumber(decoded.count) then
            return cjson.encode({error='INVALID_CART'})
        end
        count = tonumber(decoded.count)
        if count < 0 or count ~= math.floor(count) then return cjson.encode({error='INVALID_CART'}) end
        if decoded.status ~= nil then selected = decoded.status end
    end
    local total = count + item.count
    if total > item.available_stock then return cjson.encode({error='STOCK_CHANGED'}) end
    table.insert(updates, {sku_id=item.sku_id, value=cjson.encode({count=total,status=selected})})
end
for _, item in ipairs(updates) do redis.call('HSET', KEYS[1], item.sku_id, item.value) end
local result = {code=200,data={carts_count=redis.call('HLEN',KEYS[1]),added_count=#updates},replayed=false}
redis.call('SET',KEYS[2],cjson.encode({fingerprint=ARGV[1],result=result}),'EX',86400)
return cjson.encode(result)
'''


def add_items(conn, username, operation, fingerprint, items):
    # 本项目使用独立Redis服务；所有键均由服务端身份构造，不接受外部键名。
    result = json.loads(conn.eval(ADD_SCRIPT, 2, 'carts_' + username,
                                 receipt_key(username, operation), fingerprint, json.dumps(items)))
    if result.get('error'):
        raise CartError({'REQUEST_CONFLICT': '同一操作标识不能用于不同商品或数量',
                         'STOCK_CHANGED': '采购车累计数量超过当前可售库存，本次未添加',
                         'INVALID_CART': '采购车数据异常，本次未添加'}[result['error']])
    return result

CAS_SCRIPT = r'''
if redis.call('HGET',KEYS[1],ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('HSET',KEYS[1],ARGV[1],ARGV[3])
return 1
'''


def compare_set(conn, key, field, before, after):
    """旧采购车编辑不得以过期快照覆盖并发加入后的数量。"""
    return bool(conn.eval(CAS_SCRIPT, 1, key, str(field), before, after))
