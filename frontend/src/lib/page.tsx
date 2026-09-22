import { createContext, useContext } from "react";
import type { PagePayload } from "./types";
export const PageContext = createContext<PagePayload>({
  page: "error",
  data: { message: "Page unavailable." },
  csrf: "",
  messages: [],
  path: "/",
});
export function usePage<T>() {
  const page = useContext(PageContext);
  return { ...page, data: page.data as T };
}
export function date(value?: string, time = false) {
  if (!value) return "Not recorded";
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        ...(time
          ? { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }
          : {}),
      }).format(d);
}
export function safeUrl(value?: string) {
  if (!value) return undefined;
  try {
    const u = new URL(value, location.origin);
    return ["http:", "https:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
export async function requestData<T>(
  url: string,
  body?: FormData,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = AbortSignal.timeout(45000);
  const response = await fetch(url, {
    method: body ? "POST" : "GET",
    body,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => {
    throw new Error(
      "The server returned an invalid response. Refresh the page and try again.",
    );
  });
  if (!response.ok)
    throw new Error(
      payload.error ||
        payload.data?.message ||
        payload.data?.error ||
        "Unable to save. Refresh the page and try again.",
    );
  return payload;
}
