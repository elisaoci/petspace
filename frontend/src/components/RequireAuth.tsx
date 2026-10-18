import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ConsentGate } from "./ConsentGate";

/** Пускает в кабинет только вошедшего пользователя с актуальными согласиями. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <main className="content">
        <section className="card empty-card">
          <p className="muted">Проверяем сессию…</p>
        </section>
      </main>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // Согласия обновились (или отозваны) — сначала подтверждение, потом кабинет.
  if (!user.consents_accepted) {
    return <ConsentGate />;
  }

  return <>{children}</>;
}
