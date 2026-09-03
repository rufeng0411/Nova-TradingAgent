import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
    closestCenter,
    DndContext,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    type DragEndEvent,
} from '@dnd-kit/core'
import {
    SortableContext,
    arrayMove,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Brain, Clock3, GripVertical, Pause, Play, RotateCcw, Square, Trash2, Zap } from 'lucide-react'

import { api } from '@/services/api'
import type { TaskCenterItem, TaskCenterListResponse } from '@/types'

type TaskActionState = Record<string, boolean>

function statusBadge(item: TaskCenterItem): string {
    if (item.status === 'queued') return 'badge-blue'
    if (item.status === 'paused') return 'badge-yellow'
    if (item.status === 'running') return 'badge-purple'
    if (item.status === 'completed') return 'badge-green'
    return 'badge-red'
}

function statusLabel(item: TaskCenterItem): string {
    if (item.status === 'queued') return '排队中'
    if (item.status === 'paused') return '已暂停'
    if (item.status === 'running') return '执行中'
    if (item.status === 'completed') return '已完成'
    if ((item.error || '').includes('取消')) return '已取消'
    return '失败'
}

function formatTime(value?: string | null): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 19)
}

function taskKindBadge(kind: string): { text: string; cls: string; Icon: typeof Brain } {
    if (kind === 'fast_analysis') {
        return { text: '快速分析', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', Icon: Zap }
    }
    return { text: '智能分析', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', Icon: Brain }
}

function TaskKindChip({ kind, compact = false }: { kind: string; compact?: boolean }) {
    const meta = taskKindBadge(kind)
    return (
        <span className={`inline-flex items-center gap-1 rounded-full ${compact ? 'px-2 py-0.5 text-[11px]' : 'px-2 py-0.5'} ${meta.cls}`}>
            <meta.Icon className="h-3.5 w-3.5" />
            {meta.text}
        </span>
    )
}

function getTaskViewReportLink(item: TaskCenterItem): { to: string; label: string } | null {
    if (item.status === 'running') {
        if (item.task_kind === 'fast_analysis') {
            return {
                to: '/analysis/fast',
                label: '查看报告',
            }
        }
        return {
            to: `/analysis?job_id=${encodeURIComponent(item.job_id)}`,
            label: '查看报告',
        }
    }
    if (item.status === 'completed') {
        const kind = item.task_kind === 'fast_analysis' ? '&kind=fast' : ''
        return {
            to: `/reports?report=${encodeURIComponent(item.job_id)}${kind}`,
            label: '查看报告',
        }
    }
    return null
}

function SortableQueuedRow({
    item,
    actionBusy,
    onPause,
    onResume,
    onCancel,
}: {
    item: TaskCenterItem
    actionBusy: boolean
    onPause: (jobId: string) => void
    onResume: (jobId: string) => void
    onCancel: (jobId: string) => void
}) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.job_id })
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    }
    return (
        <tr
            ref={setNodeRef}
            style={style}
            className={`border-b border-slate-200/70 dark:border-slate-700/70 ${isDragging ? 'bg-blue-50/60 dark:bg-blue-900/20' : ''}`}
        >
            <td className="px-3 py-3 text-center">
                <button
                    className="inline-flex items-center justify-center rounded-md p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 disabled:opacity-40"
                    disabled={actionBusy}
                    aria-label="拖拽排序"
                    {...attributes}
                    {...listeners}
                >
                    <GripVertical className="h-4 w-4" />
                </button>
            </td>
            <td className="px-3 py-3 text-sm font-medium text-slate-800 dark:text-slate-100">{item.task_name}</td>
            <td className="px-3 py-3 text-xs text-slate-500 dark:text-slate-300"><TaskKindChip kind={item.task_kind} /></td>
            <td className="px-3 py-3 text-xs text-slate-500 dark:text-slate-300">{formatTime(item.created_at)}</td>
            <td className="px-3 py-3 text-xs text-slate-500 dark:text-slate-300">{item.description || '-'}</td>
            <td className="px-3 py-3">
                <span className={statusBadge(item)}>{statusLabel(item)}</span>
                {typeof item.waiting_ahead_count === 'number' ? (
                    <p className="mt-1 text-[11px] text-slate-500">前方 {item.waiting_ahead_count} 个</p>
                ) : null}
                {item.task_kind === 'fast_analysis' && item.status === 'queued' ? (
                    <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-300">✨ 已自动插队</p>
                ) : null}
            </td>
            <td className="px-3 py-3">
                <div className="flex items-center gap-2">
                    {item.status === 'queued' ? (
                        <button
                            className="inline-flex items-center gap-1 rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
                            onClick={() => onPause(item.job_id)}
                            disabled={actionBusy}
                        >
                            <Pause className="h-3.5 w-3.5" />
                            暂停
                        </button>
                    ) : (
                        <button
                            className="inline-flex items-center gap-1 rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
                            onClick={() => onResume(item.job_id)}
                            disabled={actionBusy}
                        >
                            <Play className="h-3.5 w-3.5" />
                            继续
                        </button>
                    )}
                    <button
                        className="inline-flex items-center gap-1 rounded border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-950/30"
                        onClick={() => onCancel(item.job_id)}
                        disabled={actionBusy}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                        取消
                    </button>
                </div>
            </td>
        </tr>
    )
}

export default function TaskCenter() {
    const [data, setData] = useState<TaskCenterListResponse>({ running: [], queued: [], recent: [] })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [actionBusyMap, setActionBusyMap] = useState<TaskActionState>({})

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    )

    const queuedIds = useMemo(() => data.queued.map((item) => item.job_id), [data.queued])

    const setBusy = (jobId: string, busy: boolean) => {
        setActionBusyMap((prev) => ({ ...prev, [jobId]: busy }))
    }

    const loadData = useCallback(async () => {
        setError(null)
        try {
            const next = await api.listMyTasks()
            setData(next)
        } catch (e) {
            setError(e instanceof Error ? e.message : '加载任务中心失败')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void loadData()
        const timer = window.setInterval(() => {
            void loadData()
        }, 12000)
        return () => window.clearInterval(timer)
    }, [loadData])

    const onDragEnd = async (event: DragEndEvent) => {
        const { active, over } = event
        if (!over || active.id === over.id) return
        const oldIndex = queuedIds.indexOf(String(active.id))
        const newIndex = queuedIds.indexOf(String(over.id))
        if (oldIndex < 0 || newIndex < 0) return

        const nextQueued = arrayMove(data.queued, oldIndex, newIndex)
        setData((prev) => ({ ...prev, queued: nextQueued }))
        try {
            await api.reorderMyTasks(nextQueued.map((item) => item.job_id))
        } catch (e) {
            setError(e instanceof Error ? e.message : '拖拽排序失败')
            await loadData()
        }
    }

    const pauseTask = async (jobId: string) => {
        setBusy(jobId, true)
        try {
            await api.pauseQueueTask(jobId)
            await loadData()
        } catch (e) {
            setError(e instanceof Error ? e.message : '暂停任务失败')
        } finally {
            setBusy(jobId, false)
        }
    }

    const resumeTask = async (jobId: string) => {
        setBusy(jobId, true)
        try {
            await api.resumeQueueTask(jobId)
            await loadData()
        } catch (e) {
            setError(e instanceof Error ? e.message : '继续任务失败')
        } finally {
            setBusy(jobId, false)
        }
    }

    const cancelTask = async (jobId: string) => {
        setBusy(jobId, true)
        try {
            await api.cancelQueueTask(jobId)
            await loadData()
        } catch (e) {
            setError(e instanceof Error ? e.message : '取消任务失败')
        } finally {
            setBusy(jobId, false)
        }
    }

    const stopRunningTask = async (jobId: string) => {
        setBusy(jobId, true)
        try {
            const resp = await api.cancelAnalysisJob(jobId)
            if (resp.status === 'cancel_requested' || resp.status === 'cancelled') {
                setError(null)
            }
            await loadData()
        } catch (e) {
            setError(e instanceof Error ? e.message : '停止任务失败')
        } finally {
            setBusy(jobId, false)
        }
    }

    const deleteTaskRecord = async (jobId: string, opts?: { stopFirst?: boolean }) => {
        setBusy(jobId, true)
        try {
            if (opts?.stopFirst) {
                try {
                    await api.cancelAnalysisJob(jobId)
                } catch {
                    // 仍继续尝试删除；若任务仍在运行，后端会返回 409。
                }
            }
            await api.deleteTaskRecord(jobId)
            setError(null)
            await loadData()
        } catch (e) {
            const msg = e instanceof Error ? e.message : '删除任务失败'
            if (/409|running|stop first/i.test(msg)) {
                setError('任务仍在停止中，请稍后再删除。')
            } else {
                setError(msg)
            }
        } finally {
            setBusy(jobId, false)
        }
    }

    return (
        <div className="space-y-4">
            <section className="card">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">任务中心</h1>
                        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                            管理智能分析任务排队，支持停止、删除、暂停、继续与拖拽排序。
                        </p>
                    </div>
                    <button
                        className="btn-secondary inline-flex items-center gap-1"
                        onClick={() => void loadData()}
                        disabled={loading}
                    >
                        <RotateCcw className="h-4 w-4" />
                        刷新
                    </button>
                </div>
                {error ? <p className="mt-3 text-sm text-rose-500">{error}</p> : null}
            </section>

            <section className="card">
                <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">执行中任务</h2>
                {loading ? (
                    <p className="text-sm text-slate-500">加载中...</p>
                ) : data.running.length === 0 ? (
                    <p className="text-sm text-slate-500">暂无执行中任务</p>
                ) : (
                    <div className="space-y-2">
                        {data.running.map((item) => {
                            const viewLink = getTaskViewReportLink(item)
                            return (
                            <div key={item.job_id} className="rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-700">
                                <div className="flex items-center gap-2">
                                    <Clock3 className="h-4 w-4 text-blue-500" />
                                    <span className="font-medium text-slate-800 dark:text-slate-100">{item.task_name}</span>
                                    <span className={statusBadge(item)}>{statusLabel(item)}</span>
                                    <TaskKindChip kind={item.task_kind} compact />
                                </div>
                                <p className="mt-1 text-xs text-slate-500">
                                    {item.description || '正在执行深度分析'} | {formatTime(item.updated_at)}
                                </p>
                                <div className="mt-2 flex items-center gap-2">
                                    <button
                                        className="inline-flex items-center gap-1 rounded border border-amber-300 px-2 py-1 text-xs text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-950/30"
                                        onClick={() => void stopRunningTask(item.job_id)}
                                        disabled={Boolean(actionBusyMap[item.job_id])}
                                    >
                                        <Square className="h-3.5 w-3.5" />
                                        停止
                                    </button>
                                    <button
                                        className="inline-flex items-center gap-1 rounded border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-950/30"
                                        onClick={() => void deleteTaskRecord(item.job_id, { stopFirst: true })}
                                        disabled={Boolean(actionBusyMap[item.job_id])}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                        删除
                                    </button>
                                </div>
                                {viewLink ? (
                                    <Link
                                        to={viewLink.to}
                                        className="mt-2 inline-flex text-xs text-blue-600 hover:underline"
                                    >
                                        {viewLink.label}
                                    </Link>
                                ) : null}
                            </div>
                        )})}
                    </div>
                )}
            </section>

            <section className="card overflow-hidden">
                <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">排队任务</h2>
                {data.queued.length === 0 ? (
                    <p className="text-sm text-slate-500">暂无排队任务</p>
                ) : (
                    <div className="overflow-x-auto">
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                            <table className="w-full min-w-[920px] text-left">
                                <thead>
                                    <tr className="border-b border-slate-200 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                                        <th className="px-3 py-2 text-center">排序</th>
                                        <th className="px-3 py-2">任务名称</th>
                                        <th className="px-3 py-2">类别</th>
                                        <th className="px-3 py-2">创建时间</th>
                                        <th className="px-3 py-2">描述</th>
                                        <th className="px-3 py-2">状态</th>
                                        <th className="px-3 py-2">操作</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <SortableContext items={queuedIds} strategy={verticalListSortingStrategy}>
                                        {data.queued.map((item) => (
                                            <SortableQueuedRow
                                                key={item.job_id}
                                                item={item}
                                                actionBusy={Boolean(actionBusyMap[item.job_id])}
                                                onPause={pauseTask}
                                                onResume={resumeTask}
                                                onCancel={cancelTask}
                                            />
                                        ))}
                                    </SortableContext>
                                </tbody>
                            </table>
                        </DndContext>
                    </div>
                )}
            </section>

            <section className="card">
                <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">最近任务</h2>
                {data.recent.length === 0 ? (
                    <p className="text-sm text-slate-500">暂无历史任务</p>
                ) : (
                    <div className="space-y-2">
                        {data.recent.map((item) => {
                            const viewLink = getTaskViewReportLink(item)
                            return (
                            <div key={item.job_id} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-700">
                                <div>
                                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.task_name}</p>
                                    <p className="text-xs text-slate-500">{formatTime(item.updated_at)}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <TaskKindChip kind={item.task_kind} compact />
                                    <span className={statusBadge(item)}>{statusLabel(item)}</span>
                                    {viewLink ? (
                                        <Link
                                            to={viewLink.to}
                                            className="inline-flex items-center gap-1 rounded border border-blue-300 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-950/30"
                                        >
                                            {viewLink.label}
                                        </Link>
                                    ) : null}
                                    <button
                                        className="inline-flex items-center gap-1 rounded border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-950/30 disabled:opacity-60"
                                        onClick={() => void deleteTaskRecord(item.job_id)}
                                        disabled={Boolean(actionBusyMap[item.job_id])}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                        删除
                                    </button>
                                </div>
                            </div>
                        )})}
                    </div>
                )}
            </section>
        </div>
    )
}
