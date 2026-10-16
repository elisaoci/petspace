import { useState } from "react";
import { Heart, Menu, X } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Главная", end: true },
  { to: "/app", label: "Кабинет", end: true },
  { to: "/app/pet", label: "Питомец", end: false },
  { to: "/app/calendar", label: "Календарь", end: false },
  { to: "/app/chat", label: "ИИ-помощник", end: false },
  { to: "/plus", label: "Plus", end: false },
];

export function Layout() {
  const [open, setOpen] = useState(false);

  return (
    <div className="app-shell site-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink className="brand" to="/" aria-label="PetSpace, главная" onClick={() => setOpen(false)}>
            <span className="brand-mark" aria-hidden="true"><Heart fill="currentColor" size={18} /></span>
            <span>PetSpace</span>
          </NavLink>
          <nav className="desktop-nav" aria-label="Основная навигация">
            {links.map(link => (
              <NavLink
                key={link.to}
                className={({ isActive }) => `desktop-nav-item${isActive ? " active" : ""}`}
                end={link.end}
                to={link.to}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <NavLink className="button primary header-cta" to="/app">Открыть кабинет</NavLink>
            <button className="menu-toggle" type="button" aria-label={open ? "Закрыть меню" : "Открыть меню"} onClick={() => setOpen(value => !value)}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
        {open && (
          <nav className="mobile-menu" aria-label="Мобильная навигация">
            {links.map(link => (
              <NavLink key={link.to} className={({ isActive }) => `mobile-menu-item${isActive ? " active" : ""}`} end={link.end} to={link.to} onClick={() => setOpen(false)}>
                {link.label}
              </NavLink>
            ))}
            <NavLink className="button primary full-button" to="/app" onClick={() => setOpen(false)}>Открыть кабинет</NavLink>
          </nav>
        )}
      </header>
      <Outlet />
      <footer className="site-footer">
        <div className="footer-inner">
          <div>
            <p className="brand footer-brand">PetSpace</p>
            <p className="muted">Цифровой дневник здоровья питомца: профиль, календарь и осторожный ИИ-помощник.</p>
          </div>
          <div className="footer-links">
            <NavLink to="/app/pet">Профиль</NavLink>
            <NavLink to="/app/calendar">Календарь</NavLink>
            <NavLink to="/app/chat">ИИ-помощник</NavLink>
            <NavLink to="/plus">PetSpace Plus</NavLink>
          </div>
          <p className="disclaimer">Ответы ИИ носят информационный характер и не заменяют консультацию ветеринара.</p>
        </div>
      </footer>
    </div>
  );
}
