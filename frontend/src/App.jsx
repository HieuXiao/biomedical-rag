import { useState, useRef, useEffect, useCallback } from 'react';
import './App.css';
import {
  PipelineBar,
  PipelineTrace,
  Citations,
  FactCheckBadge,
  RouteBadge,
} from './components.jsx';

const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001';
const API_BASE_URL = rawApiBaseUrl.replace('0.0.0.0', '127.0.0.1');

const FALLBACK_MODELS = [
  'gemini-3.5-flash',
  'gemini-3.5-flash-lite',
  'gemini-flash-latest',
  'gemini-flash-lite-latest',
];

const STAGE_ORDER = ['deid', 'route', 'graph', 'retrieve', 'generate', 'factcheck', 'reid'];

function getInitialTheme() {
  try {
    const saved = localStorage.getItem('medrag-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch (e) { /* ignore */ }
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [modelStats, setModelStats] = useState([]);
  const [selectedModel, setSelectedModel] = useState(FALLBACK_MODELS[0]);
  const [statusMessage, setStatusMessage] = useState('');
  const [activeStage, setActiveStage] = useState(null);
  const [theme, setTheme] = useState(getInitialTheme);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('medrag-theme', theme); } catch (e) { /* ignore */ }
  }, [theme]);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { scrollToBottom(); }, [messages]);

  const loadModels = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/models`);
      if (!response.ok) throw new Error('Không tải được model list');
      const data = await response.json();
      if (Array.isArray(data.models) && data.models.length > 0) {
        setModelStats(data.models);
        setSelectedModel((prev) => (data.models.some((m) => m.name === prev) ? prev : data.models[0].name));
        return;
      }
    } catch (error) {
      console.warn(error);
    }
    setModelStats(FALLBACK_MODELS.map((name) => ({ name, used: 0, limit: 20, usage_percent: 0 })));
  }, []);

  useEffect(() => { loadModels(); }, [loadModels]);

  const isTransientError = (message) => {
    const t = (message || '').toLowerCase();
    return (
      t.includes('rate limit') || t.includes('429') || t.includes('quota') ||
      t.includes('503') || t.includes('unavailable') || t.includes('overload') ||
      t.includes('high demand')
    );
  };

  const getNextModel = (currentModel) => {
    const source = modelStats.length > 0 ? modelStats.map((m) => m.name) : FALLBACK_MODELS;
    const index = source.indexOf(currentModel);
    if (index < 0 || index === source.length - 1) return null;
    return source[index + 1];
  };

  // ---- SSE streaming ----------------------------------------------------
  const streamChat = async (question, modelName, onEvent) => {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: question, model: modelName, api_key: apiKey }),
    });

    if (!response.ok || !response.body) {
      let detail = 'Lỗi máy chủ';
      try { const err = await response.json(); detail = err.detail || detail; } catch (e) { /* ignore */ }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';
      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try { onEvent(JSON.parse(payload)); } catch (e) { console.warn('Bad SSE chunk', e); }
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');
    setLoading(true);
    setActiveStage('deid');

    // chèn 1 message bot rỗng để stream vào.
    const botIndex = messages.length + 1;
    setMessages((prev) => [...prev, { role: 'bot', content: '', streaming: true, pipeline: null, sources: [], factcheck: null }]);

    const patchBot = (patch) => {
      setMessages((prev) => {
        const next = [...prev];
        const i = next.length - 1;
        if (i >= 0 && next[i].role === 'bot') next[i] = { ...next[i], ...(typeof patch === 'function' ? patch(next[i]) : patch) };
        return next;
      });
    };

    const attempt = async (modelName) => {
      // Trả về {gotToken, errorMsg}. Nếu lỗi tạm thời và chưa có token -> cho fallback.
      let gotToken = false;
      let errorMsg = null;
      patchBot({ content: '', streaming: true, pipeline: null, sources: [], factcheck: null, error: false });
      await streamChat(question, modelName, (event) => {
        if (event.type === 'pipeline') {
          patchBot({ pipeline: event.data });
          setActiveStage('retrieve');
          setStatusMessage('Đã truy xuất ngữ cảnh, đang sinh câu trả lời...');
        } else if (event.type === 'token') {
          gotToken = true;
          setActiveStage('generate');
          patchBot((m) => ({ content: (m.content || '') + event.data }));
        } else if (event.type === 'done') {
          setActiveStage('factcheck');
          patchBot({
            streaming: false,
            content: event.data.answer || '',
            sources: event.data.sources || [],
            factcheck: event.data.factcheck || null,
          });
          setStatusMessage('Hoàn tất');
        } else if (event.type === 'error') {
          errorMsg = event.data;
        }
      });
      return { gotToken, errorMsg };
    };

    try {
      let model = selectedModel;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        setStatusMessage(`Đang xử lý với ${model}...`);
        const { gotToken, errorMsg } = await attempt(model);
        if (!errorMsg) break; // thành công

        const canFallback = !gotToken && isTransientError(errorMsg);
        const next = canFallback ? getNextModel(model) : null;
        if (next) {
          setStatusMessage(`Model ${model} quá tải/hết quota, chuyển sang ${next}...`);
          model = next;
          setSelectedModel(next);
          continue;
        }
        patchBot((m) => ({ streaming: false, content: (m.content || '') + `\n\n⚠️ ${errorMsg}`, error: true }));
        setStatusMessage('Có lỗi xảy ra');
        break;
      }
      loadModels();
    } catch (error) {
      console.error(error);
      patchBot({ streaming: false, content: `⚠️ Lỗi: ${error.message || 'Không kết nối được máy chủ.'}`, error: true });
      setStatusMessage('Có lỗi khi gửi câu hỏi');
    } finally {
      setLoading(false);
      setActiveStage(null);
      void botIndex;
    }
  };

  const currentUsage = modelStats.find((m) => m.name === selectedModel)?.usage_percent ?? 0;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">✚</span>
            <div className="brand-text">
              <h1>Trợ lý Y tế RAG</h1>
              <p className="brand-sub">Clinical Medical RAG · GraphRAG · Hybrid Search · PHI-safe</p>
            </div>
          </div>

          <div className="header-controls">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="API Key (tuỳ chọn)"
              className="ctl api-key-input"
            />
            <div className="model-wrap">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="ctl model-selector"
              >
                {(modelStats.length > 0 ? modelStats : FALLBACK_MODELS.map((name) => ({ name, usage_percent: 0 }))).map((model) => (
                  <option key={model.name || model} value={model.name || model}>
                    {(model.name || model)} · {model.usage_percent ?? 0}%
                  </option>
                ))}
              </select>
              <span className="usage-dot" title={`Usage ${currentUsage}%`} style={{ '--p': `${currentUsage}%` }} />
            </div>
            <button
              type="button"
              className="ctl theme-toggle"
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
              title="Đổi giao diện sáng/tối"
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
        <PipelineBar order={STAGE_ORDER} active={activeStage} />
      </header>

      <main className="chat-container">
        <div className="chat-inner">
          {messages.length === 0 ? (
            <EmptyState onPick={(q) => setInput(q)} />
          ) : (
            <div className="message-list">
              {messages.map((msg, idx) => (
                <MessageBubble key={idx} msg={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </main>

      <footer className="app-footer">
        <form onSubmit={handleSubmit} className="input-form">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Nhập câu hỏi tra cứu y khoa…"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            {loading ? '…' : 'Gửi'}
          </button>
        </form>
        {statusMessage && <div className="status-line">{statusMessage}</div>}
      </footer>
    </div>
  );
}

function EmptyState({ onPick }) {
  const samples = [
    'Phác đồ điều trị đái tháo đường týp 2 dùng thuốc gì đầu tiên?',
    'Metformin có chống chỉ định khi suy thận không?',
    'Metformin có tương tác với rượu bia không?',
    'Mục tiêu HbA1c trong điều trị đái tháo đường là bao nhiêu?',
  ];
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">🩺</div>
      <h2>Bắt đầu tra cứu lâm sàng</h2>
      <p>Hỏi về phác đồ, tương tác thuốc, chống chỉ định… Hệ thống truy xuất y văn + Knowledge Graph và luôn kèm trích dẫn nguồn.</p>
      <div className="samples">
        {samples.map((s) => (
          <button key={s} className="sample-chip" onClick={() => onPick(s)}>{s}</button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`message ${msg.role}`}>
      <div className="avatar" aria-hidden="true">{isUser ? '👤' : '✚'}</div>
      <div className={`bubble ${msg.error ? 'bubble-error' : ''}`}>
        {!isUser && msg.pipeline?.route && (
          <div className="bubble-topmeta">
            <RouteBadge route={msg.pipeline.route} />
            {msg.pipeline.deid?.total > 0 && (
              <span className="chip chip-phi">🔐 Đã ẩn danh {msg.pipeline.deid.total} PHI</span>
            )}
            {msg.factcheck && <FactCheckBadge fc={msg.factcheck} />}
          </div>
        )}

        <div className="bubble-content">
          {msg.content
            ? <p>{msg.content}</p>
            : (msg.streaming ? <TypingDots /> : <p className="muted">Không có phản hồi.</p>)}
          {msg.streaming && msg.content && <span className="caret" />}
        </div>

        {!isUser && !msg.streaming && msg.sources?.length > 0 && <Citations sources={msg.sources} />}
        {!isUser && msg.pipeline && <PipelineTrace pipeline={msg.pipeline} />}
      </div>
    </div>
  );
}

function TypingDots() {
  return <span className="typing"><i></i><i></i><i></i></span>;
}

export default App;
