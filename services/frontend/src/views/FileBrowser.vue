<template>
  <div>
    <div style="margin-bottom:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <el-select v-model="dirKey" style="width:160px" @change="loadDir">
        <el-option label="源文件 (SMB)" value="originals" />
        <el-option label="输出目录 (NFS)" value="output" />
        <el-option label="缓存目录 (NFS)" value="cache" />
        <el-option label="整理目录 (NFS)" value="organized" />
      </el-select>
      <el-tooltip content="返回上一级" placement="bottom">
        <el-button :disabled="!currentRelPath" circle size="small" @click="goUp">
          <el-icon><Top /></el-icon>
        </el-button>
      </el-tooltip>
      <el-breadcrumb v-if="currentRelPath !== undefined" separator="/">
        <el-breadcrumb-item><a @click="goToPath('')">{{ dirKey }}</a></el-breadcrumb-item>
        <el-breadcrumb-item v-for="(seg, i) in pathSegments" :key="i">
          <a @click="goToPath(seg.fullPath)">{{ seg.name }}</a>
        </el-breadcrumb-item>
      </el-breadcrumb>
      <div style="margin-left:auto;display:flex;gap:6px">
        <el-button size="small" @click="showSources = !showSources">
          <el-icon><Setting /></el-icon> 扫描源
        </el-button>
      </div>
    </div>

    <div v-if="showSources" style="margin-bottom:14px;border:1px solid #e8e8e8;border-radius:6px;padding:14px">
      <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
        <span style="font-weight:600;font-size:13px">扫描源管理</span>
        <el-button size="small" type="primary" @click="showAddSource = true">添加路径</el-button>
        <el-button size="small" @click="triggerScanAll" :loading="scanningAll">扫描全部</el-button>
        <el-tag v-if="scanMsg" :type="scanMsg.type" size="small">{{ scanMsg.text }}</el-tag>
      </div>
      <el-table :data="sources" size="small" stripe style="width:100%">
        <el-table-column prop="name" label="名称" width="120" />
        <el-table-column prop="path" label="路径" min-width="250" />
        <el-table-column prop="source_type" label="类型" width="80" />
        <el-table-column prop="file_count" label="文件数" width="80" />
        <el-table-column label="上次扫描" width="160">
          <template #default="{row}">{{ row.last_scanned || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{row}">
            <el-button size="small" link @click="triggerScan(row.id)" :loading="scanningId === row.id">扫描</el-button>
            <el-popconfirm title="删除此扫描源?" @confirm="deleteSource(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div style="display:flex;gap:12px">
      <div style="flex:1;min-width:0">
        <el-card shadow="never">
          <template #header>
            <span style="font-size:13px;font-weight:600">目录</span>
            <span style="float:right;font-size:12px;color:#909399">{{ dirs.length }} 目录</span>
          </template>
          <div style="max-height:300px;overflow-y:auto">
            <div v-for="d in dirs" :key="d.name" class="file-row" @click="openDir(d)">
              <el-icon style="color:#e6a23c"><FolderOpened /></el-icon>
              <span class="file-name" style="font-weight:500">{{ d.name }}</span>
              <span class="file-actions"></span>
            </div>
            <el-empty v-if="!dirs.length" description="无子目录" :image-size="40" />
          </div>
        </el-card>
        <el-card shadow="never" style="margin-top:12px">
          <template #header>
            <span style="font-size:13px;font-weight:600">文件</span>
            <span style="float:right;font-size:12px;color:#909399">{{ files.length }} 文件 · 第 {{ page }} / {{ totalPages }} 页</span>
          </template>
          <div v-loading="loading" style="min-height:150px" v-if="files.length">
            <div v-for="f in pagedFiles" :key="f.name" class="file-row">
              <el-icon style="color:#409eff"><Document /></el-icon>
              <span class="file-name">{{ f.name }}</span>
              <span class="file-size">{{ (f.size/1024).toFixed(1) }} KB</span>
              <span class="file-actions">
                <el-button link size="small" @click.stop="previewFile(f)">查看</el-button>
                <el-button link size="small" type="danger" @click.stop="deleteFile(f)">删除</el-button>
              </span>
            </div>
            <div style="text-align:center;padding:12px" v-if="totalPages>1">
              <el-pagination small background layout="prev,pager,next" :total="files.length" :page-size="pageSize" v-model:current-page="page" @current-change="()=>{}" />
            </div>
          </div>
          <el-empty v-else description="无文件" :image-size="40" />
        </el-card>
      </div>
      <div v-if="previewContent !== null" style="width:45%;min-width:300px">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-size:13px;font-weight:600">{{ previewFileName }}</span>
              <div><el-tag size="small" v-if="previewEncoding">{{ previewEncoding }}</el-tag><el-button link style="margin-left:8px" @click="previewContent=null">关闭</el-button></div>
            </div>
          </template>
          <pre class="full-content" style="max-height:70vh;font-size:14px;line-height:1.9">{{ previewContent }}</pre>
        </el-card>
      </div>
    </div>

    <el-dialog v-model="showAddSource" title="添加扫描源" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="newSource.name" placeholder="例如：SMB 电子书" /></el-form-item>
        <el-form-item label="路径"><el-input v-model="newSource.path" placeholder="例如：/data/originals" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="newSource.source_type">
            <el-option label="本地" value="local" />
            <el-option label="SMB" value="smb" />
            <el-option label="NFS" value="nfs" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddSource=false">取消</el-button>
        <el-button type="primary" @click="doAddSource" :loading="addingSource">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Top, Setting } from '@element-plus/icons-vue'
import api from '../api.js'

const dirKey = ref('originals')
const currentRelPath = ref('')
const dirs = ref([])
const allFiles = ref([])
const loading = ref(false)
const previewContent = ref(null)
const previewFileName = ref('')
const previewEncoding = ref('')
const page = ref(1)
const pageSize = ref(20)
const showSources = ref(false)
const sources = ref([])
const scanningAll = ref(false)
const scanningId = ref(null)
const scanMsg = ref(null)
const showAddSource = ref(false)
const addingSource = ref(false)
const newSource = ref({ name: '', path: '', source_type: 'local' })

onMounted(() => { loadDir(); loadSources() })
watch(dirKey, () => { currentRelPath.value = ''; page.value = 1; loadDir() })
watch(page, () => {})

const pathSegments = computed(() => {
  if (!currentRelPath.value) return []
  const parts = currentRelPath.value.split('/').filter(Boolean)
  let acc = ''
  return parts.map(p => { acc = acc ? acc+'/'+p : p; return { name: p, fullPath: acc } })
})
const totalPages = computed(() => Math.max(1, Math.ceil(allFiles.value.length / pageSize.value)))
const pagedFiles = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return allFiles.value.slice(start, start + pageSize.value)
})
const files = computed(() => allFiles.value)

async function loadDir() {
  loading.value = true; previewContent.value = null
  try {
    const r = await api.get('/files/list', { params: { path: currentRelPath.value, dir_key: dirKey.value } })
    dirs.value = r.data.dirs || []
    allFiles.value = r.data.files || []
  } catch(e) { dirs.value = []; allFiles.value = [] }
  loading.value = false
}
async function loadSources() {
  try { const r = await api.get('/sources'); sources.value = r.data || [] } catch(e) { sources.value = [] }
}
function goToPath(p) { currentRelPath.value = p; page.value = 1; loadDir() }
function goUp() {
  if (!currentRelPath.value) return
  const parts = currentRelPath.value.split('/').filter(Boolean)
  parts.pop()
  goToPath(parts.join('/'))
}
function openDir(d) { goToPath(d.path) }

async function previewFile(f) {
  try {
    const r = await api.get('/files/read', { params: { path: f.path, dir_key: dirKey.value } })
    previewContent.value = r.data.content || '(无法读取)'
    previewFileName.value = f.name
    previewEncoding.value = r.data.encoding || ''
  } catch(e) { ElementPlus.ElMessage.error('读取失败') }
}
async function deleteFile(f) {
  try {
    await ElementPlus.ElMessageBox.confirm('确定删除 ' + f.name + ' ？', '确认')
    await api.post('/files/delete', { path: f.path, dir_key: dirKey.value })
    ElementPlus.ElMessage.success('已删除'); loadDir()
  } catch(e) { if (e !== 'cancel') ElementPlus.ElMessage.error('删除失败') }
}

async function triggerScan(id) {
  scanningId.value = id
  try { await api.post(`/sources/${id}/scan?cleanup=true`); ElementPlus.ElMessage.success('扫描已触发') } catch(e) { ElementPlus.ElMessage.error('扫描失败') }
  scanningId.value = null
}
async function triggerScanAll() {
  scanningAll.value = true; scanMsg.value = { type: 'info', text: '扫描中...' }
  try {
    await api.post('/sources/scan-all?cleanup=true')
    scanMsg.value = { type: 'success', text: '已触发全部扫描' }
  } catch(e) { scanMsg.value = { type: 'danger', text: '扫描失败' } }
  scanningAll.value = false; loadSources()
}
async function deleteSource(id) {
  try { await api.delete(`/sources/${id}`); ElementPlus.ElMessage.success('已删除'); loadSources() } catch(e) { ElementPlus.ElMessage.error('删除失败') }
}
async function doAddSource() {
  if (!newSource.value.name || !newSource.value.path) { ElementPlus.ElMessage.warning('请填写名称和路径'); return }
  addingSource.value = true
  try {
    await api.post('/sources', newSource.value)
    ElementPlus.ElMessage.success('已添加'); showAddSource.value = false; newSource.value = { name: '', path: '', source_type: 'local' }
    loadSources()
  } catch(e) { ElementPlus.ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message)) }
  addingSource.value = false
}
</script>

<style scoped>
.file-row { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-bottom: 1px solid #f5f5f5; cursor: pointer; font-size: 13px; }
.file-row:hover { background: #f0f2f5; }
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: #909399; width: 70px; text-align: right; font-size: 12px; }
.file-actions { width: 100px; text-align: right; }
</style>
