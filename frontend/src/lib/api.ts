export type Session = {
  mode: "demo" | "live"; authenticated: boolean; graph_configured: boolean;
  requires_login: boolean; login_url: string; user?: {displayName: string; userPrincipalName: string} | null;
};
export type ChatResult = {response: string; mode: "demo" | "live"; sources: {id: string; name: string}[]};
export type MailItem = {id?: string; subject?: string; from?: {emailAddress?: {name?: string; address?: string}}; receivedDateTime?: string};
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/" + path, {...options, credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-Aether-Request": "1", ...options.headers}});
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.error === "string" ? data.error : "接続できませんでした。もう一度お試しください。");
  if (data === null) throw new Error("応答を読み取れませんでした。");
  return data as T;
}
