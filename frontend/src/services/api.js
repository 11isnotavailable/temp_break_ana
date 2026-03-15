const DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1/analysis";
const PULSE_INTERVAL_MS = 10000;
const SEED_RECORD_COUNT = 10;
const MOCK_DEVICE = {
  name: "离心泵机组 A-17",
  model: "CPX-80",
  location: "诊断演示工位",
  workshop: "三号产线",
  maintainer: "巡检班组 B"
};

const seedRows = [
  { t_predicted: 80.0, t_actual: 79.8, extra_metrics: { current: 18.1, vibration: 0.5, pressure: 1.22 } },
  { t_predicted: 80.0, t_actual: 80.1, extra_metrics: { current: 18.2, vibration: 0.52, pressure: 1.21 } },
  { t_predicted: 80.0, t_actual: 79.9, extra_metrics: { current: 18.3, vibration: 0.54, pressure: 1.2 } },
  { t_predicted: 80.0, t_actual: 80.4, extra_metrics: { current: 18.4, vibration: 0.56, pressure: 1.18 } },
  { t_predicted: 80.0, t_actual: 80.6, extra_metrics: { current: 18.5, vibration: 0.58, pressure: 1.16 } },
  { t_predicted: 80.0, t_actual: 80.2, extra_metrics: { current: 18.6, vibration: 0.6, pressure: 1.15 } },
  { t_predicted: 80.0, t_actual: 79.7, extra_metrics: { current: 18.7, vibration: 0.61, pressure: 1.14 } },
  { t_predicted: 80.0, t_actual: 80.5, extra_metrics: { current: 18.9, vibration: 0.63, pressure: 1.13 } },
  { t_predicted: 80.0, t_actual: 80.8, extra_metrics: { current: 19.0, vibration: 0.65, pressure: 1.11 } },
  { t_predicted: 80.0, t_actual: 81.0, extra_metrics: { current: 19.2, vibration: 0.66, pressure: 1.1 } }
];

const scenarioPulses = [
  {
    t_predicted: 80.0,
    t_actual: 81.4,
    status: "RUNNING",
    extra_metrics: { current: 18.8, vibration: 0.64, pressure: 1.18 }
  },
  {
    t_predicted: 80.0,
    t_actual: 82.6,
    status: "RUNNING",
    extra_metrics: { current: 19.1, vibration: 0.71, pressure: 1.15 }
  },
  {
    t_predicted: 80.0,
    t_actual: 84.2,
    status: "RUNNING",
    extra_metrics: { current: 19.9, vibration: 0.78, pressure: 1.11 }
  },
  {
    t_predicted: 80.0,
    t_actual: 88.4,
    status: "RUNNING",
    extra_metrics: { current: 20.8, vibration: 0.96, pressure: 1.03 }
  },
  {
    t_predicted: 80.0,
    t_actual: 95.6,
    status: "RUNNING",
    extra_metrics: { current: 23.6, vibration: 1.46, pressure: 0.89 }
  }
];

function createTaskId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `demo-${Date.now()}`;
}

function formatTimestamp() {
  return new Date().toLocaleString("zh-CN", { hour12: false });
}

function formatRecordedAtFromSequence(sequence) {
  const baseTime = new Date("2026-03-15T21:01:27");
  const date = new Date(baseTime.getTime() + (sequence - 1) * 10000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function buildSeedRecords() {
  return seedRows.map((row, index) => ({
    sequence: index + 1,
    recorded_at: formatRecordedAtFromSequence(index + 1),
    status: "RUNNING",
    scout_analysis: "监控判断设备温度与预测值接近，维持常规巡检。",
    ...row
  }));
}

function buildRuntimeRecord(sequence, pulse, analysis) {
  return {
    sequence,
    recorded_at: formatRecordedAtFromSequence(sequence),
    status: pulse.status,
    t_predicted: pulse.t_predicted,
    t_actual: pulse.t_actual,
    extra_metrics: pulse.extra_metrics || {},
    scout_analysis: analysis
  };
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json();
}

function mapFrame(payload) {
  const historyRecords = payload.history?.data_records || [];
  const latestHistoryRecord = historyRecords[historyRecords.length - 1] || null;
  const fallbackSequence = latestHistoryRecord?.sequence || 0;
  const fallbackRecordedAt = latestHistoryRecord?.recorded_at || "";

  if (payload.feedback) {
    return {
      task_id: payload.task_id,
      timestamp: formatTimestamp(),
      latest_sequence: payload.feedback.latest_sequence ?? fallbackSequence,
      latest_recorded_at: payload.feedback.latest_recorded_at ?? fallbackRecordedAt,
      report: payload.feedback.latest_report,
      is_anomaly: payload.feedback.is_anomaly,
      expert_status: payload.feedback.expert_status,
      conversation_closed: payload.feedback.conversation_closed,
      monitoring_locked: payload.feedback.monitoring_locked,
      report_ready: payload.feedback.report_ready,
      diagnosis: payload.feedback.diagnosis,
      actions: payload.feedback.actions,
      requests: payload.feedback.requests,
      expert_turn_count: payload.feedback.expert_turn_count,
      conversation_history: payload.feedback.conversation_history,
      history: {},
      decision: payload.decision
    };
  }

  return {
    task_id: payload.task_id,
    timestamp: formatTimestamp(),
    latest_sequence: payload.summary.latest_sequence ?? fallbackSequence,
    latest_recorded_at: payload.summary.latest_recorded_at ?? fallbackRecordedAt,
    report: payload.summary.latest_report,
    is_anomaly: payload.summary.is_anomaly,
    expert_status: payload.summary.expert_status,
    conversation_closed: payload.summary.conversation_closed,
    monitoring_locked: payload.summary.monitoring_locked,
    report_ready: payload.summary.report_ready,
    diagnosis: payload.diagnosis.conclusion,
    actions: payload.diagnosis.actions,
    requests: payload.diagnosis.requests,
    expert_turn_count: payload.summary.expert_turn_count,
    conversation_history: payload.conversation_history,
    history: payload.history,
    decision: payload.decision,
    report_html: payload.report_html || ""
  };
}

function enrichSimulatedFrame(frame, sentPulses) {
  const fallbackSequence = SEED_RECORD_COUNT + sentPulses.length;
  return {
    ...frame,
    latest_sequence: Number.isFinite(frame.latest_sequence) && frame.latest_sequence > 0 ? frame.latest_sequence : fallbackSequence,
    latest_recorded_at: frame.latest_recorded_at || frame.timestamp
  };
}

function attachMockDashboard(frame, records) {
  const latestRecord = records[records.length - 1] || null;
  const actual = latestRecord?.t_actual || 0;
  const predicted = latestRecord?.t_predicted || 0;
  const delta = actual - predicted;
  const vibration = latestRecord?.extra_metrics?.vibration || 0;
  const current = latestRecord?.extra_metrics?.current || 0;
  const pressure = latestRecord?.extra_metrics?.pressure || 0;
  const healthScore = Math.max(12, Math.min(99, Math.round(100 - Math.abs(delta) * 3.6 - vibration * 12)));

  return {
    ...frame,
    dashboard: {
      device: {
        ...MOCK_DEVICE,
        taskId: frame.task_id,
        statusLabel: frame.monitoring_locked
          ? "待人工处理"
          : frame.is_anomaly
            ? "异常审查中"
            : "在线监测",
        source: "mock-local",
        updatedAt: latestRecord?.recorded_at || frame.latest_recorded_at || frame.timestamp
      },
      latestRecord,
      healthScore,
      records: records.slice(-12),
      metrics: {
        actual,
        predicted,
        delta,
        current,
        vibration,
        pressure
      }
    }
  };
}

export function createAnalysisService({ mode = "api-simulated", baseUrl = DEFAULT_BASE_URL } = {}) {
  let taskId = createTaskId();
  let started = false;
  let pulseIndex = 0;
  let finalized = false;
  let lastPulseAt = 0;
  const sentPulses = [];
  let timelineRecords = buildSeedRecords();

  async function startSession(currentTaskId) {
    timelineRecords = buildSeedRecords();
    await requestJson(`${baseUrl}/start`, {
      method: "POST",
      body: JSON.stringify({
        task_id: currentTaskId,
        device_id: "MOCK-0004",
        category: "离心泵",
        metadata: {
          location: "诊断演示工位",
          source: "frontend-simulated-pulse"
        }
      })
    });
    started = true;
  }

  async function ensureSession() {
    if (started || mode === "api") {
      return;
    }
    await startSession(taskId);
  }

  async function restartLocalState() {
    pulseIndex = 0;
    finalized = false;
    lastPulseAt = 0;
    sentPulses.length = 0;
    timelineRecords = buildSeedRecords();
  }

  async function restartSession() {
    await restartLocalState();
    if (mode === "api") {
      return;
    }
    await requestJson(`${baseUrl}/restart`, {
      method: "POST",
      body: JSON.stringify({ task_id: taskId })
    });
    started = true;
  }

  return {
    get taskId() {
      return taskId;
    },
    async fetchReport(externalTaskId) {
      if (mode === "api") {
        const data = await requestJson(`${baseUrl}/report/${externalTaskId}`, { method: "GET" });
        return mapFrame(data);
      }

      await ensureSession();

      const now = Date.now();
      const shouldPushPulse =
        !finalized &&
        pulseIndex < scenarioPulses.length &&
        (pulseIndex === 0 || now - lastPulseAt >= PULSE_INTERVAL_MS);

      if (shouldPushPulse) {
        const pulse = scenarioPulses[pulseIndex];
        let data;

        try {
          data = await requestJson(`${baseUrl}/pulse`, {
            method: "POST",
            body: JSON.stringify({
              task_id: taskId,
              ...pulse
            })
          });
        } catch (error) {
          if (error instanceof Error && error.message.includes("Task not found")) {
            taskId = createTaskId();
            started = false;
            await startSession(taskId);
            data = await requestJson(`${baseUrl}/pulse`, {
              method: "POST",
              body: JSON.stringify({
                task_id: taskId,
                ...pulse
              })
            });
          } else {
            throw error;
          }
        }

        sentPulses.push(pulse);
        pulseIndex += 1;
        lastPulseAt = now;
        const mappedFrame = enrichSimulatedFrame(mapFrame(data), sentPulses);
        timelineRecords = [
          ...timelineRecords,
          buildRuntimeRecord(SEED_RECORD_COUNT + sentPulses.length, pulse, mappedFrame.report)
        ];

        if (data.feedback.conversation_closed || data.feedback.monitoring_locked || data.feedback.expert_status === "done") {
          finalized = true;
        }

        return {
          ...attachMockDashboard(mappedFrame, timelineRecords),
          history: {
            pulse_history: [...sentPulses],
            data_records: [...timelineRecords]
          }
        };
      }

      const data = await requestJson(`${baseUrl}/report/${taskId}`, { method: "GET" });
      const mappedFrame = enrichSimulatedFrame(mapFrame(data), sentPulses);
      return attachMockDashboard(mappedFrame, timelineRecords);
    },
    async generateReport({ taskId: reportTaskId, issueSummary, historyData, chatMessages }) {
      return requestJson(`${baseUrl}/report/generate`, {
        method: "POST",
        body: JSON.stringify({
          task_id: reportTaskId || taskId,
          issue_summary: issueSummary,
          history_data: historyData,
          chat_messages: chatMessages
        })
      });
    },
    async restartMonitoring(targetTaskId) {
      const currentTaskId = targetTaskId || taskId;
      await requestJson(`${baseUrl}/restart`, {
        method: "POST",
        body: JSON.stringify({
          task_id: currentTaskId
        })
      });
      taskId = currentTaskId;
      started = true;
      await restartLocalState();
      return { task_id: taskId };
    }
  };
}
