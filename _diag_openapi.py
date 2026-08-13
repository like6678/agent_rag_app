"""诊断脚本: 复现 /openapi.json 500 错误"""
import sys
import os
import traceback

sys.path.insert(0, r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')
os.chdir(r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')

try:
    from app.main import app
    print("=== App 加载成功 ===")
    schema = app.openapi()
    print(f"=== OpenAPI 生成成功, 路径数: {len(schema.get('paths', {}))} ===")
    for p in schema.get('paths', {}):
        print(f"  {p}")
except Exception as e:
    print("=== OpenAPI 生成失败 ===")
    traceback.print_exc()