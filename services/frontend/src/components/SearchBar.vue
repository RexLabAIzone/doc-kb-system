<template>
  <div>
    <el-input v-model="query" :placeholder="placeholder" @keyup.enter="$emit('search', query)" clearable>
      <template #prefix><el-icon><Search /></el-icon></template>
      <template #append>
        <el-select v-model="searchType" style="width:110px">
          <el-option label="全文搜索" value="fulltext" />
          <el-option label="语义搜索" value="semantic" />
        </el-select>
        <el-button type="primary" @click="$emit('search', query)">搜索</el-button>
      </template>
    </el-input>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ placeholder: { type: String, default: '搜索文档...' } })
defineEmits(['search'])
const query = ref('')
const searchType = ref('fulltext')
</script>
