export type ServiceCategory = "grooming" | "sitter" | "taxi";

export type Provider = {
  id: number;
  category: ServiceCategory;
  name: string;
  role: string;
  area: string;
  rating: number;
  reviews: number;
  tags: string[];
  services: { title: string; price: number }[];
};

export const CATEGORIES: { id: ServiceCategory; title: string }[] = [
  { id: "grooming", title: "Груминг" },
  { id: "sitter", title: "Ситтеры" },
  { id: "taxi", title: "Зоотакси" },
];

export const PROVIDERS: Provider[] = [
  { id: 1, category: "grooming", name: "Студия «Пушистик»", role: "Салон груминга", area: "Тверской район", rating: 4.9, reviews: 212, tags: ["Кошки и собаки", "Тихие фены"], services: [{ title: "Комплексный груминг, мелкая порода", price: 2800 }, { title: "Гигиеническая стрижка", price: 1200 }, { title: "Стрижка когтей", price: 400 }] },
  { id: 2, category: "grooming", name: "Анна Соколова", role: "Грумер с выездом на дом", area: "Хамовники", rating: 5.0, reviews: 87, tags: ["Выезд на дом", "Работает с кошками"], services: [{ title: "Груминг кошки на дому", price: 3500 }, { title: "Вычесывание колтунов, от", price: 1000 }, { title: "Чистка ушей и зубов", price: 600 }] },
  { id: 3, category: "grooming", name: "Грум-бар «Лапки»", role: "Салон груминга", area: "Сокольники", rating: 4.7, reviews: 156, tags: ["Жёсткошёрстные породы", "Сертификат FCI"], services: [{ title: "Тримминг жёсткошёрстных", price: 3900 }, { title: "SPA-уход с маской", price: 1500 }, { title: "Экспресс-линька", price: 2200 }] },
  { id: 4, category: "sitter", name: "Мария Крылова", role: "Догситтер, передержка у себя", area: "Сокольники", rating: 4.9, reviews: 64, tags: ["Дом с садом", "Отчёт с фото"], services: [{ title: "Передержка, сутки", price: 1600 }, { title: "Выгул 60 минут", price: 600 }, { title: "Визит к кошке на дом", price: 700 }] },
  { id: 5, category: "sitter", name: "Игорь Беляев", role: "Ситтер с ветеринарным образованием", area: "Арбат", rating: 5.0, reviews: 41, tags: ["Уколы и капельницы", "Пожилые питомцы"], services: [{ title: "Уход дома у владельца, сутки", price: 2200 }, { title: "Уколы и капельницы по назначению", price: 900 }, { title: "Выгул 30 минут", price: 400 }] },
  { id: 6, category: "sitter", name: "Сервис «Друг дома»", role: "Сеть проверенных ситтеров", area: "Вся Москва", rating: 4.8, reviews: 298, tags: ["Страховка", "Замена при болезни"], services: [{ title: "Выгул 30 минут", price: 450 }, { title: "Кормление и уборка лотка", price: 500 }, { title: "Отпуск: ежедневные визиты, неделя", price: 3300 }] },
  { id: 7, category: "taxi", name: "«Лапа-Экспресс»", role: "Зоотакси по Москве и области", area: "Круглосуточно", rating: 4.9, reviews: 330, tags: ["Переноски в салоне", "Подача за 20 минут"], services: [{ title: "Поездка до 10 км", price: 900 }, { title: "К ветеринару и обратно, с ожиданием", price: 1800 }, { title: "Ночной тариф, надбавка", price: 300 }] },
  { id: 8, category: "taxi", name: "Pet Cab", role: "Перевозка крупных собак", area: "Москва и аэропорты", rating: 4.8, reviews: 121, tags: ["Просторный фургон", "Помощь с посадкой"], services: [{ title: "Крупная собака, до 10 км", price: 1400 }, { title: "Трансфер в аэропорт", price: 2600 }, { title: "Сопровождающий", price: 500 }] },
  { id: 9, category: "taxi", name: "Алексей Гринёв", role: "Водитель, возит кошек и грызунов", area: "Юго-запад", rating: 4.7, reviews: 58, tags: ["Тихая езда", "Подогрев салона"], services: [{ title: "Кошка или грызун, до 10 км", price: 700 }, { title: "К ветеринару и обратно", price: 1300 }, { title: "Переезд с питомцем", price: 2500 }] },
];

export const minPrice = (provider: Provider) => Math.min(...provider.services.map(item => item.price));
export const money = (value: number) => `${value.toLocaleString("ru-RU")} ₽`;

export function reviewsLabel(count: number): string {
  const last = count % 10;
  const lastTwo = count % 100;
  const word = last === 1 && lastTwo !== 11 ? "отзыв" : [2, 3, 4].includes(last) && ![12, 13, 14].includes(lastTwo) ? "отзыва" : "отзывов";
  return `${count} ${word}`;
}
