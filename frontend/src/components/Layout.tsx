import { useState } from "react";
import { Bell, LogOut, Mail, Menu, Phone, Send, Settings, X } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const ownerLinks = [
  { to: "/app", label: "Кабинет" },
  { to: "/app/pet", label: "Питомец" },
  { to: "/app/calendar", label: "Календарь" },
  { to: "/app/services", label: "Услуги" },
  { to: "/app/smart-id", label: "Smart ID" },
  { to: "/app/chat", label: "ИИ-помощник" },
  { to: "/plus", label: "Plus" },
];

export function Layout() {
  const [open, setOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isClinic = user?.role.startsWith("clinic_") ?? false;
  const links = user
    ? isClinic
      ? [{ to: "/clinics", label: "Кабинет клиники" }]
      : ownerLinks
    : [{ to: "/clinics", label: "Клиникам" }];

  const handleLogout = async () => {
    setOpen(false);
    await logout();
    navigate("/", { replace: true });
  };

  return (
    <div className="app-shell site-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink className="brand" to="/" aria-label="PetSpace, главная" onClick={() => setOpen(false)}>
            <span>PetSpace</span>
          </NavLink>
          <nav className="desktop-nav" aria-label="Основная навигация">
            {links.map(link => (
              <NavLink
                key={link.to}
                className={({ isActive }) => `desktop-nav-item${isActive ? " active" : ""}`}
                to={link.to}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            {user ? (
              <>
                {!isClinic && (
                  <NavLink className="header-icon" to="/app/calendar" aria-label="Уведомления" title="Уведомления">
                    <Bell size={18} />
                  </NavLink>
                )}
                <button className="logout-button" type="button" onClick={handleLogout}>
                  <LogOut size={16} /> Выйти
                </button>
                {!isClinic && (
                  <NavLink className="header-icon" to="/app/settings" aria-label="Настройки" title="Настройки">
                    <Settings size={18} />
                  </NavLink>
                )}
              </>
            ) : (
              <NavLink className="header-login" to="/login">Вход</NavLink>
            )}
            <button className="menu-toggle" type="button" aria-label={open ? "Закрыть меню" : "Открыть меню"} onClick={() => setOpen(value => !value)}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
        {open && (
          <nav className="mobile-menu" aria-label="Мобильная навигация">
            {links.map(link => (
              <NavLink key={link.to} className={({ isActive }) => `mobile-menu-item${isActive ? " active" : ""}`} to={link.to} onClick={() => setOpen(false)}>
                {link.label}
              </NavLink>
            ))}
            {user ? (
              <>
                {!isClinic && <NavLink className="mobile-menu-item" to="/app/settings" onClick={() => setOpen(false)}>Настройки</NavLink>}
                <button className="button primary full-button" type="button" onClick={handleLogout}>Выйти</button>
              </>
            ) : <NavLink className="button primary full-button" to="/login" onClick={() => setOpen(false)}>Вход</NavLink>}
          </nav>
        )}
      </header>
      <Outlet />
      <footer className="site-footer">
        <div className="footer-inner">
          <div>
            <p className="brand footer-brand">PetSpace</p>
            <p className="muted">Забота о вашем питомце в одном приложении.</p>
          </div>
          <div className="footer-contacts" aria-label="Контакты">
            <a href="tel:+7946352747"><Phone size={16} /> +7946352747</a>
            <a href="mailto:malvinka_petspace@gmail.com"><Mail size={16} /> malvinka_petspace@gmail.com</a>
          </div>
          <div className="footer-social" aria-label="Социальные сети">
            <span className="footer-social-icon telegram" title="Telegram" role="img" aria-label="Telegram"><Send size={17} /></span>
            <span className="footer-social-icon vk" title="ВКонтакте" role="img" aria-label="ВКонтакте">vk</span>
            <span className="footer-social-icon max" title="MAX" role="img" aria-label="MAX">MAX</span>
          </div>
          <div className="footer-links">
            <NavLink to="/clinics">Клиникам</NavLink>
            <NavLink to="/login">Вход</NavLink>
          </div>
          <p className="disclaimer">Ответы ИИ носят информационный характер и не заменяют консультацию ветеринара.</p>
        </div>
      </footer>
    </div>
  );
}
