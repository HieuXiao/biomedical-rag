import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';

export default function SaveBox() {
  const [userDocs, setUserDocs] = useState([]);
  const [systemDocs, setSystemDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const fileRef = useRef(null);

  const load = () => api.listDocuments()
    .then((d) => { setUserDocs(d.user_documents || []); setSystemDocs(d.system_documents || []); })
    .catch((e) => setError(e.message));

  useEffect(() => { load(); }, []);

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(''); setUploading(true);
    try {
      await api.uploadDocument(file, note);
      setNote('');
      if (fileRef.current) fileRef.current.value = '';
      await load();
    } catch (err) {
      setError(err.message || 'Lỗi tải lên');
    } finally {
      setUploading(false);
    }
  };

  const onToggle = async (id) => { try { await api.toggleDocument(id); await load(); } catch (e) { setError(e.message); } };
  const onDelete = async (id) => {
    if (!window.confirm('Xoá tài liệu này khỏi hệ thống?')) return;
    try { await api.deleteDocument(id); await load(); } catch (e) { setError(e.message); }
  };

  return (
    <div className="page-pad">
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>📁 Tài liệu của tôi</h3>
            <p className="panel-sub">Tải tài liệu riêng (PDF/TXT/MD) để đưa vào truy xuất RAG. Bật/tắt để chọn tài liệu dùng khi hỏi.</p>
          </div>
        </div>

        <div className="upload-row">
          <input type="text" className="ctl" placeholder="Ghi chú (tuỳ chọn)" value={note} onChange={(e) => setNote(e.target.value)} />
          <label className={`upload-btn ${uploading ? 'disabled' : ''}`}>
            {uploading ? 'Đang xử lý…' : '⬆️ Tải tài liệu lên'}
            <input ref={fileRef} type="file" accept=".pdf,.txt,.md" onChange={onUpload} disabled={uploading} hidden />
          </label>
        </div>
        {error && <div className="auth-error" style={{ marginBottom: 12 }}>⚠️ {error}</div>}

        <DocTable docs={userDocs} emptyText="Chưa có tài liệu riêng. Hãy tải lên tài liệu đầu tiên." onToggle={onToggle} onDelete={onDelete} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h3>🏛️ Tài liệu hệ thống (chỉ đọc)</h3>
        </div>
        <p className="panel-sub">Tài liệu gốc do quản trị viên cung cấp, luôn được dùng khi đang bật.</p>
        <DocTable docs={systemDocs} emptyText="Chưa có tài liệu hệ thống." readOnly />
      </div>
    </div>
  );
}

function DocTable({ docs, emptyText, onToggle, onDelete, readOnly }) {
  if (!docs.length) return <div className="conv-empty">{emptyText}</div>;
  return (
    <div className="doc-table">
      {docs.map((d) => (
        <div key={d.id} className="doc-row">
          <span className="doc-icon">📄</span>
          <div className="doc-main">
            <div className="doc-name">{d.filename}</div>
            <div className="doc-meta">
              {d.num_chunks} đoạn · {d.indexed ? 'đã lập chỉ mục' : 'chưa lập chỉ mục'}
              {d.note ? ` · ${d.note}` : ''}
            </div>
          </div>
          <span className={`doc-status ${d.active ? 'on' : 'off'}`}>{d.active ? 'Đang dùng' : 'Đã tắt'}</span>
          {!readOnly && (
            <div className="doc-actions">
              <button className="mini-btn" onClick={() => onToggle(d.id)}>{d.active ? 'Tắt' : 'Bật'}</button>
              <button className="mini-btn danger" onClick={() => onDelete(d.id)}>Xoá</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
