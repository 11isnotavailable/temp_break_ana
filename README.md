# 工业设备故障检测与诊断子模块

这是工业测温主项目中的一个独立子功能，负责对上游监控结果进行异常检测、深度诊断、报告生成，并提供一个可单独运行的 Vue 页面用于演示和后续移植。

当前仓库包含两部分：

- 后端：`FastAPI + LangGraph + LangChain`
- 前端：`Vue 3 + Vite`

目标不是替代主项目，而是提供一个可单独启动、可单独联调、可被主项目接入的“故障诊断工作区”。

## 功能概览

- 实时监控 Agent 负责接收温度脉冲并判断是否异常
- 深度专家 Agent 在异常时介入，进行多轮诊断
- 聊天区展示真实后端返回的诊断过程
- 诊断完成后自动生成分析报告
- 报告生成后当前任务进入锁定状态，不再继续消耗 token
- 人工处理完成后，可点击“继续工作”重新启动监控

## 目录结构

```text
app/
  agents/        LangGraph 节点与状态
  api/           FastAPI 接口与数据模型
  core/          配置项
  services/      工具函数与报告生成
frontend/
  src/           Vue 页面与组件
tests/
  test_api.py    后端接口回归测试
test_mock.py     本地接口调用示例
```

## 技术栈

### 后端

- `FastAPI`
- `LangGraph`
- `LangChain`
- `langchain-openai`
- OpenAI 兼容模型接口
  - 默认按 `DeepSeek` 配置

### 前端

- `Vue 3`
- `Vite`

## 运行前准备

### 1. Python 环境

项目内已有本地虚拟环境目录：

- `temp_break_ana/`

如果你使用现成环境，可以直接用这个解释器启动。

### 2. 环境变量

根目录 `.env` 需要至少包含：

```env
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
TDI_THRESHOLD=0.15
STABLE_CYCLES=3
MAX_EXPERT_TURNS=5
```

说明：

- `OPENAI_API_BASE` 使用 OpenAI 兼容格式
- 对 `DeepSeek` 来说，`https://api.deepseek.com/v1` 可用

## 启动方式

### 后端

在仓库根目录执行：

```powershell
cd d:\singleproject\breakdown analyse
.\temp_break_ana\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口文档：

- `http://127.0.0.1:8000/docs`

说明：

- 调试阶段建议不要加 `--reload`
- 当前会话状态保存在内存中，热重载会清空任务状态

### 前端

```powershell
cd d:\singleproject\breakdown analyse\frontend
cmd /c npm install
cmd /c npm run dev
```

默认访问地址：

- `http://127.0.0.1:5173`

## 前端运行模式

当前默认是：

- `api-simulated`

含义：

- 页面使用内置模拟脉冲序列
- 但异常分析、聊天内容、报告生成都是真实调用后端接口

也就是说：

- 输入数据：模拟
- 智能体分析：真实
- 报告生成：真实

如果后续接主项目真实脉冲源，只需要替换前端数据输入层即可。

## 核心业务流程

### 1. 初始化任务

前端或主项目调用：

- `POST /v1/analysis/start`

创建一个新的诊断任务。

### 2. 周期推送脉冲

主项目持续调用：

- `POST /v1/analysis/pulse`

输入：

- `task_id`
- `t_predicted`
- `t_actual`
- `status`
- `extra_metrics`

监控 Agent 会基于 TDI 和当前状态判断是否继续、是否需要专家介入。

### 3. 异常时进入诊断

当检测到异常：

- 实时监控 Agent 输出异常摘要
- 深度专家 Agent 进入诊断
- 前端聊天框展示后端真实返回的 `conversation_history`

### 4. 生成报告

当专家诊断完成，前端调用：

- `POST /v1/analysis/report/generate`

后端生成 HTML 报告，并将当前任务标记为：

- `report_ready = true`
- `monitoring_locked = true`
- `conversation_closed = true`

### 5. 锁死与人工恢复

报告生成后：

- 当前任务不再继续分析
- 后续再来的 `pulse` 会被直接短路
- 这样可以避免在人工检修阶段继续浪费 token

人工处理完成后，可调用：

- `POST /v1/analysis/restart`

或者在前端页面点击“继续工作”，重新开始当前任务的监控。

## 关键接口

### `POST /v1/analysis/start`

初始化诊断任务。

### `POST /v1/analysis/pulse`

输入一次监控脉冲，返回：

- 当前是否异常
- 当前最新监控摘要
- 专家状态
- 当前对话历史
- 是否已锁定
- 是否已可下载报告

### `GET /v1/analysis/report/{task_id}`

获取当前任务完整状态，包括：

- 设备信息
- 诊断摘要
- 对话历史
- 历史脉冲
- 报告 HTML

### `POST /v1/analysis/report/generate`

生成分析报告。

### `POST /v1/analysis/restart`

清空当前任务诊断状态，重新开始监控。

## 页面说明

页面分为左右两部分：

- 左侧：主项目占位区
  - 设备信息
  - 温度趋势
- 右侧：故障检测与诊断工作区
  - 实时监控 Agent
  - 深度专家评估聊天区
  - 底部状态条

异常阶段的交互逻辑：

- 聊天消息逐条追加
- 聊天区固定高度，内部滚动
- 诊断完成后出现“下载分析报告”
- 报告生成后出现“继续工作”

## 后端状态字段说明

当前诊断状态中几个关键字段：

- `expert_status`
  - `sleeping`
  - `running`
  - `done`
- `conversation_closed`
  - 表示当前专家会话是否已结束
- `monitoring_locked`
  - 表示当前任务是否已锁定，锁定后不再继续消耗 token
- `report_ready`
  - 表示报告是否已经生成完成

## 测试

运行后端测试：

```powershell
cd d:\singleproject\breakdown analyse
.\temp_break_ana\Scripts\python.exe -m unittest tests.test_api
```

测试覆盖：

- 正常脉冲
- 异常诊断
- 报告生成
- 报告生成后锁死
- 手动重启监控

## 调试日志

后端终端默认输出关键链路日志，包括：

- `start_task received/completed`
- `pulse received`
- `graph invoke started/completed`
- `scout model invoke started/completed`
- `expert model invoke started/completed`
- `generate_report received/completed`

适合排查：

- 前端没有发到后端
- 模型请求慢
- 报告生成卡住
- 会话丢失

## 当前实现边界

这部分只负责故障检测与诊断子模块，不负责主项目左侧真实业务数据源。

当前不负责的内容：

- 设备信息真实接口
- 温度趋势真实接口
- 主项目路由集成
- 持久化存储

当前会话状态仍是：

- 进程内内存存储

如果后续进入多人联调或生产化阶段，建议替换为：

- Redis
- 数据库
- LangGraph 持久化方案

## 后续建议

- 将会话状态从内存迁移到 Redis
- 进一步收严“专家只看请求项补充数据”的上下文输入
- 增加 PDF 导出或打印样式
- 与主项目真实脉冲源和设备信息接口对接

## 适用场景

适合：

- 比赛演示
- 子模块联调
- 主项目移植前的独立验收

不适合直接视为生产版：

- 当前无持久化
- 无鉴权
- 无多实例共享会话
