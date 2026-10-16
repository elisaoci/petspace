import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "../components/Layout";
import { RequireAuth } from "../components/RequireAuth";
import { CalendarPage } from "../pages/CalendarPage";
import { ChatPage } from "../pages/ChatPage";
import { DashboardPage } from "../pages/DashboardPage";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { MedicalCardPage } from "../pages/MedicalCardPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PetPage } from "../pages/PetPage";
import { PlusPage } from "../pages/PlusPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        {/* Кабинет доступен только вошедшему владельцу. */}
        <Route path="/app" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        <Route path="/app/pet" element={<RequireAuth><PetPage /></RequireAuth>} />
        <Route path="/app/calendar" element={<RequireAuth><CalendarPage /></RequireAuth>} />
        <Route path="/app/chat" element={<RequireAuth><ChatPage /></RequireAuth>} />
        <Route path="/plus" element={<RequireAuth><PlusPage /></RequireAuth>} />
        <Route path="/profile" element={<Navigate to="/plus" replace />} />
        <Route path="/medical/:token" element={<MedicalCardPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
