import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">404</p>
          <h1>Такой страницы нет</h1>
        </div>
      </div>
      <section className="card empty-card">
        <p className="muted large">Проверьте адрес или вернитесь на главную.</p>
        <Link className="button primary" to="/">На главную</Link>
      </section>
    </main>
  );
}
