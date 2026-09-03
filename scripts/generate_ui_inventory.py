"""Generate docs/ui-inventory.csv per plan §7.1 columns."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "ui-inventory.csv"

HEADERS = [
    "id",
    "route",
    "level",
    "parent_id",
    "feature",
    "subfeature",
    "interaction",
    "motion",
    "chart_or_kline",
    "data_source",
    "source_file",
    "gap_note",
]


def rows() -> list[list[str]]:
    r: list[list[str]] = []

    def add(*cols: str) -> None:
        assert len(cols) == len(HEADERS)
        r.append(list(cols))

    # --- global / shell ---
    add(
        "G-AUTH-01",
        "global",
        "L0壳层",
        "",
        "RequireAuth",
        "hydrate gate",
        "未 hydrated 时阻塞子树；完成后允许 Layout",
        "静态居中文案",
        "无",
        "authStore hydrate",
        "frontend/src/App.tsx",
        "",
    )
    add(
        "G-LAYOUT-01",
        "global",
        "L0壳层",
        "",
        "Layout",
        "Sidebar+Header+main",
        "主路由出口渲染当前页",
        "无",
        "无",
        "N/A",
        "frontend/src/components/Layout.tsx",
        "",
    )
    add(
        "G-SIDE-01",
        "global",
        "L2页内分区",
        "",
        "Sidebar",
        "悬停展开窄条",
        "mouseEnter/Leave 切换 isExpanded；NavLink 跳转",
        "aside w-16↔w-48 transition-all duration-300",
        "无",
        "N/A; navItems×7",
        "frontend/src/components/Sidebar.tsx; sidebarNav.ts",
        "",
    )
    add(
        "G-SIDE-02",
        "global",
        "L2页内分区",
        "G-SIDE-01",
        "Sidebar",
        "构建版本脚注",
        "展开后显示 __APP_BUILD_*",
        "无",
        "无",
        "vite define; __APP_BUILD__*",
        "frontend/src/components/Sidebar.tsx",
        "",
    )
    add(
        "G-HEAD-01",
        "global",
        "L2页内分区",
        "",
        "Header",
        "公告铃铛",
        "点击切换下拉；读 localStorage 未读标记",
        "backdrop-blur；Chevron",
        "无",
        "GET /v1/announcements/latest",
        "frontend/src/components/Header.tsx",
        "",
    )
    add(
        "G-HEAD-02",
        "global",
        "L2页内分区",
        "",
        "Header",
        "主题循环",
        "点击 cycleTheme system→light→dark；写 ta-theme",
        "ThemeIcon 切换",
        "无",
        "localStorage ta-theme",
        "frontend/src/components/Header.tsx",
        "",
    )
    add(
        "G-HEAD-03",
        "global",
        "L2页内分区",
        "",
        "Header",
        "浏览器通知",
        "请求 Notification 权限",
        "无",
        "无",
        "Notification API",
        "frontend/src/components/Header.tsx",
        "",
    )
    add(
        "G-HEAD-04",
        "global",
        "L2页内分区",
        "",
        "Header",
        "用户菜单",
        "GitHub/赞助/致谢/登出/我的报告/设置",
        "下拉；外链",
        "无",
        "mixed",
        "frontend/src/components/Header.tsx",
        "",
    )
    add(
        "G-GAP-404",
        "global",
        "L1页面",
        "",
        "路由缺口",
        "未匹配内层 path",
        "内层 Routes 无 path=*；未知子路径主区可能空白",
        "无",
        "无",
        "N/A",
        "frontend/src/App.tsx",
        "已知缺口见 docs/page-structure.md §1",
    )
    add(
        "G-GAP-RECHARTS",
        "global",
        "L0壳层",
        "",
        "依赖未使用",
        "recharts",
        "package.json 声明但 src 无 import",
        "无",
        "无",
        "N/A",
        "frontend/package.json",
        "技术债；与 page-structure 缺口一致",
    )

    # --- login ---
    add(
        "L-01",
        "/login",
        "L1页面",
        "",
        "Login",
        "用户名/邮箱 + 密码（无图形验证码）",
        "提交→api.login；成功 replace /analysis；链到注册/忘记密码",
        "Loader2 animate-spin",
        "无",
        "POST /v1/auth/login",
        "frontend/src/pages/Login.tsx",
        "",
    )
    add(
        "L-02",
        "/login",
        "L2页内分区",
        "L-01",
        "Login",
        "左侧产品说明",
        "只读；外链 GitHub",
        "无",
        "无",
        "N/A",
        "frontend/src/pages/Login.tsx",
        "",
    )

    # sponsor thanks
    add(
        "SP-01",
        "/sponsor",
        "L1页面",
        "",
        "Sponsor",
        "ExternalRedirect",
        "非 app.510168.xyz 整页跳转线上",
        "无",
        "无",
        "window.location",
        "frontend/src/App.tsx; pages/Sponsor.tsx",
        "",
    )
    add(
        "TH-01",
        "/thanks",
        "L1页面",
        "",
        "Thanks",
        "致谢名单与外链",
        "hover 卡片 transition；头像 ring scale",
        "transition-colors；group-hover scale-110",
        "无",
        "GET /v1/sponsors",
        "frontend/src/pages/Thanks.tsx",
        "",
    )

    # dashboard
    add(
        "D-01",
        "/",
        "L1页面",
        "",
        "Dashboard",
        "错误条",
        "API 失败时展示 dashboardError",
        "无",
        "无",
        "GET /v1/reports; GET /v1/dashboard/tracking-board",
        "frontend/src/pages/Dashboard.tsx",
        "",
    )
    add(
        "D-02",
        "/",
        "L2页内分区",
        "",
        "Dashboard",
        "四格 StatCard",
        "只读展示 agents/isAnalyzing/reportTotal",
        "无",
        "无",
        "useAnalysisStore；api.getReports",
        "frontend/src/pages/Dashboard.tsx",
        "",
    )
    add(
        "D-03",
        "/",
        "L2页内分区",
        "",
        "Dashboard",
        "跟踪摘要",
        "点击进入 /tracking-board",
        "hover transition-colors",
        "无",
        "GET /v1/dashboard/tracking-board",
        "frontend/src/pages/Dashboard.tsx",
        "",
    )
    add(
        "D-04",
        "/",
        "L2页内分区",
        "",
        "Dashboard",
        "快速开始三卡",
        "导航 /analysis /reports /settings",
        "hover border transition-all duration-200",
        "无",
        "N/A",
        "frontend/src/pages/Dashboard.tsx",
        "",
    )
    add(
        "D-05",
        "/",
        "L2页内分区",
        "",
        "Dashboard",
        "最近分析列表",
        "行点击 navigate /reports?report=id",
        "row hover transition-colors",
        "无",
        "GET /v1/reports",
        "frontend/src/pages/Dashboard.tsx",
        "",
    )

    # analysis
    add(
        "A-CHAT-01",
        "/analysis",
        "L2页内分区",
        "",
        "ChatCopilotPanel",
        "输入与发送",
        "submit 流式 fetch /v1/chat/completions；scrollTo 底部",
        "streaming 状态；Loader2",
        "无",
        "POST /v1/chat/completions (SSE)",
        "frontend/src/components/ChatCopilotPanel.tsx",
        "",
    )
    add(
        "A-CHAT-02",
        "/analysis",
        "L3组件内子状态",
        "A-CHAT-01",
        "ChatCopilotPanel",
        "章节卡片/清空",
        "选择章节联动 ReportViewer；清空对话",
        "无",
        "无",
        "analysisStore；api",
        "frontend/src/components/ChatCopilotPanel.tsx",
        "",
    )
    add(
        "A-KL-01",
        "/analysis",
        "L2页内分区",
        "",
        "KlinePanel",
        "蜡烛图主图",
        "crosshair 移动更新 OHLC；resize 自适应",
        "MutationObserver 主题；图表库内部动画",
        "lightweight-charts CandlestickSeries",
        "GET /v1/market/kline",
        "frontend/src/components/KlinePanel.tsx",
        "",
    )
    add(
        "A-KL-02",
        "/analysis",
        "L4组件内子状态",
        "A-KL-01",
        "KlinePanel",
        "指数预设按钮",
        "切换标的触发重新拉取",
        "button hover",
        "同上",
        "GET /v1/market/kline",
        "frontend/src/components/KlinePanel.tsx",
        "",
    )
    add(
        "A-KL-03",
        "/analysis?symbol=",
        "L4组件内子状态",
        "",
        "Analysis",
        "URL 查询参数",
        "symbol 同步 activeSymbol 与 initialChatInput",
        "无",
        "无",
        "N/A",
        "frontend/src/pages/Analysis.tsx",
        "",
    )
    add(
        "A-FLOW-01",
        "/analysis",
        "L2页内分区",
        "",
        "AgentCollaboration",
        "ReactFlow 协作图",
        "拖拽画布；节点点击→辩论抽屉；选中章节",
        "React Flow 默认平移缩放",
        "@xyflow/react 拓扑",
        "job events / analysisStore",
        "frontend/src/components/AgentCollaboration.tsx",
        "",
    )
    add(
        "A-DEB-01",
        "/analysis",
        "L3叠加层",
        "",
        "DebateDrawer",
        "研究/风控辩论",
        "Analysis 传入 debateDrawer；关闭清空",
        "抽屉过渡视实现",
        "无",
        "事件流来自分析 job",
        "frontend/src/components/DebateDrawer.tsx; DebateTimeline.tsx",
        "无独立 URL",
    )
    add(
        "A-DEC-01",
        "/analysis",
        "L2页内分区",
        "",
        "DecisionCard",
        "裁决摘要",
        "展开 reasoning Chevron",
        "Chevron rotate",
        "无",
        "report from analysisStore",
        "frontend/src/components/DecisionCard.tsx",
        "",
    )
    add(
        "A-RR-01",
        "/analysis",
        "L2页内分区",
        "",
        "RiskRadar",
        "风险条目列表",
        "只读列表非坐标图",
        "无",
        "无",
        "analysisStore riskItems",
        "frontend/src/components/RiskRadar.tsx",
        "产品名雷达实为列表",
    )
    add(
        "A-KM-01",
        "/analysis",
        "L2页内分区",
        "",
        "KeyMetrics",
        "关键指标行",
        "只读",
        "无",
        "无",
        "analysisStore keyMetrics",
        "frontend/src/components/KeyMetrics.tsx",
        "",
    )
    add(
        "A-RV-01",
        "/analysis",
        "L2页内分区",
        "",
        "ReportViewer",
        "章节 Markdown",
        "activeSection 联动 Chat/Flow",
        "无",
        "无",
        "analysisStore report",
        "frontend/src/components/ReportViewer.tsx",
        "",
    )

    # reports
    add(
        "R-01",
        "/reports",
        "L2页内分区",
        "",
        "Reports",
        "列表搜表分页删",
        "行点击进详情 setSearchParams report=",
        "分页按钮 disabled opacity；行 hover",
        "无",
        "GET/DELETE /v1/reports",
        "frontend/src/pages/Reports.tsx",
        "",
    )
    add(
        "R-02",
        "/reports",
        "L2页内分区",
        "",
        "Reports",
        "详情态",
        "返回清除 report 参数",
        "进度条 width transition duration-700；pulse 运行点",
        "无",
        "GET /v1/reports/{id}",
        "frontend/src/pages/Reports.tsx",
        "",
    )
    add(
        "R-03",
        "/reports?report=",
        "L4组件内子状态",
        "",
        "Reports",
        "深链打开详情",
        "初次加载读 query report_id",
        "无",
        "无",
        "GET /v1/reports/{id}",
        "frontend/src/pages/Reports.tsx",
        "",
    )

    # portfolio
    add(
        "P-01",
        "/portfolio",
        "L2页内分区",
        "",
        "Portfolio",
        "自选添加",
        "搜索选股票；批量；截图 VLM 解析",
        "segmented Knob transition-transform 300ms；spinners",
        "无",
        "GET /v1/market/stock-search; POST /v1/watchlist; POST /v1/portfolio/parse-image",
        "frontend/src/pages/Portfolio.tsx",
        "",
    )
    add(
        "P-02",
        "/portfolio",
        "L2页内分区",
        "",
        "Portfolio",
        "自选列表行",
        "定时/分析/删除",
        "button transition-colors",
        "无",
        "watchlist scheduled APIs",
        "frontend/src/pages/Portfolio.tsx",
        "",
    )
    add(
        "P-03",
        "/portfolio",
        "L2页内分区",
        "",
        "Portfolio",
        "定时任务批量条",
        "改时间/测试/启停/删",
        "批量按钮 Loader2",
        "无",
        "/v1/scheduled batch",
        "frontend/src/pages/Portfolio.tsx",
        "",
    )

    # tracking
    add(
        "TB-01",
        "/tracking-board",
        "L1页面",
        "",
        "TrackingBoardPanel",
        "简洁/详细切换",
        "localStorage 持久视图",
        "toggle pill transition-colors",
        "无",
        "localStorage",
        "frontend/src/components/TrackingBoardPanel.tsx",
        "",
    )
    add(
        "TB-02",
        "/tracking-board",
        "L2页内分区",
        "",
        "TrackingBoardPanel",
        "导入区",
        "文本/图片解析；保存；清空",
        "spin；按钮 hover",
        "无",
        "imports parse-image dashboard",
        "frontend/src/components/TrackingBoardPanel.tsx",
        "",
    )
    add(
        "TB-03",
        "/tracking-board",
        "L2页内分区",
        "",
        "TrackingBoardPanel",
        "简洁表 SVG 列",
        "展示微型 OHLC SVG",
        "无",
        "SVG 微型K与区间条",
        "GET /v1/dashboard/tracking-board",
        "frontend/src/components/TrackingBoardPanel.tsx",
        "",
    )
    add(
        "TB-04",
        "/tracking-board",
        "L2页内分区",
        "",
        "TrackingBoardPanel",
        "详细卡片区",
        "刷新按钮 RefreshCw animate-spin",
        "refreshing 状态",
        "无",
        "GET /v1/dashboard/tracking-board",
        "frontend/src/components/TrackingBoardPanel.tsx",
        "",
    )

    # feedback
    add(
        "F-01",
        "/feedback",
        "L2页内分区",
        "",
        "Feedback",
        "列表分页",
        "卡片点击进详情子视图",
        "hover shadow transition-all",
        "无",
        "/v1/feedbacks",
        "frontend/src/pages/Feedback.tsx",
        "",
    )
    add(
        "F-02",
        "/feedback",
        "L2页内分区",
        "",
        "Feedback",
        "新建表单",
        "展开/提交",
        "按钮 gradient hover shadow",
        "无",
        "POST /v1/feedbacks",
        "frontend/src/pages/Feedback.tsx",
        "",
    )

    # settings
    add(
        "SET-01",
        "/settings",
        "L2页内分区",
        "",
        "Settings",
        "模型与 endpoint",
        "PATCH /v1/config",
        "加载 Loader2 animate-spin",
        "无",
        "GET/PATCH /v1/config；POST /v1/config/warmup",
        "frontend/src/pages/Settings.tsx",
        "",
    )
    add(
        "SET-02",
        "/settings",
        "L2页内分区",
        "",
        "Settings",
        "API Token CRUD",
        "创建/删除 token",
        "卡片 transition-all",
        "无",
        "/v1/tokens",
        "frontend/src/pages/Settings.tsx",
        "",
    )
    add(
        "SET-03",
        "/settings",
        "L2页内分区",
        "",
        "Settings",
        "邮件/企微开关",
        "toggle translate-x",
        "transition-colors transform",
        "无",
        "PATCH config；wecom warmup",
        "frontend/src/pages/Settings.tsx",
        "",
    )
    add(
        "SET-04",
        "/settings",
        "L2页内分区",
        "",
        "Settings",
        "保存全部",
        "聚合提交",
        "Save Loader2 spin",
        "无",
        "PATCH /v1/config",
        "frontend/src/pages/Settings.tsx",
        "",
    )

    add(
        "R-TB-01",
        "/reports",
        "L2页内分区",
        "",
        "TaskProgressBanner",
        "运行中任务条",
        "展示进行中分析进度文案",
        "animate-pulse 状态点",
        "无",
        "job polling / store",
        "frontend/src/components/TaskProgressBanner.tsx",
        "嵌入 Reports 详情流",
    )
    add(
        "IDX-CSS-01",
        "global",
        "L0壳层",
        "",
        "index.css",
        "animate-in 工具类",
        "用于挂载节点若使用则有 keyframes 进场",
        "@keyframes animateIn 0.3s",
        "无",
        "N/A",
        "frontend/src/index.css",
        "按需核对哪些组件加 class",
    )
    add(
        "HOOK-DEAD-01",
        "global",
        "L0壳层",
        "",
        "hooks",
        "useSSE / useTypeWriter",
        "当前 src 内无页面 import；保留或清理",
        "无",
        "无",
        "N/A",
        "frontend/src/hooks/useSSE.ts; useTypeWriter.ts",
        "规划表标潜在死代码",
    )

    return r


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = rows()
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(data)
    print(f"Wrote {len(data)} rows to {OUT}")


if __name__ == "__main__":
    main()
