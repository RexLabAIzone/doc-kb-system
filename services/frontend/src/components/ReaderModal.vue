<template>
  <el-drawer v-model="visible" :title="doc?.file_name || '在线阅读'" size="90%" direction="rtl" destroy-on-close>
    <template v-if="loading">
      <div style="text-align:center;padding:80px"><el-icon class="is-loading" :size="32"><Loading /></el-icon><p style="margin-top:12px;color:#909399">加载中...</p></div>
    </template>
    <template v-else-if="doc">
      <div class="reader-layout">
        <div class="reader-main">
          <div class="reader-toolbar">
            <el-space>
              <el-button size="small" @click="prevDoc" :disabled="!prevId"><el-icon><ArrowLeft /></el-icon> 上一篇</el-button>
              <el-button size="small" @click="nextDoc" :disabled="!nextId">下一篇 <el-icon><ArrowRight /></el-icon></el-button>
              <el-button size="small" @click="fontSize+=2"><el-icon><ZoomIn /></el-icon></el-button>
              <el-button size="small" @click="fontSize=Math.max(12,fontSize-2)"><el-icon><ZoomOut /></el-icon></el-button>
              <el-button size="small" @click="showSidebar=!showSidebar"><el-icon><Operation /></el-icon></el-button>
              <el-button v-if="doc.truncated && !fullLoaded" size="small" :loading="loadingMore" @click="loadMore">加载更多</el-button>
            </el-space>
            <span style="font-size:12px;color:#909399">
              {{ displayContent.length.toLocaleString() }} 字
              <span v-if="doc.truncated && !fullLoaded"> / {{ doc.total_chars?.toLocaleString() }}</span>
            </span>
          </div>
          <div class="reader-content" :style="{ fontSize: fontSize+'px', lineHeight: lineHeight }">
            {{ displayContent }}
          </div>
        </div>
        <Transition name="slide">
          <div v-if="showSidebar" class="reader-sidebar">
            <el-card shadow="never">
              <template #header><span style="font-weight:600;font-size:14px">文档信息</span></template>
              <div class="meta-field" v-if="doc.category"><label>分类</label><el-tag size="small" type="success">{{ doc.category }}</el-tag></div>
              <div class="meta-field" v-if="kp?.real_title"><label>书名</label><span>{{ kp.real_title }}</span></div>
              <div class="meta-field" v-if="kp?.author"><label>作者</label><span>{{ kp.author }}</span></div>
              <div class="meta-field" v-if="kp?.publish_year && kp.publish_year!='0'"><label>年份</label><span>{{ kp.publish_year }}</span></div>
              <div class="meta-field" v-if="kp?.genre"><label>体裁</label><el-tag size="small">{{ kp.genre }}</el-tag></div>
              <div class="meta-field"><label>格式</label><span>{{ doc.file_ext }}</span></div>
              <div class="meta-field"><label>路径</label><span style="font-size:11px;word-break:break-all">{{ doc.file_path }}</span></div>
              <div class="meta-field" v-if="doc.tags?.length"><label>标签</label>
                <el-space wrap><el-tag v-for="t in doc.tags" :key="t" size="small">{{ t }}</el-tag></el-space>
              </div>
              <div v-if="doc.summary" style="margin-top:12px">
                <div style="font-weight:600;font-size:13px;margin-bottom:4px">摘要</div>
                <p style="font-size:13px;color:#666;line-height:1.7">{{ doc.summary }}</p>
              </div>
            </el-card>
          </div>
        </Transition>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'
import api from '../api.js'

const props = defineProps({ modelValue: Boolean, docId: [Number, String], prevId: [Number, String], nextId: [Number, String] })
const emit = defineEmits(['update:modelValue', 'prev', 'next'])

const visible = ref(false)
const doc = ref(null)
const loading = ref(false)
const loadingMore = ref(false)
const fullLoaded = ref(false)
const fontSize = ref(16)
const lineHeight = ref('1.9')
const showSidebar = ref(true)

watch(() => props.modelValue, async (v) => {
  visible.value = v
  if (v && props.docId) await loadDoc()
})
watch(() => props.docId, async (id) => {
  if (id && visible.value) await loadDoc()
})

const kp = computed(() => doc.value?.key_points || {})
const displayContent = computed(() => {
  if (doc.value?.content_text) return doc.value.content_text
  if (doc.value?._fallback_content) return doc.value._fallback_content
  return '(暂无内容)'
})

async function loadDoc() {
  loading.value = true; fullLoaded.value = false
  try {
    const r = await api.get('/documents/' + props.docId, { params: { max_size: 200000 } })
    doc.value = r.data
    if (!r.data.content_text && r.data.file_path) {
      fallbackReadFile(r.data.file_path)
    }
  } catch(e) {
    doc.value = null
  }
  loading.value = false
}

async function fallbackReadFile(fp) {
  try {
    const fr = await api.get('/files/read', { params: { path: fp, dir_key: 'originals', max_size: 5000000 } })
    if (fr.data.content) {
      doc.value._fallback_content = fr.data.content
      doc.value.char_count = fr.data.content.length
      doc.value.truncated = false
    }
  } catch(e2) {}
}

async function loadMore() {
  loadingMore.value = true
  try {
    const skip = doc.value.content_text.length
    const r = await api.get('/documents/' + props.docId, { params: { max_size: skip + 200000 } })
    if (r.data.content_text && r.data.content_text.length > skip) {
      doc.value.content_text = r.data.content_text
    }
    if (!r.data.truncated) fullLoaded.value = true
  } catch(e) {}
  loadingMore.value = false
}

function prevDoc() { emit('prev') }
function nextDoc() { emit('next') }
</script>

<style scoped>
.reader-layout { display: flex; height: calc(100vh - 60px); gap: 0; }
.reader-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.reader-toolbar { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; border-bottom: 1px solid #e8e8e8; background: #fff; flex-shrink: 0; }
.reader-content { flex: 1; overflow-y: auto; padding: 24px 48px; background: #fafafa; white-space: pre-wrap; word-break: break-word; }
.reader-sidebar { width: 300px; overflow-y: auto; border-left: 1px solid #e8e8e8; padding: 12px; background: #fff; }
.meta-field { display: flex; gap: 6px; align-items: center; padding: 4px 0; font-size: 13px; flex-wrap: wrap; }
.meta-field label { color: #909399; min-width: 40px; flex-shrink: 0; }
.slide-enter-active, .slide-leave-active { transition: width .3s ease, opacity .3s ease; }
.slide-enter-from, .slide-leave-to { width: 0 !important; opacity: 0; padding: 0 !important; overflow: hidden; }
</style>
