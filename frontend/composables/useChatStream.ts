// 以 fetch POST 消費後端 /chat 的 SSE(EventSource 只支援 GET,故手動解析)
export interface ChatEvent {
  type: string;
  [k: string]: any;
}

export const useChatStream = () => {
  const base = useRuntimeConfig().public.apiBase as string;

  const stream = async (
    payload: { message: string; lake_id?: string; session_id?: string },
    onEvent: (ev: ChatEvent) => void,
  ) => {
    const resp = await fetch(base + "/chat", {
      method: "POST",
      // 改變狀態的請求一律夾帶 CSRF token(見 useCsrfToken.ts)
      headers: { "content-type": "application/json", ...csrfHeaders() },
      body: JSON.stringify(payload),
    });
    if (!resp.body) throw new Error("no stream body");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // SSE 事件以空行分隔;sse_starlette 用 \r\n,故同時容忍 \r\n\r\n 與 \n\n
      const chunks = buf.split(/\r?\n\r?\n/);
      buf = chunks.pop() || "";
      for (const chunk of chunks) {
        const dataLine = chunk
          .split(/\r?\n/)
          .find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        try {
          onEvent(JSON.parse(dataLine.slice(5).trim()));
        } catch {
          /* ignore malformed */
        }
      }
    }
  };

  return { stream };
};
