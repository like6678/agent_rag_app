"""
技能存储服务
- 内置商店目录 skills_catalog/<name>/SKILL.md 扫描与安装
- 自定义导入(ZIP / 单个 SKILL.md)
- MySQL 持久化技能元数据 + MinIO 存放资产文件
- 技能为指令型(仅 SKILL.md 说明 + 模板/资料文件, 不执行任意代码)
"""
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from app.services.mysql import mysql_service
from app.services.minio import minio_service
from app.config import settings

# 内置商店目录(项目根目录 skills_catalog)
CATALOG_DIR = Path(__file__).resolve().parents[2] / "skills_catalog"

NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")

# 导入限制
MAX_ZIP_SIZE = 5 * 1024 * 1024
MAX_ZIP_FILES = 20
MAX_ASSET_SIZE = 2 * 1024 * 1024

CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _content_type(path: str) -> str:
    return CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def _parse_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    """解析 SKILL.md 的 YAML front-matter(极简解析, 不引入 yaml 依赖)"""
    meta: Dict[str, Any] = {
        "name": "",
        "display_name": "",
        "description": "",
        "version": "1.0.0",
        "author": "",
        "tags": [],
    }
    if not text.startswith("---"):
        return meta, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta, text
    fm, body = parts[1], parts[2].lstrip("\n")
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower()
        v = v.strip().strip('"').strip("'")
        if k == "tags":
            if v.startswith("[") and v.endswith("]"):
                v = v[1:-1]
            meta[k] = [t.strip().strip('"').strip("'") for t in v.split(",") if t.strip()]
        elif k == "version":
            meta[k] = v or "1.0.0"
        elif k in ("name", "display_name", "description", "author"):
            meta[k] = v
    return meta, body


def _validate_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("技能 name 必须为 1-64 位小写字母/数字/连字符/下划线(如 my-skill)")
    return name


def _slugify(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-").lower()
    return s[:60] or "doc"


class SkillStore:
    """技能存储(MySQL 元数据 + MinIO 资产)"""

    # ---------- 目录/解析 ----------

    def load_catalog(self) -> List[Dict[str, Any]]:
        """读取内置商店目录(磁盘扫描)"""
        entries: List[Dict[str, Any]] = []
        if not CATALOG_DIR.exists():
            logger.warning(f"技能商店目录不存在: {CATALOG_DIR}")
            return entries
        for skill_dir in sorted(CATALOG_DIR.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
                meta, body = _parse_front_matter(text)
                if not meta.get("name"):
                    meta["name"] = skill_dir.name
                meta["name"] = _validate_name(meta["name"])
                files = [
                    str(p.relative_to(skill_dir)).replace("\\", "/")
                    for p in sorted(skill_dir.rglob("*"))
                    if p.is_file() and p.name != "SKILL.md"
                ]
                entries.append({
                    "name": meta["name"],
                    "display_name": meta.get("display_name") or meta["name"],
                    "description": meta.get("description", ""),
                    "version": meta.get("version", "1.0.0"),
                    "author": meta.get("author", "system"),
                    "tags": meta.get("tags", []),
                    "file_count": len(files),
                    "content": body,
                    "files": files,
                })
            except Exception as e:
                logger.warning(f"解析商店技能失败 {skill_dir.name}: {e}")
        return entries

    def _installed_names(self) -> set:
        try:
            rows = mysql_service.query("SELECT name FROM skills")
            return {r["name"] for r in rows}
        except Exception as e:
            logger.warning(f"查询已安装技能失败: {e}")
            return set()

    def list_store(self) -> List[Dict[str, Any]]:
        installed = self._installed_names()
        out = []
        for item in self.load_catalog():
            out.append({
                "name": item["name"],
                "display_name": item["display_name"],
                "description": item["description"],
                "version": item["version"],
                "author": item["author"],
                "tags": item["tags"],
                "installed": item["name"] in installed,
            })
        return out

    # ---------- 安装/导入 ----------

    def install_from_store(self, name: str) -> Dict[str, Any]:
        """从内置商店安装技能(复制到 DB + MinIO)"""
        name = _validate_name(name)
        item = None
        for e in self.load_catalog():
            if e["name"] == name:
                item = e
                break
        if item is None:
            raise ValueError(f"商店中不存在技能: {name}")

        # 同名已存在则覆盖更新
        existing = self._get_by_name(name)
        skill_id = existing["id"] if existing else str(uuid.uuid4())
        self._save_skill(
            skill_id=skill_id,
            name=name,
            display_name=item["display_name"],
            description=item["description"],
            version=item["version"],
            author=item["author"],
            tags=item["tags"],
            source="store",
            content=item["content"],
        )
        # 复制资产到 MinIO(覆盖)
        for rel in item["files"]:
            src = CATALOG_DIR / name / rel
            data = src.read_bytes()
            self._put_asset(skill_id, rel, data)
        self._set_file_count(skill_id)
        logger.info(f"技能已从商店安装: {name} (id={skill_id})")
        return self._get_by_id(skill_id) or {"id": skill_id, "name": name}

    def import_skill(self, data: bytes, filename: str) -> Dict[str, Any]:
        """导入自定义技能: 支持 ZIP 或单个 SKILL.md"""
        fname = (filename or "").lower()
        if not data:
            raise ValueError("导入文件为空")
        if len(data) > MAX_ZIP_SIZE:
            raise ValueError(f"导入文件过大(>{MAX_ZIP_SIZE // 1024 // 1024}MB)")

        if fname.endswith(".zip"):
            skill_md_text, assets = self._extract_zip(data)
        elif fname.endswith((".md", ".markdown")):
            skill_md_text, assets = data.decode("utf-8", errors="replace"), {}
        else:
            raise ValueError("仅支持 .zip 或 .md/.markdown 文件")

        meta, body = _parse_front_matter(skill_md_text)
        name = _validate_name(meta["name"])
        if not meta.get("description"):
            raise ValueError("SKILL.md 缺少 description(供模型判断何时调用)")
        if not body.strip():
            raise ValueError("SKILL.md 正文不能为空")

        existing = self._get_by_name(name)
        skill_id = existing["id"] if existing else str(uuid.uuid4())
        self._save_skill(
            skill_id=skill_id,
            name=name,
            display_name=meta.get("display_name") or name,
            description=meta["description"],
            version=meta.get("version", "1.0.0"),
            author=meta.get("author", "imported"),
            tags=meta.get("tags", []),
            source="imported",
            content=body,
        )
        for rel, blob in assets.items():
            self._put_asset(skill_id, rel, blob)
        self._set_file_count(skill_id)
        logger.info(f"技能导入成功: {name} (id={skill_id}, 资产={len(assets)})")
        return self._get_by_id(skill_id) or {"id": skill_id, "name": name}

    def _extract_zip(self, data: bytes) -> Tuple[str, Dict[str, bytes]]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ValueError("无效的 ZIP 文件")
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > MAX_ZIP_FILES:
            raise ValueError(f"ZIP 内文件过多(>{MAX_ZIP_FILES} 个)")

        # 支持根目录 SKILL.md 或单一顶层目录下的 SKILL.md
        skill_rel = None
        prefix = ""
        if "SKILL.md" in names:
            skill_rel = "SKILL.md"
        else:
            for n in names:
                if n.endswith("/SKILL.md") and n.count("/") == 1:
                    skill_rel = n
                    prefix = n[: n.index("/")] + "/"
                    break
        if skill_rel is None:
            raise ValueError("ZIP 中未找到 SKILL.md(需位于根目录或单一顶层目录)")

        assets: Dict[str, bytes] = {}
        skill_text = ""
        for n in names:
            # zip-slip 防护: 禁止绝对路径与 .. 穿越
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError(f"非法路径: {n}")
            if len(zf.read(n)) > MAX_ASSET_SIZE:
                raise ValueError(f"文件过大: {n}")
            if n == skill_rel:
                skill_text = zf.read(n).decode("utf-8", errors="replace")
            elif prefix and n.startswith(prefix):
                assets[n[len(prefix):]] = zf.read(n)
            elif not prefix:
                assets[n] = zf.read(n)
        if not skill_text.strip():
            raise ValueError("SKILL.md 内容为空")
        return skill_text, assets

    # ---------- 查询/管理 ----------

    def list_skills(self) -> List[Dict[str, Any]]:
        try:
            rows = mysql_service.query("SELECT * FROM skills ORDER BY created_at DESC")
            out = []
            for r in rows:
                s = self._normalize_row(r)
                s["tags"] = [t for t in (r.get("tags") or "").split(",") if t]
                out.append(s)
            return out
        except Exception as e:
            logger.warning(f"列出技能失败: {e}")
            return []

    def _normalize_row(self, r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": r["id"],
            "name": r["name"],
            "display_name": r.get("display_name") or r["name"],
            "description": r.get("description") or "",
            "version": r.get("version") or "1.0.0",
            "author": r.get("author") or "",
            "tags": [],
            "source": r.get("source") or "imported",
            "enabled": bool(r.get("enabled", 1)),
            "file_count": int(r.get("file_count") or 0),
            "used_count": int(r.get("used_count") or 0),
            "content": r.get("content") or "",
            "created_at": str(r.get("created_at") or ""),
            "updated_at": str(r.get("updated_at") or ""),
        }

    def _get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            row = mysql_service.query_one("SELECT * FROM skills WHERE name = %s", (name,))
            return self._normalize_row(row) if row else None
        except Exception as e:
            logger.warning(f"查询技能失败: {e}")
            return None

    def _get_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = mysql_service.query_one("SELECT * FROM skills WHERE id = %s", (skill_id,))
            return self._normalize_row(row) if row else None
        except Exception as e:
            logger.warning(f"查询技能失败: {e}")
            return None

    def get_skill(self, ref: str) -> Optional[Dict[str, Any]]:
        """按 id 或 name 查询技能"""
        row = mysql_service.query_one("SELECT * FROM skills WHERE id = %s", (ref,))
        if row is None:
            row = mysql_service.query_one("SELECT * FROM skills WHERE name = %s", (ref,))
        return self._normalize_row(row) if row else None

    def set_enabled(self, skill_id: str, enabled: bool) -> bool:
        try:
            affected = mysql_service.execute(
                "UPDATE skills SET enabled = %s, updated_at = NOW() WHERE id = %s",
                (1 if enabled else 0, skill_id),
            )
            return affected > 0
        except Exception as e:
            logger.warning(f"更新技能状态失败: {e}")
            return False

    def increment_used(self, skill_id: str):
        try:
            mysql_service.execute(
                "UPDATE skills SET used_count = used_count + 1, updated_at = NOW() WHERE id = %s",
                (skill_id,),
            )
        except Exception as e:
            logger.warning(f"技能使用计数失败: {e}")

    def delete_skill(self, skill_id: str) -> bool:
        """卸载技能(DB + MinIO 资产)"""
        try:
            mysql_service.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
            # 清理 MinIO 资产
            prefix = f"skills/{skill_id}/"
            try:
                for obj in minio_service.list_objects(prefix=prefix):
                    minio_service.delete(obj["name"])
            except Exception as e:
                logger.warning(f"清理技能资产失败: {e}")
            logger.info(f"技能已卸载: {skill_id}")
            return True
        except Exception as e:
            logger.warning(f"卸载技能失败: {e}")
            return False

    def _save_skill(self, skill_id, name, display_name, description, version, author, tags, source, content):
        """插入或更新技能记录"""
        tags_str = ",".join(tags)
        row = mysql_service.query_one("SELECT id FROM skills WHERE id = %s", (skill_id,))
        if row:
            mysql_service.execute(
                "UPDATE skills SET name=%s, display_name=%s, description=%s, version=%s, author=%s, "
                "tags=%s, source=%s, content=%s, updated_at=NOW() WHERE id=%s",
                (name, display_name, description, version, author, tags_str, source, content, skill_id),
            )
        else:
            mysql_service.execute(
                "INSERT INTO skills (id, name, display_name, description, version, author, tags, source, content) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (skill_id, name, display_name, description, version, author, tags_str, source, content),
            )

    def _set_file_count(self, skill_id: str):
        try:
            count = len(minio_service.list_objects(prefix=f"skills/{skill_id}/"))
            mysql_service.execute(
                "UPDATE skills SET file_count = %s, updated_at = NOW() WHERE id = %s",
                (count, skill_id),
            )
        except Exception as e:
            logger.warning(f"更新技能资产数失败: {e}")

    # ---------- 资产 ----------

    def list_assets(self, skill_id: str) -> List[Dict[str, Any]]:
        try:
            return [
                {"path": obj["name"].split(f"skills/{skill_id}/", 1)[-1], "size": obj["size"]}
                for obj in minio_service.list_objects(prefix=f"skills/{skill_id}/")
            ]
        except Exception as e:
            logger.warning(f"列出技能资产失败: {e}")
            return []

    def get_asset(self, skill_ref: str, path: str) -> Tuple[bytes, str, str]:
        """读取技能资产 -> (data, content_type, filename)"""
        skill = self.get_skill(skill_ref)
        if skill is None:
            raise ValueError(f"技能不存在: {skill_ref}")
        rel = (path or "").strip().lstrip("/")
        if not rel or ".." in Path(rel).parts:
            raise ValueError("非法资产路径")
        object_name = f"skills/{skill['id']}/{rel}"
        data = minio_service.download(object_name)
        return data, _content_type(rel), rel.split("/")[-1]

    def _put_asset(self, skill_id: str, rel: str, data: bytes):
        minio_service.upload_bytes(
            f"skills/{skill_id}/{rel}",
            data,
            content_type=_content_type(rel),
        )


skill_store = SkillStore()