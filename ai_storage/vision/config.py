"""独立视觉配置；任务只保存不含密钥的快照。"""
from dataclasses import asdict, dataclass
import math
import os
from urllib.parse import urlsplit
from typing import Optional

from .contracts import CONTRACT_VERSION, TASKS, VisionError


@dataclass(frozen=True)
class VisionConfig:
    provider: str
    base_url: str
    model: str
    revision: str
    output_format: str = 'json_object'
    token_parameter: str = 'max_tokens'
    image_detail: str = 'omit'
    thinking: str = 'omit'
    temperature: Optional[float] = None
    timeout_seconds: int = 90
    max_attempts: int = 2
    concurrency: int = 2
    max_output_tokens: int = 4096
    max_image_bytes: int = 10000000
    max_pages: int = 20
    max_calls: int = 40
    prompt_version: str = 'vision-prompt-v1'
    contract_version: str = CONTRACT_VERSION

    def snapshot(self):
        return asdict(self)


def current_config():
    def value(name, default=''):
        return os.getenv('AI_VISION_' + name, default).strip()
    def integer(name, default, low, high):
        try:
            result = int(value(name, str(default)))
            if not low <= result <= high:
                raise ValueError()
            return result
        except ValueError:
            raise VisionError('VISION_INVALID_CONFIG') from None
    raw_temperature = value('TEMPERATURE', 'omit')
    try:
        temperature = None if raw_temperature == 'omit' else float(raw_temperature)
        if temperature is not None and (not math.isfinite(temperature) or not 0 <= temperature <= 2):
            raise ValueError()
    except ValueError:
        raise VisionError('VISION_INVALID_CONFIG') from None
    config = VisionConfig(
        provider=value('PROVIDER', 'disabled'), base_url=value('BASE_URL').rstrip('/'),
        model=value('MODEL'), revision=value('REVISION', 'unversioned'),
        output_format=value('OUTPUT_FORMAT', 'json_object'),
        token_parameter=value('TOKEN_PARAMETER', 'max_tokens'),
        image_detail=value('IMAGE_DETAIL', 'omit'), thinking=value('THINKING', 'omit'), temperature=temperature,
        timeout_seconds=integer('TIMEOUT_SECONDS', 90, 1, 180),
        max_attempts=integer('MAX_ATTEMPTS', 2, 1, 3), concurrency=integer('CONCURRENCY', 2, 1, 8),
        max_output_tokens=integer('MAX_OUTPUT_TOKENS', 4096, 256, 16000),
        max_image_bytes=integer('MAX_IMAGE_BYTES', 10000000, 1024, 20000000),
        max_pages=integer('MAX_PAGES', 20, 1, 200), max_calls=integer('MAX_CALLS', 40, 1, 600),
        prompt_version=value('PROMPT_VERSION', 'vision-prompt-v1'))
    try:
        parsed = urlsplit(config.base_url)
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
    except ValueError:
        raise VisionError('VISION_INVALID_CONFIG') from None
    local_http = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if (config.provider != 'openai_compatible' or not config.model or not config.revision
            or not config.prompt_version or not os.getenv('AI_VISION_API_KEY', '').strip()
            or not parsed.hostname or (parsed.scheme != 'https' and not local_http)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(c.isspace() for c in config.base_url)
            or config.output_format not in ('json_object', 'json_schema')
            or config.token_parameter not in ('max_tokens', 'max_completion_tokens')
            or config.image_detail not in ('omit', 'auto', 'high', 'low')
            or config.thinking not in ('omit', 'disabled', 'enabled', 'auto')):
        raise VisionError('VISION_INVALID_CONFIG')
    return config


def freeze(mode='off', tasks=None):
    if mode not in ('off', 'auto', 'force'):
        raise VisionError('VISION_INVALID_MODE')
    if mode == 'off':
        if tasks:
            raise VisionError('VISION_TASK_REQUIRES_ENABLED_MODE')
        return {'mode': 'off'}
    selected = tuple(tasks or (('ocr_text',) if mode == 'force' else TASKS))
    if not selected or len(set(selected)) != len(selected) or any(t not in TASKS for t in selected):
        raise VisionError('VISION_INVALID_TASK')
    return {'mode': mode, 'tasks': list(selected), 'config': current_config().snapshot()}


def verify_snapshot(snapshot):
    config = current_config()
    if snapshot.get('config') != config.snapshot():
        raise VisionError('VISION_CONFIG_CHANGED')
    return config
