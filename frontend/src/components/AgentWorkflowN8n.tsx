import { memo, useMemo, useCallback, type MouseEvent } from 'react'
import {
    ReactFlow,
    Controls,
    Handle,
    Position,
    MarkerType,
    type Node,
    type Edge,
    type NodeProps,
    type NodeTypes,
    type EdgeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react'
import {
    BOTTOM_HANDLE_NODES,
    TOP_HANDLE_NODES,
    EDGE_DEFS,
    GROUP_LABELS,
    NODE_POSITIONS,
    VERDICT_COLORS,
    type AgentFlowNode,
    type AgentNodeData,
    type AgentWorkflowViewProps,
    type GroupLabelFlowNode,
    type GroupLabelNodeData,
    type N8nEdgeData,
    type N8nEdgePhase,
} from '@/components/agentWorkflowModel'
import type { AgentStatus } from '@/types'
import { N8nBezierEdge } from '@/components/N8nBezierEdge'

const N8N_STATUS_FOOTER: Record<AgentStatus, string> = {
    pending: '待命',
    in_progress: '研判中',
    completed: '完成',
    skipped: '跳过',
    error: '异常',
}

function N8nAgentNode({ data }: NodeProps<AgentFlowNode>) {
    const { meta, status, verdict, isParticipating, selected } = data
    const active = status === 'in_progress'
    const done = status === 'completed'
    const { Icon } = meta

    return (
        <div
            className="workflow-n8n-node nodrag"
            data-status={status}
            data-selected={selected ? 'true' : 'false'}
            data-participating={isParticipating ? 'true' : 'false'}
            data-tone={meta.n8nKind}
        >
            <Handle
                type="target"
                position={Position.Left}
                id="left"
                className="!w-2 !h-2 !border-0 !min-w-0 !min-h-0 !bg-slate-400/80 dark:!bg-slate-500"
            />
            <Handle
                type="source"
                position={Position.Right}
                id="right"
                className="!w-2 !h-2 !border-0 !min-w-0 !min-h-0 !bg-slate-400/80 dark:!bg-slate-500"
            />
            {BOTTOM_HANDLE_NODES.has(meta.name) && (
                <Handle
                    type="source"
                    position={Position.Bottom}
                    id="bottom"
                    className="!w-2 !h-2 !border-0 !min-w-0 !min-h-0 !bg-slate-400/80 dark:!bg-slate-500"
                />
            )}
            {TOP_HANDLE_NODES.has(meta.name) && (
                <Handle
                    type="target"
                    position={Position.Top}
                    id="top"
                    className="!w-2 !h-2 !border-0 !min-w-0 !min-h-0 !bg-slate-400/80 dark:!bg-slate-500"
                />
            )}

            <div className="flex items-start gap-2">
                <div className={`workflow-n8n-node-icon ${meta.badgeBg}`}>
                    {active ? (
                        <Loader2 className={`h-[18px] w-[18px] animate-spin ${meta.badgeText}`} />
                    ) : (
                        <Icon className={`h-[18px] w-[18px] ${meta.badgeText}`} />
                    )}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5">
                        <span className="rounded border border-slate-200/80 bg-slate-50/90 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wide text-slate-500 dark:border-slate-600 dark:bg-slate-800/80 dark:text-slate-400">
                            {meta.n8nKind}
                        </span>
                    </div>
                    <div
                        className={`text-[14px] font-black leading-tight tracking-tight ${active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-800 dark:text-slate-100'}`}
                    >
                        {meta.label}
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] font-medium leading-snug text-slate-500 dark:text-slate-400">
                        {meta.goal}
                    </p>
                </div>
            </div>

            {active && (
                <div className="mt-2 flex items-center gap-2">
                    <span className="flex gap-1">
                        <span className="workflow-n8n-pulse-dot" />
                        <span className="workflow-n8n-pulse-dot" />
                        <span className="workflow-n8n-pulse-dot" />
                    </span>
                    <span className="text-[11px] font-bold text-blue-600 dark:text-blue-400">流式输出中</span>
                </div>
            )}

            {done && verdict && (
                <div className="mt-2 flex min-w-0 flex-col gap-1">
                    <span
                        className={`w-fit text-[11px] font-black px-2 py-0.5 rounded-full leading-none ${VERDICT_COLORS[verdict.direction] ?? VERDICT_COLORS._default}`}
                    >
                        {verdict.direction}
                    </span>
                    <span className="line-clamp-2 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                        {verdict.reason}
                    </span>
                </div>
            )}

            {done && !verdict && (
                <div className="mt-2 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                    <span className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400">段落已生成</span>
                </div>
            )}

            <div className="workflow-n8n-node-footer">
                <span className="tabular-nums">{N8N_STATUS_FOOTER[status]}</span>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden />
            </div>
        </div>
    )
}

function N8nGroupLabelNode({ data }: NodeProps<GroupLabelFlowNode>) {
    return (
        <div
            className="workflow-n8n-group pointer-events-none relative"
            style={{ width: data.width, height: data.height }}
        >
            <span className="workflow-n8n-group-title">{data.label}</span>
        </div>
    )
}

const nodeTypes: NodeTypes = {
    agent: memo(N8nAgentNode),
    groupLabel: memo(N8nGroupLabelNode),
}

const edgeTypes: EdgeTypes = {
    n8nBezier: N8nBezierEdge,
}

function edgePhase(sourceDone: boolean, targetActive: boolean): N8nEdgePhase {
    if (sourceDone) return 'completed'
    if (targetActive) return 'active'
    return 'idle'
}

function phaseStrokeForMarker(phase: N8nEdgePhase): string {
    if (phase === 'completed') return '#34d399'
    if (phase === 'active') return '#3b82f6'
    return '#94a3b8'
}

export default function AgentWorkflowN8n({
    cards,
    cardMap,
    doneN,
    participatingCount,
    workflowTargetLabel,
    selectedSection,
    handleNodeClick,
    isAnalyzing,
    currentHorizon,
}: AgentWorkflowViewProps) {
    const nodes: (AgentFlowNode | GroupLabelFlowNode)[] = useMemo(() => {
        const agentNodes: AgentFlowNode[] = cards.map((card) => ({
            id: card.meta.name,
            type: 'agent',
            position: NODE_POSITIONS[card.meta.name] ?? { x: 0, y: 0 },
            data: {
                meta: card.meta,
                status: card.status,
                verdict: card.verdict,
                isParticipating: card.isParticipating,
                selected: !!card.meta.section && card.meta.section === selectedSection,
            } satisfies AgentNodeData,
        }))

        const labelNodes: GroupLabelFlowNode[] = GROUP_LABELS.map((g) => ({
            id: g.id,
            type: 'groupLabel',
            position: g.position,
            data: { label: g.label, width: g.width, height: g.height } satisfies GroupLabelNodeData,
            selectable: false,
            draggable: false,
            zIndex: -1,
        }))

        return [...labelNodes, ...agentNodes]
    }, [cards, selectedSection])

    const edges: Edge[] = useMemo(() => {
        return EDGE_DEFS.map((def, i) => {
            const sourceCard = cardMap.get(def.source)
            const targetCard = cardMap.get(def.target)
            const sourceDone = sourceCard?.status === 'completed'
            const targetActive = targetCard?.status === 'in_progress'
            const phase = edgePhase(!!sourceDone, !!targetActive)
            const stroke = phaseStrokeForMarker(phase)

            const edgeData: N8nEdgeData = {
                phase,
                thin: def.thin,
                bidirectional: def.bidirectional,
            }

            return {
                id: `e-n8n-${i}`,
                source: def.source,
                target: def.target,
                sourceHandle: def.sourceHandle ?? 'right',
                targetHandle: def.targetHandle ?? 'left',
                type: 'n8nBezier',
                label: def.label,
                data: edgeData,
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: stroke,
                    width: 14,
                    height: 14,
                },
                ...(def.bidirectional && {
                    markerStart: {
                        type: MarkerType.ArrowClosed,
                        color: stroke,
                        width: 14,
                        height: 14,
                    },
                }),
            } satisfies Edge
        })
    }, [cardMap])

    const onNodeClick = useCallback(
        (e: MouseEvent, node: Node) => {
            handleNodeClick(e, node)
        },
        [handleNodeClick],
    )

    const pct = participatingCount > 0 ? Math.round((doneN / participatingCount) * 100) : 0
    const activeAgentLabel = cards.find((c) => c.status === 'in_progress')?.meta.label

    const runStatus = isAnalyzing
        ? '分析中'
        : participatingCount > 0 && doneN >= participatingCount
          ? '已完成'
          : '待命'

    return (
        <div className="workflow-n8n-shell">
            <div className="workflow-n8n-hud">
                <span
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${
                        isAnalyzing
                            ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                            : 'border-slate-200/70 bg-slate-50/80 text-slate-500 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-400'
                    }`}
                >
                    <span
                        className={`h-1.5 w-1.5 rounded-full ${isAnalyzing ? 'animate-pulse bg-emerald-500 shadow-[0_0_8px_#10b981]' : 'bg-slate-300 dark:bg-slate-600'}`}
                    />
                    {isAnalyzing ? 'Active' : 'Idle'}
                </span>
                <div className="min-w-0 flex flex-1 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
                    <span className="text-sm font-black tracking-tight text-slate-900 dark:text-white">
                        多智能体工作流
                    </span>
                    <span className="truncate text-[12px] font-semibold text-slate-500 dark:text-slate-400 tabular-nums">
                        {workflowTargetLabel}
                    </span>
                </div>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                    {isAnalyzing && currentHorizon && (
                        <span
                            className={`rounded-full border px-2.5 py-0.5 text-[10px] font-black tracking-widest ${
                                currentHorizon === 'short'
                                    ? 'border-blue-400/30 bg-blue-600/10 text-blue-600 dark:text-blue-400'
                                    : 'border-purple-400/30 bg-purple-600/10 text-purple-600 dark:text-purple-400'
                            }`}
                        >
                            {currentHorizon === 'short' ? '短线' : '中线'}
                        </span>
                    )}
                    <div className="text-right">
                        <div className="text-lg font-black tabular-nums text-blue-600 dark:text-blue-400">
                            {doneN}/{participatingCount} · {pct}%
                        </div>
                        <p className="text-[9px] font-bold uppercase tracking-tight text-slate-400">进度</p>
                    </div>
                </div>
            </div>

            <div className="workflow-n8n-canvas agent-collab-flow min-h-[720px] h-[min(920px,calc(100vh-10rem))] w-full touch-pan-y">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    onNodeClick={onNodeClick}
                    defaultViewport={{ x: 20, y: 10, zoom: 0.92 }}
                    minZoom={0.35}
                    maxZoom={1.85}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    nodesFocusable={false}
                    edgesFocusable={false}
                    panOnDrag
                    zoomOnScroll
                    zoomOnPinch
                    zoomOnDoubleClick
                    preventScrolling={false}
                    translateExtent={[[-120, -100], [1920, 920]]}
                    proOptions={{ hideAttribution: true }}
                >
                    <Controls
                        showInteractive={false}
                        position="top-right"
                        className="!m-2 !bg-white/85 dark:!bg-slate-900/80 !border-slate-200/80 dark:!border-slate-600 !shadow-md !backdrop-blur"
                    />
                </ReactFlow>
            </div>

            <div className="workflow-n8n-footer">
                <span>
                    节点 <span className="tabular-nums text-slate-700 dark:text-slate-200">{cards.length}</span>
                </span>
                <span>
                    连接 <span className="tabular-nums text-slate-700 dark:text-slate-200">{EDGE_DEFS.length}</span>
                </span>
                <span>
                    运行 <span className="text-slate-800 dark:text-slate-100">{runStatus}</span>
                </span>
                {activeAgentLabel && (
                    <span className="min-w-0 truncate">
                        当前 <span className="text-blue-600 dark:text-blue-400">{activeAgentLabel}</span>
                    </span>
                )}
            </div>
        </div>
    )
}
