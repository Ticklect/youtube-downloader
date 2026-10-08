export const API_BASE = "http://127.0.0.1:17865";
let firefoxToken = null;

export function setFirefoxToken(token) {
  if (typeof token !== "string" || !/^[A-Za-z0-9+/]{43}=$/.test(token)) {
    throw new Error("Firefox helper authorization returned an invalid token.");
  }
  firefoxToken = token;
}

async function request(path, { method = "GET", body, stateChanging = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (stateChanging) headers["X-YCD-Client"] = "1";
  if (firefoxToken) headers["X-YCD-Token"] = firefoxToken;

  let response;
  try {
    response = await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Local helper is not running. Start it with scripts/start-helper.ps1.");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data?.error?.message || ("Helper request failed (" + response.status + ")."));
    error.code = data?.error?.code || "request_failed";
    throw error;
  }
  return data;
}

export const health = () => request("/health");
export const loadChannel = (url) => request("/channel", { method: "POST", body: { url }, stateChanging: true });
export const pickFolder = () => request("/folder/pick", { method: "POST", stateChanging: true });
export const getFolder = () => request("/folder");
export const createJob = (payload) => request("/jobs", { method: "POST", body: payload, stateChanging: true });
export const getJob = (id) => request("/jobs/" + encodeURIComponent(id));
export const retryJob = (id) => request("/jobs/" + encodeURIComponent(id) + "/retry", { method: "POST", stateChanging: true });
