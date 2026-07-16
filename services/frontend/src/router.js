import { createRouter, createWebHashHistory } from 'vue-router'

import Dashboard from './views/Dashboard.vue'
import SearchView from './views/SearchView.vue'
import DocumentDetail from './views/DocumentDetail.vue'
import MergeCenter from './views/MergeCenter.vue'
import BatchOrganize from './views/BatchOrganize.vue'
import CategoryBrowse from './views/CategoryBrowse.vue'
import FileBrowser from './views/FileBrowser.vue'
import Login from './views/Login.vue'
import AdminUsers from './views/AdminUsers.vue'
import KnowledgeGraph from './views/KnowledgeGraph.vue'
import SeriesManagement from './views/SeriesManagement.vue'
import HealthCheck from './views/HealthCheck.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/search', component: SearchView },
  { path: '/doc/:id', component: DocumentDetail },
  { path: '/merge', component: MergeCenter },
  { path: '/organize', component: BatchOrganize },
  { path: '/browse', component: CategoryBrowse },
  { path: '/files', component: FileBrowser },
  { path: '/login', component: Login },
  { path: '/admin', component: AdminUsers },
  { path: '/graph', component: KnowledgeGraph },
  { path: '/series', component: SeriesManagement },
  { path: '/health', component: HealthCheck },
]

export default createRouter({ history: createWebHashHistory(), routes })
