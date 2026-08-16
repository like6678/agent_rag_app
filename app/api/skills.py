"""
技能管理接口
- GET    /api/skills/store              内置商店目录(含已安装标记)
- POST   /api/skills/install            从商店安装
- POST   /api/skills/import             导入自定义技能(ZIP / SKILL.md)
- GET    /api/skills                    已安装技能列表
- PATCH  /api/skills/{id}               启用/停用
- DELETE /api/skills/{id}               卸载
- GET    /api/skills/{id}/files?path=   读取技能资产(模板/资料)
- GET    /api/skills/artifacts/download 下载技能生成的文档(MD/PDF)
- POST   /api/skills/artifacts/cleanup  手动清理过期产物
"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from loguru import logger

from app.models.schemas import (
    SkillInfo,
    SkillStoreItem,
    SkillInstallRequest,
    SkillEnableRequest,
)
from app.services.skill_store import skill_store
from app.services.skill_artifacts import get_artifact, cleanup_artifacts

router = APIRouter()


def _content_disposition(disposition: str, filename: str) -> str:
    """兼容中文文件名的 Content-Disposition(RFC 5987)"""
    ascii_name = filename.encode("ascii", errors="ignore").decode() or "file"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _skill_info(row: dict) -> dict:
    return SkillInfo(**row).model_dump()


@router.get("/store", response_model=list[SkillStoreItem], summary="内置技能商店目录")
def list_store():
    """返回内置商店可安装技能(含是否已安装)"""
    return [SkillStoreItem(**item).model_dump() for item in skill_store.list_store()]


@router.post("/install", summary="从商店安装技能")
def install_skill(req: SkillInstallRequest):
    """把商店技能安装到本地(重复安装 = 覆盖更新)"""
    try:
        skill = skill_store.install_from_store(req.name)
        return {"message": f"技能已安装: {skill['name']}", "skill": _skill_info(skill)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"安装技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"安装技能失败: {e}")


@router.post("/import", summary="导入自定义技能(ZIP / SKILL.md)")
async def import_skill(file: UploadFile = File(...)):
    """导入 .zip(内含 SKILL.md + 可选资产) 或单个 .md/.markdown 文件"""
    try:
        data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取上传文件失败: {e}")
    try:
        skill = skill_store.import_skill(data, file.filename or "")
        return {"message": f"技能导入成功: {skill['name']}", "skill": _skill_info(skill)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导入技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入技能失败: {e}")


@router.get("", response_model=list[SkillInfo], summary="已安装技能列表")
def list_skills():
    """列出所有已安装技能(含启用状态/使用次数)"""
    return [_skill_info(s) for s in skill_store.list_skills()]


@router.patch("/{skill_id}", summary="启用/停用技能")
def set_enabled(skill_id: str, req: SkillEnableRequest):
    if not skill_store.get_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"技能不存在: {skill_id}")
    ok = skill_store.set_enabled(skill_id, req.enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="更新技能状态失败")
    return {"skill_id": skill_id, "enabled": req.enabled, "message": "已启用" if req.enabled else "已停用"}


@router.delete("/{skill_id}", summary="卸载技能")
def uninstall_skill(skill_id: str):
    """卸载技能(删除 DB 记录 + MinIO 资产)"""
    if not skill_store.get_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"技能不存在: {skill_id}")
    skill_store.delete_skill(skill_id)
    return {"skill_id": skill_id, "message": "技能已卸载"}


@router.get("/{skill_id}/files", summary="读取技能资产文件")
def get_skill_file(skill_id: str, path: str = Query(..., description="资产相对路径, 如 files/template.md")):
    """读取技能资产(模板/资料), 用于前端预览或注入"""
    try:
        data, content_type, filename = skill_store.get_asset(skill_id, path)
        return Response(
            content=data,
            media_type=content_type,
            headers={"Content-Disposition": _content_disposition("inline", filename)},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"读取技能资产失败: {e}")
        raise HTTPException(status_code=404, detail=f"资产不存在: {path}")


@router.get("/artifacts/download", summary="下载技能生成的文档")
def download_artifact(object_name: str = Query(..., description="MinIO object_name(skill-outputs/ 前缀)")):
    """下载技能通过 export_document 生成的 MD/PDF 文件"""
    try:
        art = get_artifact(object_name)
        return Response(
            content=art["data"],
            media_type=art["content_type"],
            headers={
                "Content-Disposition": _content_disposition("attachment", art["filename"]),
                "Content-Length": str(len(art["data"])),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"下载技能产物失败: {e}")
        raise HTTPException(status_code=404, detail=f"文件不存在或已过期清理: {object_name}")


@router.post("/artifacts/cleanup", summary="清理过期技能产物")
def run_cleanup(max_age_days: int = Query(7, ge=1, le=90)):
    deleted = cleanup_artifacts(max_age_days)
    return {"deleted": deleted, "message": f"已清理 {deleted} 个过期产物(>{max_age_days}天)"}