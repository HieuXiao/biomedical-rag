import { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import { useAuth } from './auth.jsx';
import Sidebar from './Sidebar.jsx';
import ChatView from './ChatView.jsx';
import SaveBox from './SaveBox.jsx';
import AdminPanel from './AdminPanel.jsx';
import Profile from './Profile.jsx';

const FALLBACK_MODELS = ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-flash-latest', 'gemini-flash-lite-latest'];

const VIEW_TITLES = {
  chat: 'Trò chuyện lâm sàng',
  savebox: 'Save box — Tài liệu của tôi',
  admin: 'Quản trị hệ thống',
  profile: 'Hồ sơ cá nhân',
};

export default function Workspace({ theme, toggleTheme }) {
  const { user, logout } = useAuth();
  const [view, setView] = useState('chat');
  const [collapsed, setCollapsed] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [modelStats, setModelStats] = useState([]);
  const [selectedModel, setSelectedModel] = useState(FALLBACK_MODELS[0]);
  const [userMenu, setUserMenu] = useState(false);

  const loadConversations = useCallback(async () => {
    try {
      const d = await api.listConversations();
      setConversations(d.conversations || []);
      return d.conversations || [];
    } catch { return []; }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const d = await api.models();
      if (Array.isArray(d.models) && d.models.length) {
        setModelStats(d.models);
        setSelectedModel((prev) => (d.models.some((m) => m.name === prev) ? prev : d.models[0].name));
        return;
      }
    } catch { /* ignore */ }
    setModelStats(FALLBACK_MODELS.map((name) => ({ name, usage_percent: 0 })));
  }, []);

  useEffect(() => { loadConversations(); loadModels(); }, [loadConversations, loadModels]);

  const handleNewChat = () => { setActiveConvId(null); setView('chat'); };
  const handleSelectConv = (id) => { setActiveConvId(id); setView('chat'); };
  const handleDeleteConv = async (id) => {
    if (!window.confirm('Xoá cuộc trò chuyện này?')) return;
    try { await api.deleteConversation(id); } catch { /* ignore */ }
    if (activeConvId === id) setActiveConvId(null);
    loadConversations();
  };

  const onConversationStarted = async (id) => {
    setActiveConvId(id);
    await loadConversations();
  };

  const currentUsage = modelStats.find((m) => m.name === selectedModel)?.usage_percent ?? 0;

  return (
    <div className="workspace">
      <Sidebar
        conversations={conversations}
        activeConvId={activeConvId}
        view={view}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        onNewChat={handleNewChat}
        onSelectConv={handleSelectConv}
        onDeleteConv={handleDeleteConv}
        onNavigate={setView}
      />

      <div className="main-col">
        <header className="topbar">
          <h2 className="topbar-title">{VIEW_TITLES[view]}</h2>
          <div className="topbar-controls">
            {view === 'chat' && (
              <div className="model-wrap">
                <select className="ctl model-selector" value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                  {(modelStats.length ? modelStats : FALLBACK_MODELS.map((name) => ({ name, usage_percent: 0 }))).map((m) => (
                    <option key={m.name || m} value={m.name || m}>{(m.name || m)} · {m.usage_percent ?? 0}%</option>
                  ))}
                </select>
                <span className="usage-dot" style={{ '--p': `${currentUsage}%` }} title={`Usage ${currentUsage}%`} />
              </div>
            )}
            <button className="ctl theme-toggle" onClick={toggleTheme} title="Sáng/tối">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <div className="user-menu-wrap">
              <button className="user-chip" onClick={() => setUserMenu((o) => !o)}>
                <span className="user-avatar">{(user.username || 'U').charAt(0).toUpperCase()}</span>
                <span className="user-name">{user.username}</span>
                {user.role === 'admin' && <span className="role-badge">admin</span>}
              </button>
              {userMenu && (
                <div className="user-dropdown" onMouseLeave={() => setUserMenu(false)}>
                  <button onClick={() => { setView('profile'); setUserMenu(false); }}>👤 Hồ sơ</button>
                  <button onClick={() => { setView('savebox'); setUserMenu(false); }}>📁 Save box</button>
                  {user.role === 'admin' && <button onClick={() => { setView('admin'); setUserMenu(false); }}>🛡️ Quản trị</button>}
                  <div className="dropdown-sep" />
                  <button className="danger" onClick={logout}>🚪 Đăng xuất</button>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="main-body">
          {view === 'chat' && (
            <ChatView
              key={activeConvId || 'new'}
              conversationId={activeConvId}
              selectedModel={selectedModel}
              onConversationStarted={onConversationStarted}
              onAfterChat={loadConversations}
            />
          )}
          {view === 'savebox' && <SaveBox />}
          {view === 'profile' && <Profile />}
          {view === 'admin' && user.role === 'admin' && <AdminPanel />}
        </div>
      </div>
    </div>
  );
}
