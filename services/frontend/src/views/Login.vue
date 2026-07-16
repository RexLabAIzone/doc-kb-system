<template>
  <div class="login-container">
    <el-card style="width:380px">
      <template #header><h2 style="text-align:center">文档知识库登录</h2></template>
      <el-form :model="form" label-width="0">
        <el-form-item><el-input v-model="form.username" placeholder="用户名" size="large" /></el-form-item>
        <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" size="large" show-password /></el-form-item>
        <el-form-item><el-button type="primary" size="large" style="width:100%" :loading="loading" @click="doLogin">登录</el-button></el-form-item>
      </el-form>
      <div v-if="errMsg" style="color:#f56c6c;font-size:13px;text-align:center">{{ errMsg }}</div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errMsg = ref('')

async function doLogin() {
  if (!form.username || !form.password) { errMsg.value = '请输入用户名和密码'; return }
  loading.value = true; errMsg.value = ''
  try {
    const r = await api.post('/auth/login', null, { params: { username: form.username, password: form.password } })
    localStorage.setItem('auth_token', r.data.access_token)
    localStorage.setItem('auth_user', r.data.username)
    localStorage.setItem('auth_role', r.data.role || 'user')
    ElementPlus.ElMessage.success('登录成功')
    router.push('/')
  } catch(e) {
    errMsg.value = '登录失败: ' + (e.response?.data?.detail || '用户名或密码错误')
  }
  loading.value = false
}
</script>

<style scoped>
.login-container { display: flex; justify-content: center; align-items: center; height: 80vh; }
</style>
