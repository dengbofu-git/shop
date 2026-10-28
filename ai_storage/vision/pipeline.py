"""将已校验的模型候选转换为页面块，原始提取结果保留供人工核对。"""
import copy

from .cache import VisionCache
from .config import verify_snapshot
from .contracts import VisionError
from .openai_compatible import OpenAICompatibleVisionAdapter


def _box(box, width, height):
    return [box[0] * width, box[1] * height, box[2] * width, box[3] * height]


def _overlap(a, b):
    area = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / area if area else 0


def table_text(table):
    def escape(value):
        return value.replace('|', '\\|').replace('\n', ' ').replace('\r', ' ').strip()
    context = [table['title'], ('Unit: ' + table['unit']) if table['unit'] else '']
    context += ['Note: ' + n for n in table['notes']]
    prefix = '\n'.join(escape(s) for s in context if s)
    header = '| ' + ' | '.join(escape(h) for h in table['headers']) + ' |'
    separator = '| ' + ' | '.join('---' for h in table['headers']) + ' |'
    prefix = '\n'.join(s for s in (prefix, header, separator) if s)
    rows = ['| ' + ' | '.join(escape(c) for c in row) + ' |' for row in table['rows']]
    return prefix + '\n' + '\n'.join(rows), {'header': prefix, 'rows': rows}


class VisionPageProcessor:
    def __init__(self, snapshot, *, cache_root, namespace):
        self.snapshot = snapshot
        self.config = verify_snapshot(snapshot)
        self.cache = VisionCache(cache_root, namespace, self.config)
        self.calls = 0
        self.pages = 0
        self.hits = 0
        self.adapter = OpenAICompatibleVisionAdapter(self.config, before_attempt=self._admit)

    def _admit(self):
        if self.calls >= self.config.max_calls:
            raise VisionError('VISION_CALL_BUDGET_EXCEEDED')
        self.calls += 1

    def close(self):
        self.adapter.close()

    def process(self, original, image):
        page = copy.deepcopy(original)
        candidates = set(page.get('vision_candidates', []))
        tasks = self.snapshot['tasks'] if self.snapshot['mode'] == 'force' else [
            t for t in self.snapshot['tasks'] if t in candidates]
        if not page.get('has_content', bool(page['blocks'])) or not tasks:
            return page
        self.pages += 1
        if self.pages > self.config.max_pages:
            raise VisionError('VISION_PAGE_BUDGET_EXCEEDED')
        warnings = set(page['warnings'])
        for task in tasks:
            context = 'PDF physical page {}; task={}; source language must be preserved'.format(page['number'], task)
            key = self.cache.identity(image, task, context)
            result = self.cache.get(key, task)
            if result is None:
                result = self.adapter.extract(image=image, task=task, context=context)
                result = self.cache.put(key, result)
            else:
                self.hits += 1
            payload = result['payload']
            warnings.add('vision_model_output_requires_review')
            if payload['warnings']:
                warnings.add('vision_blocking_uncertain_output')
            trace = {'provider': result['provider'], 'model': result['model'], 'revision': result['revision'],
                     'task': task, 'prompt_version': self.config.prompt_version,
                     'contract_version': self.config.contract_version, 'cache_digest': key,
                     'confidence_kind': 'model_reported', 'confidence': payload['confidence'],
                     'warnings': payload['warnings']}
            def block(text, bbox, kind):
                return {'id': 'p{}-v{}'.format(page['number'], len(page['blocks']) + 1),
                        'text': text, 'bbox': _box(bbox, page['width'], page['height']),
                        'kind': kind, 'method': 'vision_' + task, 'heading': False,
                        'confidence': None, 'extraction': trace}
            if task == 'ocr_text':
                for item in page['blocks']:
                    item['indexable'] = False
                page['blocks'].extend(block(item['text'], item['bbox'], 'paragraph') for item in payload['blocks'])
            elif task == 'table_extract':
                table_boxes = [_box(t['bbox'], page['width'], page['height']) for t in payload['tables']]
                for i, box in enumerate(table_boxes):
                    if any(_overlap(box, other) > .1 for other in table_boxes[:i]):
                        warnings.add('vision_blocking_overlapping_tables')
                for item in page['blocks']:
                    if item.get('indexable', True) and item.get('kind') != 'figure':
                        overlap = max((_overlap(item['bbox'], box) for box in table_boxes), default=0)
                        if overlap >= .95:
                            item['indexable'] = False
                        elif overlap > .05:
                            # 不静默删除横跨表格与正文的粗粒度 OCR 块。
                            warnings.add('vision_blocking_partial_table_overlap')
                for table in payload['tables']:
                    if table['uncertain_cells']:
                        warnings.add('vision_blocking_uncertain_cells')
                    text, structure = table_text(table)
                    item = block(text, table['bbox'], 'table')
                    item['extraction'] = dict(trace, uncertain_cells=table['uncertain_cells'])
                    item['table'] = structure
                    page['blocks'].append(item)
            else:
                page['blocks'].extend(block(item['text'], item['bbox'], 'figure') for item in payload['figures'])
        page['warnings'] = sorted(warnings)
        page['method'] = 'mixed'
        return page
