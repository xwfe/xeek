#!/usr/bin/env python3
"""iOS设计、引用和专项任务静态检查。只使用标准库，不验证真实凭据能力。"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re


def main() -> None:
    design = Path(__file__).resolve().parent
    adr = design.parent
    preview = design / 'zh-CN'

    class Assets(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            for name, value in attrs:
                if name in ('src', 'href') and value and not value.startswith(('#', 'data:')):
                    assert not value.startswith(('http:', 'https:', '//')), value
                    assert (preview / value).is_file(), value

    html = (preview / 'ios.html').read_text()
    assert 'lang="zh-CN"' in html
    Assets().feed(html)
    script = (preview / 'ios.js').read_text()
    nav = re.search(r'const NAV = \[(.*?)\n\];', script, re.S)
    assert nav
    labels = re.findall(r"label:'([^']+)'", nav.group(1))
    assert labels == ['密码', '验证', '证件', '银行', '设置'], labels
    assert not re.search(r'\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage)\b', script)
    assert 'https://' not in (preview / 'ios.css').read_text()

    task_text = (adr / 'MOBILE_SYNC_TASKS.md').read_text()
    rows = re.findall(r'^\| (M\d{2}) \|[^\n]+$', task_text, re.M)
    assert rows == [f'M{i:02}' for i in range(1, 25)], rows
    main_ids = set(re.findall(r'^\| (K\d{3}) \|', (adr / 'TASKS.md').read_text(), re.M))
    deps: dict[str, list[str]] = {}
    for line in task_text.splitlines():
        cells = [cell.strip() for cell in line.split('|')]
        if len(cells) > 4 and re.fullmatch(r'M\d{2}', cells[1]):
            assert set(re.findall(r'K\d{3}', cells[2])) <= main_ids, cells[2]
            deps[cells[1]] = re.findall(r'M\d{2}', cells[3])
    seen: set[str] = set()
    active: set[str] = set()

    def visit(task: str) -> None:
        assert task in deps, task
        assert task not in active, f'循环依赖：{task}'
        if task in seen:
            return
        active.add(task)
        for dependency in deps[task]:
            visit(dependency)
        active.remove(task)
        seen.add(task)

    for task in deps:
        visit(task)

    research = adr / 'research/mobile-sync-2026-10-12.md'
    source_ids = set(re.findall(r'^(R\d{2})\b', research.read_text(), re.M))
    assert source_ids == {f'R{i:02}' for i in range(1, 20)}, source_ids
    documents = [*adr.glob('000[234]-*.md'), adr / 'MOBILE_SYNC_TASKS.md', design / 'IOS_DESIGN.md', research]
    checked_links = 0
    for document in documents:
        text = document.read_text()
        for ref in re.findall(r'\bR\d{2}\b', text):
            assert ref in source_ids, f'{document}: {ref}'
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if link.startswith(('http:', 'https:', '#')):
                continue
            assert (document.parent / link.split('#')[0]).exists(), (document, link)
            checked_links += 1

    print(json.dumps({'ios_navigation': labels, 'local_asset_paths_valid': True, 'subtasks_unique': len(rows), 'subtask_dependencies_acyclic': True, 'source_ids': len(source_ids), 'local_links_checked': checked_links, 'production_credentials_tested': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
