<template>
  <div v-loading="loading">
    <el-card style="margin-bottom:14px">
      <template #header>整理规则</template>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
        <span style="font-size:13px;font-weight:600">选择规则:</span>
        <el-select v-model="selectedRuleId" style="width:240px" @change="onRuleChange">
          <el-option v-for="r in rules" :key="r.id" :label="(r.is_default?'⭐ ':'') + r.name" :value="r.id" />
        </el-select>
        <el-button size="small" @click="showAddRule = true" :icon="Plus">自定义</el-button>
        <el-popconfirm v-if="selectedRule && !selectedRule.is_default" title="删除此规则?" @confirm="deleteRule">
          <template #reference>
            <el-button size="small" type="danger" link :icon="Delete">删除</el-button>
          </template>
        </el-popconfirm>
      </div>
      <div style="margin-bottom:10px">
        <span style="font-size:12px;color:#909399">规则模式:</span>
        <el-tag size="small" style="margin-left:6px;font-family:monospace">{{ currentPattern }}</el-tag>
        <span style="margin-left:10px;font-size:12px;color:#909399">可用变量: {category} {year} {author} {genre} {file_name} {file_ext} {id}</span>
      </div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <span style="font-size:13px">归档目录:</span>
        <el-input v-model="targetDir" style="width:260px" size="small" />
        <el-button size="small" @click="preview" :loading="previewing">预览</el-button>
        <el-button type="primary" size="small" :loading="organizing" @click="doOrganize">执行整理</el-button>
        <el-checkbox v-model="deleteOriginals" label="删除源文件" />
        <el-checkbox v-model="suggestMode" label="显示分类建议" />
      </div>
    </el-card>

    <el-card v-if="suggestMode && suggestResult" style="margin-bottom:14px">
      <template #header>分类建议</template>
      <div style="display:flex;gap:12px;align-items:center">
        <span style="font-size:13px">建议: <el-tag type="warning">{{ suggestResult.category }}</el-tag>
          <el-tag type="success" style="margin-left:6px">{{ suggestResult.genre }}</el-tag></span>
        <span style="font-size:12px;color:#909399">当前: {{ suggestResult.current_category }} / {{ suggestResult.current_author }}</span>
        <el-button size="small" @click="loadSuggest" :loading="suggestLoading">刷新建议</el-button>
      </div>
    </el-card>

    <el-card>
      <template #header>
        预览
        <span style="float:right;font-size:12px;color:#909399">
          <el-button size="small" link @click="selectAll">全选</el-button>
          <el-button size="small" link @click="deselectAll">取消全选</el-button>
          {{ filteredDocs.length }} 条
        </span>
      </template>
      <div v-if="filteredDocs.length">
        <div v-for="d in filteredDocs" :key="d.id" style="display:flex;align-items:center;padding:5px 0;border-bottom:1px solid #f5f5f5;font-size:13px">
          <el-checkbox v-model="d._selected" size="small" style="margin-right:8px" />
          <span style="flex:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:#409eff" @click="showPreview(d)">{{ d.file_name }}</span>
          <span style="width:80px;font-size:12px;color:#909399">{{ d.category || '-' }}</span>
          <el-icon style="margin:0 8px;color:#909399"><ArrowRight /></el-icon>
          <span style="flex:2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#409eff">{{ getPreviewPath(d) }}</span>
        </div>
        <div v-if="docs.length > 50" style="text-align:center;margin-top:10px">
          <el-button size="small" link @click="showAll = !showAll">{{ showAll ? '收起' : '显示全部 ' + docs.length + ' 条' }}</el-button>
        </div>
      </div>
      <el-empty v-else description="暂无文档，请先搜索或选择" :image-size="50"/>
    </el-card>

    <el-dialog v-model="previewVisible" title="文档预览" width="700px" top="3vh">
      <template v-if="previewDoc">
        <div style="font-size:14px;font-weight:600;margin-bottom:8px">{{ previewDoc.file_name }}</div>
        <div style="font-size:12px;color:#909399;margin-bottom:10px">
          <span v-if="previewDoc.category">分类: {{ previewDoc.category }}</span>
          <span v-if="previewDoc.author" style="margin-left:12px">作者: {{ previewDoc.author }}</span>
          <span v-if="previewDoc.year" style="margin-left:12px">年份: {{ previewDoc.year }}</span>
        </div>
        <el-input
          type="textarea"
          :rows="18"
          :model-value="previewDoc.content_text || '（无内容）'"
          readonly
          style="font-size:13px;font-family:monospace"
        />
      </template>
      <div v-else v-loading="previewLoading" style="height:200px" />
    </el-dialog>

    <el-dialog v-model="showAddRule" title="自定义规则" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="newRule.name" placeholder="例如：按作者/书名" /></el-form-item>
        <el-form-item label="规则模式">
          <el-input v-model="newRule.pattern" placeholder="{author}/{file_name}" />
          <div style="font-size:12px;color:#909399;margin-top:4px">
            可用: {category} {year} {author} {genre} {file_name} {file_ext} {id}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddRule=false">取消</el-button>
        <el-button type="primary" @click="doAddRule" :loading="addingRule">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus, Delete, ArrowRight, View, Document } from '@element-plus/icons-vue'
import api from '../api.js'

const docs = ref([]); const loading = ref(false); const organizing = ref(false); const previewing = ref(false)
const targetDir = ref('/data/output/organized'); const deleteOriginals = ref(false)
const rules = ref([]); const selectedRuleId = ref(null); const selectedRule = ref(null)
const currentPattern = ref('{category}/{year}/{file_name}')
const showAll = ref(false); const suggestMode = ref(false); const suggestResult = ref(null)
const suggestLoading = ref(false); const showAddRule = ref(false); const addingRule = ref(false)
const newRule = ref({ name: '', pattern: '' })
const previewDoc = ref(null); const previewLoading = ref(false); const previewVisible = ref(false)

onMounted(async () => {
  await loadRules()
  if (rules.value.length) { selectedRuleId.value = rules.value[0].id; onRuleChange() }
  loadDocs()
})

const filteredDocs = computed(() => showAll.value ? docs.value : docs.value.slice(0, 50))

async function loadRules() {
  try { const r = await api.get('/organize/rules'); rules.value = r.data || [] } catch(e) { rules.value = [] }
}
function onRuleChange() {
  selectedRule.value = rules.value.find(r => r.id === selectedRuleId.value)
  currentPattern.value = selectedRule.value ? selectedRule.value.pattern : '{category}/{year}/{file_name}'
}
async function loadDocs() {
  loading.value = true
  try { const r = await api.get('/documents?limit=200'); docs.value = (r.data.items || r.data || []).map(d => ({ ...d, _selected: true })) }
  catch(e) { docs.value = [] }
  loading.value = false
}
async function preview() {
  previewing.value = true
  const ids = docs.value.filter(d => d._selected).map(d => d.id)
  try {
    const r = await api.post('/documents/organize', {
      ids, dry_run: true, rule_id: selectedRuleId.value,
      custom_pattern: selectedRuleId.value ? null : currentPattern.value,
      target_dir: targetDir.value,
    })
    docs.value = (r.data.plan || []).map(p => ({ ...p, _selected: true }))
  } catch(e) { ElMessage.error('预览失败: ' + (e.response?.data?.detail || e.message)) }
  previewing.value = false
}
async function doOrganize() {
  organizing.value = true
  const ids = docs.value.filter(d => d._selected).map(d => d.id)
  try {
    const r = await api.post('/documents/organize', {
      ids, delete_originals: deleteOriginals.value, rule_id: selectedRuleId.value,
      target_dir: targetDir.value,
    })
    ElMessage.success(`整理完成：已复制 ${r.data.copied} 个文件` + (r.data.deleted ? `，已删除 ${r.data.deleted} 个源文件` : ''))
    loadDocs()
  } catch(e) { ElMessage.error('整理失败: ' + (e.response?.data?.detail || e.message)) }
  organizing.value = false
}
function getPreviewPath(d) {
  return d.target_path || currentPattern.value
    .replace('{category}', d.category || '未分类')
    .replace('{year}', String(d.year || 'unknown'))
    .replace('{author}', d.author || '佚名')
    .replace('{genre}', d.genre || '未分类')
    .replace('{file_name}', d.file_name)
}
function selectAll() { docs.value.forEach(d => { d._selected = true }) }
function deselectAll() { docs.value.forEach(d => { d._selected = false }) }
async function showPreview(d) {
  previewDoc.value = null; previewLoading.value = true; previewVisible.value = true
  try {
    const r = await api.get('/documents/' + d.id)
    previewDoc.value = r.data
  } catch(e) { ElementPlus.ElMessage.error('获取文档内容失败'); previewVisible.value = false }
  previewLoading.value = false
}
async function loadSuggest() {
  const first = docs.value.find(d => d._selected)
  if (!first) { ElMessage.warning('请先选择文档'); return }
  suggestLoading.value = true
  try { const r = await api.get('/organize/suggest/' + first.id); suggestResult.value = r.data } catch(e) { ElMessage.error('建议获取失败') }
  suggestLoading.value = false
}
async function deleteRule() {
  if (!selectedRule.value) return
  try { await api.delete('/organize/rules/' + selectedRule.value.id); ElMessage.success('已删除'); loadRules() }
  catch(e) { ElMessage.error('删除失败') }
}
async function doAddRule() {
  if (!newRule.value.name || !newRule.value.pattern) { ElMessage.warning('请填写完整'); return }
  addingRule.value = true
  try { await api.post('/organize/rules', newRule.value); ElMessage.success('已添加'); showAddRule.value = false; newRule.value = { name: '', pattern: '' }; loadRules() }
  catch(e) { ElMessage.error('添加失败') }
  addingRule.value = false
}
</script>
