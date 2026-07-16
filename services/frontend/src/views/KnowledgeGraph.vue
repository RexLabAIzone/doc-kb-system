<template>
  <div class="kg-container">
    <div class="kg-toolbar">
      <el-button size="small" :loading="loading" @click="loadGraph">刷新</el-button>
      <el-button size="small" type="primary" :loading="extracting" @click="triggerExtract">提取实体</el-button>
      <el-button size="small" type="success" :loading="simBusy" @click="triggerSimilarity">构建相似关系</el-button>
      <el-select v-model="filterType" placeholder="实体类型" size="small" clearable @change="loadGraph" style="width:140px">
        <el-option label="全部" value="" />
        <el-option label="文档" value="document" />
        <el-option label="作者" value="author" />
        <el-option label="分类" value="category" />
        <el-option label="人物" value="person" />
        <el-option label="地点" value="place" />
        <el-option label="概念" value="concept" />
        <el-option label="系列" value="series" />
      </el-select>
      <span v-if="nodeCount" style="font-size:12px;color:#909399;margin-left:8px">{{ nodeCount }} 节点 / {{ linkCount }} 边</span>
    </div>
    <div ref="svgRef" class="kg-canvas" />
    <div v-if="selectedNode" class="kg-detail">
      <div style="font-weight:600">{{ selectedNode.name }}</div>
      <div style="font-size:12px;color:#909399">类型: {{ typeLabel(selectedNode.type) }}</div>
      <div v-if="selectedNode.doc_id" style="margin-top:6px">
        <el-button size="small" @click="router.push('/doc/'+selectedNode.doc_id)">查看文档</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as d3 from 'd3'
import api from '../api.js'

const router = useRouter()
const svgRef = ref(null)
const loading = ref(false)
const extracting = ref(false)
const simBusy = ref(false)
const filterType = ref('')
const nodeCount = ref(0)
const linkCount = ref(0)
const selectedNode = ref(null)
let simulation = null
let svg = null

const typeLabel = (t) => ({ document:'文档', author:'作者', category:'分类', person:'人物', place:'地点', concept:'概念', series:'系列' }[t] || t)

async function loadGraph() {
  loading.value = true
  try {
    const params = { limit: 800 }
    if (filterType.value) params.types = filterType.value
    const r = await api.get('/knowledge-graph', { params })
    const data = r.data
    nodeCount.value = data.nodes.length
    linkCount.value = data.links.length
    await nextTick()
    renderGraph(data)
  } catch(e) { console.error(e) }
  loading.value = false
}

async function triggerExtract() {
  extracting.value = true
  try { await api.post('/knowledge-graph/extract?limit=300') } catch(e) { console.error(e) }
  extracting.value = false
}

async function triggerSimilarity() {
  simBusy.value = true
  try { await api.post('/knowledge-graph/similarity') } catch(e) { console.error(e) }
  simBusy.value = false
}

function renderGraph(data) {
  const container = svgRef.value
  if (!container) return
  container.innerHTML = ''
  const w = container.clientWidth || 900
  const h = container.clientHeight || 600

  svg = d3.select(container).append('svg').attr('width', w).attr('height', h)
  const g = svg.append('g')

  const zoom = d3.zoom().scaleExtent([0.1, 4]).on('zoom', (e) => g.attr('transform', e.transform))
  svg.call(zoom)

  const colorMap = { document:'#409eff', author:'#67c23a', category:'#e6a23c', person:'#f56c6c', place:'#909399', concept:'#b37feb', series:'#ff85c0' }

  const links = data.links.map(l => ({ source: l.source, target: l.target, type: l.type, weight: l.weight }))
  const nodes = data.nodes.map(n => ({ ...n, id: n.id }))

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => 200 / (d.weight || 0.5)))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collision', d3.forceCollide().radius(20))

  const link = g.append('g').selectAll('line').data(links).join('line')
    .attr('stroke', '#999').attr('stroke-opacity', 0.4).attr('stroke-width', d => Math.min(d.weight || 0.5, 3))

  const node = g.append('g').selectAll('g').data(nodes).join('g').style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
    )

  node.append('circle').attr('r', d => d.type === 'document' ? 4 : 6)
    .attr('fill', d => colorMap[d.type] || '#aaa')
    .attr('stroke', '#fff').attr('stroke-width', 1.5)

  node.append('text').text(d => d.name.length > 12 ? d.name.slice(0, 12) + '…' : d.name)
    .attr('x', 8).attr('y', 4).attr('font-size', 11).attr('fill', '#333')

  node.on('click', (e, d) => {
    selectedNode.value = d
    if (d.doc_id) router.push('/doc/' + d.doc_id)
  })

  node.on('mouseenter', (e, d) => {
    link.attr('stroke-opacity', l => (l.source.id === d.id || l.target.id === d.id) ? 0.8 : 0.1)
    node.attr('opacity', n => n.id === d.id ? 1 : 0.3)
  }).on('mouseleave', () => {
    link.attr('stroke-opacity', 0.4)
    node.attr('opacity', 1)
  })

  simulation.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
    node.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')')
  })
}

onMounted(() => { loadGraph() })
onBeforeUnmount(() => { if (simulation) simulation.stop() })
</script>

<style scoped>
.kg-container { display: flex; flex-direction: column; height: 100%; }
.kg-toolbar { display: flex; gap: 8px; align-items: center; padding: 8px 0; flex-wrap: wrap; }
.kg-canvas { flex: 1; border: 1px solid #eee; border-radius: 6px; background: #fafafa; min-height: 500px; }
.kg-detail { position: fixed; bottom: 24px; right: 24px; background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 2px 12px rgba(0,0,0,.12); min-width: 180px; z-index: 100; }
</style>
