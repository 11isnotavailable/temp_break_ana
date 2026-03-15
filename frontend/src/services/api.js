const DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1/analysis";

const scenarioPulses = [
  {
    t_predicted: 80.0,
    t_actual: 80.8,
    status: "RUNNING",
    extra_metrics: { current: 18.2, vibration: 0.6, pressure: 1.2 }
  },
  {
    t_predicted: 80.0,
    t_actual: 81.2,
    status: "RUNNING",
    extra_metrics: { current: 18.6, vibration: 0.7, pressure: 1.18 }
  },
  {
    t_predicted: 80.0,
    t_actual: 94.0,
    status: "RUNNING",
    extra_metrics: { current: 22.8, vibration: 1.3, pressure: 0.96 }
  },
  {
    t_predicted: 80.0,
    t_actual: 97.5,
    status: "RUNNING",
    extra_metrics: { current: 23.9, vibration: 1.5, pressure: 0.88 }
  },
  {
    t_predicted: 80.0,
    t_actual: 95.6,
    status: "RUNNING",
    extra_metrics: { current: 23.1, vibration: 1.4, pressure: 0.91 }
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
  if (payload.feedback) {
    return {
      task_id: payload.task_id,
      timestamp: formatTimestamp(),
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

export function createAnalysisService({ mode = "api-simulated", baseUrl = DEFAULT_BASE_URL } = {}) {
  let taskId = createTaskId();
  let started = false;
  let pulseIndex = 0;
  let finalized = false;
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
    sentPulses.length = 0;
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

      if (!finalized && pulseIndex < scenarioPulses.length) {
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

        if (data.feedback.conversation_closed || data.feedback.monitoring_locked || data.feedback.expert_status === "done") {
          finalized = true;
        }

        return {
          ...mapFrame(data),
          history: {
            pulse_history: [...sentPulses]
          }
        };
      }

      const data = await requestJson(`${baseUrl}/report/${taskId}`, { method: "GET" });
      return mapFrame(data);
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
