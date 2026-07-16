<template>
  <div>
    <div class="stats-row">
      <el-card shadow="hover"><div style="font-size:12px;color:#909399">总计</div><div style="font-size:28px;font-weight:700">{{ stats?.total || 0 }}</div></el-card>
      <el-card shadow="hover"><div style="font-size:12px;color:#909399">已解析</div><div style="font-size:28px;font-weight:700;color:#67c23a">{{ stats?.parsed || 0 }}</div></el-card>
      <el-card shadow="hover"><div style="font-size:12px;color:#909399">已分类</div><div style="font-size:28px;font-weight:700;color:#409eff">{{ stats?.classified || 0 }}</div></el-card>
      <el-card shadow="hover"><div style="font-size:12px;color:#909399">已向量化</div><div style="font-size:28px;font-weight:700;color:#e6a23c">{{ stats?.embedded || 0 }}</div></el-card>
    </div>
    <div class="chart-row">
      <el-card><template #header><span style="font-size:13px">处理状态</span></template><div ref="chartRef" style="height:240px"></div></el-card>
      <el-card><template #header><span style="font-size:13px">批量操作</span></template>
        <div style="display:flex;flex-direction:column;gap:8px">
          <el-button size="small" :loading="busy.enrich" @click="runBatchEnrich">
            <el-icon><MagicStick /></el-icon> 批量AI分类 ({{ stats ? stats.total - stats.classified : '?' }} 待处理)
          </el-button>
          <el-button size="small" :loading="busy.embed" @click="runBatchEmbed">
            <el-icon><Collection /></el-icon> 批量向量化 ({{ stats ? stats.total - stats.embedded : '?' }} 待处理)
          </el-button>
          <el-button size="small" :loading="busy.scan" @click="runScan">
            <el-icon><Refresh /></el-icon> 扫描新文件
          </el-button>
          <el-button size="small" :loading="busy.repair" type="warning" @click="runRepair">
            <el-icon><WarnTriangleFilled /></el-icon> 修复乱码文档 (100篇/批)
          </el-button>
          <el-tag v-if="lastMsg" :type="lastMsg.type" size="small">{{ lastMsg.text }}</el-tag>
        </div>
      </el-card>
    </div>
    <el-card><template #header><span style="font-size:13px">最近文档</span></template>
      <template v-if="recentDocs.length">
        <DocumentCard v-for="d in recentDocs" :key="d.id" :doc="d" @click="router.push('/doc/'+d.id)" @read="reader?.open(d.id)" />
      </template>
      <el-empty v-else description="暂无文档" :image-size="50"/>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch, inject, reactive } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api.js'
import DocumentCard from '../components/DocumentCard.vue'

const router = useRouter()
const reader = inject('reader')
const stats = ref(null); const catList = ref([]); const recentDocs = ref([]); const chartRef = ref(null)
const busy = reactive({ enrich: false, embed: false, scan: false, repair: false })
const lastMsg = ref(null)

async function load() {
  try {
    const [sr, cr, dr] = await Promise.all([
      api.get('/stats'), api.get('/categories'), api.get('/documents?limit=10')
    ])
    stats.value = sr.data; catList.value = cr.data || []
    recentDocs.value = dr.data.items || dr.data || []
  } catch(e) {}
  nextTick(initChart)
}
onMounted(load)
watch(stats, () => setTimeout(initChart, 200))

function initChart() {
  if (!chartRef.value || !stats.value) return
  const ec = echarts.getInstanceByDom(chartRef.value) || echarts.init(chartRef.value)
  const p = stats.value
  ec.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    color: ['#67c23a','#e6a23c','#409eff','#909399'],
    series: [{ type: 'pie', radius: ['35%','65%'], data: [
      { value: p.parsed||0, name: '已解析' },
      { value: Math.max(0,(p.total||0)-(p.parsed||0)), name: '待解析' },
      { value: p.classified||0, name: '已分类' },
      { value: p.embedded||0, name: '已向量化' },
    ], label: { formatter: '{b}\n{c}', fontSize: 11 } }]
  })
}

async function runBatchEnrich() {
  busy.enrich = true; lastMsg.value = { type: 'info', text: '启动批量分类（后台运行）...' }
  try {
    await api.post('/documents/enrich-batch?limit=20')
    lastMsg.value = { type: 'success', text: '批量分类完成一批（20篇），继续运行中' }
    load()
  } catch(e) { lastMsg.value = { type: 'danger', text: '批量分类失败: '+ (e.response?.data?.detail||e.message) } }
  busy.enrich = false
}
async function runBatchEmbed() {
  busy.embed = true; lastMsg.value = { type: 'info', text: '启动批量向量化...' }
  try {
    await api.post('/embeddings/generate-batch?limit=20')
    lastMsg.value = { type: 'success', text: '批量向量化完成一批' }
    load()
  } catch(e) { lastMsg.value = { type: 'danger', text: '向量化失败: '+ (e.message) } }
  busy.embed = false
}
async function runRepair() {
  busy.repair = true; lastMsg.value = { type: 'info', text: '修复乱码文档中（100篇/批，后台运行）...' }
  try {
    await api.post('/documents/repair-garbled?limit=100')
    lastMsg.value = { type: 'success', text: '修复任务已启动，请刷新查看效果' }
    load()
  } catch(e) { lastMsg.value = { type: 'danger', text: '修复失败: '+ (e.message) } }
  busy.repair = false
}
async function runScan() {
  busy.scan = true; lastMsg.value = { type: 'info', text: '扫描中...' }
  try {
    const r = await api.post('/sources/scan-all')
    lastMsg.value = { type: 'success', text: '扫描完成，新增 ' + (r.data?.results?.[0]?.new_files||0) + ' 个文件' }
    load()
  } catch(e) { lastMsg.value = { type: 'danger', text: '扫描失败' } }
  busy.scan = false
}
</script>

<style scoped>
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px; }
.chart-row { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; margin-bottom: 14px; }
</style>
