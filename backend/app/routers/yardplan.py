"""堆场策划接口：箱位登记、箱位矩阵图、分配明细动作与堆存看板。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.yardplan import BusinessError, YardplanService

router = APIRouter(prefix="/api/yardplan", tags=["堆场策划"])

service = YardplanService()


def _fail(message: str, status: int = 409) -> HTTPException:
    """业务报错原样带出，不再由前端替换成笼统提示。"""
    return HTTPException(status_code=status, detail=message)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按箱位编号检索"),
    block: str | None = Query(default=None, description="按所在箱区过滤"),
    status: str | None = Query(default=None, description="空闲、已占用、预留中、已锁定"),
    page: int = 1,
    size: int = 200,
) -> PageResult[dict]:
    """箱位列表（详情口径）：占用层数/状态由分配明细重算后返回。"""
    if size > 1000:
        raise _fail("每页最多 1000 条，请缩小分页范围", status=400)
    try:
        items, total = service.list_entries(block=block, keyword=keyword, status=status,
                                            page=page, size=size)
    except BusinessError as exc:
        raise _fail(str(exc), status=400)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/matrix")
def get_matrix(block: str | None = Query(default=None, description="箱区，如 A区")) -> dict[str, Any]:
    """箱位矩阵图：轴标号和格子用同一份箱位记录，避免贝位号/排位号错位。"""
    return service.matrix(block)


@router.get("/board")
def get_board() -> dict[str, Any]:
    """堆存看板：占位数等指标全部按分配明细实时重算。"""
    return service.board()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出堆场策划清单：返回全量重算后的箱位数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "yardplan", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条箱位详情（含分配明细）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise _fail(f"箱位 {entry_id} 不存在或已归档", status=404)
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条箱位，缺字段或编号重复时说明原因而不是静默丢弃。"""
    try:
        entry, missing = service.create_entry(payload.values)
    except BusinessError as exc:
        raise _fail(str(exc), status=400)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="箱位已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """分配/释放/锁定/预留箱位；规则冲突（越界、重复锁定等）原样返回服务端说明。"""
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, payload.values)
    except BusinessError as exc:
        raise _fail(str(exc))
    return ActionResult(ok=True, message=message, entry=entry)
