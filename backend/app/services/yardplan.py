"""堆场策划业务规则。

占用口径（矩阵图、箱位详情、堆存看板共用这一份，避免两处读到的占用不一致）：
- 每条箱位（yardplan）登记箱区/贝位/排位/层高上限/预留箱型；
- 每条分配明细（yardplan_allocation）记录某个箱位上落了一只什么箱型的箱子；
- 箱位的「当前层数」「箱位状态」一律由分配明细重算，不允许各处自行维护。

层高与箱型冲突时以箱型为准：高箱（40HQ/45HQ）按 2 层占位计算，
已堆箱高超出层高上限的箱位在锁定时会被拦下并指出是哪块箱位越界。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "yardplan"
ALLOC_MODULE = "yardplan_allocation"

REQUIRED_FIELDS = ["箱位编号", "所在箱区", "贝位号", "排位号", "层高上限"]
STATUS_FREE = "空闲"
STATUS_OCCUPIED = "已占用"
STATUS_RESERVED = "预留中"
STATUS_LOCKED = "已锁定"

# 箱型实际占用层数：高箱按两层占位。未登记的箱型按普通箱一层处理。
TYPE_TIERS: dict[str, int] = {"20GP": 1, "40GP": 1, "40HQ": 2, "45HQ": 2}

ACTIONS = ("分配箱位", "释放箱位", "锁定箱位", "预留箱位")


class BusinessError(Exception):
    """业务规则冲突：调用方据此返回非 2xx，错误信息原样带给前端。"""

    @property
    def message(self) -> str:
        return str(self)


def _tier_of(container_type: Any) -> int:
    try:
        return TYPE_TIERS[str(container_type).strip().upper()]
    except KeyError:
        return 1


def _to_int(value: Any, field: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise BusinessError(f"{field}必须是整数，收到的是「{value}」")
    return number


class YardplanService:
    def __init__(self) -> None:
        self.recompute_all()

    # ---- 占用重算：唯一的数据口径 -------------------------------------

    def allocations(self, slot_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(ALLOC_MODULE) if int(row.get("箱位id", 0)) == slot_id]

    def recompute_slot(self, slot: dict[str, Any]) -> dict[str, Any]:
        """按分配明细重算单块箱位的层数/状态，矩阵图与详情都读这份结果。"""
        allocations = self.allocations(int(slot.get("id", 0)))
        used = sum(_tier_of(item.get("箱型")) for item in allocations)
        limit = _to_int(slot.get("层高上限", 0), "层高上限")
        slot["当前层数"] = used
        slot["层高越界"] = used > limit
        slot["status"] = self.derive_status(slot)
        slot["箱位状态"] = slot["status"]
        slot["pending"] = not slot.get("已锁定")
        slot["abnormal"] = bool(slot["层高越界"])
        return slot

    @staticmethod
    def derive_status(slot: dict[str, Any]) -> str:
        if slot.get("已锁定"):
            return STATUS_LOCKED
        if int(slot.get("当前层数", 0)) > 0:
            return STATUS_OCCUPIED
        if slot.get("预留"):
            return STATUS_RESERVED
        return STATUS_FREE

    def recompute_all(self) -> None:
        """层高/箱型口径调整后，对全部已有箱位占用记录重算一遍。"""
        for slot in store.rows(MODULE):
            self.recompute_slot(slot)

    def slot_view(self, slot: dict[str, Any]) -> dict[str, Any]:
        """矩阵图与箱位详情共用的序列化结构，保证两处占用一致。"""
        view = dict(slot)
        view["分配明细"] = [dict(item) for item in self.allocations(int(slot["id"]))]
        return view

    # ---- 查询 ---------------------------------------------------------

    def list_entries(
        self,
        *,
        block: str | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 200,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self.recompute_slot(slot) for slot in store.rows(MODULE)]
        if block:
            rows = [row for row in rows if str(row.get("所在箱区", "")) == block]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("箱位编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: (str(row.get("所在箱区", "")),
                                   _to_int(row.get("贝位号", 0), "贝位号"),
                                   _to_int(row.get("排位号", 0), "排位号")))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.slot_view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        slot = store.find(MODULE, entry_id)
        if slot is None:
            return None
        return self.slot_view(self.recompute_slot(slot))

    def matrix(self, block: str | None = None) -> dict[str, Any]:
        """箱位矩阵图：行=排位、列=贝位，轴标号直接取自箱位记录，杜绝贝位/排位错位。"""
        slots, _ = self.list_entries(block=block, page=1, size=100000)
        blocks = sorted({str(slot.get("所在箱区", "")) for slot in store.rows(MODULE)})
        bays = sorted({_to_int(slot["贝位号"], "贝位号") for slot in slots})
        rows = sorted({_to_int(slot["排位号"], "排位号") for slot in slots})
        index = {
            (_to_int(slot["贝位号"], "贝位号"), _to_int(slot["排位号"], "排位号")): slot
            for slot in slots
        }
        return {
            "箱区": blocks,
            "贝位": bays,
            "排位": rows,
            "cells": [[index.get((bay, tier)) for bay in bays] for tier in rows],
        }

    def board(self) -> dict[str, Any]:
        """堆存看板：占位数完全跟着分配明细重算，明细一动看板就跟着动。"""
        slots = [self.recompute_slot(slot) for slot in store.rows(MODULE)]
        return {
            "箱区": sorted({str(slot.get("所在箱区", "")) for slot in slots}),
            "箱位总数": len(slots),
            "占位数": sum(int(slot["当前层数"]) for slot in slots),
            "已占用箱位": sum(1 for slot in slots if slot["status"] == STATUS_OCCUPIED),
            "预留箱位": sum(1 for slot in slots if slot["status"] == STATUS_RESERVED),
            "锁定箱位": sum(1 for slot in slots if slot["status"] == STATUS_LOCKED),
            "空闲箱位": sum(1 for slot in slots if slot["status"] == STATUS_FREE),
            "越界箱位": sum(1 for slot in slots if slot.get("层高越界")),
        }

    # ---- 写入 ---------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if str(values.get(field) or "").strip() == ""]
        if missing:
            return None, missing
        code = str(values["箱位编号"]).strip()
        if any(str(row.get("箱位编号")) == code for row in store.rows(MODULE)):
            raise BusinessError(f"箱位编号「{code}」已存在，不能重复登记")
        limit = _to_int(values["层高上限"], "层高上限")
        if limit <= 0:
            raise BusinessError("层高上限必须大于 0")
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({
            "箱位编号": code,
            "所在箱区": str(values["所在箱区"]).strip(),
            "贝位号": _to_int(values["贝位号"], "贝位号"),
            "排位号": _to_int(values["排位号"], "排位号"),
            "层高上限": limit,
            "堆放箱型": str(values.get("堆放箱型") or "20GP").strip().upper(),
            "预留": False,
            "已锁定": False,
        })
        rows.append(entry)
        return self.slot_view(self.recompute_slot(entry)), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        slot = store.find(MODULE, entry_id)
        if slot is None:
            raise BusinessError(f"箱位 {entry_id} 不存在或已归档")
        if action not in ACTIONS:
            raise BusinessError(f"动作「{action}」不属于堆场策划可执行范围")
        values = values or {}

        if action == "分配箱位":
            self._allocate(slot, values)
        elif action == "预留箱位":
            if slot.get("已锁定"):
                raise BusinessError(f"箱位 {slot['箱位编号']} 已锁定，不能再预留")
            slot["预留"] = True
        elif action == "释放箱位":
            # 抹掉预留/锁定标记与全部落箱明细，但留住箱位登记的堆放箱型。
            slot["预留"] = False
            slot["已锁定"] = False
            store.rows(ALLOC_MODULE)[:] = [
                item for item in store.rows(ALLOC_MODULE)
                if int(item.get("箱位id", 0)) != int(slot["id"])
            ]
        else:  # 锁定箱位：同一块箱位重复锁定只认第一次
            if slot.get("已锁定"):
                raise BusinessError(f"箱位 {slot['箱位编号']} 已锁定，重复锁定只认第一次")
            self.recompute_slot(slot)
            if slot["层高越界"]:
                raise BusinessError(
                    f"箱位 {slot['箱位编号']}（{slot['所在箱区']} "
                    f"贝{slot['贝位号']} 排{slot['排位号']}）当前堆放 {slot['当前层数']} 层，"
                    f"超过层高上限 {slot['层高上限']} 层，不能锁定"
                )
            slot["已锁定"] = True

        return self.slot_view(self.recompute_slot(slot)), f"箱位已{action}"

    def _allocate(self, slot: dict[str, Any], values: dict[str, Any]) -> None:
        if slot.get("已锁定"):
            raise BusinessError(f"箱位 {slot['箱位编号']} 已锁定，不能再分配箱子")
        container_no = str(values.get("箱号") or "").strip()
        container_type = str(values.get("箱型") or slot.get("堆放箱型") or "20GP").strip().upper()
        if not container_no:
            raise BusinessError("分配箱位必须提供箱号")
        allocations = store.rows(ALLOC_MODULE)
        if any(str(item.get("箱号")) == container_no for item in allocations):
            raise BusinessError(f"箱号「{container_no}」已分配箱位，不能重复落箱")
        # 分配允许超层（现场可能先落箱后补策划），只做越界标记；真正的硬卡口在锁定环节。
        allocations.append({
            "id": max((int(item.get("id", 0)) for item in allocations), default=0) + 1,
            "箱位id": int(slot["id"]),
            "箱号": container_no,
            "箱型": container_type,
        })
        slot["预留"] = False
