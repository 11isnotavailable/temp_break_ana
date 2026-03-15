<script setup>
import { computed } from "vue";

const props = defineProps({
  cards: {
    type: Array,
    required: true
  },
  anomaly: {
    type: Boolean,
    required: true
  },
  nextWriteCountdown: {
    type: Number,
    default: 0
  },
  writeActive: {
    type: Boolean,
    default: false
  },
  pullInFlight: {
    type: Boolean,
    default: false
  },
  latestSequence: {
    type: Number,
    default: 0
  }
});

const displayRows = computed(() => [...props.cards].reverse());
</script>

<template>
  <section class="panel scout-panel">
    <div class="panel-header">
      <div class="agent-dot"></div>
      <div>
        <p class="panel-kicker">Agent 1</p>
        <h2>实时监控 Agent</h2>
      </div>
      <div class="loop-mark">↻</div>
    </div>

    <div class="scout-meta">
      <div class="scout-meta-card">
        <span class="meta-label">Mock 数据库</span>
        <strong>已写入第 {{ latestSequence }} 条</strong>
      </div>
      <div class="scout-meta-card" :class="writeActive ? 'meta-live' : 'meta-paused'">
        <span class="meta-label">写入节奏</span>
        <strong v-if="pullInFlight">正在等待后端分析</strong>
        <strong v-else-if="writeActive">{{ nextWriteCountdown }} 秒后写入下一条</strong>
        <strong v-else>{{ anomaly ? "异常已触发，转入专家审查" : "当前暂停写入" }}</strong>
      </div>
    </div>

    <div class="scout-log-shell">
      <div class="scout-log-header">
        <span>序号 / 时间</span>
        <span>监控结论</span>
      </div>

      <div class="scout-log-list">
        <article
          v-for="(card, idx) in displayRows"
          :key="`${card.latest_sequence}-${idx}`"
          class="scout-log-row"
          :class="[
            idx === 0 ? 'is-current' : '',
            idx === 0 && anomaly ? 'is-alert' : ''
          ]"
        >
          <div class="log-index">
            <strong>#{{ card.latest_sequence }}</strong>
            <time>{{ card.latest_recorded_at || card.timestamp }}</time>
          </div>
          <p>{{ card.report }}</p>
        </article>

        <div v-if="!displayRows.length" class="scout-empty">
          等待首条监测记录写入。
        </div>
      </div>
    </div>
  </section>
</template>
