/**
 * 智能分析 — 容错与断点续传（前端策略）
 *
 * ## 断点续传锚点
 * - 以服务端 `job_id` 为唯一锚：`job.ready` 即写入 `currentJobId`，与 `/v1/jobs/:id/events` 同源。
 * - 刷新/断网后：先 `GET /v1/jobs/:id` 判终态；未完成则 `GET .../events` 续订直至 `done`。
 * - **服务端事件日志**：持久化 `job_events`，SSE 带 `id:`；续订时传 `?after=` 或 `Last-Event-ID` 可回放历史，再衔接实时流。
 * - 前端在 zustand 中持久化 `lastEventIdByJob[job_id]`，与上述 cursor 对齐。
 * - LangGraph 默认使用 SQLite checkpoint（`LANGGRAPH_CHECKPOINTER=sqlite`），API 重启后可从 thread_id（job_id / job_id_horizon）继续。
 *
 * ## 容错原则
 * - 主 `fetch` SSE body **提前结束** ≠ 任务失败：须走「续订 events → 轮询 result」。
 * - 重试时**禁止** `reset()` 清空 `currentJobId`，避免重复排队与伪超时。
 * - 网络类错误才触发「静默恢复」；业务 4xx 不重试盲等。
 */

/** 主聊天 SSE 自动重试次数（含首轮） */
export const CHAT_STREAM_MAX_ATTEMPTS = 3

/** 第 n 次重试前等待（ms），n 从 2 起：与历史行为 500*attempt 对齐 */
export function chatStreamRetryDelayMs(attemptIndex: number): number {
    if (attemptIndex < 2) return 0
    return 500 * attemptIndex
}

/** 续订 job events 前短延迟，降低 job 尚未写入 store 的 404 竞态 */
export const JOB_RESUME_PRE_POLL_DELAY_MS = 250

/** 页面挂载恢复前短延迟 */
export const MOUNT_RESUME_PRE_POLL_DELAY_MS = 300

/** 任务完成态轮询：最大轮数 × 间隔（总约 12s 级，可按需调大） */
export const JOB_COMPLETION_POLL_MAX_ROUNDS = 8
export const JOB_COMPLETION_POLL_INTERVAL_MS = 1500

/** localStorage 持久化：单 job 流式片段总预算（字符） */
export const PERSIST_STREAMING_CHAR_BUDGET = 120_000

/** 辩论消息每 key 最多保留条数 */
export const PERSIST_DEBATE_MESSAGES_PER_KEY = 48

/** 可识别的 agent 列表最小长度（防损坏 JSON 误合并） */
export const PERSIST_MIN_AGENT_COUNT = 10

/** 是否像网络 / 流中断类错误（用于是否走 recover 分支） */
export function isLikelyNetworkOrStreamError(message: string): boolean {
    return /network|fetch|stream|sse|body|aborted|timeout|failed to fetch|load failed/i.test(message)
}
