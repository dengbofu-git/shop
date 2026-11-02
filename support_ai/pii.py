"""Shared application policy using public LangChain hooks, including non-Agent paths."""

import re
import uuid
from functools import lru_cache
from urllib.parse import parse_qsl, unquote, urlsplit
from langchain_core.messages import HumanMessage


NON_PERSON_SUBJECTS = frozenset(('黄茶','白茶','红茶','绿茶','黑茶','乌龙茶','陈皮','黄山','王老吉'))


def _person_subject(match):
    return match.group() if match.group() in NON_PERSON_SUBJECTS else '[姓名]'


PATTERNS = (
    (re.compile(r'(?:订单号|订单编号|单号)\s*[:：#]?\s*[A-Za-z0-9-]{6,64}'), '[订单号]'),
    (re.compile(r'\border\s*(?:id|number|#)\s*[:：#]?\s*[A-Za-z0-9_-]{6,64}', re.I), '[订单号]'),
    (re.compile(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)'), '[手机号]'),
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'), '[证件号]'),
    (re.compile(r'(?:银行卡号|信用卡号|卡号)\s*[:：]?\s*(?:\d[ -]?){13,19}(?!\d)'), '[敏感号码]'),
    # “联系人工客服” is a support instruction, not a 联系人 name label.
    (re.compile(r'(?:姓名|收货人|联系人(?!工客服)|我叫)\s*[:：是]?\s*(?:[\u4e00-\u9fff]{2,4}?(?=喜欢|想买|想购买|[\s，,。；;]|$)|[\u4e00-\u9fff]{2,4})'), '[姓名]'),
    # Bounded subject + business verb, not general Chinese NER.
    (re.compile(r'(?<![\u4e00-\u9fff])[张李王赵陈刘杨黄周吴徐孙朱胡林何郭马高郑梁谢宋唐许韩邓][\u4e00-\u9fff]{1,2}(?=喜欢|想买|想购买|的手机号|的电话)'), _person_subject),
    (re.compile(r'(?:用户名|账号)\s*[:：是]?\s*[A-Za-z0-9_]{3,32}'), '[账号]'),
    (re.compile(r'(?:(?:收货|联系|详细)?地址|住址)\s*[:：]\s*[^，,。;；\n]{4,80}'), '[地址]'),
    (re.compile(r'[\u4e00-\u9fff]{2,12}(?:省|市|自治区|特别行政区)[\u4e00-\u9fff\d号弄栋室]{4,70}(?:路|街|道|号|室)'), '[地址]'),
)


@lru_cache(maxsize=1)
def _rules():
    # Only public APIs. Import failure must not silently disable detection.
    from langchain.agents.middleware import PIIMiddleware
    return tuple((PIIMiddleware(kind, strategy='redact'), label) for kind,label in (
        ('email','[邮箱]'),('credit_card','[敏感号码]'),('ip','[IP]'),('mac_address','[MAC]')))


def _common_pii(text):
    """Official detectors, with Chinese/ASCII boundary adaptation."""
    result=text
    for middleware,label in _rules():
        def scrub(match):
            chunk=match.group()
            update=middleware.before_model({'messages':[HumanMessage(content=chunk)]},None)
            return update['messages'][0].content.replace('[REDACTED_'+middleware.pii_type.upper()+']',label) if update else chunk
        result=re.sub(r'[^\u4e00-\u9fff]+',scrub,result)
    return result


URL_PRIVATE_KEYS = frozenset(('token','access_token','refresh_token','id_token','api_key','apikey',
    'password','passwd','secret','client_secret','authorization','auth','signature','sig',
    'x-amz-signature','x-amz-credential','x-goog-signature','x-goog-credential',
    'email','phone','mobile','receiver_mobile','address','receiver_address','id_card'))
HTTP_URL = re.compile(r'https?://[^\s<>"\'，。；）)\]}]+',re.I)


def _url_projection(match):
    raw=match.group()
    def private_text(value):
        safe=_common_pii(value)
        for pattern,replacement in PATTERNS:safe=pattern.sub(replacement,safe)
        return safe!=value
    try:
        url=urlsplit(raw)
        if '@' in url.netloc:return '[敏感链接]'
        if private_text(unquote(unquote(url.path))):return '[敏感链接]'
        for component in (url.query,url.fragment.rsplit('?',1)[-1]):
            for key,value in parse_qsl(component,keep_blank_values=True,max_num_fields=100):
                key=unquote(key).casefold()
                value=unquote(value)
                if value and (key in URL_PRIVATE_KEYS or private_text(value)):
                    return '[敏感链接]'
    except ValueError:
        return '[敏感链接]'
    return raw


def _unknown_number(match):
    text=match.string
    # The server's public bundle identity is exactly twelve lowercase hex
    # characters. Only exempt this shape from the *unknown number* fallback;
    # actual phone/card/email detection runs first and still wins.
    for reference in re.finditer(r'(?<![A-Za-z0-9_-])bundle-[a-f0-9]{12}(?![A-Za-z0-9_-])',text):
        if reference.start()<=match.start() and match.end()<=reference.end():
            return match.group()
    before=text[max(0,match.start()-24):match.start()]
    after=text[match.end():match.end()+12]
    number=match.group()
    product=(re.search(r'(?:商品|产品|SKU)\s*(?:编号|编码|ID)?\s*[:：#]?\s*$',before,re.I)
        or (re.search(r'编号\s*[:：#]?\s*$',before) and re.match(r'的?商品',after)))
    money=(re.search(r'(?:预算|价格|金额|CNY|USD|AED|SAR|EUR)\s*[:：]?\s*$',before,re.I)
        or re.match(r'(?:\.\d{1,2})?\s*(?:元|块|CNY|USD|AED|SAR|EUR)',after,re.I))
    return number if (len(number)<=12 and product) or money else '[号码]'


def redact(text, order_ids=()):
    result = text
    for order_id in order_ids:
        if order_id:
            result = result.replace(str(order_id), '[订单号]')
    # Inspect links before generic replacement can destroy their credentials or
    # encoding context. Only local parsing; never fetch a source URL here.
    result=HTTP_URL.sub(_url_projection,result)
    result=_common_pii(result)
    for pattern, replacement in PATTERNS:
        result = pattern.sub(replacement, result)
    result=re.sub(r'(?<!\d)\d{8,24}(?!\d)',_unknown_number,result)
    return result


def contains_pii(text):
    return redact(text) != text


CONTACT_FIELDS = {
    'phone':'[手机号]', 'mobile':'[手机号]', 'receiver_mobile':'[手机号]', '手机号':'[手机号]',
    'email':'[邮箱]', '邮箱':'[邮箱]', 'receiver':'[姓名]', 'recipient':'[姓名]',
    'real_name':'[姓名]', 'full_name':'[姓名]', '收货人':'[姓名]',
    'address':'[地址]', 'receiver_address':'[地址]', '住址':'[地址]',
    'id_card':'[证件号]', 'id_card_number':'[证件号]', '身份证号':'[证件号]',
}


def redact_value(value):
    """Copy JSON-shaped values, preserving numeric amounts and schema keys."""
    if isinstance(value,str):return redact(value)
    if isinstance(value,(tuple,list)):return [redact_value(item) for item in value]
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            # Explicit private contact fields, not generic product name/ID or
            # numeric fields. bool is an int subclass but is not contact text.
            contact=CONTACT_FIELDS.get(key.casefold()) if isinstance(key,str) else None
            if contact and ((isinstance(item,str) and item) or type(item) is int):
                result[key]=contact
                continue
            if key in ('conversation_id','request_id') and isinstance(item,str):
                try:
                    if str(uuid.UUID(item))==item:
                        result[key]=item
                        continue
                except ValueError:pass
            result[key]=redact_value(item)
        return result
    return value


def redact_messages(prompt):
    """Last provider boundary: all roles/content blocks, not only latest human."""
    if isinstance(prompt,str):return redact(prompt)
    messages=prompt.to_messages() if hasattr(prompt,'to_messages') else list(prompt)
    output=[]
    for message in messages:
        if isinstance(message,dict):output.append(redact_value(message));continue
        updates={'content':redact_value(message.content)}
        for field in ('additional_kwargs','tool_calls','invalid_tool_calls'):
            if hasattr(message,field):updates[field]=redact_value(getattr(message,field))
        output.append(message.model_copy(update=updates))
    return output
