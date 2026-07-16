<template>
  <div class="file-tree">
    <div v-for="entry in entries" :key="entry.path" class="tree-item" :style="{ paddingLeft: (depth*20)+'px' }">
      <div class="tree-row" @click="toggle(entry)" :class="{ selected: selected?.path === entry.path }">
        <el-icon v-if="entry.is_dir" :class="{ 'is-open': openSet.has(entry.path) }"><FolderOpened v-if="openSet.has(entry.path)" /><Folder v-else /></el-icon>
        <el-icon v-else><Document /></el-icon>
        <span class="tree-name">{{ entry.name }}</span>
        <span v-if="!entry.is_dir" class="tree-size">{{ (entry.size/1024).toFixed(1) }}KB</span>
      </div>
      <div v-if="entry.is_dir && openSet.has(entry.path) && children[entry.path]">
        <FileTree :entries="children[entry.path]" :depth="depth+1" :selected="selected" @select="e=>$emit('select',e)" @load="e=>$emit('load',e)" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import api from '../api.js'
defineProps({ entries: Array, depth: { type: Number, default: 0 }, selected: Object })
defineEmits(['select', 'load'])
const openSet = ref(new Set())
const children = reactive({})
async function toggle(entry) {
  if (!entry.is_dir) { return }
  if (openSet.value.has(entry.path)) {
    openSet.value.delete(entry.path)
    openSet.value = new Set(openSet.value)
    return
  }
  try {
    const r = await api.get('/files/list', { params: { path: entry.path, dir_key: 'originals' } })
    children[entry.path] = r.data.entries || []
    openSet.value.add(entry.path)
    openSet.value = new Set(openSet.value)
  } catch(e) {}
}
</script>

<style scoped>
.file-tree { font-size: 13px; user-select: none; }
.tree-row { display: flex; align-items: center; gap: 6px; padding: 4px 6px; cursor: pointer; border-radius: 4px; }
.tree-row:hover { background: #f0f2f5; }
.tree-row.selected { background: #e6f4ff; color: #1890ff; }
.tree-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-size { color: #909399; font-size: 11px; }
.is-open { color: #e6a23c; }
</style>
