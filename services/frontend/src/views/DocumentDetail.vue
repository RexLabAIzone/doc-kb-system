<template>
  <div v-loading="loading">
    <el-button @click="router.push('/search')" style="margin-bottom:14px;font-size:13px"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
    <div style="float:right;display:flex;gap:6px;margin-bottom:14px">
      <el-button size="small" type="primary" @click="reader?.open(doc?.id)"><el-icon><Reading /></el-icon> 在线阅读</el-button>
      <el-button size="small" @click="enrichDoc"><el-icon><MagicStick /></el-icon> AI 识别元数据</el-button>
      <el-button size="small" :loading="caching" @click="cacheToNfs"><el-icon><Upload /></el-icon> 缓存到 NAS</el-button>
    </div>
    <template v-if="doc">
      <el-card style="margin-bottom:14px">
        <template #header><div style="font-weight:600;font-size:15px">{{ doc.file_name }}</div></template>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px;color:#666">
          <div>路径: {{ doc.file_path }}</div><div>格式: {{ doc.file_ext }}</div>
          <div>大小: {{ (doc.file_size/1024/1024).toFixed(2) }} MB</div><div>字数: {{ doc.char_count?.toLocaleString() }}</div>
          <div>创建: {{ doc.created_at }}</div>
          <div v-if="kp?.author">作者: {{ kp.author }}</div>
          <div v-if="kp?.genre">体裁: {{ kp.genre }}</div>
          <div v-if="kp?.publish_year && kp.publish_year!='0'">年份: {{ kp.publish_year }}</div>
        </div>
        <div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap">
          <el-tag v-if="doc.category" size="small" type="primary">{{ doc.category }}</el-tag>
          <el-tag v-for="t in (doc.tags||[])" :key="t" size="small">{{ t }}</el-tag>
        </div>
      </el-card>
      <el-card v-if="doc.summary" style="margin-bottom:14px">
        <template #header>AI 摘要</template>
        <div style="font-size:14px;line-height:1.8">{{ doc.summary }}</div>
      </el-card>
      <el-card v-if="similarDocs.length" style="margin-bottom:14px">
        <template #header>相似文档推荐</template>
        <div v-for="s in similarDocs" :key="s.id" style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f5f5f5;font-size:13px">
          <router-link :to="'/doc/'+s.id" style="color:#409eff;text-decoration:none">{{ s.file_name }}</router-link>
          <el-tag :type="s.similarity>0.9?'danger':'warning'" size="small">{{ (s.similarity*100).toFixed(1) }}%</el-tag>
        </div>
      </el-card>
      <el-card v-if="recommendDocs.length" style="margin-bottom:14px">
        <template #header><el-icon style="vertical-align:-2px"><TrendCharts /></el-icon> 猜你喜欢</template>
        <div v-for="s in recommendDocs" :key="s.id" style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f5f5f5;font-size:13px">
          <router-link :to="'/doc/'+s.id" style="color:#409eff;text-decoration:none">{{ s.file_name }}</router-link>
          <el-tag size="small" type="success">{{ s.category || '未分类' }}</el-tag>
        </div>
      </el-card>
      <el-card><template #header>原文</template>
        <div class="full-content">{{ doc.content_text || '（内容已迁移至 NAS）' }}</div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api.js'

const route = useRoute(); const router = useRouter()
const reader = inject('reader')
const doc = ref(null); const loading = ref(true); const caching = ref(false)
const similarDocs = ref([])
const recommendDocs = ref([])

const kp = computed(() => doc.value?.key_points || {})

async function loadDoc() {
  loading.value = true
  try {
    const r = await api.get('/documents/'+route.params.id)
    doc.value = r.data
    loadSimilar()
    loadRecommend()
  }
  catch(e) { ElementPlus.ElMessage.error('文档不存在'); router.push('/search') }
  loading.value = false
}
onMounted(loadDoc)

async function loadSimilar() {
  try {
    const r = await api.get('/documents/'+route.params.id+'/similar')
    similarDocs.value = r.data || []
  } catch(e) { similarDocs.value = [] }
}

async function loadRecommend() {
  try {
    const r = await api.get('/recommendations/'+route.params.id)
    recommendDocs.value = r.data || []
  } catch(e) { recommendDocs.value = [] }
}

async function cacheToNfs() {
  caching.value = true
  try { await api.post('/documents/'+route.params.id+'/cache-to-nfs'); ElementPlus.ElMessage.success('已缓存到 NAS'); loadDoc() }
  catch(e) { ElementPlus.ElMessage.error('缓存失败: '+(e.response?.data?.detail||e.message)) }
  caching.value = false
}

async function enrichDoc() {
  try {
    const r = await api.post('/documents/'+route.params.id+'/enrich')
    ElementPlus.ElMessage.success('AI 元数据已更新: ' + r.data.category)
    loadDoc()
  } catch(e) { ElementPlus.ElMessage.error('AI 分析失败: '+(e.response?.data?.detail||e.message)) }
}
</script>
