import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, X } from "lucide-react";

type Toast = { id: number; message: string };

const ToastContext = createContext<{ show: (message: string) => void } | null>(null);

/** Простые тосты: подтверждение действий и мягкие ошибки. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string) => {
    const id = Date.now() + Math.random();
    setToasts(current => [...current, { id, message }]);
    window.setTimeout(() => {
      setToasts(current => current.filter(toast => toast.id !== id));
    }, 4000);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map(toast => (
          <div className="toast" key={toast.id}>
            <CheckCircle2 size={16} />
            <span>{toast.message}</span>
            <button
              type="button"
              aria-label="Закрыть"
              onClick={() => setToasts(current => current.filter(item => item.id !== toast.id))}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
