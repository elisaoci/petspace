import { useEffect, useRef, useState } from "react";
import { Send, Trash2 } from "lucide-react";
import { PetSwitcher } from "../components/PetSwitcher";
import { usePets } from "../context/PetContext";
import { api, authorizedFetch } from "../lib/api";
import { track } from "../lib/analytics";
import type { ChatHistoryItem } from "../lib/types";

type ChatMessage = { role: "user" | "assistant"; text: string };

export function ChatPage() {
  const { pet } = usePets();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [lastPrompt, setLastPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!pet) return;
    api<ChatHistoryItem[]>(`/chat/history/pet-${pet.id}`)
      .then(history => {
        const restored = history
          .filter(item => item.role === "user" || item.role === "assistant")
          .map(item => ({ role: item.role as "user" | "assistant", text: item.content }));
        setMessages(restored.length ? restored : [{
          role: "assistant",
          text: `Привет! Я помогу разобраться с уходом, кормлением и самочувствием ${pet.name}. Что вас интересует?`,
        }]);
      })
      .catch(() => {
        setMessages([{
          role: "assistant",
          text: `Привет! Я помогу разобраться с уходом, кормлением и самочувствием ${pet.name}. Что вас интересует?`,
        }]);
      });
  }, [pet?.id]);

  const send = async (retryPrompt?: string) => {
    if (!pet) return;
    const text = (retryPrompt ?? input).trim();
    if (!text || loading) return;
    setInput("");
    setLastPrompt(text);
    setError(null);
    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", text: "" }]);
    track("chat_message_sent", "/app/chat");
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await authorizedFetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ message: text, conversation_id: `pet-${pet.id}`, pet_id: pet.id }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error("Backend не смог открыть поток ответа.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      while (!finished) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const line = event.split("\n").find(item => item.startsWith("data: "));
          if (!line) continue;
          const data = line.slice(6);
          if (data === "[DONE]") { finished = true; break; }
          const payload = JSON.parse(data) as { content?: string; error?: string };
          if (payload.error) throw new Error(payload.error);
          if (payload.content) {
            setMessages(prev => {
              const next = [...prev];
              const last = next.length - 1;
              next[last] = { ...next[last], text: next[last].text + payload.content };
              return next;
            });
          }
        }
      }
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        const message = caught instanceof Error ? caught.message : "Не удалось получить ответ.";
        setError(`Ollama недоступна или backend не запущен: ${message}`);
        setMessages(prev => prev.length > 0 && prev[prev.length - 1].text ? prev : prev.slice(0, -1));
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const stop = () => abortRef.current?.abort();
  const clearHistory = async () => {
    if (!pet) return;
    stop();
    setError(null);
    setMessages([{ role: "assistant", text: `История очищена. Чем помочь ${pet.name}?` }]);
    try {
      await authorizedFetch(`/chat/history/pet-${pet.id}`, { method: "DELETE" });
    } catch {
      setError("История очищена только на экране. Backend недоступен.");
    }
  };

  if (!pet) {
    return (
      <main className="content">
        <div className="page-heading">
          <div><p className="eyebrow">ИИ-помощник</p><h1>Сначала добавьте питомца</h1></div>
          <PetSwitcher />
        </div>
      </main>
    );
  }

  return (
    <main className="content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Персональный помощник</p>
          <h1>ИИ-чат о {pet.name}</h1>
        </div>
        <div className="pet-controls">
          <PetSwitcher />
          <button className="button secondary" type="button" onClick={clearHistory}><Trash2 size={16} /> Очистить</button>
        </div>
      </div>
      <section className="card chat-card">
        <div className="quick-chips">
          {["Сколько корма давать?", "Чем кормить щенка?", "Что делать, если не ест?"].map(question => (
            <button key={question} type="button" onClick={() => setInput(question)}>{question}</button>
          ))}
        </div>
        <div className="messages">
          {messages.map((message, index) => (
            <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <span>{message.text || " "}</span>
            </div>
          ))}
          {loading && <div className="typing">Печатает…</div>}
          {error && (
            <div className="chat-error" role="alert">
              {error}
              <button type="button" onClick={() => send(lastPrompt)}>Повторить</button>
            </div>
          )}
        </div>
        <div className="chat-input">
          <input
            value={input}
            disabled={loading}
            onChange={event => setInput(event.target.value)}
            onKeyDown={event => event.key === "Enter" && send()}
            placeholder={`Напишите вопрос о ${pet.name}…`}
          />
          {loading
            ? <button className="stop-button" aria-label="Остановить ответ" onClick={stop} type="button">Остановить</button>
            : <button className="send-button" aria-label="Отправить вопрос" onClick={() => send()} type="button"><Send size={18} /></button>}
        </div>
        <p className="disclaimer">Ответы носят информационный характер и не заменяют консультацию ветеринара.</p>
      </section>
    </main>
  );
}
