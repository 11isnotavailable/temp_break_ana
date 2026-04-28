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
      statusLabel: "监控正常",
      source: "mock-local",
      updatedAt: "--"
    }
);

const metrics = computed(
  () =>
    props.dashboard?.metrics || {
      actual: 80,
      predicted: 85,
      delta: 5,
      current: 18.2,
      vibration: 0.58,
      pressure: 1.2
    }
);

const healthScore = computed(() => props.dashboard?.healthScore ?? 96);
const trendRecords = computed(() => props.dashboard?.records?.slice(-5) || []);
const alarmTemperature = computed(() => props.dashboard?.alarmTemperature ?? 89);
const chartRange = computed(() => props.dashboard?.chartRange || { min: 68, max: 92 });

const chartGeometry = {
  width: 560,
  height: 220,
  paddingX: 18,
  paddingY: 18
};

function formatNumber(value, fractionDigits = 1) {
  return Number(value || 0).toFixed(fractionDigits);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function seededUnit(index, channel = 0) {
  const raw = Math.sin((index + 1) * 12.9898 + channel * 78.233) * 43758.5453;
  return raw - Math.floor(raw);
}

const displayRecords = computed(() =>
  trendRecords.value.map((record) => ({
    ...record,
    chartValue: Number(record.chart_value ?? record.t_actual ?? 0),
    actualVisible: record.actual_visible !== false
  }))
);

const scaleModel = computed(() => {
  const min = Number(chartRange.value?.min ?? 68);
  const max = Number(chartRange.value?.max ?? 92);
  const span = Math.max(max - min, 1);
  const stepX =
    displayRecords.value.length <= 1
      ? 0
      : (chartGeometry.width - chartGeometry.paddingX * 2) / (displayRecords.value.length - 1);
  return { min, span, stepX };
});

function valueToY(value) {
  const { min, span } = scaleModel.value;
  return (
    chartGeometry.height -
    chartGeometry.paddingY -
    ((value - min) / span) * (chartGeometry.height - chartGeometry.paddingY * 2)
  );
}

function buildPoints({ predicted = false } = {}) {
  return displayRecords.value
    .map((record, index) => {
      if (!predicted && !record.actualVisible) {
        return null;
      }

      return {
        x: chartGeometry.paddingX + scaleModel.value.stepX * index,
        y: valueToY(record.chartValue)
      };
    })
    .filter(Boolean);
}

function toPolyline(points) {
  if (!points.length) {
    return "";
  }
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function toJaggedPolyline(points) {
  if (!points.length) {
    return "";
  }
  if (points.length < 2) {
    return toPolyline(points);
  }

  const topBound = chartGeometry.paddingY;
  const bottomBound = chartGeometry.height - chartGeometry.paddingY;
  const jaggedPoints = [points[0]];
  const insertedPointsPerSegment = 28;

  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const segmentHeight = Math.abs(end.y - start.y);
    const amplitudeBase = Math.max(3.6, Math.min(8.8, segmentHeight * 0.6 + 3.6));
    const sequenceSeed = index + 1;

    for (let step = 1; step <= insertedPointsPerSegment; step += 1) {
      const ratio = step / (insertedPointsPerSegment + 1);
      const x = start.x + (end.x - start.x) * ratio;
      const baselineY = start.y + (end.y - start.y) * ratio;
      const direction = seededUnit(sequenceSeed * 29 + step, 1) > 0.5 ? 1 : -1;
      const wave =
        Math.sin(
          (step / insertedPointsPerSegment) * Math.PI * 8 +
            seededUnit(sequenceSeed, 2) * Math.PI
        ) * 0.4;
      const noiseScale = 0.35 + seededUnit(sequenceSeed * 29 + step, 3) * 0.65;
      const y = clamp(
        baselineY + direction * amplitudeBase * noiseScale + wave * amplitudeBase,
        topBound,
        bottomBound
      );
      jaggedPoints.push({ x, y });
    }

    jaggedPoints.push(end);
  }

  return toPolyline(jaggedPoints);
}

function toSmoothPath(points) {
  if (!points.length) {
    return "";
  }
  if (points.length === 1) {
    return `M ${points[0].x} ${points[0].y}`;
  }

  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const controlX = (current.x + next.x) / 2;
    path += ` C ${controlX} ${current.y}, ${controlX} ${next.y}, ${next.x} ${next.y}`;
  }
  return path;
}

const actualPoints = computed(() => toJaggedPolyline(buildPoints()));
const predictedPath = computed(() => toSmoothPath(buildPoints({ predicted: true })));
const alarmLineY = computed(() => valueToY(alarmTemperature.value));
const latestActualRecord = computed(() => {
  const records = displayRecords.value.filter((record) => record.actualVisible);
  return records[records.length - 1] || null;
});
const latestPredictedRecord = computed(() => {
  const records = displayRecords.value;
  return records[records.length - 1] || null;
});
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
        <div class="trend-badge">5 点滑动预测窗</div>
      </div>

      <div class="trend-chart-shell">
        <svg
          class="trend-chart"
          :viewBox="`0 0 ${chartGeometry.width} ${chartGeometry.height}`"
          preserveAspectRatio="none"
        >
          <line
            class="trend-threshold"
            :x1="chartGeometry.paddingX"
            :x2="chartGeometry.width - chartGeometry.paddingX"
            :y1="alarmLineY"
            :y2="alarmLineY"
          />
          <text
            class="trend-threshold-label"
            :x="chartGeometry.width - chartGeometry.paddingX"
            :y="Math.max(chartGeometry.paddingY + 12, alarmLineY - 6)"
          >
            警报线 {{ formatNumber(alarmTemperature) }}°C
          </text>
          <path class="trend-line trend-line-predicted" :d="predictedPath" />
          <polyline class="trend-line trend-line-actual" :points="actualPoints" />
        </svg>

        <div class="trend-legend">
          <span><i class="legend-dot legend-actual"></i>真实值 3 点</span>
          <span><i class="legend-dot legend-predicted"></i>预测值 5 点</span>
          <span><i class="legend-dot legend-threshold"></i>警报线</span>
        </div>
      </div>

      <div class="trend-footnote" v-if="latestActualRecord || latestPredictedRecord">
        <span v-if="latestActualRecord">最新真实值 {{ formatNumber(latestActualRecord.chartValue) }}°C</span>
        <span v-if="latestPredictedRecord">窗口最右预测值 {{ formatNumber(latestPredictedRecord.chartValue) }}°C</span>
        <span>警报线 {{ formatNumber(alarmTemperature) }}°C</span>
      </div>
    </div>
  </section>
</template>
