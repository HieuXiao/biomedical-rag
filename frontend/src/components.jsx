import { useState } from 'react';

const STAGE_META = {
  deid: { label: 'Khử định danh', icon: '🔐' },
  route: { label: 'Định tuyến', icon: '🧭' },
  graph: { label: 'Knowledge Graph', icon: '🕸️' },
  retrieve: { label: 'Hybrid Retrieval', icon: '🔍' },
  generate: { label: 'Sinh câu trả lời', icon: '🧠' },
  factcheck: { label: 'FactCheck', icon: '✅' },
  reid: { label: 'Giải mã danh tính', icon: '🔓' },
};

export function PipelineBar({ order, active }) {
  if (!active) return <div className="pipeline-bar idle" aria-hidden="true" />;
  const activeIdx = order.indexOf(active);
  return (
    <div className="pipeline-bar" role="status" aria-label="Tiến trình xử lý">
      {order.map((id, i) => {
        const m = STAGE_META[id] || { label: id, icon: '•' };
        const state = i < activeIdx ? 'done' : i === activeIdx ? 'active' : 'todo';
        return (
          <div key={id} className={`pstage ${state}`} title={m.label}>
            <span className="pstage-icon">{m.icon}</span>
            <span className="pstage-label">{m.label}</span>
          </div>
        );
      })}
    </div>
  );
}

export function RouteBadge({ route }) {
  const isEhr = route.intent === 'ehr';
  return (
    <span className={`chip ${isEhr ? 'chip-ehr' : 'chip-guideline'}`} title={route.reason}>
      {isEhr ? '📋 Luồng Bệnh án' : '📚 Luồng Phác đồ'} · {Math.round((route.confidence || 0) * 100)}%
    </span>
  );
}

export function FactCheckBadge({ fc }) {
  if (!fc) return null;
  const pct = Math.round((fc.grounded_ratio ?? 0) * 100);
  const cls = fc.passed ? 'chip-ok' : 'chip-warn';
  const icon = fc.passed ? '✅' : '⚠️';
  return (
    <span className={`chip ${cls}`} title={fc.note || ''}>
      {icon} Bám nguồn {pct}%
    </span>
  );
}

export function Citations({ sources }) {
  if (!sources?.length) return null;
  return (
    <div className="citations">
      <div className="citations-head">📎 Nguồn trích dẫn ({sources.length})</div>
      <ol className="citations-list">
        {sources.map((s) => (
          <li key={s.index}>
            <span className="cite-num">[{s.index}]</span>
            <span className="cite-body">
              <span className="cite-file">{s.file_name}</span>
              {s.page && <span className="cite-meta"> · trang {s.page}</span>}
              {s.section && <span className="cite-meta"> · {s.section}</span>}
              {typeof s.score === 'number' && <span className="cite-score">{s.score.toFixed(3)}</span>}
              <span className="cite-snippet">{s.snippet}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function PipelineTrace({ pipeline }) {
  const [open, setOpen] = useState(false);
  if (!pipeline) return null;
  const g = pipeline.graph || {};
  const r = pipeline.retrieval || {};
  const d = pipeline.deid || {};

  return (
    <div className="trace">
      <button className="trace-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? '▾' : '▸'} Chi tiết pipeline
        <span className="trace-hint">
          {r.method || 'hybrid'}{r.reranked ? ' +rerank' : ''}
          {g.available && g.entities?.length ? ` · ${g.entities.length} thực thể KG` : ''}
        </span>
      </button>
      {open && (
        <div className="trace-body">
          <TraceRow label="Model" value={pipeline.model} />
          <TraceRow label="Thời gian chuẩn bị" value={pipeline.prep_seconds != null ? `${pipeline.prep_seconds}s` : '—'} />
          <TraceRow
            label="Khử định danh PHI"
            value={d.enabled ? (d.total ? `${d.total} mục (${Object.entries(d.removed || {}).map(([k, v]) => `${k}:${v}`).join(', ')})` : 'không phát hiện') : 'tắt'}
          />
          <TraceRow
            label="Retrieval"
            value={`${r.method || '—'} · vector:${r.stats?.vector_hits ?? '—'} bm25:${r.stats?.bm25_hits ?? '—'} → ${r.stats?.returned ?? '—'} tài liệu`}
          />
          <TraceRow
            label="Knowledge Graph"
            value={g.available ? `${g.backend} · ${g.entities?.length || 0} thực thể, ${g.triples?.length || 0} quan hệ` : 'không dùng'}
          />
          {g.entities?.length > 0 && (
            <div className="trace-chips">
              {g.entities.map((e) => <span key={e} className="chip chip-entity">{e}</span>)}
            </div>
          )}
          {g.triples?.length > 0 && (
            <ul className="trace-triples">
              {g.triples.slice(0, 8).map((t, i) => (
                <li key={i}><b>{t[0]}</b> <span className="rel">{t[1]}</span> <b>{t[2]}</b></li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function TraceRow({ label, value }) {
  return (
    <div className="trace-row">
      <span className="trace-label">{label}</span>
      <span className="trace-value">{value}</span>
    </div>
  );
}
