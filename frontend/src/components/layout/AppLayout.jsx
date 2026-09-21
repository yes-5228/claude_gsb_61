import { Outlet, useLocation } from 'react-router-dom'
import { NAV_ITEMS } from '../../constants/index.js'
import SideNav from './SideNav.jsx'
import TopBar from './TopBar.jsx'

export default function AppLayout() {
  const location = useLocation()
  const current =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.to)) || NAV_ITEMS[0]

  return (
    <div className="app">
      <SideNav />
      <div className="main">
        <TopBar item={current} />
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
