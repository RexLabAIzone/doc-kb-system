<template>
  <div class="diff-viewer">
    <div class="diff-header">
      <span class="diff-label">版本 A</span>
      <span class="diff-label">版本 B</span>
    </div>
    <div class="diff-body">
      <div class="diff-side" v-for="(text,idx) in [textA, textB]" :key="idx">
        <div v-for="(line,li) in text.split('\\n').slice(0,200)" :key="li"
          :class="['diff-line', lineClass(line, idx)]">{{ line }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ textA: { type: String, default: '' }, textB: { type: String, default: '' } })
function lineClass(line, side) { return '' }
</script>

<style scoped>
.diff-viewer { border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }
.diff-header { display: flex; background: #fafafa; border-bottom: 1px solid #e8e8e8; }
.diff-label { flex: 1; padding: 8px 12px; font-weight: 600; font-size: 13px; text-align: center; }
.diff-body { display: flex; }
.diff-side { flex: 1; overflow: auto; max-height: 400px; font-family: monospace; font-size: 12px; line-height: 1.6; }
.diff-side:first-child { border-right: 1px solid #e8e8e8; }
.diff-line { padding: 1px 8px; white-space: pre; }
</style>
