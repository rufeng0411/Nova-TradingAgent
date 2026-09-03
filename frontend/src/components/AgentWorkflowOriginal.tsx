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
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CheckCircle2, Loader2 } from 'lucide-react'
import {
    BOTTOM_HANDLE_NODES,
    TOP_HANDLE_NODES,
    EDGE_DEFS,
    GROUP_LABELS,
    NODE_POSITIONS,
    STATUS_LABEL,
    VERDICT_COLORS,
    type AgentFlowNode,
    type AgentNodeData,
    type AgentWorkflowViewProps,
    type GroupLabelFlowNode,
    type GroupLabelNodeData,
} from '@/components/agentWorkflowModel'

function AgentNodeComponent({ data }: NodeProps<AgentFlowNode>) {
    const { meta, status, verdict, isParticipating, selected } = data
    const active = status === 'in_progress'
    const done = status === 'completed'
    const skipped = status === 'skipped'
    const { Icon } = meta

    return (
        <div
            className={[
                'px-4 py-3 rounded-xl border transition-all duration-300 min-w-[210px] max-w-[218px]',
                !isParticipating ? 'opacity-30 grayscale' : '',
                selected
                    ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-500/10 shadow-lg ring-2 ring-blue-400/30'
                    : active
                      ? 'border-blue-400 dark:border-blue-500/60 bg-white dark:bg-slate-800 shadow-[0_0_14px_rgba(59,130,246,0.25)]'
                      : done
                        ? 'border-emerald-300 dark:border-emerald-500/50 bg-white dark:bg-slate-800/80 shadow-sm'
                        : skipped
                          ? 'border-slate-100 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 opacity-40'
                          : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm',
            ].join(' ')}
        >
            <Handle
                type="target"
                position={Position.Left}
                id="left"
                className="!w-2 !h-2 !bg-slate-300 dark:!bg-slate-600 !border-0 !min-w-0 !min-h-0"
            />
            <Handle
                type="source"
                position={Position.Right}
                id="right"
                className="!w-2 !h-2 !bg-slate-300 dark:!bg-slate-600 !border-0 !min-w-0 !min-h-0"
            />

            {BOTTOM_HANDLE_NODES.has(meta.name) && (
                <Handle
                    type="source"
                    position={Position.Bottom}
                    id="bottom"
                    className="!w-2 !h-2 !bg-slate-300 dark:!bg-slate-600 !border-0 !min-w-0 !min-h-0"
                />
            )}
            {TOP_HANDLE_NODES.has(meta.name) && (
                <Handle
                    type="target"
                    position={Position.Top}
                    id="top"
                    className="!w-2 !h-2 !bg-slate-300 dark:!bg-slate-600 !border-0 !min-w-0 !min-h-0"
                />
            )}

            <div className="flex items-center gap-2.5">
                <div className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${meta.badgeBg}`}>
                    {active ? (
                        <Loader2 className={`w-[18px] h-[18px] animate-spin ${meta.badgeText}`} />
                    ) : (
                        <Icon className={`w-[18px] h-[18px] ${meta.badgeText}`} />
                    )}
                </div>
                <span
                    className={`text-[15px] font-bold flex-1 leading-tight ${active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-800 dark:text-slate-200'}`}
                >
                    {meta.label}
                </span>
                <span
                    className={[
                        'shrink-0 text-[11px] px-2 py-0.5 rounded-full font-bold',
                        active
                            ? 'bg-blue-600 text-white animate-pulse'
                            : done
                              ? 'bg-emerald-500 text-white'
                              : 'bg-slate-100 text-slate-400 dark:bg-slate-700 dark:text-slate-500',
                    ].join(' ')}
                >
                    {STATUS_LABEL[status]}
                </span>
            </div>

            {active && (
                <div className="flex items-center gap-2 mt-2">
                    <span className="flex gap-1">
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" />
                    </span>
                    <span className="text-[12px] text-blue-600 dark:text-blue-400 font-bold">研判中...</span>
                </div>
            )}

            {done && verdict && (
                <div className="flex items-start gap-2 mt-2 min-w-0">
                    <span
                        className={`shrink-0 mt-0.5 text-[11px] font-black px-2 py-0.5 rounded-full leading-none ${VERDICT_COLORS[verdict.direction] ?? VERDICT_COLORS._default}`}
                    >
                        {verdict.direction}
                    </span>
                    <span className="text-[12px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-2">
                        {verdict.reason}
                    </span>
                </div>
            )}

            {done && !verdict && (
                <div className="flex items-center gap-1.5 mt-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span className="text-[12px] text-emerald-600 dark:text-emerald-400 font-bold">完成</span>
                </div>
            )}
        </div>
    )
}

function GroupLabelNode({ data }: NodeProps<GroupLabelFlowNode>) {
    return (
        <div
            className="rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700/60 pointer-events-none"
            style={{ width: data.width, height: data.height }}
        >
            <div className="absolute -top-3 left-4 px-2 bg-white dark:bg-slate-900">
                <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                    {data.label}
                </span>
            </div>
        </div>
    )
}

const nodeTypes: NodeTypes = {
    agent: memo(AgentNodeComponent),
    groupLabel: memo(GroupLabelNode),
}

export default function AgentWorkflowOriginal({
    cards,
    cardMap,
    selectedSection,
    handleNodeClick,
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

            const color = sourceDone ? '#10b981' : targetActive ? '#3b82f6' : '#cbd5e1'

            return {
                id: `e-${i}`,
                source: def.source,
                target: def.target,
                sourceHandle: def.sourceHandle ?? 'right',
                targetHandle: def.targetHandle ?? 'left',
                type: 'default',
                animated: targetActive,
                label: def.label,
                labelStyle: { fontSize: 10, fontWeight: 600, fill: '#64748b' },
                labelBgStyle: { fill: 'white', fillOpacity: 0.85 },
                labelBgPadding: [4, 2] as [number, number],
                labelBgBorderRadius: 4,
                style: {
                    stroke: color,
                    strokeWidth: def.thin ? 1 : 1.5,
                    opacity: def.thin ? 0.6 : 1,
                },
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color,
                    width: 16,
                    height: 16,
                },
                ...(def.bidirectional && {
                    markerStart: {
                        type: MarkerType.ArrowClosed,
                        color,
                        width: 16,
                        height: 16,
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

    return (
        <div className="agent-collab-flow min-h-[720px] h-[min(920px,calc(100vh-10rem))] w-full touch-pan-y">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
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
                    className="!bg-white/90 dark:!bg-slate-800/90 !border-slate-200 dark:!border-slate-600 !shadow-md"
                />
            </ReactFlow>
        </div>
    )
}
