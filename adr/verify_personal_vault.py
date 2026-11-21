#!/usr/bin/env python3
"""个人数据保险柜规划静态校验；不运行或证明任何生产安全功能。"""
from __future__ import annotations

import json
from pathlib import Path
import re


def validate_graph(graph: dict[str, list[str]]) -> None:
    seen: set[str] = set()
    active: set[str] = set()

    def visit(task: str) -> None:
        if task not in graph:
            raise ValueError(f'未知依赖：{task}')
        if task in active:
            raise ValueError(f'循环依赖：{task}')
        if task in seen:
            return
        active.add(task)
        for dependency in graph[task]:
            visit(dependency)
        active.remove(task)
        seen.add(task)

    for task in graph:
        visit(task)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    adr = Path(__file__).resolve().parent
    root = adr.parent
    tasks_text = (adr / 'TASKS.md').read_text(encoding='utf-8')
    task_ids: list[str] = []
    graph: dict[str, list[str]] = {}
    for line in tasks_text.splitlines():
        cells = [cell.strip() for cell in line.split('|')]
        if len(cells) > 4 and re.fullmatch(r'K\d{3}', cells[1]):
            task_ids.append(cells[1])
            require(cells[1] not in graph, f'重复任务：{cells[1]}')
            graph[cells[1]] = re.findall(r'K\d{3}', cells[3])
    require(task_ids == [f'K{i:03}' for i in range(1, 97)], '主任务编号应连续且唯一：K001–K096')
    validate_graph(graph)
    # 任务可以正常推进；不再用方案初稿的“全部 TODO”断言阻止真实状态更新。
    require('evidence/K068.md' in tasks_text and 'evidence/K069.md' in tasks_text,
            '当前字段契约/样本任务缺少证据入口')
    require('K069' in graph['K003'], '候选writer缺少新领域无损样本依赖')
    require('K072' in graph['K081'], 'Web生产客户端缺少GW0授权/同步实验依赖')
    require('K055' in graph['K087'], '新领域互通回归缺少既有凭据回归依赖')

    require('K094' in graph['K010'], '生产骨架缺少 NSH 迁移门槛')
    require({'K091', 'K092', 'K093', 'K007', 'K008'} <= set(graph['K094']),
            'GN 缺少四端/Web/独立原生提供者证据依赖')
    require('K010' not in graph['K094'], 'GN 不得依赖生产骨架')
    require('K093' in graph['K081'], 'NSH Web 生产缺少新构建实验')
    require('K095' in graph['K087'], '跨端回归缺少桌面生产集成')
    require('K096' in graph['K089'], '完整交付缺少桌面发布验收')

    plan = (adr / 'PERSONAL_VAULT_PLAN.md').read_text(encoding='utf-8')
    detailed = re.findall(r'^\| (K\d{3}) \|', plan, re.M)
    require(detailed == [f'K{i:03}' for i in range(68, 90)], '专项计划应恰好细化K068–K089')
    scenarios = re.findall(r'^\| (VT\d{2})\b', plan, re.M)
    require(scenarios == [f'VT{i:02}' for i in range(1, 19)], 'VT场景缺失或重复')
    source_path = adr / 'research/personal-vault-2026-10-16.md'
    source_ids = re.findall(r'^(PV\d{2})\b', source_path.read_text(encoding='utf-8'), re.M)
    require(source_ids == [f'PV{i:02}' for i in range(1, 17)], '研究来源缺失或重复')

    # 原始导出、生成快照和历史证据不被改写；检查本轮入口与直接相关文档。
    documents = [root / 'README.md', root / 'AGENTS.md', *sorted(adr.glob('*.md')),
                 source_path, adr / 'design/README.md', adr / 'evidence/D06.md', adr / 'evidence/D07.md']
    links = 0
    for document in documents:
        text = document.read_text(encoding='utf-8')
        for ref in re.findall(r'\bPV\d{2}\b', text):
            require(ref in source_ids, f'{document.relative_to(root)}：未知来源 {ref}')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if target.startswith(('https:', 'http:', '#', 'mailto:')):
                continue
            relative = target.split('#')[0]
            if relative:
                resolved = (document.parent / relative).resolve()
                require(resolved.is_relative_to(root), f'文档链接越界：{target}')
                require(resolved.exists(), f'{document.relative_to(root)}：本地链接不存在 {target}')
                links += 1

    acceptance = (adr / 'ACCEPTANCE.md').read_text(encoding='utf-8')
    for section in ['AC-VAULT-DATA', 'AC-VAULT-REL', 'AC-VAULT-LIFE', 'AC-VAULT-COMPAT', 'AC-WEB', 'AC-NSH']:
        require(f'## {section}：' in acceptance, f'缺验收章节：{section}')
    print(json.dumps({
        'main_tasks_unique': len(task_ids),
        'main_dependencies_acyclic': True,
        'incremental_tasks_detailed': len(detailed),
        'acceptance_scenarios': len(scenarios),
        'research_sources': len(source_ids),
        'local_links_checked': links,
        'new_acceptance_sections': 6,
        'nsh_migration_dependencies_checked': True,
        'production_features_tested': False,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
