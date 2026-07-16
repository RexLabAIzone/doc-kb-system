import { ref } from 'vue'

const visible = ref(false)
const docId = ref(null)
const prevId = ref(null)
const nextId = ref(null)

export function useReader() {
  function open(id, prev, next) {
    docId.value = id
    prevId.value = prev || null
    nextId.value = next || null
    visible.value = true
  }
  function close() {
    visible.value = false
    docId.value = null
  }
  function goPrev() {
    if (prevId.value) open(prevId.value)
  }
  function goNext() {
    if (nextId.value) open(nextId.value)
  }
  return { visible, docId, prevId, nextId, open, close, goPrev, goNext }
}
