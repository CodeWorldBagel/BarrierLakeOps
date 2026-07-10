// CSRF 防護:每個瀏覽器工作階段產生一組隨機 nonce,所有改變狀態的請求
// (POST/PATCH/上傳/chat)以 X-CSRF-Token 自訂 header 夾帶送出。
// 跨站攻擊者無法在偽造請求上附加自訂 header(會觸發 CORS preflight 而被擋),
// 後端 CSRFOriginGuard 對已授權跨源請求驗證此 header 存在,與 Origin 檢查互為雙重防護。
const STORAGE_KEY = "blo-csrf-token";

export const useCsrfToken = (): string => {
  if (import.meta.server) return ""; // SSR 端不發送改變狀態的請求
  let csrfToken = sessionStorage.getItem(STORAGE_KEY);
  if (!csrfToken) {
    csrfToken = crypto.randomUUID();
    sessionStorage.setItem(STORAGE_KEY, csrfToken);
  }
  return csrfToken;
};

/** 供 fetch/$fetch 直接展開使用的 CSRF 防護 headers。 */
export const csrfHeaders = (): Record<string, string> => ({
  "x-csrf-token": useCsrfToken(),
});
