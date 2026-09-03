import { BrowserRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { useMobile } from './hooks/useMobile'
import MobileLayout from './components/mobile/MobileLayout'
import MobileDashboard from './pages/mobile/MobileDashboard'
import MobileAnalysis from './pages/mobile/MobileAnalysis'
import MobileFastAnalysis from './pages/mobile/MobileFastAnalysis'
import MobileChartPro from './pages/mobile/MobileChartPro'
import MobileReports from './pages/mobile/MobileReports'
import MobileTrackingBoard from './pages/mobile/MobileTrackingBoard'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Analysis from './pages/Analysis'
import FastAnalysis from './pages/FastAnalysis'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Portfolio from './pages/Portfolio'
import TrackingBoard from './pages/TrackingBoard'
import RealtimeBoard from './pages/RealtimeBoard'
import TaskCenter from './pages/TaskCenter'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import Account from './pages/Account'
import Subscription from './pages/Subscription'
import Feedback from './pages/Feedback'
import Sponsor from './pages/Sponsor'
import Thanks from './pages/Thanks'
import ChartPro from './pages/ChartPro'
import AdminShell from './pages/admin/AdminShell'
import AdminDashboard from './pages/admin/Dashboard'
import ReportsOverview from './pages/admin/reports/Overview'
import UsersTrendReport from './pages/admin/reports/UsersTrend'
import ProjectsTrendReport from './pages/admin/reports/ProjectsTrend'
import RevenueTrendReport from './pages/admin/reports/RevenueTrend'
import UsageTrendReport from './pages/admin/reports/UsageTrend'
import OpsStatsReport from './pages/admin/reports/OpsStats'
import FeatureTokenReport from './pages/admin/reports/FeatureToken'
import CommerceOrders from './pages/admin/commerce/Orders'
import CommerceOrderDetail from './pages/admin/commerce/OrderDetail'
import CommercePricing from './pages/admin/commerce/PricingTable'
import CommerceCreditPackages from './pages/admin/commerce/CreditPackages'
import CommercePaymentSettings from './pages/admin/commerce/PaymentSettings'
import CommerceCreditLedger from './pages/admin/commerce/CreditLedger'
import CommerceReconciliation from './pages/admin/commerce/ReconciliationCenter'
import CommerceApiCosts from './pages/admin/commerce/ApiCosts'
import OpsTasks from './pages/admin/ops/Tasks'
import OpsUsageRecords from './pages/admin/ops/UsageRecords'
import OpsAiCallLogs from './pages/admin/ops/AiCallLogs'
import ContentHome from './pages/admin/content/HomeContent'
import ContentAssets from './pages/admin/content/AssetLibrary'
import ContentSiteMessages from './pages/admin/content/SiteMessages'
import ContentAppearance from './pages/admin/content/AppearanceSettings'
import AdminUsers from './pages/admin/Users'
import AdminUserDetail from './pages/admin/UserDetail'
import AdminAccessLogs from './pages/admin/AccessLogs'
import AdminPlans from './pages/admin/Plans'
import AdminAuditLogs from './pages/admin/AuditLogs'
import AdminSignals from './pages/admin/Signals'
import AdminExports from './pages/admin/Exports'
import { useAuthStore } from './stores/authStore'

function RequireAuth({ children }: { children: JSX.Element }) {
    const { user, hydrated, hydrate } = useAuthStore()
    const isMobile = useMobile()
    const location = useLocation()

    useEffect(() => {
        if (!hydrated) void hydrate()
    }, [hydrated, hydrate])

    if (!hydrated) {
        return <div className="min-h-screen flex items-center justify-center text-slate-500">加载中...</div>
    }

    if (!user) {
        return <Navigate to="/login" replace />
    }

    // 移动端路由重定向拦截
    if (isMobile && !location.pathname.startsWith('/m') && !location.pathname.startsWith('/admin')) {
        const dest = location.pathname === '/' ? '/m' : `/m${location.pathname}`
        return <Navigate to={dest} replace />
    }
    // 桌面端访问移动端链接则切回
    if (!isMobile && location.pathname.startsWith('/m')) {
        const dest = location.pathname === '/m' ? '/' : location.pathname.replace(/^\/m/, '')
        return <Navigate to={dest || '/'} replace />
    }

    return children
}

function RequireAdmin({ children }: { children: JSX.Element }) {
    const { user, hydrated, hydrate } = useAuthStore()

    useEffect(() => {
        if (!hydrated) void hydrate()
    }, [hydrated, hydrate])

    if (!hydrated) {
        return <div className="min-h-screen flex items-center justify-center text-slate-500">加载中...</div>
    }

    if (!user) {
        return <Navigate to="/login" replace />
    }

    if (user.role !== 'admin') {
        return <Navigate to="/" replace />
    }

    return children
}

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route path="/sponsor" element={<Sponsor />} />
                <Route path="/thanks" element={<Thanks />} />
                <Route
                    path="/admin/*"
                    element={
                        <RequireAdmin>
                            <AdminShell />
                        </RequireAdmin>
                    }
                >
                    <Route index element={<Navigate to="/admin/reports/overview" replace />} />
                    <Route path="reports/overview" element={<ReportsOverview />} />
                    <Route path="reports/users-trend" element={<UsersTrendReport />} />
                    <Route path="reports/projects-trend" element={<ProjectsTrendReport />} />
                    <Route path="reports/revenue-trend" element={<RevenueTrendReport />} />
                    <Route path="reports/usage-trend" element={<UsageTrendReport />} />
                    <Route path="reports/ops-stats" element={<OpsStatsReport />} />
                    <Route path="reports/feature-token" element={<FeatureTokenReport />} />
                    <Route path="commerce/orders" element={<CommerceOrders />} />
                    <Route path="commerce/orders/:id" element={<CommerceOrderDetail />} />
                    <Route path="commerce/pricing" element={<CommercePricing />} />
                    <Route path="commerce/credit-packages" element={<CommerceCreditPackages />} />
                    <Route path="commerce/payment-settings" element={<CommercePaymentSettings />} />
                    <Route path="commerce/credit-ledger" element={<CommerceCreditLedger />} />
                    <Route path="commerce/reconciliation" element={<CommerceReconciliation />} />
                    <Route path="commerce/api-costs" element={<CommerceApiCosts />} />
                    <Route path="ops/tasks" element={<OpsTasks />} />
                    <Route path="ops/usage" element={<OpsUsageRecords />} />
                    <Route path="ops/ai-calls" element={<OpsAiCallLogs />} />
                    <Route path="content/home" element={<ContentHome />} />
                    <Route path="content/assets" element={<ContentAssets />} />
                    <Route path="content/messages" element={<ContentSiteMessages />} />
                    <Route path="content/appearance" element={<ContentAppearance />} />
                    <Route path="signals" element={<AdminSignals />} />
                    <Route path="exports" element={<AdminExports />} />
                    <Route path="users" element={<AdminUsers />} />
                    <Route path="users/:id" element={<AdminUserDetail />} />
                    <Route path="access-logs" element={<AdminAccessLogs />} />
                    <Route path="plans" element={<AdminPlans />} />
                    <Route path="audit-logs" element={<AdminAuditLogs />} />
                    {/* 兼容旧链接：/admin 下仍保留原仪表盘路由别名 */}
                    <Route path="legacy-dashboard" element={<AdminDashboard />} />
                </Route>
                <Route
                    path="/m/*"
                    element={
                        <RequireAuth>
                            <MobileLayout>
                                <Routes>
                                    <Route path="/" element={<MobileDashboard />} />
                                    <Route path="analysis" element={<MobileAnalysis />} />
                                    <Route path="analysis/fast" element={<MobileFastAnalysis />} />
                                    <Route path="chart" element={<MobileChartPro />} />
                                    <Route path="reports" element={<MobileReports />} />
                                    <Route path="tracking-board" element={<MobileTrackingBoard />} />
                                    <Route path="tasks" element={<TaskCenter />} />
                                    <Route path="account" element={<Account />} />
                                    <Route path="subscription" element={<Subscription />} />
                                </Routes>
                            </MobileLayout>
                        </RequireAuth>
                    }
                />
                <Route
                    path="*"
                    element={
                        <RequireAuth>
                            <Layout>
                                <Routes>
                                    <Route path="/" element={<Dashboard />} />
                                    <Route path="/tracking-board" element={<TrackingBoard />} />
                                    <Route path="/realtime-board" element={<RealtimeBoard />} />
                                    <Route path="/chart" element={<ChartPro />} />
                                    <Route path="/tasks" element={<TaskCenter />} />
                                    <Route path="/analysis" element={<Analysis />} />
                                    <Route path="/analysis/fast" element={<FastAnalysis />} />
                                    <Route path="/reports" element={<Reports />} />
                                    <Route path="/portfolio" element={<Portfolio />} />
                                    <Route path="/settings" element={<Settings />} />
                                    <Route path="/feedback" element={<Feedback />} />
                                    <Route path="/account" element={<Account />} />
                                    <Route path="/subscription" element={<Subscription />} />
                                </Routes>
                            </Layout>
                        </RequireAuth>
                    }
                />
            </Routes>
        </BrowserRouter>
    )
}

export default App
