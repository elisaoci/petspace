import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Car, Home, Scissors, Search, Star } from "lucide-react";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import {
  CATEGORIES,
  PROVIDERS,
  minPrice,
  money,
  reviewsLabel,
  type Provider,
  type ServiceCategory,
} from "../lib/servicesCatalog";
import "../styles/services.css";

type CategoryFilter = ServiceCategory | "all";
type SortKey = "rating" | "price" | "reviews";

const ICONS = { grooming: Scissors, sitter: Home, taxi: Car } as const;
const SPECIES: Record<string, string> = { dog: "собака", cat: "кошка" };
const TIMES = ["10:00", "12:00", "14:00", "16:00", "18:00"];
const SORTERS: Record<SortKey, (a: Provider, b: Provider) => number> = {
  rating: (a, b) => b.rating - a.rating || b.reviews - a.reviews,
  price: (a, b) => minPrice(a) - minPrice(b),
  reviews: (a, b) => b.reviews - a.reviews,
};

function today(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

function BookingDialog({ provider, onClose, onSubmit }: {
  provider: Provider;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const { pets, pet } = usePets();
  const [service, setService] = useState(0);
  const [petId, setPetId] = useState(pet?.id ?? pets[0]?.id ?? 0);
  const [date, setDate] = useState(today());
  const [time, setTime] = useState(TIMES[0]);
  const [comment, setComment] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal-card svc-form"
        role="dialog"
        aria-modal="true"
        aria-labelledby="svc-dialog-title"
        onClick={event => event.stopPropagation()}
        onSubmit={submit}
      >
        <div>
          <h2 id="svc-dialog-title" style={{ margin: 0 }}>{provider.name}</h2>
          <p className="lead" style={{ margin: "4px 0 0" }}>{provider.role}, {provider.area}</p>
        </div>
        <label className="field-label">Услуга
          <select className="text-input" autoFocus value={service} onChange={event => setService(Number(event.target.value))}>
            {provider.services.map((item, index) => (
              <option key={item.title} value={index}>{item.title}, {money(item.price)}</option>
            ))}
          </select>
        </label>
        <label className="field-label">Питомец
          <select className="text-input" value={petId} onChange={event => setPetId(Number(event.target.value))} disabled={!pets.length}>
            {pets.length === 0 && <option value={0}>Сначала добавьте питомца</option>}
            {pets.map(item => (
              <option key={item.id} value={item.id}>{item.name}, {SPECIES[item.species] ?? item.species}</option>
            ))}
          </select>
        </label>
        <div className="svc-pair">
          <label className="field-label">Дата
            <input className="text-input" type="date" min={today()} value={date} onChange={event => setDate(event.target.value)} required />
          </label>
          <label className="field-label">Время
            <select className="text-input" value={time} onChange={event => setTime(event.target.value)}>
              {TIMES.map(slot => <option key={slot}>{slot}</option>)}
            </select>
          </label>
        </div>
        <label className="field-label">Комментарий
          <textarea className="text-input" rows={2} placeholder="Например, адрес или особенности питомца" value={comment} onChange={event => setComment(event.target.value)} />
        </label>
        <p className="muted">Демо-каталог: заявка не отправится исполнителю.</p>
        <div className="svc-actions">
          <button className="button secondary" type="button" onClick={onClose}>Отмена</button>
          <button className="button primary" type="submit">Проверить форму</button>
        </div>
      </form>
    </div>
  );
}

export function ServicesPage() {
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("rating");
  const [booking, setBooking] = useState<Provider | null>(null);
  const [notice, setNotice] = useState("");

  const items = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    return PROVIDERS.filter(provider => {
      if (category !== "all" && provider.category !== category) return false;
      if (!needle) return true;
      const haystack = [provider.name, provider.role, provider.area, ...provider.tags, ...provider.services.map(item => item.title)];
      return haystack.join(" ").toLocaleLowerCase("ru").includes(needle);
    }).sort(SORTERS[sort]);
  }, [category, query, sort]);

  const tabs: { id: CategoryFilter; title: string; count: number }[] = [
    { id: "all", title: "Все услуги", count: PROVIDERS.length },
    ...CATEGORIES.map(item => ({ ...item, count: PROVIDERS.filter(provider => provider.category === item.id).length })),
  ];

  return (
    <main className="content">
      <div className="page-heading">
        <div><h1>Услуги для питомцев</h1></div>
        <PetSwitcher />
      </div>
      <p className="lead">Грумеры, ситтеры и зоотакси рядом с вами. Выберите услугу, питомца и удобное время.</p>

      <div className="svc-layout">
        <div className="svc-cats" role="group" aria-label="Категории услуг">
          {tabs.map(tab => (
            <button key={tab.id} type="button" className="svc-cat" aria-pressed={category === tab.id} onClick={() => setCategory(tab.id)}>
              {tab.title}<span>{tab.count}</span>
            </button>
          ))}
        </div>

        <div>
          <div className="svc-tools">
            <label className="visually-hidden" htmlFor="services-search">Поиск по услугам</label>
            <input
              id="services-search"
              className="text-input"
              type="search"
              placeholder="Найти услугу или исполнителя"
              value={query}
              onChange={event => setQuery(event.target.value)}
            />
            <label className="visually-hidden" htmlFor="services-sort">Сортировка</label>
            <select id="services-sort" className="text-input" value={sort} onChange={event => setSort(event.target.value as SortKey)}>
              <option value="rating">Сначала с лучшим рейтингом</option>
              <option value="price">Сначала подешевле</option>
              <option value="reviews">Сначала с большим числом отзывов</option>
            </select>
          </div>

          <div className="svc-list" aria-live="polite">
            {items.length === 0 && (
              <div className="svc-empty">
                <Search size={20} aria-hidden="true" />
                <p>Ничего не нашли по запросу «{query.trim()}».</p>
                <button className="button secondary" type="button" onClick={() => setQuery("")}>Сбросить поиск</button>
              </div>
            )}
            {items.map(provider => {
              const Icon = ICONS[provider.category];
              return (
                <article className="card svc-row" key={provider.id}>
                  <div className={`svc-ava ${provider.category}`} aria-hidden="true"><Icon size={28} /></div>
                  <div>
                    <h2 className="svc-name">{provider.name}</h2>
                    <div className="svc-sub">
                      <span>{provider.role}</span>
                      <span>{provider.area}</span>
                      <span><span className="svc-rate"><Star size={13} fill="currentColor" aria-hidden="true" />{provider.rating.toFixed(1).replace(".", ",")}</span>{" "}{reviewsLabel(provider.reviews)}</span>
                    </div>
                    <div className="svc-tags">{provider.tags.map(tag => <span className="svc-tag" key={tag}>{tag}</span>)}</div>
                    <ul className="svc-menu">
                      {provider.services.map(item => <li key={item.title}><span>{item.title}</span><i /><b>{money(item.price)}</b></li>)}
                    </ul>
                  </div>
                  <div className="svc-side">
                    <div className="svc-from">от<strong>{money(minPrice(provider))}</strong></div>
                    <button className="button primary" type="button" onClick={() => { setNotice(""); setBooking(provider); }}>Записаться</button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </div>

      <p className="svc-note">Демо-каталог: исполнители, отзывы и цены приведены для примера; заявки пока не отправляются.</p>
      {notice && <p className="muted" role="status">{notice}</p>}
      {booking && (
        <BookingDialog
          provider={booking}
          onClose={() => setBooking(null)}
          onSubmit={() => {
            setBooking(null);
            setNotice("Форма проверена. Заявка не отправлена: каталог пока демонстрационный.");
          }}
        />
      )}
    </main>
  );
}
