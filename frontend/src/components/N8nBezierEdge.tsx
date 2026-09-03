import { memo } from 'react'
import {
    BaseEdge,
    EdgeLabelRenderer,
    getBezierPath,
    type EdgeProps,
} from '@xyflow/react'
import type { N8nEdgeData, N8nEdgePhase } from '@/components/agentWorkflowModel'

function phaseStroke(phase: N8nEdgePhase): string {
    if (phase === 'completed') return 'rgb(52 211 153)'
    if (phase === 'active') return 'rgb(59 130 246)'
    return 'rgb(148 163 184)'
}

export const N8nBezierEdge = memo(function N8nBezierEdge(props: EdgeProps) {
    const {
        id,
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
        markerEnd,
        markerStart,
        data,
        label,
    } = props

    const edgeData = data as N8nEdgeData | undefined
    const phase: N8nEdgePhase = edgeData?.phase ?? 'idle'
    const thin = !!edgeData?.thin

    const [edgePath, labelX, labelY] = getBezierPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
    })

    const stroke = phaseStroke(phase)
    const opacity = phase === 'idle' ? (thin ? 0.28 : 0.38) : phase === 'completed' ? 0.72 : 0.95

    const pathClass =
        phase === 'active'
            ? 'workflow-n8n-edge-path workflow-n8n-edge-path--active'
            : phase === 'completed'
              ? 'workflow-n8n-edge-path workflow-n8n-edge-path--done'
              : 'workflow-n8n-edge-path'

    return (
        <>
            <BaseEdge
                id={id}
                path={edgePath}
                className={pathClass}
                style={{
                    stroke,
                    strokeWidth: thin ? 1 : 1.5,
                    strokeDasharray: '8 6',
                    strokeLinecap: 'round',
                    opacity,
                    fill: 'none',
                }}
                markerEnd={markerEnd}
                markerStart={markerStart}
            />
            {label != null && label !== '' && (
                <EdgeLabelRenderer>
                    <div
                        className="workflow-n8n-edge-label nodrag nopan"
                        style={{
                            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
                        }}
                    >
                        {label}
                    </div>
                </EdgeLabelRenderer>
            )}
        </>
    )
})
