"""Private, ephemeral displayed-page binding. Never expose its contents to models."""
import json
from django.utils.crypto import salted_hmac
from django_redis import get_redis_connection
from .models import SupportTurn

TTL = 86400


def key(owner, conversation):
    return 'support-order-page:' + salted_hmac('support-order-page-v1', str(owner)+':'+str(conversation)).hexdigest()


SAVE = '''
local old=redis.call('GET',KEYS[1])
if old and tonumber(cjson.decode(old).revision)>=tonumber(ARGV[1]) then return 0 end
redis.call('SET',KEYS[1],ARGV[2],'EX',86400)
return 1
'''


def publish(owner, conversation, revision, page):
    try:
        ids = page['ids']
        if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(i,str) or len(i)>64 for i in ids):
            return
        payload=dict(page,owner=owner,conversation=str(conversation),revision=revision)
        get_redis_connection('default').eval(SAVE,1,key(owner,conversation),revision,json.dumps(payload))
    except Exception:
        # No contents or transport exception text in logs; normal queries remain usable.
        pass


def load(owner, conversation):
    if conversation is None:return None
    try:
        raw=get_redis_connection('default').get(key(owner,conversation))
        if not raw:return None
        page=json.loads(raw)
        latest=SupportTurn.objects.filter(user_id=owner,conversation_id=conversation,
            response__has_key='order_result').order_by('-sequence').values_list('sequence',flat=True).first()
        if page['owner']!=owner or page['conversation']!=str(conversation) or page['revision']!=latest:
            return None
        if not isinstance(page['ids'],list) or not 0<len(page['ids'])<=20:return None
        return page
    except Exception:
        return None
