<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import ExpertPanel from "./components/ExpertPanel.vue";
import LeftPlaceholder from "./components/LeftPlaceholder.vue";
import ScoutPanel from "./components/ScoutPanel.vue";
import StatusBar from "./components/StatusBar.vue";
import { createAnalysisService } from "./services/api";

const service = createAnalysisService({
  mode: "api-simulated"
});

const initialFrame = () => ({
  task_id: service.taskId,
  timestamp: "",
  latest_sequence: 10,
  latest_recorded_at: "",
  report: "等待首轮监控数据输入",
  is_anomaly: false,
  expert_status: "sleeping",
  conversation_closed: false,
  monitoring_locked: false,
  report_ready: false,
  diagnosis: "",
  actions: [],
  requests: [],
  expert_turn_count: 0,
  conversation_history: [],
  history: {},
  dashboard: null,
  decision: "CONTINUE",
  report_html: ""
});

const cards = ref([]);
const chatMessages = ref([]);
const currentFrame = ref(initialFrame());
const loading = ref(true);
const errorMessage = ref("");
const reportLoading = ref(false);
const reportError = ref("");
const reportHtml = ref("");
const reportModalOpen = ref(false);
const reportGeneratedFor = ref("");
const nextWriteCountdown = ref(10);
const lastSequenceChangedAt = ref(Date.now());
const pullInFlight = ref(false);
let timer = null;
let countdownTimer = null;

const anomaly = computed(() => currentFrame.value.is_anomaly);
const expectedChatCount = computed(() => currentFrame.value.conversation_history?.length || 0);
const writeActive = computed(
  () => !currentFrame.value.monitoring_locked && currentFrame.value.expert_status !== "done"
);

async function pullFrame() {
  if (pullInFlight.value) {
    return;
  }

  try {
    pullInFlight.value = true;
    errorMessage.value = "";
    const frame = await service.fetchReport(currentFrame.value.task_id);
    const previousKey = `${currentFrame.value.latest_sequence}-${currentFrame.value.latest_recorded_at}-${currentFrame.value.report}`;
    const nextKey = `${frame.latest_sequence}-${frame.latest_recorded_at}-${frame.report}`;
    if (nextKey !== previousKey) {
      cards.value = [...cards.value, frame].slice(-6);
    }
    currentFrame.value = frame;
    if (frame.report_html) {
      reportHtml.value = frame.report_html;
    }
    loading.value = false;
  } catch (error) {
    loading.value = false;
    errorMessage.value = error instanceof Error ? error.message : "数据加载失败";
  } finally {
    pullInFlight.value = false;
  }
}

async function generateReport() {
  if (
    !anomaly.value ||
    currentFrame.value.expert_status !== "done" ||
    currentFrame.value.report_ready ||
    reportLoading.value
  ) {
    return;
  }

  const signature = `${currentFrame.value.task_id}-${currentFrame.value.expert_turn_count}-${currentFrame.value.diagnosis}`;
  if (reportGeneratedFor.value === signature && reportHtml.value) {
    return;
  }

  try {
    reportLoading.value = true;
    reportError.value = "";
    const response = await service.generateReport({
      taskId: currentFrame.value.task_id,
      issueSummary: currentFrame.value.report,
      historyData: {
        pulse_history: currentFrame.value.history?.pulse_history || [],
        tdi_history: currentFrame.value.history?.tdi_history || [],
        scout_reports: cards.value.map((item) => item.report),
        data_records: currentFrame.value.history?.data_records || []
      },
      chatMessages: chatMessages.value
    });
    reportHtml.value = response.report_html;
    reportGeneratedFor.value = signature;
    await pullFrame();
  } catch (error) {
    reportError.value = error instanceof Error ? error.message : "报告生成失败";
  } finally {
    reportLoading.value = false;
  }
}

async function restartMonitoring() {
  try {
    loading.value = true;
    errorMessage.value = "";
    reportLoading.value = false;
    reportError.value = "";
    reportHtml.value = "";
    reportGeneratedFor.value = "";
    reportModalOpen.value = false;
    cards.value = [];
    chatMessages.value = [];
    await service.restartMonitoring(currentFrame.value.task_id);
    currentFrame.value = initialFrame();
    currentFrame.value.task_id = service.taskId;
    await pullFrame();
  } catch (error) {
    loading.value = false;
    errorMessage.value = error instanceof Error ? error.message : "监控重启失败";
  }
}

function handleMessagesUpdated(value) {
  chatMessages.value = value;
}

function openReportModal() {
  reportModalOpen.value = true;
}

function closeReportModal() {
  reportModalOpen.value = false;
}

watch(
  () => [
    currentFrame.value.expert_status,
    currentFrame.value.report_ready,
    expectedChatCount.value,
    chatMessages.value.length,
    currentFrame.value.diagnosis
  ],
  async () => {
    if (
      currentFrame.value.expert_status === "done" &&
      !currentFrame.value.report_ready &&
      expectedChatCount.value > 0 &&
      chatMessages.value.length >= expectedChatCount.value
    ) {
      await generateReport();
    }
  },
  { deep: true }
);

watch(
  () => currentFrame.value.is_anomaly,
  (isAnomaly) => {
    if (!isAnomaly) {
      reportLoading.value = false;
      reportError.value = "";
      reportHtml.value = "";
      reportGeneratedFor.value = "";
      reportModalOpen.value = false;
    }
  }
);

watch(
  () => currentFrame.value.latest_sequence,
  (next, prev) => {
    if (next && next !== prev) {
      lastSequenceChangedAt.value = Date.now();
      nextWriteCountdown.value = 10;
    }
  }
);

onMounted(async () => {
  await pullFrame();
  timer = window.setInterval(pullFrame, 2000);
  countdownTimer = window.setInterval(() => {
    if (pullInFlight.value) {
      nextWriteCountdown.value = 0;
      return;
    }
    if (!writeActive.value || currentFrame.value.is_anomaly) {
      nextWriteCountdown.value = 0;
      return;
    }
    const elapsedSeconds = Math.floor((Date.now() - lastSequenceChangedAt.value) / 1000);
    nextWriteCountdown.value = Math.max(0, 10 - elapsedSeconds);
  }, 1000);
});

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer);
  }
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
  }
});
</script>

<template>
  <main class="screen-shell">
    <section class="screen-grid">
      <LeftPlaceholder :dashboard="currentFrame.dashboard" />

      <section class="diagnosis-shell">
        <section class="workspace-frame">
          <header class="workspace-header">
            <div>
              <p class="workspace-kicker">Industrial Fault Diagnosis Console</p>
              <h1>故障检测与诊断</h1>
            </div>
            <div class="mode-badge">{{ anomaly ? "ALERT MODE" : "MONITOR MODE" }}</div>
          </header>

          <div v-if="errorMessage" class="banner error-banner">{{ errorMessage }}</div>
          <div v-else-if="loading" class="banner">正在建立诊断会话...</div>

          <div class="workspace-grid">
            <ScoutPanel
              :cards="cards"
              :anomaly="anomaly"
              :next-write-countdown="nextWriteCountdown"
              :write-active="writeActive && !anomaly"
              :pull-in-flight="pullInFlight"
              :latest-sequence="currentFrame.latest_sequence"
            />
            <ExpertPanel
              :anomaly="anomaly"
              :expert-status="currentFrame.expert_status"
              :monitoring-locked="currentFrame.monitoring_locked"
              :conversation-history="currentFrame.conversation_history"
              :report-loading="reportLoading"
              :report-ready="currentFrame.report_ready && Boolean(reportHtml)"
              :report-error="reportError"
              @messages-updated="handleMessagesUpdated"
              @download-report="openReportModal"
              @restart-monitoring="restartMonitoring"
            />
          </div>

          <StatusBar
            :anomaly="anomaly"
            :sequence="currentFrame.latest_sequence"
            :recorded-at="currentFrame.latest_recorded_at"
            :expert-status="currentFrame.expert_status"
            :monitoring-locked="currentFrame.monitoring_locked"
          />
        </section>
      </section>
    </section>

    <div v-if="reportModalOpen" class="report-modal-backdrop" @click.self="closeReportModal">
      <section class="report-modal">
        <header class="report-modal-header">
          <div>
            <p class="panel-kicker">Generated Report</p>
            <h2>完整分析报告</h2>
          </div>
          <button class="modal-close" type="button" @click="closeReportModal">关闭</button>
        </header>
        <div class="report-modal-body" v-html="reportHtml"></div>
      </section>
    </div>
  </main>
</template>
