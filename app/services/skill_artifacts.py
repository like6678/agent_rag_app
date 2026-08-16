"""
技能生成文档(产物)服务
- export_document: 生成 Markdown, 可选转 PDF(xhtml2pdf, 中文用系统字体)
- 产物写入 MinIO skill-outputs/<session_id>/ 前缀, TTL 自动清理
- 每次请求的文件收集器(供 Agent 循环收集 export_document 产物)
"""
import io
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import quote
from loguru import logger

from app.services.minio import minio_service

ARTIFACT_PREFIX = "skill-outputs/"
DEFAULT_TTL_DAYS = 7


def _safe_filename(title: str, fmt: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (title or "文档").strip(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:60] or "document") + "." + fmt


# ---------- PDF 生成 ----------

_CJK_FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",  # 微软雅黑加粗
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    r"C:\Windows\Fonts\simsun.ttc",  # 宋体
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _find_cjk_font() -> Optional[str]:
    for p in _CJK_FONT_PATHS:
        if os.path.exists(p):
            return p
    return None


def _md_to_pdf_bytes(content_md: str) -> Optional[bytes]:
    """Markdown -> PDF(UTF-8). 依赖缺失或渲染失败时返回 None(调用方降级为纯 MD)"""
    try:
        import markdown
        from xhtml2pdf import pisa
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as e:
        logger.warning(f"PDF 依赖未安装, 降级为纯 MD: {e}")
        return None

    body = markdown.markdown(content_md, extensions=["tables", "fenced_code", "toc", "nl2br"])
    font_family = "Helvetica"
    font_path = _find_cjk_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("CJKFont", font_path))
            font_family = "CJKFont"
        except Exception as e:
            logger.warning(f"注册中文字体失败({font_path}), 继续尝试: {e}")

    html = f"""<html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 18mm 16mm; }}
    body {{ font-family: {font_family}, sans-serif; font-size: 11pt; line-height: 1.6; color: #222; }}
    h1 {{ font-size: 20pt; margin: 14px 0 8px; }}
    h2 {{ font-size: 16pt; margin: 12px 0 6px; }}
    h3 {{ font-size: 13pt; margin: 10px 0 5px; }}
    pre {{ background: #f5f6f8; padding: 8px; font-size: 9pt; border-radius: 4px; }}
    code {{ background: #f5f6f8; padding: 1px 4px; border-radius: 3px; font-size: 9.5pt; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 10pt; }}
    img {{ max-width: 100%; }}
    </style></head><body>{body}</body></html>"""

    try:
        buf = io.BytesIO()
        result = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
        if result is not None and getattr(result, "err", 0):
            logger.warning("PDF 渲染返回错误状态, 降级为纯 MD")
            return None
        pdf = buf.getvalue()
        return pdf if len(pdf) > 100 else None
    except Exception as e:
        logger.warning(f"PDF 渲染失败, 降级为纯 MD: {e}")
        return None


# ---------- 导出 ----------

def export_document(
    title: str,
    content_md: str,
    format: str = "md",
    session_id: str = "unknown",
) -> Dict[str, Any]:
    """生成文档并写入 MinIO, 返回下载信息(同时记录到请求级收集器)"""
    fmt = (format or "md").lower()
    if fmt not in ("md", "pdf"):
        fmt = "md"
    filename = _safe_filename(title, fmt)
    ts = time.strftime("%Y%m%d%H%M%S")
    object_name = f"{ARTIFACT_PREFIX}{session_id}/{ts}_{filename}"

    if fmt == "pdf":
        pdf = _md_to_pdf_bytes(content_md)
        if pdf is None:
            fmt = "md"
            filename = _safe_filename(title, "md")
            object_name = f"{ARTIFACT_PREFIX}{session_id}/{ts}_{filename}"
            data, content_type = content_md.encode("utf-8"), "text/markdown; charset=utf-8"
        else:
            data, content_type = pdf, "application/pdf"
    else:
        data, content_type = content_md.encode("utf-8"), "text/markdown; charset=utf-8"

    minio_service.upload_bytes(object_name, data, content_type=content_type)
    info = {
        "name": filename,
        "object_name": object_name,
        "download_url": f"/api/skills/artifacts/download?object_name={quote(object_name, safe='')}",
        "format": fmt,
        "size": len(data),
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    logger.info(f"技能产物已生成: {object_name} ({len(data)} bytes, {fmt})")
    return info


def get_artifact(object_name: str) -> Dict[str, Any]:
    """读取产物 -> {data, filename, content_type}"""
    if not object_name.startswith(ARTIFACT_PREFIX):
        raise ValueError("非法的产物路径(仅允许 skill-outputs/ 前缀)")
    data = minio_service.download(object_name)
    name = object_name.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ct = "application/pdf" if ext == "pdf" else "text/markdown; charset=utf-8"
    return {"data": data, "filename": name, "content_type": ct}


def cleanup_artifacts(max_age_days: int = DEFAULT_TTL_DAYS) -> int:
    """删除超过 N 天的技能产物, 返回删除数量"""
    if max_age_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=max_age_days)
    deleted = 0
    try:
        for obj in minio_service.list_objects(prefix=ARTIFACT_PREFIX):
            last = obj.get("last_modified") or ""
            try:
                ts = datetime.fromisoformat(last.replace("Z", "+00:00")).replace(tzinfo=None)
                if ts < cutoff:
                    minio_service.delete(obj["name"])
                    deleted += 1
            except Exception:
                continue
        if deleted:
            logger.info(f"技能产物 TTL 清理: 删除 {deleted} 个过期文件")
    except Exception as e:
        logger.warning(f"技能产物清理失败: {e}")
    return deleted