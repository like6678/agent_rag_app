---
name: meeting-minutes
display_name: 会议纪要
description: 将会议讨论内容整理为结构化会议纪要, 包含议题、结论、待办事项与责任人
version: 1.0.0
author: system
tags: [办公, 文档]
---
# 会议纪要技能

## 目标
将用户的会议记录/讨论内容整理成可直接分发的会议纪要。

## 执行步骤
1. 先调用 get_skill_file(skill=meeting-minutes, path=files/会议纪要模板.md) 读取模板
2. 提取并组织: 会议主题、时间、参会人、议题讨论、结论、待办事项(含责任人/截止时间)
3. 待办事项使用清单列出, 明确责任人与时间
4. 内容忠于原讨论, 不臆造结论; 有歧义处标注"待确认"

## 输出
- 对话中给出纪要正文
- 用户要求文件时调用 export_document 导出(建议 PDF)