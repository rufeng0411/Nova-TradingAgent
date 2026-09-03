import type { FC, MouseEvent } from 'react'
import type { Node } from '@xyflow/react'
import {
    TrendingUp, MessageCircle, Newspaper, Calculator,
    BarChart2, DollarSign, ArrowBigUp, ArrowBigDown,
    Brain, Briefcase, Flame, Scale, Shield, CheckCircle2,
    Activity,
} from 'lucide-react'
import type { AgentStatus } from '@/types'
import type { Verdict } from '@/utils/reportText'

/** n8n 风格节点类型角标 */
export type N8nWorkflowKind = 'analysis' | 'research' | 'trade' | 'risk' | 'decision'

export interface AgentMeta {
    name: string
    label: string
    goal: string
    section?: string
    debate?: 'research' | 'risk'
    n8nKind: N8nWorkflowKind
    Icon: FC<{ className?: string }>
    badgeBg: string
    badgeText: string
}

export const STATUS_LABEL: Record<AgentStatus, string> = {
    pending: '待命',
    in_progress: '分析中',
    completed: '完成',
    skipped: '跳过',
    error: '异常',
}

export const VERDICT_COLORS: Record<string, string> = {
    '看多': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300',
    '偏多': 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300',
    '中性': 'bg-slate-100 text-slate-500 dark:bg-slate-700/50 dark:text-slate-400',
    '偏空': 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300',
    '看空': 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300',
    '谨慎': 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300',
    _default: 'bg-slate-100 text-slate-500 dark:bg-slate-700/50 dark:text-slate-400',
}

export const META: AgentMeta[] = [
    { name: 'Market Analyst', label: '技术面', goal: '技术指标与价格形态分析', section: 'market_report', n8nKind: 'analysis', Icon: TrendingUp, badgeBg: 'bg-blue-100 dark:bg-blue-500/20', badgeText: 'text-blue-600 dark:text-blue-400' },
    { name: 'Social Analyst', label: '舆情', goal: '舆论情绪与社交媒体分析', section: 'sentiment_report', n8nKind: 'analysis', Icon: MessageCircle, badgeBg: 'bg-fuchsia-100 dark:bg-fuchsia-500/20', badgeText: 'text-fuchsia-600 dark:text-fuchsia-400' },
    { name: 'News Analyst', label: '新闻', goal: '政策资讯与行业动态分析', section: 'news_report', n8nKind: 'analysis', Icon: Newspaper, badgeBg: 'bg-cyan-100 dark:bg-cyan-500/20', badgeText: 'text-cyan-600 dark:text-cyan-400' },
    { name: 'Fundamentals Analyst', label: '基本面', goal: '财务报表与估值分析', section: 'fundamentals_report', n8nKind: 'analysis', Icon: Calculator, badgeBg: 'bg-emerald-100 dark:bg-emerald-500/20', badgeText: 'text-emerald-600 dark:text-emerald-400' },
    { name: 'Macro Analyst', label: '宏观', goal: '板块轮动与政策驱动分析', section: 'macro_report', n8nKind: 'analysis', Icon: BarChart2, badgeBg: 'bg-violet-100 dark:bg-violet-500/20', badgeText: 'text-violet-600 dark:text-violet-400' },
    { name: 'Smart Money Analyst', label: '主力资金', goal: '机构资金行为与龙虎榜', section: 'smart_money_report', n8nKind: 'analysis', Icon: DollarSign, badgeBg: 'bg-amber-100 dark:bg-amber-500/20', badgeText: 'text-amber-600 dark:text-amber-400' },
    { name: 'Volume Price Analyst', label: '量价', goal: '成交量与价格形态分析', section: 'volume_price_report', n8nKind: 'analysis', Icon: Activity, badgeBg: 'bg-rose-100 dark:bg-rose-500/20', badgeText: 'text-rose-600 dark:text-rose-400' },
    { name: 'Bull Researcher', label: '多头', goal: '评估标的基本面与上行空间信息', section: 'investment_plan', debate: 'research', n8nKind: 'research', Icon: ArrowBigUp, badgeBg: 'bg-emerald-100 dark:bg-emerald-500/20', badgeText: 'text-emerald-600 dark:text-emerald-400' },
    { name: 'Bear Researcher', label: '空头', goal: '评估下行风险与潜在危机', section: 'investment_plan', debate: 'research', n8nKind: 'research', Icon: ArrowBigDown, badgeBg: 'bg-rose-100 dark:bg-rose-500/20', badgeText: 'text-rose-600 dark:text-rose-400' },
    { name: 'Research Manager', label: '研究总监', goal: '综合多空论据形成沙盘草案', section: 'investment_plan', debate: 'research', n8nKind: 'research', Icon: Brain, badgeBg: 'bg-indigo-100 dark:bg-indigo-500/20', badgeText: 'text-indigo-600 dark:text-indigo-400' },
    { name: 'Trader', label: '交易员', goal: '将研究结论整理为路径推演草稿（非交易指令）', section: 'trader_investment_plan', n8nKind: 'trade', Icon: Briefcase, badgeBg: 'bg-orange-100 dark:bg-orange-500/20', badgeText: 'text-orange-600 dark:text-orange-400' },
    { name: 'Aggressive Analyst', label: '激进', goal: '风险参数设定', section: 'final_trade_decision', debate: 'risk', n8nKind: 'risk', Icon: Flame, badgeBg: 'bg-red-100 dark:bg-red-500/20', badgeText: 'text-red-600 dark:text-red-400' },
    { name: 'Neutral Analyst', label: '中性', goal: '均衡风险收益策略约束', section: 'final_trade_decision', debate: 'risk', n8nKind: 'risk', Icon: Scale, badgeBg: 'bg-slate-100 dark:bg-slate-500/20', badgeText: 'text-slate-600 dark:text-slate-400' },
    { name: 'Conservative Analyst', label: '稳健', goal: '低风险保守策略约束', section: 'final_trade_decision', debate: 'risk', n8nKind: 'risk', Icon: Shield, badgeBg: 'bg-amber-100 dark:bg-amber-500/20', badgeText: 'text-amber-600 dark:text-amber-400' },
    { name: 'Portfolio Manager', label: '组合经理', goal: '综合裁决形成研判结论', section: 'final_trade_decision', debate: 'risk', n8nKind: 'decision', Icon: CheckCircle2, badgeBg: 'bg-teal-100 dark:bg-teal-500/20', badgeText: 'text-teal-600 dark:text-teal-400' },
]

export const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
    'Market Analyst': { x: 0, y: 0 },
    'Social Analyst': { x: 0, y: 105 },
    'News Analyst': { x: 0, y: 210 },
    'Fundamentals Analyst': { x: 0, y: 315 },
    'Macro Analyst': { x: 0, y: 420 },
    'Smart Money Analyst': { x: 0, y: 525 },
    'Volume Price Analyst': { x: 0, y: 630 },
    'Bull Researcher': { x: 470, y: 80 },
    'Research Manager': { x: 630, y: 240 },
    'Bear Researcher': { x: 470, y: 400 },
    'Trader': { x: 890, y: 240 },
    'Aggressive Analyst': { x: 1180, y: 80 },
    'Neutral Analyst': { x: 1180, y: 240 },
    'Conservative Analyst': { x: 1180, y: 400 },
    'Portfolio Manager': { x: 1470, y: 240 },
}

export const BOTTOM_HANDLE_NODES = new Set(['Bull Researcher'])
export const TOP_HANDLE_NODES = new Set(['Bear Researcher'])

export interface EdgeDef {
    source: string
    target: string
    sourceHandle?: string
    targetHandle?: string
    label?: string
    bidirectional?: boolean
    thin?: boolean
}

export const EDGE_DEFS: EdgeDef[] = [
    ...['Market Analyst', 'Social Analyst', 'News Analyst', 'Fundamentals Analyst', 'Macro Analyst', 'Smart Money Analyst', 'Volume Price Analyst']
        .map((s) => ({ source: s, target: 'Bull Researcher', thin: true } as EdgeDef)),
    ...['Market Analyst', 'Social Analyst', 'News Analyst', 'Fundamentals Analyst', 'Macro Analyst', 'Smart Money Analyst', 'Volume Price Analyst']
        .map((s) => ({ source: s, target: 'Bear Researcher', thin: true } as EdgeDef)),
    { source: 'Bull Researcher', target: 'Bear Researcher', sourceHandle: 'bottom', targetHandle: 'top', label: '辩论', bidirectional: true },
    { source: 'Bull Researcher', target: 'Research Manager' },
    { source: 'Bear Researcher', target: 'Research Manager' },
    { source: 'Research Manager', target: 'Trader', label: '沙盘草案' },
    { source: 'Trader', target: 'Aggressive Analyst' },
    { source: 'Trader', target: 'Neutral Analyst', label: '路径预案摘要' },
    { source: 'Trader', target: 'Conservative Analyst' },
    { source: 'Aggressive Analyst', target: 'Portfolio Manager' },
    { source: 'Neutral Analyst', target: 'Portfolio Manager' },
    { source: 'Conservative Analyst', target: 'Portfolio Manager' },
]

export interface GroupLabelDef {
    id: string
    label: string
    position: { x: number; y: number }
    width: number
    height: number
}

export const GROUP_LABELS: GroupLabelDef[] = [
    { id: 'group-sources', label: '技术分析', position: { x: -16, y: -30 }, width: 248, height: 760 },
    { id: 'group-research', label: '研究团队', position: { x: 454, y: 44 }, width: 410, height: 450 },
    { id: 'group-risk', label: '风控团队', position: { x: 1164, y: 44 }, width: 248, height: 450 },
]

export interface AgentWorkflowCard {
    meta: AgentMeta
    status: AgentStatus
    isStreaming: boolean
    verdict: Verdict | null
    isParticipating: boolean
}

export interface AgentNodeData {
    meta: AgentMeta
    status: AgentStatus
    verdict: Verdict | null
    isParticipating: boolean
    selected: boolean
    [key: string]: unknown
}

export type AgentFlowNode = Node<AgentNodeData, 'agent'>

export interface GroupLabelNodeData {
    label: string
    width: number
    height: number
    [key: string]: unknown
}

export type GroupLabelFlowNode = Node<GroupLabelNodeData, 'groupLabel'>

export type N8nEdgePhase = 'idle' | 'active' | 'completed'

export interface N8nEdgeData extends Record<string, unknown> {
    phase: N8nEdgePhase
    thin?: boolean
    bidirectional?: boolean
}

export interface AgentWorkflowViewProps {
    cards: AgentWorkflowCard[]
    cardMap: Map<string, AgentWorkflowCard>
    doneN: number
    participatingCount: number
    workflowTargetLabel: string
    selectedSection?: string
    handleNodeClick: (event: MouseEvent, node: Node) => void
    isAnalyzing: boolean
    currentHorizon: string | null
}
