<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  anomaly: {
    type: Boolean,
    required: true
  },
  expertStatus: {
    type: String,
    required: true
  },
  monitoringLocked: {
    type: Boolean,
    default: false
  },
  conversationHistory: {
    type: Array,
    required: true
  },
  reportLoading: {
    type: Boolean,
    default: false
  },
  reportReady: {
    type: Boolean,
    default: false
  },
  reportError: {
    type: String,
    default: ""
  }
});

const emit = defineEmits(["messages-updated", "download-report", "restart-monitoring"]);

const visibleMessages = ref([]);
const chatStreamRef = ref(null);
const revealTimers = [];
const scheduledMessageIds = new Set();
const shouldStickToBottom = ref(true);

function clearTimers() {
  while (revealTimers.length) {
    window.clearTimeout(revealTimers.pop());
  }
  scheduledMessageIds.clear();
}

function scrollToBottom(force = false) {
  const el = chatStreamRef.value;
  if (!el) {
    return;
  }
  if (force || shouldStickToBottom.value) {
    el.scrollTop = el.scrollHeight;
  }
}

function handleScroll() {
  const el = chatStreamRef.value;
  if (!el) {
    return;
  }
  const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  shouldStickToBottom.value = distanceToBottom < 32;
}

function syncConversationHistory() {
  const existingIndexMap = new Map(visibleMessages.value.map((message, index) => [message.id, index]));
  let appendOffset = 0;

  props.conversationHistory.forEach((message) => {
    const existingIndex = existingIndexMap.get(message.id);
    if (existingIndex !== undefined) {
      const currentMessage = visibleMessages.value[existingIndex];
      if (
        currentMessage.text !== message.text ||
        currentMessage.title !== message.title ||
        currentMessage.type !== message.type
      ) {
        const nextMessages = [...visibleMessages.value];
        nextMessages[existingIndex] = message;
        visibleMessages.value = nextMessages;
      }
      return;
    }

    if (scheduledMessageIds.has(message.id)) {
      return;
    }

    appendOffset += 1;
    scheduledMessageIds.add(message.id);
    const timer = window.setTimeout(async () => {
      if (!visibleMessages.value.some((item) => item.id === message.id)) {
        visibleMessages.value = [...visibleMessages.value, message];
      }
      scheduledMessageIds.delete(message.id);
      await nextTick();
      scrollToBottom();
    }, 520 * appendOffset);
    revealTimers.push(timer);
  });
}

function resetChat() {
  clearTimers();
  visibleMessages.value = [];
  shouldStickToBottom.value = true;
}

watch(
  () => props.anomaly,
  (isAnomaly) => {
    if (!isAnomaly) {
      resetChat();
      return;
    }
    syncConversationHistory();
  },
  { immediate: true }
);

watch(
  () => props.conversationHistory,
  () => {
    if (!props.anomaly) {
      return;
    }
    syncConversationHistory();
  },
  { deep: true }
);

watch(
  visibleMessages,
  (value) => {
    emit("messages-updated", value);
  },
  { deep: true, immediate: true }
);

onBeforeUnmount(() => {
  clearTimers();
});
</script>

<template>
  <section class="panel expert-panel">
    <div class="panel-header">
      <div class="agent-dot"></div>
      <div>
        <p class="panel-kicker">Agent 2</p>
        <h2>深度专家评估</h2>
      </div>
    </div>

    <div v-if="!anomaly" class="sleeping-zone">
      <div class="sleeping-card">
        <span>休眠中</span>
        <p>当前仅保留监控 Agent 持续巡检，专家区未介入。</p>
      </div>
    </div>

    <div v-else class="chat-zone">
      <div ref="chatStreamRef" class="chat-stream" @scroll="handleScroll">
        <article
          v-for="message in visibleMessages"
          :key="message.id"
          class="chat-bubble"
          :class="`chat-${message.type}`"
        >
          <p class="bubble-title">{{ message.title }}</p>
          <p>{{ message.text }}</p>
        </article>

        <div v-if="expertStatus !== 'done' && !monitoringLocked" class="typing-row">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>

      <div class="report-action-bar">
        <div v-if="reportLoading" class="report-loading">
          <span></span>
          <span></span>
          <span></span>
          <p>分析报告生成中...</p>
        </div>
        <p v-else-if="reportError" class="report-error">{{ reportError }}</p>
        <button
          v-if="reportReady"
          class="report-button"
          type="button"
          @click="emit('download-report')"
        >
          下载分析报告
        </button>
        <button
          v-if="monitoringLocked"
          class="report-button restart-button"
          type="button"
          @click="emit('restart-monitoring')"
        >
          继续工作
        </button>
      </div>
    </div>
  </section>
</template>
