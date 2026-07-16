<template>
  <div v-loading="loading">
    <el-card style="margin-bottom:14px">
      <template #header>文档健康检查</template>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span style="font-size:13px;font-weight:600">扫描源:</span>
        <el-select v-model="selectedSource" style="width:360px" size="small" filterable placeholder="选择扫描源" @change="onSourceChange">
          <el-option v-for="s in sources" :key="s.path" :label="s.name + ' (' + s.path + ')'" :value="s.path" />
        </el-select>
        <el-button size="small" @click="toggleBrowse" :type="showBrowser?'warning':'default'">
          {{ showBrowser ? '收起浏览' : '浏览目录' }}
        </el-button>
        <el-button size="small" type="primary" @click="startScan" :loading="status.running" :disabled="status.running">
          开始扫描
        </el-button>
        <el-button size="small" type="danger" @click="stopScan" :disabled="!status.running">
          停止
        </el-button>
        <el-button size="small" @click="refreshStatus">刷新状态</el-button>
      </div>
    </el-card>

    <el-card v-if="showBrowser" style="margin-bottom:14px">
      <template #header>
        <span style="font-weight:600">目录浏览</span>
        <span style="float:right;font-size:12px;color:#909399">当前: {{ scanRoot }}</span>
      </template>
      <div style="margin-bottom:8px;display:flex;align-items:center;gap:4px;flex-wrap:wrap">
        <el-button size="small" link @click="browseTo('/')">/</el-button>
        <template v-for="(seg, idx) in pathSegments" :key="idx">
          <span style="color:#c0c4cc">/</span>
          <el-button size="small" link @click="browseTo(seg.path)">{{ seg.name }}</el-button>
        </template>
        <span style="margin-left:auto;font-size:12px;color:#909399">{{ subdirs.length }} 个子目录</span>
      </div>
      <el-input v-model="dirFilter" size="small" placeholder="筛选目录..." clearable style="margin-bottom:8px" />
      <div style="max-height:300px;overflow-y:auto;border:1px solid #ebeef5;border-radius:4px">
        <div v-if="subdirs.length === 0" style="padding:20px;text-align:center;color:#c0c4cc;font-size:13px">
          无子目录
        </div>
        <div v-for="d in filteredDirs" :key="d.path"
          :class="['dir-item', { active: d.path === scanRoot }]"
          @click="browseTo(d.path)"
          @dblclick="selectDir(d.path)"
          style="padding:6px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f2f2f2"
          @mouseenter="$el?.classList?.add('hover')"
          @mouseleave="$el?.classList?.remove('hover')">
          <span style="font-size:16px">📁</span>
          <span style="flex:1">{{ d.name }}</span>
          <el-button size="small" link type="primary" @click.stop="selectDir(d.path)">选择</el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="14" style="margin-bottom:14px">
      <el-col :span="6">
        <el-card>
          <div style="text-align:center">
            <div style="font-size:28px;font-weight:700;color:#409eff">{{ stats.total }}</div>
            <div style="font-size:12px;color:#909399">已检查</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div style="text-align:center">
            <div style="font-size:28px;font-weight:700;color:#67c23a">{{ stats.ok }}</div>
            <div style="font-size:12px;color:#909399">正常</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div style="text-align:center">
            <div style="font-size:28px;font-weight:700;color:#e6a23c">{{ stats.warning }}</div>
            <div style="font-size:12px;color:#909399">警告</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div style="text-align:center">
            <div style="font-size:28px;font-weight:700;color:#f56c6c">{{ stats.error }}</div>
            <div style="font-size:12px;color:#909399">异常</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="status.running" style="margin-bottom:14px">
      <template #header>扫描进度</template>
      <div style="display:flex;align-items:center;gap:12px">
        <el-progress :percentage="progressPct" :status="status.running?'':'success'" style="flex:1" />
        <span style="font-size:12px;color:#909399">已扫描 {{ status.scanned }} 个文件</span>
      </div>
    </el-card>

    <el-card style="margin-bottom:14px">
      <template #header>
        结果
        <span style="float:right;font-size:12px;color:#909399">
          <el-button size="small" link @click="loadResults">刷新</el-button>
          <el-button size="small" link @click="exportReport('csv')">导出 CSV</el-button>
          <el-button size="small" link @click="exportReport('xlsx')">导出 Excel</el-button>
          <el-button size="small" link @click="loadAI" :loading="aiLoading">AI 分析</el-button>
          <el-select v-model="filterStatus" size="small" style="width:100px;margin-left:8px" placeholder="筛选" @change="loadResults">
            <el-option label="全部" value="" />
            <el-option label="正常" value="ok" />
            <el-option label="警告" value="warning" />
            <el-option label="异常" value="error" />
          </el-select>
        </span>
      </template>
      <el-table :data="results" style="width:100%" size="small" max-height="500" stripe>
        <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ext" label="类型" width="70" />
        <el-table-column prop="category" label="分类" width="80" />
        <el-table-column prop="size" label="大小" width="80">
          <template #default="{row}">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{row}">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="encoding" label="编码" width="90" />
        <el-table-column label="问题" min-width="200">
          <template #default="{row}">
            <span v-if="row.issues?.length" style="font-size:12px;color:#f56c6c">
              <div v-for="(iss,idx) in row.issues.slice(0,3)" :key="idx">{{ iss.message }}</div>
              <el-popover v-if="row.issues.length > 3" trigger="click" placement="right" :width="300">
                <template #reference>
                  <el-button link size="small">还有 {{ row.issues.length - 3 }} 个...</el-button>
                </template>
                <div v-for="(iss,idx) in row.issues" :key="idx" style="font-size:12px;padding:2px 0">
                  <el-tag :type="iss.severity==='error'?'danger':'warning'" size="small" style="margin-right:4px">{{ iss.type }}</el-tag>
                  {{ iss.message }}
                </div>
              </el-popover>
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="totalResults > results.length" style="text-align:center;margin-top:10px">
        <el-button size="small" link @click="page++">加载更多 ({{ results.length }}/{{ totalResults }})</el-button>
      </div>
    </el-card>

    <el-card v-if="aiAnalysis" style="margin-bottom:14px">
      <template #header>AI 分析报告</template>
      <div style="white-space:pre-wrap;font-size:13px;line-height:1.7;max-height:400px;overflow-y:auto">
        {{ aiAnalysis }}
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api.js'

const loading = ref(false)
const scanRoot = ref('/data/originals')
const selectedSource = ref('/data/originals')
const sources = ref([])
const status = ref({ running: false, scanned: 0, checked: 0 })
const stats = ref({ total: 0, ok: 0, warning: 0, error: 0 })
const results = ref([])
const page = ref(1)
const totalResults = ref(0)
const filterStatus = ref('')
const aiAnalysis = ref(null)
const aiLoading = ref(false)
const showBrowser = ref(false)
const subdirs = ref([])
const dirFilter = ref('')

const progressPct = computed(() => {
  if (!status.value.checked || !status.value.scanned) return 0
  return Math.round((status.value.checked / status.value.scanned) * 100)
})

const pathSegments = computed(() => {
  const parts = scanRoot.value.replace(/\/+/g, '/').split('/').filter(Boolean)
  let cur = ''
  return parts.map(p => {
    cur += '/' + p
    return { name: p, path: cur }
  })
})

const filteredDirs = computed(() => {
  if (!dirFilter.value) return subdirs.value
  const q = dirFilter.value.toLowerCase()
  return subdirs.value.filter(d => d.name.toLowerCase().includes(q))
})

onMounted(async () => {
  try {
    const r = await api.get('/health-check/sources')
    sources.value = r.data || []
    if (sources.value.length) {
      selectedSource.value = sources.value[0].path
      scanRoot.value = sources.value[0].path
    }
  } catch {}
  refreshStatus()
})

async function onSourceChange(val) {
  scanRoot.value = val
  if (showBrowser.value) await loadSubdirs(val)
}

async function toggleBrowse() {
  showBrowser.value = !showBrowser.value
  if (showBrowser.value) await loadSubdirs(scanRoot.value)
}

async function loadSubdirs(path) {
  try {
    const r = await api.get('/health-check/browse', { params: { path } })
    subdirs.value = r.data.dirs || []
  } catch {
    subdirs.value = []
  }
}

async function browseTo(path) {
  scanRoot.value = path
  await loadSubdirs(path)
}

function selectDir(path) {
  scanRoot.value = path
}

async function refreshStatus() {
  try {
    const [s, st, r] = await Promise.all([
      api.get('/health-check/status'),
      api.get('/health-check/stats'),
      api.get('/health-check/results?size=50'),
    ])
    status.value = s.data
    stats.value = st.data
    results.value = r.data.items || []
    totalResults.value = r.data.total || 0
  } catch { /* health check not available */ }
}

async function startScan() {
  try {
    await api.post('/health-check/start', null, { params: { scan_root: scanRoot.value } })
    ElementPlus.ElMessage.success('扫描已启动: ' + scanRoot.value)
    const poll = setInterval(async () => {
      try {
        const s = await api.get('/health-check/status')
        status.value = s.data
        if (!s.data.running) {
          clearInterval(poll)
          refreshStatus()
        }
      } catch { clearInterval(poll) }
    }, 2000)
  } catch (e) {
    ElementPlus.ElMessage.error('启动失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function stopScan() {
  try {
    await api.post('/health-check/stop')
    ElementPlus.ElMessage.success('已停止')
  } catch (e) {
    ElementPlus.ElMessage.error('停止失败')
  }
}

async function loadResults() {
  try {
    const r = await api.get('/health-check/results', { params: { page: page.value, size: 50, status: filterStatus.value } })
    if (page.value === 1) results.value = r.data.items || []
    else results.value = results.value.concat(r.data.items || [])
    totalResults.value = r.data.total || 0
  } catch {}
}

async function exportReport(fmt) {
  try {
    const r = await api.get('/health-check/results/export', { params: { fmt }, responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([r.data]))
    const a = document.createElement('a')
    a.href = url; a.download = 'health_report.' + fmt; a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElementPlus.ElMessage.error('导出失败')
  }
}

async function loadAI() {
  aiLoading.value = true
  try {
    const r = await api.get('/health-check/results/ai-analysis')
    aiAnalysis.value = r.data.analysis
  } catch (e) {
    ElementPlus.ElMessage.error('AI 分析失败，请先执行扫描')
  }
  aiLoading.value = false
}

function statusTag(s) {
  if (s === 'ok') return 'success'
  if (s === 'warning') return 'warning'
  if (s === 'error') return 'danger'
  return 'info'
}

function formatSize(bytes) {
  if (!bytes) return '0B'
  const k = 1024
  const sizes = ['B','KB','MB','GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(1) + sizes[i]
}
</script>

<style scoped>
.dir-item:hover {
  background: #ecf5ff;
}
.dir-item.active {
  background: #ecf5ff;
  font-weight: 600;
}
</style>
