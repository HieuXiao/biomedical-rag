import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';

export default function AdminPanel() {
  const [tab, setTab] = useState('dashboard');
  return (
    <div className="page-pad">
      <div className="admin-tabs">
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}>📊 Dashboard</button>
        <button className={tab === 'docs' ? 'active' : ''} onClick={() => setTab('docs')}>🏛️ Tài liệu gốc</button>
        <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>👥 Người dùng</button>
      </div>
      {tab === 'dashboard' && <Dashboard />}
      {tab === 'docs' && <SystemDocs />}
      {tab === 'users' && <Users />}
    </div>
  );
}

function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api.adminActivity().then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="auth-error">⚠️ {error}</div>;
  if (!data) return <div className="conv-empty">Đang tải…</div>;
  const s = data.stats;
  const avg = s.avg_grounded_ratio != null ? `${Math.round(s.avg_grounded_ratio * 100)}%` : '—';

  return (
    <>
      <div className="stat-grid">
        <Stat icon="👥" label="Người dùng" value={s.total_users} />
        <Stat icon="💬" label="Tổng lượt hỏi" value={s.total_chats} />
        <Stat icon="📅" label="Hỏi hôm nay" value={s.chats_today} />
        <Stat icon="📄" label="Tài liệu" value={s.total_documents} />
        <Stat icon="✅" label="Bám nguồn TB" value={avg} />
      </div>

      <div className="panel">
        <div className="panel-head"><h3>Sử dụng theo model</h3></div>
        {data.per_model.length === 0 ? <div className="conv-empty">Chưa có dữ liệu.</div> : (
          <div className="bar-list">
            {(() => {
              const max = Math.max(...data.per_model.map((m) => m.count), 1);
              return data.per_model.map((m) => (
                <div key={m.model} className="bar-row">
                  <span className="bar-label">{m.model}</span>
                  <span className="bar-track"><span className="bar-fill" style={{ width: `${(m.count / max) * 100}%` }} /></span>
                  <span className="bar-val">{m.count}</span>
                </div>
              ));
            })()}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-head"><h3>Hoạt động gần đây</h3></div>
        <div className="log-table">
          <div className="log-head">
            <span>Thời gian</span><span>Người dùng</span><span>Hành động</span><span>Nội dung</span><span>Model</span><span>Bám nguồn</span>
          </div>
          {data.recent.map((r) => (
            <div key={r.id} className="log-row">
              <span className="log-time">{fmt(r.created_at)}</span>
              <span>{r.user}</span>
              <span><span className={`tag tag-${r.action}`}>{r.action}</span></span>
              <span className="log-detail" title={r.detail}>{r.detail || '—'}</span>
              <span className="log-mono">{r.model || '—'}</span>
              <span>{r.grounded_ratio != null ? `${Math.round(r.grounded_ratio * 100)}%` : '—'}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function SystemDocs() {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const fileRef = useRef(null);

  const load = () => api.adminDocuments().then((d) => setDocs(d.documents || [])).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(''); setUploading(true);
    try { await api.adminUploadDocument(file, note); setNote(''); if (fileRef.current) fileRef.current.value = ''; await load(); }
    catch (err) { setError(err.message); } finally { setUploading(false); }
  };
  const onToggle = async (id) => { try { await api.adminToggleDocument(id); await load(); } catch (e) { setError(e.message); } };
  const onDelete = async (id) => {
    if (!window.confirm('Xoá tài liệu gốc này khỏi hệ thống?')) return;
    try { await api.adminDeleteDocument(id); await load(); } catch (e) { setError(e.message); }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3>🏛️ Tài liệu gốc hệ thống</h3>
          <p className="panel-sub">Tài liệu dùng chung cho mọi người dùng. Thêm/bật/tắt/xoá để quản lý tri thức nền của hệ thống.</p>
        </div>
      </div>
      <div className="upload-row">
        <input type="text" className="ctl" placeholder="Ghi chú (tuỳ chọn)" value={note} onChange={(e) => setNote(e.target.value)} />
        <label className={`upload-btn ${uploading ? 'disabled' : ''}`}>
          {uploading ? 'Đang xử lý…' : '⬆️ Thêm tài liệu gốc'}
          <input ref={fileRef} type="file" accept=".pdf,.txt,.md" onChange={onUpload} disabled={uploading} hidden />
        </label>
      </div>
      {error && <div className="auth-error" style={{ marginBottom: 12 }}>⚠️ {error}</div>}
      {docs.length === 0 ? <div className="conv-empty">Chưa có tài liệu.</div> : (
        <div className="doc-table">
          {docs.map((d) => (
            <div key={d.id} className="doc-row">
              <span className="doc-icon">{d.is_base ? '📘' : '📄'}</span>
              <div className="doc-main">
                <div className="doc-name">{d.filename} {d.is_base && <span className="base-tag">gốc</span>}</div>
                <div className="doc-meta">{d.num_chunks} đoạn{d.note ? ` · ${d.note}` : ''}</div>
              </div>
              <span className={`doc-status ${d.active ? 'on' : 'off'}`}>{d.active ? 'Đang dùng' : 'Đã tắt'}</span>
              <div className="doc-actions">
                <button className="mini-btn" onClick={() => onToggle(d.id)}>{d.active ? 'Tắt' : 'Bật'}</button>
                {!d.is_base && <button className="mini-btn danger" onClick={() => onDelete(d.id)}>Xoá</button>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Users() {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => { api.adminUsers().then((d) => setUsers(d.users || [])).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="auth-error">⚠️ {error}</div>;
  return (
    <div className="panel">
      <div className="panel-head"><h3>👥 Người dùng ({users.length})</h3></div>
      <div className="log-table users-table">
        <div className="log-head"><span>ID</span><span>Tên</span><span>Email</span><span>Vai trò</span><span>Chuyên khoa</span><span>Hội thoại</span><span>Lượt hỏi</span></div>
        {users.map((u) => (
          <div key={u.id} className="log-row">
            <span>{u.id}</span><span>{u.username}</span><span className="log-detail">{u.email}</span>
            <span><span className={`tag ${u.role === 'admin' ? 'tag-admin' : ''}`}>{u.role}</span></span>
            <span>{u.specialty || '—'}</span><span>{u.conversations}</span><span>{u.chats}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z')); return d.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }); }
  catch { return iso; }
}
