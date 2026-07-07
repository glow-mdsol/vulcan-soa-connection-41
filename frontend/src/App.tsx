import { useState } from "react";

import { logout } from "./api/client";
import AppRoutes from "./routes";

export default function App() {
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      window.location.assign("/");
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <div>
            <h1 className="brand">Vulcan Schedule of Activities</h1>
            <p className="brand-tag">Study enrollment and visit coordination</p>
          </div>
          <button className="btn-secondary" type="button" onClick={handleLogout} disabled={loggingOut}>
            {loggingOut ? "Logging out…" : "Logout"}
          </button>
        </div>
      </header>
      <main className="container">
        <div className="app-frame">
          <AppRoutes />
        </div>
      </main>
    </div>
  );
}
