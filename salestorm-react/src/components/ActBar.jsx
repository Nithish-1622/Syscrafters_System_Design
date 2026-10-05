// SALESTORM 2026 — 5-Act Presentation Navigation Bar
import React from 'react';
import { ACTS } from '../config/aws';

export default function ActBar({ currentAct, setAct }) {
  return (
    <nav className="act-bar">
      {ACTS.map((act) => (
        <button
          key={act.id}
          className={`act-tab ${currentAct === act.id ? 'active' : ''}`}
          onClick={() => setAct(act.id)}
        >
          <span className="act-num">Act {act.id} &bull; {act.duration}</span>
          <span className="act-title">{act.title}</span>
          <span className="act-subtitle">{act.subtitle}</span>
        </button>
      ))}
    </nav>
  );
}
