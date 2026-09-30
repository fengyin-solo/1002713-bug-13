"""堆场策划业务规则：状态流转、层高/箱型校验与占用重算都收在这里。

矩阵图、明细、看板全部读取 store 里同一份箱位记录，避免两处占用口径不一致。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "yardplan"
REQUIRED_FIELDS = ["箱位编号", "所在箱区", "贝位号", "排位号"]
PRESERVED_FIELDS = ["层高上限", "堆放箱型"]
STATUS_ORDER = ["空闲", "已占用", "预留中", "已锁定"]

# 各箱型允许的最高堆垛层数；层高上限与箱型规则冲突时，一律以箱型为准
TYPE_STACK_LIMITS = {
    "20GP": 5,
    "40GP": 4,
    "40HQ": 3,
    "45HQ": 3,
    "20RF": 4,
    "40RF": 3,
}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _position(entry: dict[str, Any]) -> str:
    return (
        f"箱位 {entry.get('箱位编号', '?')}"
        f"（贝{entry.get('贝位号', '?')}-排{entry.get('排位号', '?')}）"
    )


class YardplanService:
    def __init__(self) -> None:
        # 服务启动时按统一口径重算一遍已有的箱位占用记录
        for entry in store.rows(MODULE):
            self.recompute_occupancy(entry)

    # ---- 占用口径：矩阵、明细、看板都走这一份计算 ----

    def effective_limit(self, entry: dict[str, Any]) -> tuple[int, bool]:
        """返回（有效层高, 是否箱型与层高冲突）。冲突时以箱型规则为准。"""
        height_limit = max(_to_int(entry.get("层高上限"), 0), 0)
        box_type = str(entry.get("堆放箱型") or "").strip().upper()
        type_limit = TYPE_STACK_LIMITS.get(box_type)
        if type_limit is not None and type_limit != height_limit:
            return type_limit, True
        return height_limit, False

    def recompute_occupancy(self, entry: dict[str, Any]) -> dict[str, Any]:
        """重算单条箱位占用：有效层高、当前层数封顶、预留标记、对外状态字段。"""
        limit, conflict = self.effective_limit(entry)
        level = min(max(_to_int(entry.get("当前层数")), 0), limit)
        entry["当前层数"] = level
        entry["有效层高"] = limit
        entry["层高冲突"] = conflict
        entry["箱位状态"] = entry.get("status", STATUS_ORDER[0])
        # 历史数据可能只有「预留中」状态而没有预留标记，统一补成显式标记
        entry["reserved"] = bool(entry.get("reserved")) or entry.get("status") == "预留中"
        return entry

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        enforce_limit: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("箱位编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        # 导出全量时不套分页大小；普通列表接口仍由路由层把 size 限在 200 以内
        effective_size = size if enforce_limit else max(total, 1)
        start = max(page - 1, 0) * effective_size
        page_rows = [self.recompute_occupancy(dict(row)) for row in rows[start:start + effective_size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self.recompute_occupancy(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + PRESERVED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        # 贝位号、排位号、层高上限落库即转成数字，杜绝非数值坐标把矩阵顶错位
        for coord in ("贝位号", "排位号", "层高上限"):
            entry[coord] = _to_int(entry.get(coord), 0)
        # 堆放箱型统一成大写编码，方便命中箱型层高规则
        entry["堆放箱型"] = entry["堆放箱型"].upper()
        entry["当前层数"] = 0
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["reserved"] = False
        rows.append(entry)
        return self.recompute_occupancy(entry), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"箱位 {entry_id} 不存在或已归档"

        if action == "预留箱位":
            if entry.get("status") == "已锁定":
                return None, f"{_position(entry)} 已锁定，不能再挂预留标记"
            entry["reserved"] = True
            if entry.get("status") == "空闲":
                entry["status"] = "预留中"
            return self.recompute_occupancy(entry), f"箱位 {entry['箱位编号']} 已预留"

        if action == "取消预留":
            entry["reserved"] = False
            if entry.get("status") == "预留中":
                entry["status"] = "空闲"
            return self.recompute_occupancy(entry), f"箱位 {entry['箱位编号']} 的预留标记已抹掉"

        if action == "分配箱位":
            if entry.get("status") == "已锁定":
                return None, f"{_position(entry)} 已锁定，不能重复分配"
            box_type = str(values.get("堆放箱型") or entry.get("堆放箱型") or "").strip()
            if box_type:
                entry["堆放箱型"] = box_type.upper()
            entry["status"] = "已占用"
            entry["pending"] = False
            entry["abnormal"] = False
            return self.recompute_occupancy(entry), f"箱位 {entry['箱位编号']} 已分配"

        if action == "锁定箱位":
            # 同一块箱位重复提交锁定，只认第一次
            if entry.get("status") == "已锁定":
                return None, (
                    f"箱位 {entry.get('箱位编号')} 已是锁定状态，"
                    "重复提交锁定只认第一次"
                )
            limit, conflict = self.effective_limit(entry)
            target_level = _to_int(entry.get("当前层数")) + 1
            if target_level > limit:
                rule = f"箱型 {entry.get('堆放箱型')} 允许层高" if conflict else "层高上限"
                return None, (
                    f"{_position(entry)} 锁定后将堆到第 {target_level} 层，"
                    f"超过{rule} {limit} 层，已拦截"
                )
            entry["当前层数"] = target_level
            entry["status"] = "已锁定"
            entry["pending"] = False
            entry["abnormal"] = False
            # 锁定生效后预留标记随之清掉，避免图上还挂着「预留」
            entry["reserved"] = False
            return self.recompute_occupancy(
                entry
            ), f"箱位 {entry['箱位编号']} 已锁定至第 {target_level} 层"

        if action == "释放箱位":
            level = max(_to_int(entry.get("当前层数")) - 1, 0)
            entry["当前层数"] = level
            entry["status"] = "空闲" if level == 0 else "已占用"
            entry["pending"] = level == 0
            entry["abnormal"] = False
            # 释放：预留标记必须抹掉；堆放箱型刻意保留，作为历史堆放记录
            entry["reserved"] = False
            return self.recompute_occupancy(
                entry
            ), f"箱位 {entry['箱位编号']} 已释放，预留标记已清除，堆放箱型保留"

        return None, f"动作「{action}」不属于堆场策划可执行范围"
