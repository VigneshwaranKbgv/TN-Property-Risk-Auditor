import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

/**
 * POST /api/risk
 * Evaluate property risk for given coordinates.
 * @param {number} lat
 * @param {number} lon
 * @returns {Promise<{risk_metrics: object, report: string, overall_risk: string}>}
 */
export async function assessRisk(lat, lon) {
  const response = await api.post("/api/risk", { lat, lon });
  return response.data;
}

/**
 * POST /api/chat
 * Stream a follow-up LLM answer.
 * Returns a ReadableStream from fetch (not axios — needed for SSE streaming).
 *
 * @param {string} question
 * @param {object} riskMetrics
 * @param {Array<{role: string, content: string}>} history
 * @returns {Promise<ReadableStreamDefaultReader>}
 */
export async function streamChat(question, riskMetrics, history) {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, risk_metrics: riskMetrics, history }),
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status} ${response.statusText}`);
  }

  return response.body.getReader();
}

export default api;
