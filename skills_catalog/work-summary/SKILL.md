---
name: work-summary
display_name: 工作总结
description: 将一段时间的工作内容沉淀为总结报告, 突出成果、反思与改进计划
version: 1.0.0
author: system
tags: [办公, 文档]
---
# 工作总结技能

## 目标
将用户的工作内容整理为有洞察的总结报告(周/月/季度/年度)。

## 执行步骤
1. 先调用 get_skill_file(skill=work-summary, path=files/总结模板.md) 读取模板
2. 结构: 工作概览、核心成果(量化)、经验沉淀、问题与反思、改进计划
3. 成果尽量量化(数量/效率/收益), 反思要具体而非空话
4. 语气专业诚恳, 避免过度自夸

## 输出
- 对话中给出总结正文
- 用户要求文件或内容较长时调用 export_document 导出(Markdown/PDF)