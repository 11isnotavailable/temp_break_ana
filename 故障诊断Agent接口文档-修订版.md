# 工业设备故障诊断 Agent 服务接口文档（修订版）

## 1. 文档定位

本接口文档仅覆盖“故障检测与诊断”子服务，不覆盖主项目中的以下能力：

- 设备基础信息详情接口
- 温度趋势图数据接口
- 主项目设备列表、页面路由、鉴权等通用能力

本服务主要用于支撑故障诊断功能区，尤其是以下两种页面状态：

- 正常状态：实时监控 Agent 持续监测，深度专家区休眠
- 异常状态：实时监控 Agent 发现异常，深度专家区启动诊断并输出结论

## 2. 服务职责

服务基于双 Agent 协作：

- Agent 1 `实时监控 Agent`
  - 接收主后端周期性推送的温度相关数据
  - 计算 TDI（温差偏移指标）
  - 输出实时监控摘要
  - 判断当前是否异常
  - 在稳定收敛后给出终止建议

- Agent 2 `深度专家评估`
  - 在异常时介入
  - 输出诊断结论
  - 输出维修/处置建议
  - 在信息不足时提出补充数据请求
  - 返回诊断阶段信息，供前端展示分析过程

## 3. 通信流程

1. 主后端调用 `POST /v1/analysis/start` 初始化诊断任务
2. 主后端按周期调用 `POST /v1/analysis/pulse` 推送最新脉冲数据
3. 前端诊断页面根据 `pulse` 返回结果切换正常态/异常态
4. 若前端需要恢复完整诊断状态或刷新结果，调用 `GET /v1/analysis/report/{task_id}`
5. 当 `decision = TERMINATE` 时，主后端可停止该任务的持续推送

## 4. 统一字段定义

### 4.1 术语说明

- `TDI`
  - 定义：`abs(t_actual - t_predicted) / (t_predicted + 1e-6)`
  - 含义：实际温度与预测温度的偏移比例

- `decision`
  - `CONTINUE`：继续监控或继续诊断
  - `TERMINATE`：本次任务已稳定收敛，可结束调用

- `is_anomaly`
  - `true`：当前存在异常，需要高亮展示或进入诊断态
  - `false`：当前处于正常监测态

- `expert_status`
  - `sleeping`：深度专家未介入
  - `running`：深度专家诊断中
  - `done`：深度专家已完成当前轮诊断

## 5. 接口定义

### 5.1 启动分析任务

- URL：`/v1/analysis/start`
- Method：`POST`

#### Request Body

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| task_id | string | 是 | 业务唯一任务 ID |
| device_id | string | 是 | 设备唯一编号 |
| category | string | 是 | 设备类别，如离心泵、电机 |
| metadata | object | 否 | 扩展信息，由主项目按需透传 |

#### Response

```json
{
  "status": "success",
  "message": "Analysis session initialized"
}
```

### 5.2 周期性数据推送

- URL：`/v1/analysis/pulse`
- Method：`POST`

#### Request Body

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| task_id | string | 是 | 启动任务时关联的 ID |
| t_predicted | float | 是 | 模型预测的合理温度 |
| t_actual | float | 是 | 传感器回传的真实温度 |
| status | string | 是 | 设备当前运行状态，如 `RUNNING` / `IDLE` |
| extra_metrics | object | 否 | 其他辅助指标，如振动、电流、转速等 |

#### Response

```json
{
  "task_id": "uuid_123",
  "decision": "CONTINUE",
  "feedback": {
    "is_anomaly": true,
    "tdi_value": 0.32,
    "latest_report": "实时监控Agent发现温差偏移快速放大，当前异常等级升高。",
    "expert_status": "running",
    "diagnosis": "初步判断为润滑系统异常或散热能力下降导致的持续升温。",
    "actions": [
      "优先检查润滑回路是否存在堵塞或油品劣化",
      "检查冷却循环与散热部件是否异常"
    ],
    "requests": [
      "请补充最近30分钟电流变化数据",
      "请补充最近30分钟振动变化数据"
    ],
    "expert_steps": [
      {
        "title": "读取实时监控摘要",
        "status": "done",
        "detail": "已接收当前TDI与状态信息"
      },
      {
        "title": "尝试调取历史信息",
        "status": "running",
        "detail": "正在结合历史异常模式进行比对"
      }
    ]
  }
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| feedback.is_anomaly | boolean | 页面是否进入异常态的核心判断字段 |
| feedback.tdi_value | float | 当前轮 TDI 值 |
| feedback.latest_report | string | 实时监控 Agent 的最新摘要 |
| feedback.expert_status | string | 深度专家当前状态 |
| feedback.diagnosis | string | 当前轮诊断结论，没有结论时可为空字符串 |
| feedback.actions | string[] | 建议动作列表，没有建议时返回空数组 |
| feedback.requests | string[] | 对补充数据的请求列表，没有请求时返回空数组 |
| feedback.expert_steps | object[] | 诊断阶段信息，供前端展示分析过程 |

### 5.3 获取完整诊断报告

- URL：`/v1/analysis/report/{task_id}`
- Method：`GET`

#### Response

```json
{
  "task_id": "uuid_123",
  "device_info": {
    "id": "PUMP-001",
    "category": "离心泵",
    "location": "1号产线"
  },
  "decision": "CONTINUE",
  "summary": {
    "is_anomaly": true,
    "expert_status": "done",
    "latest_tdi": 0.32,
    "latest_report": "实时监控Agent发现温差偏移快速放大，当前异常等级升高。"
  },
  "diagnosis": {
    "conclusion": "综合判断优先怀疑润滑系统异常，其次考虑散热能力下降。",
    "actions": [
      "检查润滑油状态",
      "检查冷却风路或冷却液循环"
    ],
    "requests": [
      "补充电流数据",
      "补充振动数据"
    ]
  },
  "expert_steps": [
    {
      "title": "读取实时监控摘要",
      "status": "done",
      "detail": "已完成"
    },
    {
      "title": "尝试调取历史信息",
      "status": "done",
      "detail": "已完成历史异常样本比对"
    },
    {
      "title": "生成解决方案及报告",
      "status": "done",
      "detail": "已输出诊断结论与建议"
    }
  ],
  "history": {
    "tdi_history": [0.02, 0.03, 0.18, 0.32],
    "scout_reports": [
      "系统运行平稳，TDI处于正常范围。",
      "监测到温差偏移扩大，建议关注。"
    ]
  }
}
```

#### 用途说明

该接口主要用于：

- 页面刷新后的状态恢复
- 异常态下拉取完整诊断结果
- 主项目归档当前任务的完整分析结果

## 6. 页面联动建议

前端诊断功能区建议按以下规则使用接口：

### 6.1 正常状态

- 轮询或订阅 `pulse` 结果
- 当 `feedback.is_anomaly = false` 时：
  - 上方实时监控区显示 `latest_report`
  - 下方深度专家区显示 `expert_status = sleeping`
  - 底部状态条显示“状态正常”

### 6.2 异常状态

- 当 `feedback.is_anomaly = true` 时：
  - 上方实时监控区高亮当前监控摘要
  - 下方深度专家区切换为诊断态
  - 根据 `expert_steps` 展示分析过程
  - 根据 `diagnosis`、`actions`、`requests` 展示诊断结果
  - 底部状态条显示“状态异常”

### 6.3 页面恢复

- 页面首次进入或刷新时，可调用 `GET /report/{task_id}`
- 若任务已存在历史诊断结果，则直接恢复诊断区状态

## 7. 状态码说明

| 状态码 | 说明 |
| --- | --- |
| 200 | 请求成功 |
| 404 | `task_id` 不存在 |
| 422 | 参数校验失败 |
| 500 | Agent 运行异常或模型调用异常 |

## 8. 与旧版文档的差异

本修订版主要新增或明确了以下字段：

- `feedback.is_anomaly`
- `feedback.expert_status`
- `feedback.actions`
- `feedback.expert_steps`
- `GET /v1/analysis/report/{task_id}` 的明确返回结构

这些字段用于支撑“正常态/异常态”诊断页面，而不扩展至主项目的设备详情或趋势图功能。
