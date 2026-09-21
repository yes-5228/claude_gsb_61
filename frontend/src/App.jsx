import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout.jsx'
import { ToastProvider } from './components/common/ToastProvider.jsx'
import { AuthProvider, useAuth } from './auth/AuthContext.jsx'
import { Loading } from './components/common/Feedback.jsx'
import LoginPage from './pages/login/LoginPage.jsx'
import OverviewPage from './pages/overview/OverviewPage.jsx'
import StationsPage from './pages/stations/StationsPage.jsx'
import MeasurementsPage from './pages/measurements/MeasurementsPage.jsx'
import ExceedancesPage from './pages/exceedances/ExceedancesPage.jsx'
import QueryPage from './pages/query/QueryPage.jsx'
import AdminPage from './pages/admin/AdminPage.jsx'

function RequireAuth({ children, adminOnly = false }) {
  const { user, ready, isAdmin } = useAuth()
  const location = useLocation()

  if (!ready) return <Loading text="正在校验登录状态..." />
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (adminOnly && !isAdmin) return <Navigate to="/overview" replace />
  return children
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="/overview" replace />} />
              <Route path="overview" element={<OverviewPage />} />
              <Route path="stations" element={<StationsPage />} />
              <Route path="measurements" element={<MeasurementsPage />} />
              <Route path="exceedances" element={<ExceedancesPage />} />
              <Route path="query" element={<QueryPage />} />
              <Route
                path="admin"
                element={
                  <RequireAuth adminOnly>
                    <AdminPage />
                  </RequireAuth>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
