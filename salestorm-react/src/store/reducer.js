// SALESTORM 2026 — Global State Management (useReducer Hook)

export const initialState = {
  isLiveMode: true,
  currentAct: 1,
  metrics: {
    initial_stock: 100,
    available_stock: 100,
    reserved_stock: 0,
    sold_stock: 0,
    latency_ms: 18,
    active_tasks: 2,
    uptime_seconds: 0,
  },
  isPolling: true,
  logs: [],
  simulationRunning: false,
  simProgress: 0,
  simStatus: '',
  activeServiceId: null,
  taskCount: 2,
  surgeRps: 500,
};

export const ACTION = {
  SET_MODE: 'SET_MODE',
  SET_ACT: 'SET_ACT',
  UPDATE_METRICS: 'UPDATE_METRICS',
  ADD_LOG: 'ADD_LOG',
  CLEAR_LOGS: 'CLEAR_LOGS',
  SET_SIM_RUNNING: 'SET_SIM_RUNNING',
  SET_SIM_PROGRESS: 'SET_SIM_PROGRESS',
  SET_SIM_STATUS: 'SET_SIM_STATUS',
  SET_ACTIVE_SERVICE: 'SET_ACTIVE_SERVICE',
  SET_TASK_COUNT: 'SET_TASK_COUNT',
  SET_SURGE_RPS: 'SET_SURGE_RPS',
  RESET_INVENTORY: 'RESET_INVENTORY',
};

export function reducer(state, action) {
  switch (action.type) {
    case ACTION.SET_MODE:
      return { ...state, isLiveMode: action.payload };
    case ACTION.SET_ACT:
      return { ...state, currentAct: action.payload };
    case ACTION.UPDATE_METRICS:
      return { ...state, metrics: { ...state.metrics, ...action.payload } };
    case ACTION.ADD_LOG: {
      const newLogs = [
        ...state.logs,
        { id: Date.now() + Math.random(), ...action.payload },
      ].slice(-200);
      return { ...state, logs: newLogs };
    }
    case ACTION.CLEAR_LOGS:
      return { ...state, logs: [] };
    case ACTION.SET_SIM_RUNNING:
      return { ...state, simulationRunning: action.payload };
    case ACTION.SET_SIM_PROGRESS:
      return { ...state, simProgress: action.payload };
    case ACTION.SET_SIM_STATUS:
      return { ...state, simStatus: action.payload };
    case ACTION.SET_ACTIVE_SERVICE:
      return { ...state, activeServiceId: action.payload };
    case ACTION.SET_TASK_COUNT:
      return { ...state, taskCount: action.payload };
    case ACTION.SET_SURGE_RPS:
      return { ...state, surgeRps: action.payload };
    case ACTION.RESET_INVENTORY:
      return {
        ...state,
        metrics: {
          ...state.metrics,
          available_stock: 100,
          reserved_stock: 0,
          sold_stock: 0,
        },
      };
    default:
      return state;
  }
}
