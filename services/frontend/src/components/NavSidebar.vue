<template>
  <div class="sidebar">
    <div class="sidebar-header"><h2>文档知识库</h2><small>v2 · AI 驱动</small></div>
    <div class="sidebar-menu">
      <el-menu :default-active="route.path" router background-color="#001529" text-color="#fff" active-text-color="#1890ff">
        <el-menu-item index="/"><el-icon><DataAnalysis /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/search"><el-icon><Search /></el-icon><span>搜索文档</span></el-menu-item>
        <el-menu-item index="/browse"><el-icon><Collection /></el-icon><span>分类浏览</span></el-menu-item>
        <el-menu-item index="/merge"><el-icon><Connection /></el-icon><span>相似合并</span></el-menu-item>
        <el-menu-item index="/organize"><el-icon><FolderOpened /></el-icon><span>批量整理</span></el-menu-item>
        <el-menu-item index="/files"><el-icon><Folder /></el-icon><span>文件管理</span></el-menu-item>
        <el-menu-item index="/graph"><el-icon><Share /></el-icon><span>知识图谱</span></el-menu-item>
        <el-menu-item index="/series"><el-icon><List /></el-icon><span>系列管理</span></el-menu-item>
        <el-menu-item index="/health"><el-icon><Checked /></el-icon><span>健康检查</span></el-menu-item>
      </el-menu>
    </div>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style scoped>
.sidebar { width: 220px; background: #001529; color: #fff; display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-header { padding: 18px; border-bottom: 1px solid rgba(255,255,255,.1); }
.sidebar-header h2 { font-size: 16px; font-weight: 600; }
.sidebar-header small { font-size: 11px; opacity: .6; }
.sidebar-menu { flex: 1; overflow-y: auto; }
.sidebar-menu .el-menu { border-right: none; }
</style>
