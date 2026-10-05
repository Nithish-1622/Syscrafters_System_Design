// SALESTORM 2026 — Real-Time Console Log
import React, { useRef, useEffect } from 'react';
import { ACTION } from '../store/reducer';

const LEVEL_CLASS = {
  INFO: 'log-info',
  SUCCESS: 'log-success',
  WARN: 'log-warn',
  ERROR: 'log-error',
};

function formatTime(isoStr) {
  const d = new Date(isoStr);
  return `${d.toTimeString().slice(0, 8)}.${String(d.getMilliseconds()).padStart(3, '0')}`;
}

export default function ConsoleLog({ logs, dispatch }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs.length]);

  return (
    <div className="console-panel">
      <div className="console-header">
        <div className="console-title">
          <span className="console-dot" />
          Telemetry Console
        </div>
        <div className="console-actions">
          <span className="console-count">{logs.length} entries</span>
          <button
            className="console-clear-btn"
            onClick={() => dispatch({ type: ACTION.CLEAR_LOGS })}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="console-body">
        {logs.length === 0 && (
          <div className="console-empty">No log entries. Perform an action to generate telemetry.</div>
        )}
        {logs.map((entry) => (
          <div key={entry.id} className={`log-entry ${LEVEL_CLASS[entry.level] || 'log-info'}`}>
            <span className="log-time">[{formatTime(entry.time)}]</span>
            <span className="log-level">{entry.level}</span>
            {entry.source && <span className="log-source">[{entry.source}]</span>}
            <span className="log-msg">{entry.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
