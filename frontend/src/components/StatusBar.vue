<script setup>
import { computed } from "vue";

const props = defineProps({
  anomaly: {
    type: Boolean,
    required: true
  },
  sequence: {
    type: Number,
    default: 0
  },
  recordedAt: {
    type: String,
    default: ""
  },
  expertStatus: {
    type: String,
    default: "sleeping"
  },
  monitoringLocked: {
    type: Boolean,
    default: false
  }
});

const label = computed(() => {
  if (props.monitoringLocked) {
    return `报告已生成 · 当前锁定在第 ${props.sequence} 条`;
  }
  if (props.anomaly) {
    return `第 ${props.sequence} 条触发异常 · 专家状态 ${props.expertStatus}`;
  }
  return `Mock 数据库已写入第 ${props.sequence} 条 · ${props.recordedAt || "等待下一条"}`;
});
</script>

<template>
  <footer class="status-bar" :class="anomaly ? 'status-alert' : 'status-normal'">
    <span>{{ label }}</span>
  </footer>
</template>
