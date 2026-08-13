"""直接 mock minio 的 argon2 依赖, 用真实 dashscope/milvus"""
import sys, os, types, traceback

sys.path.insert(0, r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')
os.chdir(r'C:\Users\KK\WorkBuddy\Agent\agent-rag-app')

# Mock argon2 和 _argon2_cffi_bindings, 让 minio.crypto 能导入
argon2_mod = types.ModuleType('argon2')
class _Type:
    pass
argon2_low = types.ModuleType('argon2.low_level')
argon2_low.Type = _Type
def _hash_secret_raw(*args, **kwargs):
    return b''
argon2_low.hash_secret_raw = _hash_secret_raw
argon2_mod.low_level = argon2_low
sys.modules['argon2'] = argon2_mod
sys.modules['argon2.low_level'] = argon2_low

# Mock _argon2_cffi_bindings
bind_mod = types.ModuleType('_argon2_cffi_bindings')
class _FFI:
    NULL = 0
    def string(self, x):
        return x
    def new(self, *args):
        return None
class _Lib:
    pass
bind_mod.ffi = _FFI()
bind_mod.lib = _Lib()
sys.modules['_argon2_cffi_bindings'] = bind_mod

# Mock urllib3.util.retry (minio 可能用到)
import importlib
try:
    import urllib3
    import urllib3.util
    if not hasattr( urllib3.util, 'retry'):
        urllib3.util.retry = types.ModuleType('urllib3.util.retry')
except Exception:
    pass

print("=== Stub 模块就绪 ===")

try:
    from app.main import app
    print("=== app 加载成功 ===")

    schema = app.openapi()
    print(f"=== OpenAPI 生成成功 ===")
    print(f"  路径数: {len(schema.get('paths', {}))}")
    for p in sorted(schema.get('paths', {}).keys()):
        methods = list(schema['paths'][p].keys())
        print(f"  {p}: {methods}")
except Exception as e:
    print("=== 失败 ===")
    traceback.print_exc()