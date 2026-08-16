---
name: prd
display_name: 产品需求文档 PRD
description: 根据用户描述的产品想法, 输出结构化的产品需求文档(PRD), 包含背景、目标、用户故事、功能需求与非功能需求
version: 1.0.0
author: system
tags: [产品, 文档]
---
# PRD 生成技能

## 目标
将用户的产品想法转化为可直接评审的 PRD 文档。

## 执行步骤
1. 先调用 get_skill_file(skill=prd, path=files/PRD模板.md) 读取模板
2. 按模板结构撰写: 背景与问题、目标与非目标、用户画像、用户故事、功能需求(优先级 P0/P1/P2)、非功能需求、里程碑、风险
3. 功能需求逐条编号, 描述清楚"用户场景-操作-预期结果"
4. 信息不足时给出合理假设并标注"待确认", 不要编造数据

## 输出
- 对话中给出 PRD 摘要
- 完整文档调用 export_document 导出为 Markdown(默认)或 PDF(评审用)