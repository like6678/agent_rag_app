---
name: weekly-report
display_name: 周报生成
description: 根据用户提供的本周工作内容, 生成结构化、重点突出的周报, 并可导出为 MD/PDF 文件
version: 1.0.0
author: system
tags: [办公, 文档]
---
# 周报生成技能

## 目标
将用户零散的本周工作内容整理成一份专业、结构清晰的周报。

## 执行步骤
1. 先调用 get_skill_file(skill=weekly-report, path=files/周报模板.md) 读取模板
2. 将用户提供的工作内容按模板结构归类: 本周完成、进行中、问题与风险、下周计划
3. 每项工作用一句话概括成果, 突出可量化结果(数量/进度/收益)
4. 语言简洁专业, 使用中文, 避免口语化

## 输出
- 直接在对话中给出整理后的周报正文
- 如果用户要求文件或对话内容较长(超过10行), 调用 export_document 导出为 Markdown, 正式场景可导出 PDF