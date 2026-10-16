export function DogIllustration({ className = "dog-illustration" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 240 240" role="img" aria-label="Иллюстрация собаки">
      <circle cx="120" cy="120" r="112" fill="#E9E4F7" />
      <path d="M59 80 44 35c-3-9 8-15 15-8l38 34" fill="#8E7CC3" />
      <path d="M181 80 196 35c3-9-8-15-15-8l-38 34" fill="#8E7CC3" />
      <path d="M67 94c0-42 27-63 53-63s53 21 53 63v43c0 38-24 59-53 59s-53-21-53-59Z" fill="#C6B9DC" />
      <ellipse cx="96" cy="109" rx="8" ry="11" fill="#111" />
      <ellipse cx="144" cy="109" rx="8" ry="11" fill="#111" />
      <path d="M101 143c7-8 31-8 38 0-3 16-35 16-38 0Z" fill="#111" />
      <path d="M120 143v11M105 164c9 7 21 7 30 0" fill="none" stroke="#111" strokeLinecap="round" strokeWidth="4" />
      <path d="M81 154c-17 10-22 24-16 37M159 154c17 10 22 24 16 37" fill="none" stroke="#8E7CC3" strokeLinecap="round" strokeWidth="9" />
    </svg>
  );
}
