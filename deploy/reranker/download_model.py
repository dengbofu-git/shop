"""Optional resumable parallel download from the pinned official model repository.

Run with the service stopped and its /models volume mounted. A verified prefix
from huggingface_hub is retained; failed downloads restore that original prefix.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path
import shutil
import time

import requests

REPO = 'BAAI/bge-reranker-v2-m3'
REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'
ROOT = Path('/models/hub/models--BAAI--bge-reranker-v2-m3')


def main():
    data = requests.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true', timeout=30).json()
    entry = next(item for item in data['siblings'] if item['rfilename'] == 'model.safetensors')
    size, digest = entry['size'], entry['lfs']['sha256']
    blob = ROOT / 'blobs' / digest
    partial = blob.with_name(blob.name + '.incomplete')
    working = blob.with_name(blob.name + '.parallel')
    blob.parent.mkdir(parents=True, exist_ok=True)
    if blob.exists():
        print('Model weights already cached', flush=True)
        return
    prefix = partial.stat().st_size if partial.exists() else 0
    if prefix > size:
        raise RuntimeError('invalid_partial_size')
    # Never create sparse holes in huggingface_hub's own resumable prefix. Even
    # SIGKILL must leave that prefix valid for the next normal model startup.
    if partial.exists():
        shutil.copyfile(partial, working)
    else:
        working.write_bytes(b'')
    fd = os.open(working, os.O_CREAT | os.O_RDWR, 0o644)
    chunk = 32 * 1024 * 1024
    ranges = [(start, min(start + chunk - 1, size - 1)) for start in range(prefix, size, chunk)]
    print(f'Resuming {prefix // 1048576} / {size // 1048576} MiB with 8 connections', flush=True)

    def download(bounds):
        start, end = bounds
        for attempt in range(5):
            try:
                with requests.get(f'https://huggingface.co/{REPO}/resolve/{REVISION}/model.safetensors',
                                  headers={'Range': f'bytes={start}-{end}'}, stream=True, timeout=(20, 90)) as response:
                    if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                        raise RuntimeError('invalid_range_response')
                    offset = start
                    for part in response.iter_content(chunk_size=1024 * 1024):
                        if offset + len(part) > end + 1:
                            raise RuntimeError('range_too_large')
                        written = os.pwrite(fd, part, offset)
                        if written != len(part):
                            raise RuntimeError('short_disk_write')
                        offset += written
                    if offset != end + 1:
                        raise RuntimeError('incomplete_range')
                    return end - start + 1
            except Exception:
                if attempt == 4:
                    raise RuntimeError('range_download_failed') from None
                time.sleep(2 ** attempt)

    complete = prefix
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [pool.submit(download, bounds) for bounds in ranges]
            for job in as_completed(jobs):
                complete += job.result()
                print(f'Downloaded {complete // 1048576} / {size // 1048576} MiB', flush=True)
        os.fsync(fd)
        with working.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if checksum != digest:
            raise RuntimeError('model_checksum_mismatch')
    except BaseException:
        os.ftruncate(fd, prefix)
        raise
    finally:
        os.close(fd)
    working.rename(blob)
    partial.unlink(missing_ok=True)
    link = ROOT / 'snapshots' / REVISION / 'model.safetensors'
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to('../../blobs/' + digest)
    print('SHA256 verified; pinned model weights ready', flush=True)


if __name__ == '__main__':
    main()
