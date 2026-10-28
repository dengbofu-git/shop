"""Local redaction before any customer text reaches an external model."""

import re


PATTERNS = (
    (re.compile(r'(?<!\w)[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)'), '[邮箱]'),
    (re.compile(r'(?:订单号|订单编号|单号)\s*[:：#]?\s*[A-Za-z0-9-]{6,64}'), '[订单号]'),
    (re.compile(r'\border\s*(?:id|number|#)\s*[:：#]?\s*[A-Za-z0-9_-]{6,64}', re.I), '[订单号]'),
    (re.compile(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)'), '[手机号]'),
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'), '[证件号]'),
    (re.compile(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)'), '[敏感号码]'),
    (re.compile(r'(?<!\d)\d{8,24}(?!\d)'), '[号码]'),
    # “联系人工客服” is a support instruction, not a 联系人 name label.
    (re.compile(r'(?:姓名|收货人|联系人(?!工客服)|我叫)\s*[:：是]?\s*[\u4e00-\u9fff]{2,4}'), '[姓名]'),
    (re.compile(r'(?:用户名|账号)\s*[:：是]?\s*[A-Za-z0-9_]{3,32}'), '[账号]'),
    (re.compile(r'(?:(?:收货|联系|详细)?地址|住址)\s*[:：]\s*[^，,。;；\n]{4,80}'), '[地址]'),
    (re.compile(r'[\u4e00-\u9fff]{2,12}(?:省|市|自治区|特别行政区)[\u4e00-\u9fff\d号弄栋室]{4,70}(?:路|街|道|号|室)'), '[地址]'),
)


def redact(text, order_ids=()):
    result = text
    for order_id in order_ids:
        if order_id:
            result = result.replace(str(order_id), '[订单号]')
    for pattern, replacement in PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def contains_pii(text):
    return redact(text) != text
