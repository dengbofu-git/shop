"""视觉输出是候选证据；合同校验不等于原件事实核验。"""
import json
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, model_validator


CONTRACT_VERSION = 'vision-contract-v1'
TASKS = ('ocr_text', 'table_extract', 'figure_describe')
ShortText = Annotated[StrictStr, Field(max_length=500)]


class VisionError(ValueError):
    """只暴露固定错误码，避免供应商响应或凭据进入作业日志。"""


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class LocatedText(Contract):
    text: StrictStr = Field(min_length=1, max_length=16000)
    # 相对实际上传图片的归一化坐标；仍须由审核者核对定位是否准确。
    bbox: List[float] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def validate_box(self):
        x0, y0, x1, y1 = self.bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or not self.text.strip():
            raise ValueError('Invalid text or normalized box')
        return self


class Extraction(Contract):
    schema_version: Literal['vision-contract-v1']
    confidence: Optional[float] = Field(ge=0, le=1)
    warnings: List[ShortText] = Field(max_length=20)


class OcrExtraction(Extraction):
    blocks: List[LocatedText] = Field(min_length=1, max_length=200)


class Table(Contract):
    bbox: List[float] = Field(min_length=4, max_length=4)
    title: StrictStr = Field(max_length=500)
    unit: StrictStr = Field(max_length=100)
    headers: List[StrictStr] = Field(min_length=1, max_length=32)
    rows: List[List[StrictStr]] = Field(min_length=1, max_length=200)
    notes: List[ShortText] = Field(max_length=20)
    uncertain_cells: List[ShortText] = Field(max_length=100)

    @model_validator(mode='after')
    def validate_table(self):
        x0, y0, x1, y1 = self.bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError('Invalid table box')
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError('Table width mismatch')
        if any(not h.strip() for h in self.headers):
            raise ValueError('Missing table header')
        return self


class TableExtraction(Extraction):
    tables: List[Table] = Field(min_length=1, max_length=8)


class FigureExtraction(Extraction):
    figures: List[LocatedText] = Field(min_length=1, max_length=32)


SCHEMAS = {'ocr_text': OcrExtraction, 'table_extract': TableExtraction,
           'figure_describe': FigureExtraction}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def strict_json(text):
    def invalid(value):
        raise ValueError('Non-finite JSON value')
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)


def validate_payload(task, payload):
    if task not in SCHEMAS:
        raise VisionError('VISION_INVALID_TASK')
    try:
        # 同一严格 JSON 入口也用于缓存和测试传入的对象，拒绝 NaN/Infinity。
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf8')) > 512000:
            raise ValueError('Output too large')
        return SCHEMAS[task].model_validate(strict_json(encoded)).model_dump()
    except (ValueError, TypeError, ValidationError):
        raise VisionError('VISION_INVALID_OUTPUT') from None
