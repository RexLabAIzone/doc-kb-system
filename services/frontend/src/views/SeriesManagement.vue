<template>
  <div>
    <div style="margin-bottom:14px;display:flex;gap:8px;align-items:center">
      <el-button type="primary" size="small" @click="showCreate"><el-icon><Plus /></el-icon> 新建系列</el-button>
      <el-input v-model="searchQuery" placeholder="搜索系列..." size="small" style="width:200px" clearable @change="loadSeries" />
      <el-tag v-if="lastMsg" :type="lastMsg.type" size="small">{{ lastMsg.text }}</el-tag>
    </div>

    <el-table :data="seriesList" v-loading="loading" stripe size="small" style="width:100%">
      <el-table-column prop="name" label="系列名称" min-width="200">
        <template #default="{row}">
          <span style="cursor:pointer;color:#409eff" @click="showDetail(row)">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="metadata" label="描述" min-width="300">
        <template #default="{row}">
          {{ (row.metadata && row.metadata.description) || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{row}">
          <el-button size="small" :icon="Edit" @click="showEdit(row)">编辑</el-button>
          <el-popconfirm title="确认删除?" @confirm="doDelete(row.id)">
            <template #reference>
              <el-button size="small" type="danger" :icon="Delete">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!seriesList.length && !loading" description="暂无系列数据" />

    <el-dialog v-model="formVisible" :title="editing ? '编辑系列' : '新建系列'" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="formName" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="formDesc" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible=false">取消</el-button>
        <el-button type="primary" @click="doSave">{{ editing ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" :title="detailName + ' - 详情'" width="700px">
      <div v-loading="detailLoading">
        <div style="margin-bottom:10px;display:flex;gap:8px">
          <el-button size="small" type="primary" :icon="Plus" @click="showAddDoc">添加文档</el-button>
          <el-input v-model="addDocId" placeholder="输入文档ID" size="small" style="width:120px" v-if="showAddInput" />
          <el-button size="small" @click="confirmAddDoc" v-if="showAddInput">确认</el-button>
        </div>
        <el-table :data="seriesDocs" stripe size="small" style="width:100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="文档名称" min-width="300" />
          <el-table-column label="操作" width="80">
            <template #default="{row}">
              <el-popconfirm title="移出系列?" @confirm="removeDoc(row.id)">
                <template #reference>
                  <el-button size="small" type="danger" link>移除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import api from '../api.js'

const seriesList = ref([]); const loading = ref(false); const lastMsg = ref(null)
const searchQuery = ref('')
const formVisible = ref(false); const editing = ref(false); const editId = ref(null)
const formName = ref(''); const formDesc = ref('')
const detailVisible = ref(false); const detailLoading = ref(false)
const detailName = ref(''); const detailId = ref(null)
const seriesDocs = ref([])
const showAddInput = ref(false); const addDocId = ref('')

async function loadSeries() {
  loading.value = true
  try {
    const q = searchQuery.value ? `?q=${encodeURIComponent(searchQuery.value)}&type=series` : '?type=series&limit=100'
    const r = await api.get('/knowledge-graph/entities' + q)
    seriesList.value = r.data || []
  } catch(e) { seriesList.value = [] }
  loading.value = false
}
onMounted(loadSeries)

function showCreate() { editing.value = false; editId.value = null; formName.value = ''; formDesc.value = ''; formVisible.value = true }
function showEdit(row) { editing.value = true; editId.value = row.id; formName.value = row.name; formDesc.value = (row.metadata && row.metadata.description) || ''; formVisible.value = true }

async function doSave() {
  try {
    if (editing.value) {
      await api.put(`/series/${editId.value}?name=${encodeURIComponent(formName.value)}&description=${encodeURIComponent(formDesc.value)}`)
      ElementPlus.ElMessage.success('已更新')
    } else {
      await api.post(`/series?name=${encodeURIComponent(formName.value)}&description=${encodeURIComponent(formDesc.value)}`)
      ElementPlus.ElMessage.success('已创建')
    }
    formVisible.value = false; loadSeries()
  } catch(e) { ElementPlus.ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message)) }
}

async function doDelete(id) {
  try { await api.delete(`/series/${id}`); ElementPlus.ElMessage.success('已删除'); loadSeries() }
  catch(e) { ElementPlus.ElMessage.error('删除失败') }
}

async function showDetail(row) {
  detailVisible.value = true; detailLoading.value = true
  detailName.value = row.name; detailId.value = row.id
  try {
    const r = await api.get(`/series/${row.id}/documents`)
    seriesDocs.value = r.data || []
  } catch(e) { seriesDocs.value = [] }
  detailLoading.value = false
}

function showAddDoc() { showAddInput.value = true; addDocId.value = '' }
async function confirmAddDoc() {
  if (!addDocId.value) return
  try {
    await api.post(`/series/${detailId.value}/documents?doc_id=${addDocId.value}`)
    ElementPlus.ElMessage.success('已添加')
    showAddInput.value = false
    const r = await api.get(`/series/${detailId.value}/documents`)
    seriesDocs.value = r.data || []
  } catch(e) { ElementPlus.ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message)) }
}

async function removeDoc(entityId) {
  try {
    // Find the doc_id from the entity metadata
    const doc = seriesDocs.value.find(d => d.id === entityId)
    const docId = doc?.metadata?.doc_id
    if (docId) {
      await api.delete(`/series/${detailId.value}/documents/${docId}`)
      seriesDocs.value = seriesDocs.value.filter(d => d.id !== entityId)
      ElementPlus.ElMessage.success('已移除')
    }
  } catch(e) { ElementPlus.ElMessage.error('移除失败') }
}
</script>
