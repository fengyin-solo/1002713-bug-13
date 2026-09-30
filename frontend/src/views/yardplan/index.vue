<template>
  <section class="page" data-module="yardplan">
    <header class="page-head">
      <div>
        <h2>堆场策划管理</h2>
        <p class="page-desc">
          矩阵图与明细共用同一份占用口径：贝位定列、排位定行；锁定时按有效层高拦截，释放后清除预留、保留堆放箱型。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记箱位</button>
        <button class="btn" type="button" @click="exportRows">导出堆场策划清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>箱位编号</span>
        <input v-model="filters.keyword" placeholder="按箱位编号检索" />
      </label>
      <label class="filter-item">
        <span>箱位状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <h3 class="block-title">箱位矩阵图</h3>
    <div class="matrix-scroll" v-if="matrixRows.length">
      <table class="matrix">
        <thead>
          <tr>
            <th class="axis-cell">排位 ＼ 贝位</th>
            <th v-for="bay in bayAxis" :key="bay">贝{{ bay }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rowIndex in rowAxis" :key="rowIndex">
            <td class="axis-cell">排{{ rowIndex }}</td>
            <td
              v-for="bay in bayAxis"
              :key="bay"
              class="cell"
              :class="cellClass(cellMap.get(`${bay}-${rowIndex}`))"
              @click="cellMap.get(`${bay}-${rowIndex}`) && selectSlot(cellMap.get(`${bay}-${rowIndex}`)!)"
            >
              <template v-if="cellMap.get(`${bay}-${rowIndex}`)">
                <span class="cell-name">{{ cellMap.get(`${bay}-${rowIndex}`)!.箱位编号 }}</span>
                <span class="cell-layer">
                  {{ cellMap.get(`${bay}-${rowIndex}`)!.当前层数 }}/{{ cellMap.get(`${bay}-${rowIndex}`)!.有效层高 }}层
                </span>
                <span class="cell-tags">
                  <em v-if="cellMap.get(`${bay}-${rowIndex}`)!.reserved" class="tag reserved">预留</em>
                  <em v-if="cellMap.get(`${bay}-${rowIndex}`)!.层高冲突" class="tag conflict">箱型优先</em>
                </span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty-block">当前筛选条件下没有可绘制的箱位</p>

    <div class="detail-layout">
      <div class="detail-panel" v-if="selected">
        <h3 class="block-title">箱位详情<span class="panel-close" @click="selected = null">×</span></h3>
        <dl class="detail-list">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ displayValue(selected, field) }}</dd>
          </template>
          <dt>有效层高</dt>
          <dd>
            {{ selected.有效层高 }} 层
            <em v-if="selected.层高冲突" class="tag conflict">层高与箱型冲突，已按箱型 {{ selected.堆放箱型 }} 重算</em>
          </dd>
          <dt>预留标记</dt>
          <dd>{{ selected.reserved ? '预留中' : '无' }}</dd>
        </dl>
        <div class="detail-actions">
          <button
            v-for="action in detailActions"
            :key="action.name"
            class="btn"
            :class="{ primary: action.name === '锁定箱位' }"
            type="button"
            :disabled="busyIds.has(selected.id) || action.disabled(selected)"
            @click="runAction(action.name, selected)"
          >
            {{ action.label }}
          </button>
        </div>
      </div>

      <div class="table-wrap" :class="{ 'with-panel': !!selected }">
        <h3 class="block-title">分配明细</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="column in columns" :key="column">{{ column }}</th>
              <th>标记</th>
              <th>可执行动作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="String(row.id)" :class="{ chosen: selected?.id === row.id }">
              <td v-for="column in columns" :key="column">
                <button v-if="column === '箱位编号'" class="link" type="button" @click="selectSlot(row)">
                  {{ cellText(row, column) }}
                </button>
                <template v-else>
                  <em v-if="column === '箱位状态' && row.status === '已锁定'" class="tag locked">已锁定</em>
                  <em v-else-if="column === '箱位状态' && row.reserved" class="tag reserved">预留中</em>
                  <template v-else>{{ cellText(row, column) }}</template>
                </template>
              </td>
              <td>
                <em v-if="row.层高冲突" class="tag conflict">箱型优先</em>
                <em v-if="row.reserved" class="tag reserved">预留</em>
                <span v-if="!row.reserved && !row.层高冲突">—</span>
              </td>
              <td class="row-actions">
                <button
                  v-for="action in rowActions"
                  :key="action"
                  class="link"
                  type="button"
                  :disabled="busyIds.has(row.id)"
                  @click="runAction(action, row)"
                >
                  {{ action }}
                </button>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td :colspan="columns.length + 2" class="empty-state">暂无堆场策划数据，可先登记箱位</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3 class="block-title">登记箱位</h3>
        <label v-for="field in createFields" :key="field" class="filter-item">
          <span>{{ field }}</span>
          <input
            v-model="createForm[field]"
            :type="numericFields.includes(field) ? 'number' : 'text'"
            :placeholder="`请输入${field}`"
          />
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="submit" :disabled="submitting">登记</button>
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆场策划记录</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Slot = {
  id: number
  箱位编号: string
  所在箱区: string
  贝位号: number
  排位号: number
  层高上限: number
  当前层数: number
  有效层高: number
  堆放箱型: string
  箱位状态: string
  status: string
  reserved: boolean
  层高冲突: boolean
}

const ENDPOINT = '/api/yardplan'
const columns = ['箱位编号', '所在箱区', '贝位号', '排位号', '层高上限', '当前层数', '堆放箱型', '箱位状态']
const detailFields = [...columns, '预留标记']
const rowActions = ['分配箱位', '锁定箱位', '释放箱位']
const statuses = ['空闲', '已占用', '预留中', '已锁定']
const createFields = ['箱位编号', '所在箱区', '贝位号', '排位号', '层高上限', '堆放箱型']
const numericFields = ['贝位号', '排位号', '层高上限']

const detailActions = [
  { name: '分配箱位', label: '分配箱位', disabled: (_row: Slot) => false },
  {
    name: '锁定箱位',
    label: '锁定箱位',
    disabled: (row: Slot) => row.status === '已锁定' || row.当前层数 >= row.有效层高,
  },
  { name: '释放箱位', label: '释放箱位', disabled: (_row: Slot) => false },
  { name: '预留箱位', label: '挂预留', disabled: (row: Slot) => row.reserved || row.status === '已锁定' },
  { name: '取消预留', label: '取消预留', disabled: (row: Slot) => !row.reserved },
]

const rows = ref<Slot[]>([])
const total = ref(0)
const selectedId = ref<number | null>(null)
const message = ref('')
const messageOk = ref(false)
const busyIds = ref<Set<number>>(new Set())
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })
const creating = ref(false)
const submitting = ref(false)
const createForm = reactive<Record<string, string>>({})

// 选中的详情与表格读同一份 rows，矩阵也读它：两处占用天然一致
const selected = computed<Slot | null>(() => {
  if (selectedId.value === null) return null
  return rows.value.find((row) => row.id === selectedId.value) ?? null
})

// 堆存看板：分配明细一动，这里全部由 rows 重算
const stats = computed(() => {
  const occupied = rows.value.filter((row) => row.当前层数 > 0)
  const boxes = rows.value.reduce((sum, row) => sum + Number(row.当前层数 || 0), 0)
  return [
    { label: '箱位总数', value: rows.value.length },
    { label: '占位数（有箱）', value: occupied.length },
    { label: '在场箱量（层）', value: boxes },
    { label: '预留箱位', value: rows.value.filter((row) => row.reserved).length },
    { label: '锁定箱位', value: rows.value.filter((row) => row.status === '已锁定').length },
  ]
})

// 矩阵坐标：按贝位号数值定列、排位号数值定行，杜绝按数组下标错位
const bayAxis = computed(() => axisOf('贝位号'))
const rowAxis = computed(() => axisOf('排位号'))
const matrixRows = computed(() => rows.value)
const cellMap = computed(() => {
  const map = new Map<string, Slot>()
  for (const row of rows.value) {
    map.set(`${Number(row.贝位号)}-${Number(row.排位号)}`, row)
  }
  return map
})

function axisOf(field: '贝位号' | '排位号'): number[] {
  return [...new Set(rows.value.map((row) => Number(row[field])))]
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b)
}

function cellClass(row: Slot | undefined): string[] {
  if (!row) return ['empty']
  const classes = [row.status === '已锁定' ? 'locked' : row.reserved ? 'reserved' : row.status]
  if (row.当前层数 >= row.有效层高) classes.push('full')
  if (selectedId.value === row.id) classes.push('chosen')
  return classes
}

function cellText(row: Slot, column: string): string {
  const value = (row as unknown as Record<string, unknown>)[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function displayValue(row: Slot, field: string): string | number {
  if (field === '预留标记') return row.reserved ? '预留中' : '无'
  const record = row as unknown as Record<string, string | number>
  return record[field] ?? '—'
}

function selectSlot(row: Slot) {
  selectedId.value = row.id
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  for (const field of createFields) createForm[field] = ''
  creating.value = true
}

async function submitCreate() {
  submitting.value = true
  message.value = ''
  const values: Record<string, string | number> = {}
  for (const field of createFields) {
    const raw = createForm[field]?.trim() ?? ''
    values[field] = numericFields.includes(field) && raw !== '' ? Number(raw) : raw
  }
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      // 服务端报的错原样带出，不替换成笼统提示
      throw new Error(payload?.detail ?? '箱位登记失败')
    }
    creating.value = false
    messageOk.value = true
    message.value = payload?.message ?? '箱位已登记'
    await reload()
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '箱位登记失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Slot) {
  // 同一块箱位的动作在途时直接挡住，重复锁定也只认服务端第一次
  if (busyIds.value.has(row.id)) {
    messageOk.value = false
    message.value = `箱位 ${row.箱位编号} 的动作正在提交，请勿重复点击`
    return
  }
  busyIds.value = new Set(busyIds.value).add(row.id)
  message.value = ''
  const values: Record<string, string> = { action }
  if (action === '分配箱位' && row.堆放箱型) values.堆放箱型 = row.堆放箱型
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      // 服务端 detail 原句直接显示（如越界箱位、重复锁定原因）
      throw new Error(payload?.detail ?? '堆场策划动作未生效')
    }
    messageOk.value = true
    message.value = payload?.message ?? '操作已生效'
    await reload()
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '堆场策划操作失败'
  } finally {
    const next = new Set(busyIds.value)
    next.delete(row.id)
    busyIds.value = next
  }
}

async function reload() {
  message.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('箱位列表读取失败')
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Slot[]
    total.value = payload.total ?? rows.value.length
    if (selectedId.value !== null && !rows.value.some((row) => row.id === selectedId.value)) {
      selectedId.value = null
    }
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '堆场策划列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.block-title { font-size: 14px; margin: 14px 0 8px; display: flex; justify-content: space-between; align-items: center; }
.ok-text { color: #067647; }
.empty-block { color: var(--muted); font-size: 13px; background: #fff; border: 1px dashed var(--border); padding: 18px; text-align: center; border-radius: 8px; }

.matrix-scroll { background: #fff; border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.matrix { border-collapse: collapse; width: 100%; }
.matrix th, .matrix td { border: 1px solid var(--border); text-align: center; font-size: 12px; padding: 0; }
.axis-cell { background: #f1f5f9; color: var(--muted); padding: 8px 10px; white-space: nowrap; font-weight: 600; }
.cell { min-width: 104px; height: 64px; cursor: pointer; vertical-align: middle; padding: 4px 6px; }
.cell.empty { background: #fafbfc; cursor: default; }
.cell-name { display: block; font-weight: 600; }
.cell-layer { display: block; color: var(--muted); }
.cell-tags { display: flex; gap: 4px; justify-content: center; margin-top: 2px; }
.cell.空闲 { background: #f8fafc; }
.cell.已占用 { background: #e0f2fe; }
.cell.预留中, .cell.reserved { background: #fef9c3; }
.cell.locked, .cell.已锁定 { background: #dbeafe; }
.cell.full { box-shadow: inset 0 0 0 2px #f59e0b; }
.cell.chosen { box-shadow: inset 0 0 0 2px var(--brand); }

.tag { display: inline-block; font-style: normal; font-size: 11px; border-radius: 4px; padding: 0 5px; line-height: 16px; }
.tag.reserved { background: #fde68a; color: #92400e; }
.tag.locked { background: #bfdbfe; color: #1e40af; }
.tag.conflict { background: #fee2e2; color: #b42318; }

.detail-layout { display: flex; gap: 12px; align-items: flex-start; }
.detail-panel { width: 300px; flex-shrink: 0; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.panel-close { cursor: pointer; color: var(--muted); font-size: 16px; }
.detail-list { display: grid; grid-template-columns: 88px 1fr; gap: 6px 8px; margin: 0 0 10px; font-size: 13px; }
.detail-list dt { color: var(--muted); }
.detail-list dd { margin: 0; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.table-wrap { flex: 1; min-width: 0; }
tr.chosen td { background: #eff6ff; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 16px 18px; width: 380px; display: flex; flex-direction: column; gap: 8px; }
.modal .filter-item { display: flex; flex-direction: column; gap: 2px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
