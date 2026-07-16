<template>
  <div class="app-layout">
    <NavSidebar />
    <div class="main-area">
      <div class="topbar">
        <h3>{{ pageTitle }}</h3>
        <div><el-tag size="small" type="info">{{ statsText }}</el-tag></div>
      </div>
      <div class="page-content"><router-view /></div>
    </div>
    <ReaderModal v-model="reader.visible.value" :doc-id="reader.docId.value"
      :prev-id="reader.prevId.value" :next-id="reader.nextId.value"
      @prev="reader.goPrev()" @next="reader.goNext()" @update:model-value="reader.close()" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import api from './api.js'
import NavSidebar from './components/NavSidebar.vue'
import ReaderModal from './components/ReaderModal.vue'
import { useReader } from './stores/reader.js'

const route = useRoute()
const stats = ref(null)
const reader = useReader()
provide('reader', reader)

onMounted(async () => {
  try { const r = await api.get('/stats'); stats.value = r.data } catch(e) {}
})
const pageTitle = computed(() => {
  const map = {
    '/': '仪表盘', '/search': '搜索文档', '/browse': '分类浏览',
    '/merge': '相似合并', '/organize': '批量整理', '/files': '文件管理',
    '/login': '登录',     '/admin': '用户管理', '/graph': '知识图谱', '/series': '系列管理',
  }
  for (const [k,v] of Object.entries(map)) { if (route.path === k) return v }
  if (route.path.startsWith('/doc/')) return '文档详情'
  return '文档知识库'
})
const statsText = computed(() => stats.value ? `共 ${stats.value.total} 文档` : '')
</script>
