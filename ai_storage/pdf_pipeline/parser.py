"""Runs in a disposable subprocess: native PDF blocks plus bounded Tesseract TSV."""
import csv
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile

PARSER_VERSION = 'pdf-blocks-v3'


def _quality(text):
    usable = sum(char.isalnum() for char in text)
    broken = sum(char == '\ufffd' or (ord(char) < 32 and char not in '\n\r\t') for char in text)
    return usable >= 20 and broken / max(1, len(text)) < .02


def _ocr(page, rect, config, fitz):
    scale = config['dpi'] / 72
    if rect.width * rect.height * scale * scale > config['max_pixels']:
        scale = math.sqrt(config['max_pixels'] / (rect.width * rect.height))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False, colorspace=fitz.csRGB)
    with tempfile.TemporaryDirectory(prefix='knowledge-ocr-') as folder:
        image = Path(folder) / 'page.png'
        pix.save(str(image))
        result = subprocess.run(['tesseract', str(image), 'stdout', '-l', config['languages'],
            '--psm', '3', 'tsv'], capture_output=True, timeout=config['ocr_timeout'], check=True)
    groups = {}
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf8')), delimiter='\t'):
        text = (word.get('text') or '').strip()
        if word.get('level') != '5' or not text:
            continue
        confidence = float(word['conf'])
        if not math.isfinite(confidence) or confidence < 0:
            continue
        key = (word['block_num'], word['par_num'])
        group = groups.setdefault(key, {'words': [], 'scores': [], 'boxes': []})
        group['words'].append((word['line_num'], text))
        group['scores'].append(confidence)
        left, top, width, height = [float(word[k]) for k in ('left', 'top', 'width', 'height')]
        group['boxes'].append([rect.x0 + left / scale, rect.y0 + top / scale,
                               rect.x0 + (left + width) / scale, rect.y0 + (top + height) / scale])
    blocks = []
    for group in groups.values():
        lines = {}
        for line, text in group['words']:
            lines.setdefault(line, []).append(text)
        boxes = group['boxes']
        paragraph = '\n'.join(' '.join(words) for words in lines.values())
        paragraph = re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])', '', paragraph)
        blocks.append({'text': paragraph,
            'bbox': [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)],
            'method': 'ocr', 'confidence': round(statistics.mean(group['scores']), 2), 'heading': False})
    return blocks


def parse(path, page_number, preview, config):
    import fitz
    with fitz.open(path) as document:
        if document.needs_pass or not document.is_pdf or not 1 <= len(document) <= config['max_pages']:
            raise ValueError('Encrypted, empty or oversized PDF')
        if page_number == 0:
            version = subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=5)
            return {'total_pages': len(document), 'parser': PARSER_VERSION, 'pymupdf': fitz.VersionBind,
                    'tesseract': version.stdout.decode('utf8').splitlines()[0]}
        page = document[page_number - 1]
        # All coordinates are PDF points in the unrotated page coordinate system.
        rotation = page.rotation
        if rotation:
            page.set_rotation(0)
        native, sizes = [], []
        for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
            if block['type'] != 0:
                continue
            spans = [span for line in block['lines'] for span in line['spans']]
            text = '\n'.join(''.join(span['text'] for span in line['spans']) for line in block['lines']).strip()
            if not text:
                continue
            size = max((span['size'] for span in spans), default=0)
            sizes.extend(span['size'] for span in spans if span['text'].strip())
            native.append({'text': text, 'bbox': list(block['bbox']), 'method': 'native',
                           'confidence': None, 'font_size': size, 'heading': False})
        warnings, blocks = [], native
        paddle_backend = config.get('document_parser', {}).get('backend') == 'paddleocr'
        good_native = _quality('\n'.join(block['text'] for block in native))
        images = page.get_image_info()
        if config['ocr_mode'] == 'force' or not good_native:
            # Blank pages should not be labelled OCR failures.
            if images or native or page.get_drawings():
                # The isolated parser only renders for the external GPU service.
                blocks = native if paddle_backend else _ocr(page, page.rect, config, fitz)
                if not blocks:
                    warnings.append('ocr_no_text')
        else:
            median = statistics.median(sizes) if sizes else 12
            for block in blocks:
                block['heading'] = block['font_size'] >= median * 1.2 and len(block['text']) <= 180
            for image in images:
                rect = fitz.Rect(image['bbox']) & page.rect
                if rect.is_empty or rect.width * rect.height < 1600:
                    continue
                covered = ' '.join(b['text'] for b in native if (fitz.Rect(b['bbox']) & rect).get_area() > 0)
                if _quality(covered):
                    continue  # Existing usable text layer; avoid duplicate OCR.
                extra = [] if paddle_backend else _ocr(page, rect, config, fitz)
                blocks.extend(extra)
                if not extra:
                    warnings.append('image_without_text')
        has_tables = bool(page.find_tables().tables)
        if has_tables:
            warnings.append('table_layout_requires_review')
        if any(b['method'] == 'ocr' and b['confidence'] < config['min_confidence'] for b in blocks):
            warnings.append('low_ocr_confidence')
        if blocks and not _quality(' '.join(b['text'] for b in blocks)):
            warnings.append('sparse_or_broken_text')
        # Phase one supports top-to-bottom blocks; ambiguous columns require review.
        if any(a['bbox'][2] < b['bbox'][0] and abs(a['bbox'][1] - b['bbox'][1]) < 20
               for a in blocks for b in blocks if a is not b and len(a['text']) > 100 and len(b['text']) > 100):
            warnings.append('column_order_requires_review')
        blocks.sort(key=lambda b: (round(b['bbox'][1] / 4), b['bbox'][0]))
        for index, block in enumerate(blocks):
            block['id'] = 'p{}-b{}'.format(page_number, index + 1)
        page.get_pixmap(matrix=fitz.Matrix(min(1, 1200 / max(page.rect.width, page.rect.height)),
                                         min(1, 1200 / max(page.rect.width, page.rect.height))), alpha=False).save(preview)
        result = {'number': page_number, 'width': page.rect.width, 'height': page.rect.height, 'rotation': rotation,
                'blocks': blocks, 'method': 'mixed' if len({b['method'] for b in blocks}) > 1 else
                (blocks[0]['method'] if blocks else 'blank'), 'warnings': sorted(set(warnings))}
        if config.get('vision_render_path'):
            candidates = set()
            if has_tables:
                candidates.add('table_extract')
            if set(warnings) & {'low_ocr_confidence', 'sparse_or_broken_text', 'ocr_no_text',
                                'column_order_requires_review', 'image_without_text'}:
                candidates.add('ocr_text')
            area = max(1, page.rect.width * page.rect.height)
            drawings = page.get_drawings()
            if (any((fitz.Rect(i['bbox']) & page.rect).get_area() / area >= .03 for i in images)
                    or (len(drawings) >= 3 and sum(d['rect'].get_area() for d in drawings) / area >= .03)):
                candidates.add('figure_describe')
            scale = min(config['dpi'] / 72, math.sqrt(config['max_pixels'] / area) * .99)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
            pixmap.save(config['vision_render_path'])
            result['render_geometry'] = {'pixel_width': pixmap.width, 'pixel_height': pixmap.height,
                                         'pdf_width': page.rect.width, 'pdf_height': page.rect.height,
                                         'rotation': rotation, 'coordinate_space': 'unrotated_pdf_points'}
            result.update(vision_candidates=sorted(candidates), has_content=bool(images or native or drawings))
        return result


def main():
    # Process limits supplement the worker container limits; Windows uses timeout.
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    path, page, preview, config = sys.argv[1:]
    # Third-party PDF helpers may print banners. Stdout is exclusively our JSON
    # transport; diagnostics must not corrupt the protocol or expose PDF text.
    with redirect_stdout(io.StringIO()):
        result = parse(path, int(page), preview, json.loads(config))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
