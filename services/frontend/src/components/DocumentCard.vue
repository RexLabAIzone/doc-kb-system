<template>
  <el-card shadow="hover" class="doc-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div style="flex:1;min-width:0;cursor:pointer" @click="$emit('click')">
        <div class="doc-title" v-html="highlightText(doc.file_name)"></div>
        <div v-if="doc.summary" class="doc-summary" v-html="highlightText(doc.summary)"></div>
        <div v-if="doc.snippet" class="doc-snippet" v-html="highlightText(doc.snippet)"></div>
      </div>
      <el-button size="small" text type="primary" @click.stop="$emit('read')" title="在线阅读">
        <el-icon><Reading /></el-icon>
      </el-button>
    </div>
    <div class="doc-meta">
      <el-tag v-if="doc.category" size="small" type="success" style="cursor:pointer" @click.stop="router.push('/search?category='+doc.category)">{{ doc.category }}</el-tag>
      <el-tag v-for="t in (doc.tags||[]).slice(0,3)" :key="t" size="small">{{ t }}</el-tag>
      <el-tag size="small" type="info">{{ (doc.char_count/10000).toFixed(1) }}万字</el-tag>
    </div>
  </el-card>
</template>

<script setup>
import { useRouter } from 'vue-router'
const props = defineProps({ doc: { type: Object, required: true }, highlight: { type: String, default: '' } })
defineEmits(['click', 'read'])
const router = useRouter()

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightText(text) {
  if (!text || !props.highlight) return text
  const escaped = escapeRegex(props.highlight)
  const re = new RegExp('(' + escaped + ')', 'gi')
  return text.replace(re, '<mark style="background:#ffd54f;padding:0 2px;border-radius:2px">$1</mark>')
}
</script>

<style scoped>
.doc-card { margin-bottom: 10px; cursor: pointer; transition: box-shadow .2s; }
.doc-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.1); }
.doc-title { font-weight: 600; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.doc-summary { font-size: 13px; color: #666; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.doc-snippet { font-size: 12px; color: #999; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
</style>
