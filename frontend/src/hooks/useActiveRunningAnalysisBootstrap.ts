import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/services/api'
import { useAnalysisStore } from '@/stores/analysisStore'
import { resolveExchangeListedSymbol } from '@/utils/stockDisplay'

/** 服务端仍在推进、需要在分析页续订 SSE 的状态 */
const IN_FLIGHT_JOB_STATUSES = new Set(['pending', 'running', 'queued'])

function bindJobFromServer(
    jobId: string,
    symbol: string,
    displayLabel: string | null | undefined,
    status: string,
) {
    const sym = resolveExchangeListedSymbol((symbol || '').trim() || '000001.SH')
        .trim()
        .toUpperCase()
    const isQueued = status === 'queued'
    const display = displayLabel?.trim() || null
    useAnalysisStore.setState((s) => ({
        currentJobId: jobId,
        currentSymbol: sym,
        currentSymbolDisplayName: display || s.currentSymbolDisplayName,
        activeAnalysisJobSymbol: sym,
        activeAnalysisJobDisplayName: display,
        analysisRunState: isQueued ? 'idle' : 'running',
        isAnalyzing: !isQueued,
    }))
}

/**
 * 分析页挂载时（或 URL `job_id` 变化）执行**一次**绑定：
 * - 优先 URL `job_id`；否则若本地无运行态，则从任务中心拉「执行中」任务首条。
 * - 仅当成功绑定到一个新 job 时才 `bumpResume`，让 ChatCopilot 的恢复 effect 续订 SSE。
 * - 不再以固定间隔轮询；ChatCopilot 内部有「健康守护 + 队列监视」承担后续恢复。
 *
 * 注意：此 hook 不会与 chat 主 SSE 流并发开第二条流——ChatCopilot 在 streamActiveRef
 * 上做了守卫，bumpResume 仅推动状态机评估，不会立即再开流。
 */
export function useActiveRunningAnalysisBootstrap(opts: { bumpResume: () => void }) {
    const [searchParams] = useSearchParams()
    const { bumpResume } = opts
    const lastBootstrapKey = useRef<string>('')

    useEffect(() => {
        let cancelled = false
        const run = async () => {
            const urlJob = searchParams.get('job_id')?.trim()
            if (urlJob) {
                if (lastBootstrapKey.current === `url:${urlJob}`) return
                try {
                    const st = await api.getJobStatus(urlJob)
                    if (cancelled) return
                    if (!IN_FLIGHT_JOB_STATUSES.has(st.status)) return
                    lastBootstrapKey.current = `url:${urlJob}`
                    bindJobFromServer(urlJob, st.symbol, st.display_label, st.status)
                    bumpResume()
                } catch {
                    /* 404 等：忽略 */
                }
                return
            }

            const { currentJobId, analysisRunState, isAnalyzing } = useAnalysisStore.getState()
            const localLooksRunning =
                Boolean(currentJobId) &&
                (analysisRunState === 'running' || (isAnalyzing && analysisRunState !== 'completed' && analysisRunState !== 'failed'))

            if (localLooksRunning) {
                if (lastBootstrapKey.current !== `local:${currentJobId}`) {
                    lastBootstrapKey.current = `local:${currentJobId}`
                    bumpResume()
                }
                return
            }

            try {
                const tasks = await api.listMyTasks()
                if (cancelled) return
                const runItem = tasks.running[0]
                if (!runItem?.job_id) return
                if (lastBootstrapKey.current === `server:${runItem.job_id}`) return
                const st = await api.getJobStatus(runItem.job_id)
                if (cancelled) return
                if (!IN_FLIGHT_JOB_STATUSES.has(st.status)) return
                lastBootstrapKey.current = `server:${runItem.job_id}`
                const sym = (runItem.symbol || st.symbol || '').trim()
                bindJobFromServer(runItem.job_id, sym, st.display_label, st.status)
                bumpResume()
            } catch {
                /* 未登录等 */
            }
        }

        void run()
        return () => {
            cancelled = true
        }
    }, [searchParams, bumpResume])
}
