<template>
  <div>
    <el-card shadow="never" style="margin-bottom:14px">
      <el-input v-model="query" placeholder="搜索文档名称或内容..." @keyup.enter="doSearch(1)" clearable>
        <template #prefix><el-icon><Search /></el-icon></template>
        <template #append>
          <el-select v-model="searchType" style="width:110px">
            <el-option label="全文搜索" value="fulltext" /><el-option label="语义搜索" value="semantic" />
          </el-select>
          <el-button type="primary" @click="doSearch(1)">搜索</el-button>
        </template>
      </el-input>
      <div class="search-filters" style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">
        <el-select v-model="filters.category" placeholder="分类" clearable @change="doSearch(1)">
          <el-option v-for="c in categories" :key="c.category" :label="c.category" :value="c.category" />
        </el-select>
        <el-select v-model="pageSize" placeholder="每页" style="width:100px" @change="doSearch(1)">
          <el-option label="20条/页" :value="20" />
          <el-option label="50条/页" :value="50" />
          <el-option label="100条/页" :value="100" />
        </el-select>
      </div>
    </el-card>
    <div v-if="total>0" style="margin-bottom:10px;font-size:13px;color:#909399">找到 {{ total }} 个结果</div>
    <div class="doc-list" v-loading="loading">
      <DocumentCard v-for="(d, i) in docs" :key="d.id" :doc="d" :highlight="query" @click="viewDoc(d.id)" @read="readDoc(d, i)" />
      <el-empty v-if="!docs.length && !loading" description="暂无结果" />
    </div>
    <div v-if="total>pageSize" style="text-align:center;margin-top:16px">
      <el-pagination background layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="filters.page" @current-change="doSearch" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api.js'
import DocumentCard from '../components/DocumentCard.vue'

const route = useRoute(); const router = useRouter()
const reader = inject('reader')
const query = ref(''); const searchType = ref('fulltext')
const docs = ref([]); const loading = ref(false); const total = ref(0)
const filters = reactive({ category: '', page: 1 }); const pageSize = ref(20)
const categories = ref([])

onMounted(async () => {
  if (route.query.q) { query.value = route.query.q }
  if (route.query.category) { filters.category = route.query.category }
  try { const r = await api.get('/categories'); categories.value = r.data || [] } catch(e) {}
  doSearch(1)
})

async function doSearch(page) {
  if (page) filters.page = page
  loading.value = true
  try {
    const params = { q: query.value, type: searchType.value, limit: pageSize.value, offset: (filters.page-1)*pageSize.value }
    if (filters.category) params.category = filters.category
    const r = await api.get('/documents', { params })
    docs.value = r.data.items || r.data || []
    total.value = r.data.total || docs.value.length
  } catch(e) { docs.value = []; total.value = 0 }
  loading.value = false
}
function readDoc(d, idx) {
  const list = docs.value
  const i = idx !== undefined ? idx : list.findIndex(x => x.id === d.id)
  const prev = i > 0 ? list[i-1].id : null
  const next = i < list.length-1 ? list[i+1].id : null
  reader?.open(d.id, prev, next)
}
function viewDoc(id) { router.push('/doc/'+id) }
</script>
