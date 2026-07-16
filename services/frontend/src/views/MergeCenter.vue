<template>
  <div v-loading="loading">
    <div style="margin-bottom:14px;display:flex;gap:8px">
      <el-button @click="loadGroups" size="small"><el-icon><Refresh /></el-icon> 刷新</el-button>
      <el-button @click="detectDuplicates" size="small" :loading="detecting" type="primary">
        <el-icon><Search /></el-icon> 检测重复文档 (向量+文本指纹)
      </el-button>
      <el-tag v-if="lastMsg" :type="lastMsg.type" size="small">{{ lastMsg.text }}</el-tag>
    </div>
    <div v-if="groups.length">
      <div class="merge-group" v-for="g in groups" :key="g.id">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <h4>相似对 #{{ g.id }}</h4>
          <el-tag :type="g.similarity_score>0.9?'danger':g.similarity_score>0.7?'warning':'info'" size="small">
            相似度 {{ (g.similarity_score*100).toFixed(1) }}%
          </el-tag>
        </div>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <div class="merge-version">
            <el-tag type="primary" size="small">A</el-tag>
            <a style="color:#409eff;cursor:pointer;text-decoration:none" @click="showCompare(g.doc_id_a, g.doc_id_b)">{{ g.doc_a_name || '文档'+g.doc_id_a }}</a>
          </div>
          <div class="merge-version">
            <el-tag type="success" size="small">B</el-tag>
            <a style="color:#409eff;cursor:pointer;text-decoration:none" @click="showCompare(g.doc_id_a, g.doc_id_b)">{{ g.doc_b_name || '文档'+g.doc_id_b }}</a>
          </div>
          <el-button type="primary" size="small" :icon="Edit" @click="doMerge(g.id)">合并</el-button>
          <el-button size="small" :icon="View" @click="showCompare(g.doc_id_a, g.doc_id_b)">对比</el-button>
        </div>
      </div>
    </div>
    <el-empty v-if="!groups.length && !loading" description="暂未发现重复文档" />

    <el-dialog v-model="compareVisible" title="文档对比" width="90%" top="3vh" :close-on-click-modal="false">
      <div v-loading="compareLoading" style="display:flex;gap:16px;min-height:400px">
        <div style="flex:1;overflow:auto;max-height:70vh">
          <h4 style="margin:0 0 8px">{{ compareA.file_name }}</h4>
          <pre style="white-space:pre-wrap;font-size:13px;line-height:1.6;background:#f9f9f9;padding:10px;border-radius:4px">{{ compareA.content }}</pre>
        </div>
        <div style="flex:1;overflow:auto;max-height:70vh">
          <h4 style="margin:0 0 8px">{{ compareB.file_name }}</h4>
          <pre style="white-space:pre-wrap;font-size:13px;line-height:1.6;background:#f9f9f9;padding:10px;border-radius:4px">{{ compareB.content }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh, Search, Edit, View } from '@element-plus/icons-vue'
import api from '../api.js'

const groups = ref([]); const loading = ref(false); const detecting = ref(false)
const lastMsg = ref(null)
const compareVisible = ref(false); const compareLoading = ref(false)
const compareA = ref({ file_name: '', content: '' })
const compareB = ref({ file_name: '', content: '' })

async function loadGroups() {
  loading.value = true
  try { const r = await api.get('/documents/relations?type=similar&limit=50'); groups.value = r.data.items || r.data || [] }
  catch(e) { groups.value = [] }
  loading.value = false
}
onMounted(loadGroups)

async function doMerge(id) {
  try { await api.post('/documents/merge/'+id); ElementPlus.ElMessage.success('合并成功'); loadGroups() }
  catch(e) { ElementPlus.ElMessage.error('合并失败: ' + (e.response?.data?.detail || e.message)) }
}

async function detectDuplicates() {
  detecting.value = true; lastMsg.value = { type: 'info', text: '检测中...' }
  try {
    const r = await api.post('/documents/detect-duplicates?threshold=0.70&ngram_threshold=0.15&limit=200')
    lastMsg.value = { type: 'success', text: `向量扫描 ${r.data.found} 对, 文本指纹验证后新增 ${r.data.inserted} 对` }
    loadGroups()
  } catch(e) { lastMsg.value = { type: 'danger', text: '检测失败: ' + (e.response?.data?.detail || e.message) } }
  detecting.value = false
}

async function showCompare(idA, idB) {
  compareVisible.value = true; compareLoading.value = true
  try {
    const r = await api.get('/documents/compare/'+idA+'/'+idB)
    compareA.value = r.data.doc_a
    compareB.value = r.data.doc_b
  } catch(e) {
    ElementPlus.ElMessage.error('加载对比内容失败')
    compareA.value = { file_name: '错误', content: '加载失败: ' + (e.response?.data?.detail || e.message) }
    compareB.value = { file_name: '错误', content: '' }
  }
  compareLoading.value = false
}
</script>

<style scoped>
.merge-group { border: 1px solid #e8e8e8; border-radius: 6px; padding: 14px; margin-bottom: 12px; }
.merge-version { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.merge-version a:hover { text-decoration: underline !important; }
</style>
