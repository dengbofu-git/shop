"""Versioned page blocks; coordinates are unrotated PDF points, never image pixels."""
import copy
from html.parser import HTMLParser
import math


PAGE_IR_VERSION = 'page-ir-v1'


class DocumentError(ValueError):
    """Only fixed codes cross the worker boundary."""


class _Table(HTMLParser):
    """First stage accepts rectangular cells; merged/ambiguous tables require review."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None
        self.tables = 0
        self.closed_tables = 0
        self.in_table = False
        self.unsafe = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            self.tables += 1
            self.unsafe |= self.tables != 1
            self.in_table = True
        elif tag == 'tr':
            self.unsafe |= self.row is not None or not self.in_table
            self.row = []
        elif tag in ('td', 'th'):
            self.unsafe |= self.row is None or self.cell is not None
            self.unsafe |= any(attrs.get(key, '1') != '1' for key in ('rowspan', 'colspan'))
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')
        elif tag in ('script', 'style', 'iframe', 'object'):
            self.unsafe = True

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'table':
            self.closed_tables += 1
            self.unsafe |= self.row is not None or self.cell is not None or not self.in_table
            self.in_table = False
        elif tag in ('td', 'th'):
            if self.cell is None or self.row is None:
                self.unsafe = True
            else:
                self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr':
            if self.row is None or self.cell is not None:
                self.unsafe = True
            else:
                self.rows.append(self.row)
            self.row = None


def table_block(raw):
    parsed = _Table()
    parsed.feed(raw)
    parsed.close()
    rows = parsed.rows
    if (parsed.unsafe or parsed.tables != 1 or parsed.closed_tables != 1 or parsed.row is not None or parsed.cell is not None
            or len(rows) < 2 or not rows[0] or not any(rows[0])
            or len(rows[0]) > 64 or len(rows) > 1000
            or any(len(row) != len(rows[0]) for row in rows)):
        return None
    def line(row):
        return '| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ').replace('\r', ' ') for c in row) + ' |'
    header = line(rows[0]) + '\n' + line(['---'] * len(rows[0]))
    body = [line(row) for row in rows[1:]]
    return header + '\n' + '\n'.join(body), {'header': header, 'rows': body, 'cells': rows}


def normalize_native_page(original):
    page = copy.deepcopy(original)
    page['schema_version'] = PAGE_IR_VERSION
    for index, block in enumerate(page['blocks']):
        block.update(schema_version=PAGE_IR_VERSION, reading_order=index,
                     kind=block.get('kind', 'paragraph'), indexable=block.get('indexable', True))
    return page


def normalize_page(original, raw, *, image_size, identity, warnings=()):
    """Convert one full-page, unrotated rendering. Warping/cropping is not enabled."""
    iw, ih = image_size
    if raw.get('width') != iw or raw.get('height') != ih:
        raise DocumentError('DOCUMENT_COORDINATE_MISMATCH')
    items = raw.get('parsing_res_list')
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise DocumentError('DOCUMENT_INVALID_BLOCKS')
    page = normalize_native_page(original)
    for block in page['blocks']:
        block['indexable'] = False
    findings = set(warnings)
    # The Paddle result supersedes these heuristic extraction warnings only.
    cleared = {'column_order_requires_review', 'low_ocr_confidence', 'sparse_or_broken_text',
               'ocr_no_text', 'image_without_text'}
    findings.update(set(page['warnings']) - cleared)
    findings.add('document_model_output_requires_review')
    used_orders = set()
    normalized = []
    previous_order = -1
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise DocumentError('DOCUMENT_INVALID_BLOCKS')
        label, text = item.get('block_label'), item.get('block_content')
        box, order = item.get('block_bbox'), item.get('block_order')
        if (not isinstance(label, str) or not isinstance(text, str) or len(text) > 100000
                or not isinstance(box, list) or len(box) != 4
                or any(type(v) not in (float, int) or not math.isfinite(v) for v in box)):
            raise DocumentError('DOCUMENT_INVALID_BLOCKS')
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= iw + 1 and 0 <= y0 < y1 <= ih + 1):
            raise DocumentError('DOCUMENT_INVALID_COORDINATES')
        # Image blocks can have no reading order and never become fabricated text.
        if label in ('image', 'header_image', 'footer_image'):
            continue
        if not text.strip():
            findings.add('document_blocking_empty_region')
            continue
        source_order = order
        ancillary = label in ('vision_footnote', 'header', 'footer', 'number', 'footnote', 'aside_text')
        if order is None and (ancillary or label == 'table'):
            order = previous_order + .5
            if label == 'table':
                findings.add('document_table_order_requires_review')
        else:
            if type(order) is not int or order < 0 or order in used_orders:
                raise DocumentError('DOCUMENT_INVALID_READING_ORDER')
            used_orders.add(order)
        previous_order = order
        kind = 'table' if label == 'table' else 'paragraph'
        trace = dict(identity, source_label=label, source_block_id=item.get('block_id'),
                     coordinate_space='unrotated_pdf_points', rendered_size=[iw, ih],
                     scale_to_pdf=[page['width'] / iw, page['height'] / ih],
                     raw_text=text, source_order=source_order, source_sequence=index,
                     confidence_kind='not_provided')
        block = {'id': 'p{}-pd{}'.format(page['number'], index + 1), 'text': text,
                 'bbox': [x0 / iw * page['width'], y0 / ih * page['height'],
                          min(x1, iw) / iw * page['width'], min(y1, ih) / ih * page['height']],
                 'kind': kind, 'method': 'paddleocr_vl', 'confidence': None,
                 'heading': label in ('doc_title', 'paragraph_title'), 'reading_order': order,
                 'schema_version': PAGE_IR_VERSION, 'extraction': trace,
                 'indexable': not ancillary}
        if kind == 'table':
            converted = table_block(text)
            if converted is None:
                findings.add('document_blocking_table_structure')
                block['indexable'] = False
                block['kind'] = 'unresolved_table'
            else:
                block['text'], block['table'] = converted
                trace['text_representation'] = 'canonical_table_not_pdf_verbatim'
        normalized.append(block)
    if not any(b.get('indexable') for b in normalized):
        findings.add('document_blocking_no_indexable_text')
    normalized.sort(key=lambda b: b['reading_order'])
    for rank, block in enumerate(normalized):
        block['reading_order'] = rank
    page['blocks'].extend(normalized)
    page['warnings'] = sorted(findings)
    page['method'] = 'paddleocr_vl'
    return page
