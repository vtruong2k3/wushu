import { NavLink, Outlet } from "react-router";

export function Layout() {
  return (
    <div className="app">
      <header className="app-header">
        <span className="brand">Taiji AI</span>
        <nav>
          <NavLink to="/" end>
            Trạng thái hệ thống
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
