#!/usr/bin/env python3
"""只检查设计资料，不运行或声称验证生产密码管理功能；仅依赖 Python 标准库。"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


def main() -> None:
    design = Path(__file__).resolve().parent
    root = design.parents[1]
    expected = json.loads((design / 'original-sha256.json').read_text())
    for relative, digest in expected.items():
        assert hashlib.sha256((design / relative).read_bytes()).hexdigest() == digest, relative

    class Assets(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            for key, value in attrs:
                if key in ('src', 'href') and value and not value.startswith(('#', 'data:')):
                    assert not value.startswith(('http:', 'https:', '//')), value
                    assert (design / 'zh-CN' / value).is_file(), value

    html = (design / 'zh-CN/index.html').read_text()
    assert 'lang="zh-CN"' in html
    Assets().feed(html)
    script = (design / 'zh-CN/app.js').read_text()
    navigation = re.search(r'const NAV = \[(.*?)\n\];', script, re.S)
    assert navigation is not None
    labels = re.findall(r"label:'([^']+)'", navigation.group(1))
    assert labels == ['密码', '验证', '证件', '银行', '设置'], labels
    assert not re.search(r'\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage)\b', script)

    # 校验本次编写的 Markdown 链接；原始导出不参与文档改写规则。
    documents = [root / 'README.md', root / 'AGENTS.md', *sorted((root / 'adr').glob('*.md')), design / 'README.md']
    checked_links = 0
    for path in documents:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if target.startswith(('https://', 'http://', '#')):
                continue
            local = target.split('#')[0]
            if local:
                assert (path.parent / local).exists(), f'{path}: {target}'
                checked_links += 1

    tasks_text = (root / 'adr/TASKS.md').read_text()
    task_rows = re.findall(r'^\| (K\d{3}) \|[^\n]+$', tasks_text, re.M)
    assert task_rows == [f'K{i:03}' for i in range(1, 90)], task_rows
    dependencies: dict[str, list[str]] = {}
    for line in tasks_text.splitlines():
        columns = [column.strip() for column in line.split('|')]
        if len(columns) > 4 and re.fullmatch(r'K\d{3}', columns[1]):
            dependencies[columns[1]] = re.findall(r'K\d{3}', columns[3])

    seen: set[str] = set()
    visiting: set[str] = set()

    def visit(task: str) -> None:
        assert task in dependencies, f'未知依赖：{task}'
        assert task not in visiting, f'循环依赖：{task}'
        if task in seen:
            return
        visiting.add(task)
        for dependency in dependencies[task]:
            visit(dependency)
        visiting.remove(task)
        seen.add(task)

    for task in dependencies:
        visit(task)
    print(json.dumps({'original_files_unchanged': len(expected), 'navigation': labels, 'local_links_checked': checked_links, 'tasks_unique': len(task_rows), 'task_dependency_dag': True, 'prototype_external_assets': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
