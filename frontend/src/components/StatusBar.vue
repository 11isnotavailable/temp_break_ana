<script setup>
defineProps({
  anomaly: {
    type: Boolean,
    required: true
  }
});
</script>

<template>
  <footer class="status-bar" :class="anomaly ? 'status-alert' : 'status-normal'">
    <span>{{ anomaly ? "状态异常" : "状态正常" }}</span>
  </footer>
</template>
