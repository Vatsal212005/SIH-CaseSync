export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

function csrfToken() {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find(x => x.startsWith("casesync_csrf="))?.split("=")[1] || "";
}

export async function api<T=unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method)) headers.set("X-CSRF-Token", decodeURIComponent(csrfToken()));
  const response = await fetch(`${API}${path}`, {...init, headers, credentials: "include", cache: "no-store"});
  if (!response.ok) {
    const data = await response.json().catch(() => ({detail: response.statusText}));
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function downloadUrl(path: string) { return `${API}${path}`; }

