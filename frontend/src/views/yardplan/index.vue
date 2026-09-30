<template>
  <section class="page" data-module="yardplan">
    <header class="page-head">
      <div>
        <h2>堆场策划管理</h2>
        <p class="page-desc">箱位矩阵图与详情共用同一份占用：占用层数与状态全部按分配明细重算。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记箱位</button>
        <button class="btn" type="button" @click="exportRows">导出堆场策划清单</button>
      </div>
    </header>

    <!-- 堆存看板：占位数由服务端按分配明细实时重算 -->
    <div class="stat-row">
      <article v-for="item in boardCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'error-text': item.danger }">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>所在箱区</span>
        <select v-model="filters.block">
          <option value="">全部箱区</option>
          <option v-for="block in blocks" :key="block" :value="block">{{ block }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>箱位状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="yard-layout">
      <!-- 箱位矩阵图：行=排位、列=贝位，轴标号取自箱位记录本身 -->
      <div class="matrix-panel">
        <div class="panel-title">
          <span>箱位矩阵图</span>
          <span class="legend">
            <i class="dot free"></i>空闲
            <i class="dot occupied"></i>已占用
            <i class="dot reserved"></i>预留中
            <i class="dot locked"></i>已锁定
            <i class="dot over"></i>层高越界
          </span>
        </div>
        <table v-if="matrix.bays.length" class="matrix-table">
          <thead>
            <tr>
              <th class="axis-corner">排位＼贝位</th>
              <th v-for="bay in matrix.bays" :key="bay">贝{{ bay }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tier in matrix.tiers" :key="tier">
              <th class="axis-label">排{{ tier }}</th>
              <td v-for="bay in matrix.bays" :key="bay" class="matrix-cell-box">
                <button
                  v-if="matrix.index[`${bay}-${tier}`]"
                  type="button"
                  class="cell"
                  :class="cellClass(matrix.index[`${bay}-${tier}`]!)"
                  @click="selectedId = matrix.index[`${bay}-${tier}`]!.id"
                >
                  <span class="cell-code">{{ matrix.index[`${bay}-${tier}`]!.箱位编号 }}</span>
                  <span class="cell-tier">
                    {{ matrix.index[`${bay}-${tier}`]!.当前层数 }}/{{ matrix.index[`${bay}-${tier}`]!.层高上限 }}层
                  </span>
                </button>
                <span v-else class="cell-empty">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">当前筛选条件下没有箱位</p>
      </div>

      <!-- 箱位详情：直接用列表里同一条记录，矩阵与详情占用必然一致 -->
      <aside class="detail-panel">
        <div class="panel-title"><span>箱位详情</span></div>
        <template v-if="selected">
          <dl class="detail-grid">
            <div><dt>箱位编号</dt><dd>{{ selected.箱位编号 }}</dd></div>
            <div><dt>所在箱区</dt><dd>{{ selected.所在箱区 }}</dd></div>
            <div><dt>贝位号</dt><dd>贝{{ selected.贝位号 }}</dd></div>
            <div><dt>排位号</dt><dd>排{{ selected.排位号 }}</dd></div>
            <div><dt>层高上限</dt><dd>{{ selected.层高上限 }} 层</dd></div>
            <div><dt>当前层数</dt><dd>
              <span :class="{ 'error-text': selected.层高越界 }">{{ selected.当前层数 }} 层</span>
            </dd></div>
            <div><dt>堆放箱型</dt><dd>{{ selected.堆放箱型 }}</dd></div>
            <div><dt>箱位状态</dt><dd>
              <span :class="statusClass(selected)">{{ selected.箱位状态 }}</span>
            </dd></div>
          </dl>
          <p v-if="selected.层高越界" class="error-text over-tip">
            当前堆放 {{ selected.当前层数 }} 层，已超过层高上限 {{ selected.层高上限 }} 层，锁定会被拦截。
          </p>

          <div class="detail-actions">
            <label>
              <span>落箱箱号</span>
              <input v-model="allocateForm.箱号" placeholder="如 CBHU1000114" />
            </label>
            <label>
              <span>落箱箱型</span>
              <select v-model="allocateForm.箱型">
                <option v-for="type in containerTypes" :key="type" :value="type">{{ type }}</option>
              </select>
            </label>
            <button class="btn primary" type="button" @click="runAction('分配箱位')">分配箱位</button>
            <button class="btn" type="button" @click="runAction('预留箱位')">预留箱位</button>
            <button class="btn" type="button" @click="runAction('释放箱位')">释放箱位</button>
            <button class="btn" type="button" @click="runAction('锁定箱位')">锁定箱位</button>
          </div>

          <div class="alloc-title">分配明细（{{ selected.分配明细.length }} 只）</div>
          <table class="data-table alloc-table">
            <thead><tr><th>箱号</th><th>箱型</th><th>占位</th></tr></thead>
            <tbody>
              <tr v-for="item in selected.分配明细" :key="item.id">
                <td>{{ item.箱号 }}</td>
                <td>{{ item.箱型 }}</td>
                <td>{{ tierOf(item.箱型) }} 层</td>
              </tr>
              <tr v-if="!selected.分配明细.length">
                <td colspan="3" class="empty-state">暂无落箱记录</td>
              </tr>
            </tbody>
          </table>
        </template>
        <p v-else class="empty-state">点击矩阵图中的箱位查看详情与分配明细</p>
      </aside>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆场策划记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/yardplan'
const statuses = ['空闲', '已占用', '预留中', '已锁定']
const containerTypes = ['20GP', '40GP', '40HQ', '45HQ']
const TYPE_TIERS: Record<string, number> = { '20GP': 1, '40GP': 1, '40HQ': 2, '45HQ': 2 }

interface Allocation {
  id: number
  箱位id: number
  箱号: string
  箱型: string
}

interface Slot {
  id: number
  箱位编号: string
  所在箱区: string
  贝位号: number
  排位号: number
  层高上限: number
  当前层数: number
  堆放箱型: string
  箱位状态: string
  层高越界: boolean
  分配明细: Allocation[]
  [key: string]: unknown
}

interface Board {
  箱区: string[]
  箱位总数: number
  占位数: number
  已占用箱位: number
  预留箱位: number
  锁定箱位: number
  空闲箱位: number
  越界箱位: number
}

const slots = ref<Slot[]>([])
const total = ref(0)
const board = ref<Board>({
  箱区: [], 箱位总数: 0, 占位数: 0, 已占用箱位: 0, 预留箱位: 0, 锁定箱位: 0, 空闲箱位: 0, 越界箱位: 0,
})
const errorMessage = ref('')
const selectedId = ref<number | null>(null)
const filters = reactive({ block: '', status: '' })
const allocateForm = reactive({ 箱号: '', 箱型: '20GP' })

const blocks = computed(() => board.value.箱区)

// 矩阵图直接从同一份 slots 派生：行排位、列贝位，杜绝两处占用不一致。
const matrix = computed(() => {
  const bays = [...new Set(slots.value.map((slot) => slot.贝位号))].sort((a, b) => a - b)
  const tiers = [...new Set(slots.value.map((slot) => slot.排位号))].sort((a, b) => a - b)
  const index: Record<string, Slot> = {}
  for (const slot of slots.value) {
    index[`${slot.贝位号}-${slot.排位号}`] = slot
  }
  return { bays, tiers, index }
})

const selected = computed(() => slots.value.find((slot) => slot.id === selectedId.value) ?? null)

const boardCards = computed(() => [
  { label: '箱位总数', value: board.value.箱位总数, danger: false },
  { label: '占位数（按分配明细重算）', value: board.value.占位数, danger: false },
  { label: '已占用箱位', value: board.value.已占用箱位, danger: false },
  { label: '预留箱位', value: board.value.预留箱位, danger: false },
  { label: '锁定箱位', value: board.value.锁定箱位, danger: false },
  { label: '空闲箱位', value: board.value.空闲箱位, danger: false },
  { label: '层高越界箱位', value: board.value.越界箱位, danger: board.value.越界箱位 > 0 },
])

function tierOf(type: string): number {
  return TYPE_TIERS[type] ?? 1
}

function cellClass(slot: Slot): Record<string, boolean> {
  return {
    free: slot.箱位状态 === '空闲',
    occupied: slot.箱位状态 === '已占用',
    reserved: slot.箱位状态 === '预留中',
    locked: slot.箱位状态 === '已锁定',
    selected: slot.id === selectedId.value,
    over: slot.层高越界,
  }
}

function statusClass(slot: Slot): Record<string, boolean> {
  return {
    'status-free': slot.箱位状态 === '空闲',
    'status-occupied': slot.箱位状态 === '已占用',
    'status-reserved': slot.箱位状态 === '预留中',
    'status-locked': slot.箱位状态 === '已锁定',
  }
}

function resetFilters() {
  filters.block = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '箱位登记入口尚未接入审批流'
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string }
    if (payload.detail) {
      return payload.detail
    }
  } catch {
    // 非 JSON 响应时退回状态码说明
  }
  return `服务端返回 ${response.status}，操作未生效`
}

async function runAction(action: string) {
  if (!selected.value) {
    errorMessage.value = '请先在矩阵图中选择一块箱位'
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${selected.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action,
          ...(action === '分配箱位' ? { 箱号: allocateForm.箱号.trim(), 箱型: allocateForm.箱型 } : {}),
        },
      }),
    })
    if (!response.ok) {
      // 服务端报的错原样带出，不替换成笼统提示
      throw new Error(await readError(response))
    }
    allocateForm.箱号 = ''
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆场策划操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.block) query.set('block', filters.block)
  if (filters.status) query.set('status', filters.status)
  query.set('size', '1000')
  try {
    const [listResponse, boardResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/board`),
    ])
    if (!listResponse.ok) {
      throw new Error(await readError(listResponse))
    }
    if (!boardResponse.ok) {
      throw new Error(await readError(boardResponse))
    }
    const payload = (await listResponse.json()) as { items: Slot[]; total: number }
    slots.value = payload.items
    total.value = payload.total
    board.value = (await boardResponse.json()) as Board
    if (selectedId.value && !slots.value.some((slot) => slot.id === selectedId.value)) {
      selectedId.value = null
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆场策划列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.yard-layout { display: flex; gap: 12px; align-items: flex-start; }
.matrix-panel { flex: 2; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.detail-panel { flex: 1; min-width: 320px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.panel-title { display: flex; justify-content: space-between; align-items: center; font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.legend { font-weight: 400; font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 4px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin: 0 2px 0 8px; border: 1px solid var(--border); }
.dot.free { background: #f1f5f9; }
.dot.occupied { background: #dbeafe; }
.dot.reserved { background: #fef3c7; }
.dot.locked { background: #dcfce7; }
.dot.over { background: #fee2e2; border-color: #b42318; }

.matrix-table { width: 100%; border-collapse: collapse; }
.matrix-table th { font-size: 12px; color: var(--muted); padding: 6px 4px; }
.axis-corner { text-align: left; }
.axis-label { font-weight: 600; color: #475569; font-size: 12px; white-space: nowrap; }
.matrix-cell-box { padding: 4px; text-align: center; }
.cell { width: 100%; min-width: 92px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 4px; cursor: pointer; background: #f1f5f9; display: flex; flex-direction: column; gap: 2px; }
.cell:hover { border-color: var(--brand); }
.cell.selected { outline: 2px solid var(--brand); }
.cell.occupied { background: #dbeafe; }
.cell.reserved { background: #fef3c7; }
.cell.locked { background: #dcfce7; }
.cell.over { background: #fee2e2; border-color: #b42318; }
.cell-code { font-size: 12px; font-weight: 600; }
.cell-tier { font-size: 11px; color: var(--muted); }
.cell-empty { color: #cbd5e1; }

.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin: 0 0 10px; }
.detail-grid dt { font-size: 11px; color: var(--muted); }
.detail-grid dd { margin: 0; font-size: 13px; }
.over-tip { font-size: 12px; margin: 0 0 10px; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; border-top: 1px solid var(--border); padding-top: 10px; }
.detail-actions label { display: flex; flex-direction: column; font-size: 12px; color: var(--muted); gap: 2px; }
.detail-actions input, .detail-actions select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
.alloc-title { font-size: 13px; font-weight: 600; margin: 12px 0 6px; }
.alloc-table { font-size: 12px; }
.status-occupied { color: #1d4ed8; }
.status-reserved { color: #b45309; }
.status-locked { color: #15803d; }
.status-free { color: var(--muted); }
</style>
