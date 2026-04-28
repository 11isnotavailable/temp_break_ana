const DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1/analysis";
const PREVIEW_INTERVAL_MS = 2500;
const WINDOW_SIZE = 5;
const ACTUAL_VISIBLE_COUNT = 3;
const ALARM_TEMPERATURE = 89;
const EXPERT_TRIGGER_SEQUENCE = 7;

const MOCK_DEVICE = {
  name: "离心泵机组 A-17",
  model: "CPX-80",
  location: "诊断演示工位",
  workshop: "三号产线",
  maintainer: "巡检班组 B"
};

const CURVE_POINTS = [60, 63, 65, 62, 66, 65, 72, 79, 90, 94].map((y, index) => ({
  x: index,
  y
}));

const MAX_WINDOW_INDEX = CURVE_POINTS.length - WINDOW_SIZE;

const analysisPulses = [
  {
    t_predicted: 80.0,
    t_actual: 90.6,
    status: "RUNNING",
    extra_metrics: { current: 21.8, vibration: 1.02, pressure: 0.97 }
  },
  {
    t_predicted: 80.0,
    t_actual: 92.8,
    status: "RUNNING",
    extra_metrics: { current: 22.7, vibration: 1.14, pressure: 0.93 }
  },
  {
    t_predicted: 80.0,
    t_actual: 95.4,
    status: "RUNNING",
    extra_metrics: { current: 23.9, vibration: 1.3, pressure: 0.88 }
  },
  {
    t_predicted: 80.0,
    t_actual: 98.7,
    status: "RUNNING",
    extra_metrics: { current: 25.1, vibration: 1.46, pressure: 0.82 }
  },
  {
    t_predicted: 80.0,
    t_actual: 102.9,
    status: "RUNNING",
    extra_metrics: { current: 26.4, vibration: 1.64, pressure: 0.75 }
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

function buildVisualWindow(windowIndex) {
  return CURVE_POINTS.slice(windowIndex, windowIndex + WINDOW_SIZE).map((point, index) => ({
    sequence: windowIndex + index + 1,
    recorded_at: formatRecordedAtFromSequence(windowIndex + index + 1),
    status: "RUNNING",
    t_predicted: 80.0,
    t_actual: point.y,
    chart_value: point.y,
    actual_visible: index < ACTUAL_VISIBLE_COUNT,
    extra_metrics: {
      current: Number((17.6 + point.x * 0.34).toFixed(1)),
      vibration: Number((0.42 + point.x * 0.055).toFixed(2)),
      pressure: Number((1.24 - point.x * 0.03).toFixed(2))
    }
  }));
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
  return {
    ...frame,
    latest_sequence:
      Number.isFinite(frame.latest_sequence) && frame.latest_sequence > 0
        ? frame.latest_sequence
        : sentPulses.length,
    latest_recorded_at: frame.latest_recorded_at || frame.timestamp
  };
}

function attachMockDashboard(frame, visualRecords, statusLabel) {
  const actualRecords = visualRecords.filter((record) => record.actual_visible);
  const latestActualRecord = actualRecords[actualRecords.length - 1] || null;
  const latestPredictedRecord = visualRecords[visualRecords.length - 1] || latestActualRecord;
  const actual = latestActualRecord?.chart_value ?? 0;
  const predicted = latestPredictedRecord?.chart_value ?? actual;
  const delta = predicted - actual;
  const current = latestActualRecord?.extra_metrics?.current || 0;
  const vibration = latestActualRecord?.extra_metrics?.vibration || 0;
  const pressure = latestActualRecord?.extra_metrics?.pressure || 0;
  const healthScore = Math.max(
    12,
    Math.min(99, Math.round(100 - Math.abs(delta) * 4.5 - vibration * 8))
  );

  return {
    ...frame,
    dashboard: {
      device: {
        ...MOCK_DEVICE,
        taskId: frame.task_id,
        statusLabel,
        source: "mock-local",
        updatedAt: latestActualRecord?.recorded_at || frame.latest_recorded_at || frame.timestamp
      },
      latestRecord: latestActualRecord,
      healthScore,
      alarmTemperature: ALARM_TEMPERATURE,
      chartRange: {
        min: 60,
        max: 100
      },
      records: visualRecords,
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

function buildLocalMonitorFrame(taskId, windowIndex) {
  const visualRecords = buildVisualWindow(windowIndex);
  const latestActualRecord = visualRecords.filter((record) => record.actual_visible).at(-1);
  const triggerReady = (latestActualRecord?.sequence ?? 0) >= EXPERT_TRIGGER_SEQUENCE;

  return attachMockDashboard(
    {
      task_id: taskId,
      timestamp: formatTimestamp(),
      latest_sequence: latestActualRecord?.sequence || windowIndex + ACTUAL_VISIBLE_COUNT,
      latest_recorded_at: latestActualRecord?.recorded_at || formatTimestamp(),
      report: triggerReady
        ? `已到达第 ${EXPERT_TRIGGER_SEQUENCE} 个时间步，正在切入深度专家诊断。`
        : "监控 Agent 正按滑动窗口推进。",
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
      history: {
        pulse_history: [],
        data_records: []
      },
      decision: "CONTINUE",
      report_html: ""
    },
    visualRecords,
    triggerReady ? "预警分析中" : "监控正常"
  );
}

export function createAnalysisService({ mode = "api-simulated", baseUrl = DEFAULT_BASE_URL } = {}) {
  let taskId = createTaskId();
  let sessionStarted = false;
  let analysisPulseIndex = 0;
  let finalized = false;
  let lastWindowAdvanceAt = 0;
  let lastAnalysisPulseAt = 0;
  let windowIndex = 0;
  const sentPulses = [];

  async function startSession(currentTaskId) {
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
    sessionStarted = true;
  }

  async function ensureSession() {
    if (sessionStarted || mode === "api") {
      return;
    }
    await startSession(taskId);
  }

  async function restartLocalState() {
    analysisPulseIndex = 0;
    finalized = false;
    lastWindowAdvanceAt = 0;
    lastAnalysisPulseAt = 0;
    windowIndex = 0;
    sentPulses.length = 0;
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

      const now = Date.now();
      const currentWindow = buildVisualWindow(windowIndex);
      const currentLatestActual = currentWindow.filter((record) => record.actual_visible).at(-1);
      const currentTriggerReady =
        (currentLatestActual?.sequence ?? 0) >= EXPERT_TRIGGER_SEQUENCE;

      if (!sessionStarted && !currentTriggerReady) {
        if (lastWindowAdvanceAt === 0) {
          lastWindowAdvanceAt = now;
          return buildLocalMonitorFrame(taskId, windowIndex);
        }

        if (now - lastWindowAdvanceAt >= PREVIEW_INTERVAL_MS) {
          windowIndex = Math.min(windowIndex + 1, MAX_WINDOW_INDEX);
          lastWindowAdvanceAt = now;
        }

        const advancedWindow = buildVisualWindow(windowIndex);
        const advancedLatestActual = advancedWindow.filter((record) => record.actual_visible).at(-1);
        const advancedTriggerReady =
          (advancedLatestActual?.sequence ?? 0) >= EXPERT_TRIGGER_SEQUENCE;

        if (!advancedTriggerReady) {
          return buildLocalMonitorFrame(taskId, windowIndex);
        }
      }

      if (!sessionStarted) {
        await ensureSession();
      }

      if (windowIndex < MAX_WINDOW_INDEX) {
        if (lastWindowAdvanceAt === 0) {
          lastWindowAdvanceAt = now;
        } else if (now - lastWindowAdvanceAt >= PREVIEW_INTERVAL_MS) {
          windowIndex = Math.min(windowIndex + 1, MAX_WINDOW_INDEX);
          lastWindowAdvanceAt = now;
        }
      }

      const shouldPushPulse =
        !finalized &&
        analysisPulseIndex < analysisPulses.length &&
        (analysisPulseIndex === 0 || now - lastAnalysisPulseAt >= PREVIEW_INTERVAL_MS);

      if (shouldPushPulse) {
        const pulse = analysisPulses[analysisPulseIndex];
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
            sessionStarted = false;
            await ensureSession();
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
        analysisPulseIndex += 1;
        lastAnalysisPulseAt = now;
        const mappedFrame = enrichSimulatedFrame(mapFrame(data), sentPulses);

        if (
          data.feedback.conversation_closed ||
          data.feedback.monitoring_locked ||
          data.feedback.expert_status === "done"
        ) {
          finalized = true;
        }

        return {
          ...attachMockDashboard(mappedFrame, buildVisualWindow(windowIndex), "预警分析中"),
          history: {
            pulse_history: [...sentPulses],
            data_records: []
          }
        };
      }

      if (!sentPulses.length) {
        return buildLocalMonitorFrame(taskId, windowIndex);
      }

      const data = await requestJson(`${baseUrl}/report/${taskId}`, { method: "GET" });
      const mappedFrame = enrichSimulatedFrame(mapFrame(data), sentPulses);
      return attachMockDashboard(mappedFrame, buildVisualWindow(windowIndex), "预警分析中");
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
      sessionStarted = false;
      await restartLocalState();
      return { task_id: taskId };
    }
  };
}
