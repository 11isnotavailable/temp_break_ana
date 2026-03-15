<script setup>
import { computed } from "vue";

const props = defineProps({
  dashboard: {
    type: Object,
    default: null
  }
});

const device = computed(
  () =>
    props.dashboard?.device || {
      name: "离心泵机组 A-17",
      model: "CPX-80",
      location: "诊断演示工位",
      workshop: "三号产线",
      maintainer: "巡检班组 B",
      statusLabel: "在线监测",
      source: "mock-local",
      updatedAt: "--"
    }
);

const metrics = computed(
  () =>
    props.dashboard?.metrics || {
      actual: 80,
      predicted: 80,
      delta: 0,
      current: 18.2,
      vibration: 0.58,
      pressure: 1.2
    }
);

const healthScore = computed(() => props.dashboard?.healthScore ?? 96);
const trendRecords = computed(() => props.dashboard?.records?.slice(-8) || []);

const chartGeometry = {
  width: 560,
  height: 220,
  paddingX: 18,
  paddingY: 18
};

function formatNumber(value, fractionDigits = 1) {
  return Number(value || 0).toFixed(fractionDigits);
}

function buildPoints(field) {
  const records = trendRecords.value;
  if (!records.length) {
    return "";
  }

  const values = records.flatMap((item) => [item.t_actual, item.t_predicted]);
  const min = Math.min(...values) - 1;
  const max = Math.max(...values) + 1;
  const span = Math.max(max - min, 1);
  const stepX =
    records.length === 1
      ? 0
      : (chartGeometry.width - chartGeometry.paddingX * 2) / (records.length - 1);

  return records
    .map((record, index) => {
      const value = Number(record[field] || 0);
      const x = chartGeometry.paddingX + stepX * index;
      const y =
        chartGeometry.height -
        chartGeometry.paddingY -
        ((value - min) / span) * (chartGeometry.height - chartGeometry.paddingY * 2);
      return `${x},${y}`;
    })
    .join(" ");
}

const actualPoints = computed(() => buildPoints("t_actual"));
const predictedPoints = computed(() => buildPoints("t_predicted"));
const latestRecord = computed(() => trendRecords.value[trendRecords.value.length - 1] || null);
</script>

<template>
  <section class="placeholder-shell">
    <div class="placeholder-card placeholder-tall">
      <div class="placeholder-header placeholder-header-row">
        <div>
          <p class="panel-kicker">Mock Main Project Area</p>
          <h2>设备信息</h2>
        </div>
        <div class="device-status-chip">{{ device.statusLabel }}</div>
      </div>

      <div class="device-title-block">
        <h3>{{ device.name }}</h3>
        <p>{{ device.model }} · {{ device.location }}</p>
      </div>

      <div class="device-grid">
        <article class="device-spotlight">
          <span class="metric-label">健康评分</span>
          <strong>{{ healthScore }}</strong>
          <p>根据温差、电流、振动和压力的 mock 指标综合估算。</p>
        </article>

        <div class="device-info-list">
          <div>
            <span class="metric-label">所属产线</span>
            <strong>{{ device.workshop }}</strong>
          </div>
          <div>
            <span class="metric-label">维护班组</span>
            <strong>{{ device.maintainer }}</strong>
          </div>
          <div>
            <span class="metric-label">数据源</span>
            <strong>{{ device.source }}</strong>
          </div>
          <div>
            <span class="metric-label">最后更新</span>
            <strong>{{ device.updatedAt }}</strong>
          </div>
        </div>
      </div>

      <div class="metric-strip">
        <article class="metric-tile">
          <span class="metric-label">实际温度</span>
          <strong>{{ formatNumber(metrics.actual) }}°C</strong>
        </article>
        <article class="metric-tile">
          <span class="metric-label">预测温度</span>
          <strong>{{ formatNumber(metrics.predicted) }}°C</strong>
        </article>
        <article class="metric-tile" :class="metrics.delta > 8 ? 'metric-alert' : ''">
          <span class="metric-label">温差</span>
          <strong>{{ formatNumber(metrics.delta) }}°C</strong>
        </article>
        <article class="metric-tile">
          <span class="metric-label">电流</span>
          <strong>{{ formatNumber(metrics.current) }} A</strong>
        </article>
        <article class="metric-tile">
          <span class="metric-label">振动</span>
          <strong>{{ formatNumber(metrics.vibration, 2) }}</strong>
        </article>
        <article class="metric-tile">
          <span class="metric-label">压力</span>
          <strong>{{ formatNumber(metrics.pressure, 2) }} MPa</strong>
        </article>
      </div>
    </div>

    <div class="placeholder-card">
      <div class="placeholder-header placeholder-header-row">
        <div>
          <p class="panel-kicker">Mock Main Project Area</p>
          <h2>温度趋势</h2>
        </div>
        <div class="trend-badge">
          最近 {{ trendRecords.length }} 条记录
        </div>
      </div>

      <div class="trend-chart-shell">
        <svg
          class="trend-chart"
          :viewBox="`0 0 ${chartGeometry.width} ${chartGeometry.height}`"
          preserveAspectRatio="none"
        >
          <polyline class="trend-line trend-line-predicted" :points="predictedPoints" />
          <polyline class="trend-line trend-line-actual" :points="actualPoints" />
        </svg>

        <div class="trend-legend">
          <span><i class="legend-dot legend-actual"></i>实际温度</span>
          <span><i class="legend-dot legend-predicted"></i>预测温度</span>
          <span v-if="latestRecord">最新记录 #{{ latestRecord.sequence }}</span>
        </div>
      </div>

      <div class="trend-footnote" v-if="latestRecord">
        <span>最新时间：{{ latestRecord.recorded_at }}</span>
        <span>实际 {{ formatNumber(latestRecord.t_actual) }}°C</span>
        <span>预测 {{ formatNumber(latestRecord.t_predicted) }}°C</span>
      </div>
    </div>
  </section>
</template>
