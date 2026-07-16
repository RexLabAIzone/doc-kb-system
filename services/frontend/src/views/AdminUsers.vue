<template>
  <div>
    <div style="margin-bottom:14px;display:flex;gap:8px">
      <el-input v-model="newUser.username" placeholder="用户名" style="width:160px" size="small" />
      <el-input v-model="newUser.password" type="password" placeholder="密码" style="width:160px" size="small" show-password />
      <el-select v-model="newUser.role" style="width:100px" size="small">
        <el-option label="管理员" value="admin" /><el-option label="用户" value="user" />
      </el-select>
      <el-button size="small" type="primary" :loading="creating" @click="addUser">创建用户</el-button>
    </div>
    <el-table :data="users" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="role" label="角色" width="80">
        <template #default="{row}"><el-tag :type="row.role==='admin'?'danger':'info'" size="small">{{ row.role }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="enabled" label="状态" width="70">
        <template #default="{row}"><el-tag :type="row.enabled?'success':'danger'" size="small">{{ row.enabled?'启用':'禁用' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const users = ref([]); const loading = ref(false); const creating = ref(false)
const newUser = ref({ username: '', password: '', role: 'user' })

async function loadUsers() {
  loading.value = true
  try { const r = await api.get('/auth/users'); users.value = r.data || [] }
  catch(e) { users.value = [] }
  loading.value = false
}
onMounted(loadUsers)

async function addUser() {
  if (!newUser.value.username || !newUser.value.password) return
  creating.value = true
  try {
    await api.post('/auth/register', null, { params: newUser.value })
    ElementPlus.ElMessage.success('创建成功')
    newUser.value = { username: '', password: '', role: 'user' }
    loadUsers()
  } catch(e) { ElementPlus.ElMessage.error('创建失败: '+(e.response?.data?.detail||e.message)) }
  creating.value = false
}
</script>
