export function SkeletonLines({ count = 3 }: { count?: number }) {
  return (
    <div className="skeleton-list" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div className="skeleton-row" key={index}>
          <span className="skeleton-line w-40" />
          <span className="skeleton-line w-70" />
          <span className="skeleton-line w-60" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="card" aria-hidden="true">
      <SkeletonLines count={2} />
    </div>
  );
}
