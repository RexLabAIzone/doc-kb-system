<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="按分类" name="category">
        <div v-if="categories.length" style="display:flex;flex-wrap:wrap;gap:8px">
          <el-tag v-for="c in categories" :key="c.category" style="cursor:pointer;padding:4px 12px;font-size:14px"
            :type="selectedCategory===c.category?'primary':''" @click="selectedCategory=selectedCategory===c.category?'':c.category;loadByCategory()">
            {{ c.category }} <small>({{ c.count }})</small>
          </el-tag>
        </div>
        <el-empty v-else description="暂无分类数据" :image-size="50"/>
      </el-tab-pane>
      <el-tab-pane label="按作者" name="author">
        <div v-if="authors.length" style="display:flex;flex-wrap:wrap;gap:8px">
          <el-tag v-for="a in authors" :key="a.author" style="cursor:pointer;padding:4px 12px;font-size:14px"
            :type="selectedAuthor===a.author?'primary':''" @click="selectedAuthor=selectedAuthor===a.author?'':a.author;loadByAuthor()">
            {{ a.author }} <small>({{ a.count }})</small>
          </el-tag>
        </div>
        <el-empty v-else description="暂无作者数据" :image-size="50"/>
      </el-tab-pane>
      <el-tab-pane label="按体裁" name="genre">
        <div v-if="genres.length" style="display:flex;flex-wrap:wrap;gap:8px">
          <el-tag v-for="g in genres" :key="g.genre" style="cursor:pointer;padding:4px 12px;font-size:14px"
            :type="selectedGenre===g.genre?'primary':''" @click="selectedGenre=selectedGenre===g.genre?'':g.genre;loadByGenre()">
            {{ g.genre }} <small>({{ g.count }})</small>
          </el-tag>
        </div>
        <el-empty v-else description="暂无体裁数据" :image-size="50"/>
      </el-tab-pane>
      <el-tab-pane label="按年份" name="year">
        <div v-if="years.length" style="display:flex;flex-wrap:wrap;gap:8px">
          <el-tag v-for="y in years" :key="y.year" style="cursor:pointer;padding:4px 16px;font-size:14px"
            :type="selectedYear==y.year?'primary':''" @click="selectedYear=selectedYear==y.year?0:y.year;loadByYear()">
            {{ y.year }} <small>({{ y.count }})</small>
          </el-tag>
        </div>
        <el-empty v-else description="暂无年份数据" :image-size="50"/>
      </el-tab-pane>
    </el-tabs>
    <div v-if="browseDocs.length" style="margin-top:16px">
      <DocumentCard v-for="d in browseDocs" :key="d.id" :doc="d" @click="router.push('/doc/'+d.id)" @read="reader?.open(d.id)" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api.js'
import DocumentCard from '../components/DocumentCard.vue'

const route = useRoute(); const router = useRouter(); const reader = inject('reader')
const activeTab = ref(route.query.tab || 'category')
const categories = ref([]); const authors = ref([]); const years = ref([]); const genres = ref([])
const selectedCategory = ref(route.query.category || '')
const selectedAuthor = ref(''); const selectedYear = ref(0); const selectedGenre = ref('')
const browseDocs = ref([])

onMounted(async () => {
  try {
    const [ar, yr, gr, cr] = await Promise.all([
      api.get('/metadata/authors'), api.get('/metadata/years'),
      api.get('/metadata/genres'), api.get('/metadata/categories')
    ])
    authors.value = ar.data || []; years.value = yr.data || []
    genres.value = gr.data || []; categories.value = cr.data || []
  } catch(e) {}
  if (selectedCategory.value) loadByCategory()
})

async function loadByCategory() {
  if (!selectedCategory.value) { browseDocs.value = []; return }
  try { const r = await api.get('/documents/by-category/' + encodeURIComponent(selectedCategory.value)); browseDocs.value = r.data || [] }
  catch(e) { browseDocs.value = [] }
}
async function loadByAuthor() {
  if (!selectedAuthor.value) { browseDocs.value = []; return }
  try { const r = await api.get('/documents/by-metadata', { params: { author: selectedAuthor.value } }); browseDocs.value = r.data || [] }
  catch(e) { browseDocs.value = [] }
}
async function loadByYear() {
  if (!selectedYear.value) { browseDocs.value = []; return }
  try { const r = await api.get('/documents/by-metadata', { params: { year: selectedYear.value } }); browseDocs.value = r.data || [] }
  catch(e) { browseDocs.value = [] }
}
async function loadByGenre() {
  if (!selectedGenre.value) { browseDocs.value = []; return }
  try { const r = await api.get('/documents/by-metadata', { params: { genre: selectedGenre.value } }); browseDocs.value = r.data || [] }
  catch(e) { browseDocs.value = [] }
}
</script>
