import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "../components/Layout";
import { CalendarPage } from "../pages/CalendarPage";
import { ChatPage } from "../pages/ChatPage";
import { DashboardPage } from "../pages/DashboardPage";
import { HomePage } from "../pages/HomePage";
import { MedicalCardPage } from "../pages/MedicalCardPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PetPage } from "../pages/PetPage";
import { PlusPage } from "../pages/PlusPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/app" element={<DashboardPage />} />
        <Route path="/app/pet" element={<PetPage />} />
        <Route path="/app/calendar" element={<CalendarPage />} />
        <Route path="/app/chat" element={<ChatPage />} />
        <Route path="/plus" element={<PlusPage />} />
        <Route path="/profile" element={<Navigate to="/plus" replace />} />
        <Route path="/medical/:token" element={<MedicalCardPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
