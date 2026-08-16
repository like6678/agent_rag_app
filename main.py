"""项目启动入口
用法:
    python main.py            # 等价于 uvicorn app.main:app --host 0.0.0.0 --port 8000
    或使用配置中的 APP_HOST / APP_PORT
"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )