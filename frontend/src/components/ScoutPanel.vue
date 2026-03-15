<script setup>
defineProps({
  cards: {
    type: Array,
    required: true
  },
  anomaly: {
    type: Boolean,
    required: true
  }
});
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

    <div class="stack">
      <article
        v-for="(card, idx) in cards"
        :key="`${card.timestamp}-${idx}`"
        class="scout-card"
        :class="[
          idx === cards.length - 1 ? 'is-active' : '',
          idx === cards.length - 1 && anomaly ? 'is-alert' : ''
        ]"
        :style="{ '--depth': cards.length - idx }"
      >
        <time>{{ card.timestamp }}</time>
        <p>{{ card.report }}</p>
      </article>
    </div>
  </section>
</template>
