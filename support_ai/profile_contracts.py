"""Bounded preference proposals; identity and event time are application-owned."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .pii import contains_pii
from .catalog_terms import CATEGORY_ALIASES


MAX_PROFILE_MESSAGE_CHARS = 6000
MAX_PROFILE_CANDIDATES = 6
_PRIVATE_PLACEHOLDER = re.compile(
    r'\[(?:姓名|手机号|证件号|敏感号码|订单号|账号|地址|邮箱|IP|MAC|号码|敏感链接|REDACTED[^\]]*)\]', re.I)
_FACT_VALUE = re.compile(
    r'订单|订单号|身份证|银行卡|手机号|收货地址|用户名|账号|password|api[_ -]?key|'
    r'^(?:\d+(?:\.\d+)?\s*(?:元|块钱?|CNY|USD|AED|SAR|EUR)|https?://)', re.I)


def normalize_value(value: str) -> str:
    """Normalize presentation, without translating or inventing catalog aliases."""
    if type(value) is not str:
        raise ValueError('Preference values must be strings')
    if any(unicodedata.category(char).startswith('C') for char in value):
        raise ValueError('Preference values cannot contain control characters')
    return ' '.join(unicodedata.normalize('NFKC', value).split())


def normalized_key(kind: str, value: str) -> str:
    if kind not in ('category', 'brand', 'keyword'):
        raise ValueError('Unknown preference type')
    key = normalize_value(value).casefold()
    if kind == 'category':
        key = CATEGORY_ALIASES.get(key, key).casefold()
    return kind + ':' + key


class PreferenceCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    type: Literal['category', 'brand', 'keyword']
    value: str = Field(min_length=1, max_length=40)
    polarity: Literal['like', 'hate']
    scope: Literal['long_term', 'current_turn']
    quote: str = Field(min_length=1, max_length=240)

    @field_validator('value')
    @classmethod
    def safe_value(cls, value):
        value = normalize_value(value)
        if (not value or len(value) > 40 or contains_pii(value)
                or _PRIVATE_PLACEHOLDER.search(value) or _FACT_VALUE.search(value)):
            raise ValueError('Only non-private shopping preference terms are allowed')
        return value

    @field_validator('quote')
    @classmethod
    def safe_quote(cls, value):
        if (not value.strip() or contains_pii(value) or _PRIVATE_PLACEHOLDER.search(value)
                or any(unicodedata.category(char).startswith('C') for char in value)):
            raise ValueError('Preference quotes must be bounded non-private source fragments')
        return value


class PreferenceExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    candidates: list[PreferenceCandidate] = Field(default_factory=list, max_length=MAX_PROFILE_CANDIDATES)
