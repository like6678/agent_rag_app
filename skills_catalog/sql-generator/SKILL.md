---
name: sql-generator
display_name: SQL 查询助手
description: 根据用户的自然语言需求生成 SQL 查询, 并解释执行逻辑与潜在性能风险
version: 1.0.0
author: system
tags: [数据, 代码]
---
# SQL 生成技能

## 目标
将自然语言查询需求转化为正确、高效的 SQL。

## 执行步骤
1. 明确表结构约束: 若用户提供表结构则严格遵循; 未提供时使用通用表名并注明假设
2. 输出 SQL 时说明: 查询意图、关键逻辑(JOIN/WHERE/GROUP BY 等)、可能影响性能的点与优化建议
3. 涉及敏感操作(删除/更新/大表全扫)时显式警告并建议先 SELECT 确认
4. 默认生成可读性好的标准 SQL, 标注方言兼容性(MySQL/PG 等)

## 输出
- 对话中给出 SQL + 解释
- 长脚本可调用 export_document 导出 Markdown