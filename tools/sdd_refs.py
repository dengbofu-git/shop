#!/usr/bin/env python3
"""只读检索本仓库 SDD 中的完整 ID 引用；不执行阶段或业务校验。"""
import argparse
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.md', '.yaml', '.yml', '.json'}


def identifier(value):
    if not re.fullmatch(r'[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+', value):
        raise argparse.ArgumentTypeError('ID 应为 CAP-AI-003 等大写连字符标识')
    return value


def positive_integer(value):
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('limit 必须为正整数')
    if result < 1:
        raise argparse.ArgumentTypeError('limit 必须为正整数')
    return result


def search_files(root, include_evidence=False):
    """只遍历固定 SDD 根；跳过链接和目录连接，避免跨界或循环读取。"""
    sdd = root / 'docs' / 'sdd'
    if not sdd.is_dir() or sdd.is_symlink() or sdd.resolve() != sdd:
        raise ValueError('docs/sdd 必须是仓库内的真实目录')

    def onerror(error):
        raise error

    files = []
    for directory, dirs, names in os.walk(sdd, followlinks=False, onerror=onerror):
        parent = Path(directory)
        dirs[:] = sorted(name for name in dirs if not name.startswith('.')
                         and name != 'node_modules'
                         and (include_evidence or parent != sdd or name != 'evidence')
                         and not (parent / name).is_symlink()
                         and (parent / name).resolve() == parent / name)
        for name in names:
            path = parent / name
            if (not name.startswith('.') and path.suffix.lower() in EXTENSIONS
                    and not path.is_symlink() and path.resolve() == path):
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def find_references(root, value, limit=500, include_evidence=False):
    # 下划线也属于标识的一部分，防止命中更长的代码标识。
    pattern = re.compile(r'(?<![A-Za-z0-9_-])' + re.escape(value) + r'(?![A-Za-z0-9_-])')
    matches = []
    total = 0
    for path in search_files(root, include_evidence):
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if pattern.search(line):
                total += 1
                if len(matches) < limit:
                    matches.append((path.relative_to(root).as_posix(), number, line.strip()))
    return matches, total


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id', type=identifier, help='例如 CAP-AI-003、RULE-AI-003-01')
    parser.add_argument('--limit', type=positive_integer, default=500, help='最多显示的命中行数（默认 500）')
    parser.add_argument('--include-evidence', action='store_true', help='加入 docs/sdd/evidence 历史证据')
    args = parser.parse_args(argv)
    try:
        matches, total = find_references(Path(root or ROOT).resolve(), args.id,
                                         args.limit, args.include_evidence)
    except (OSError, ValueError) as error:
        # 不输出异常正文，避免泄露宿主路径或读取到的原始字节。
        print('SDD 引用检索失败：{}；请检查 docs/sdd 的目录、读取权限和 UTF-8 编码。'.format(
            type(error).__name__), file=sys.stderr)
        return 2
    for path, number, line in matches:
        print('{}:{}: {}'.format(path, number, line))
    if total > len(matches):
        print('已截断：显示 {} / {} 个命中行。'.format(len(matches), total))
    elif total:
        print('共 {} 个命中行。'.format(total))
    else:
        print('无引用：{}（当前扫描范围）。'.format(args.id))
    return 0 if total else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
