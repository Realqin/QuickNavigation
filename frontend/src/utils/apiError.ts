import { message } from 'antd';
import axios from 'axios';

type ValidationErrorItem = {
  msg?: string;
  loc?: (string | number)[];
};

/** 从 FastAPI / Axios 错误响应中提取可读错误信息。 */
export function getApiErrorMessage(error: unknown, fallback = '操作失败'): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data && typeof data === 'object') {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) {
        return detail.trim();
      }
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) => {
            if (typeof item === 'string' && item.trim()) {
              return item.trim();
            }
            if (item && typeof item === 'object' && 'msg' in item) {
              const entry = item as ValidationErrorItem;
              const msg = String(entry.msg || '').trim();
              if (!msg) {
                return '';
              }
              const field = Array.isArray(entry.loc)
                ? entry.loc.filter((part) => typeof part === 'string').pop()
                : '';
              return field ? `${field}: ${msg}` : msg;
            }
            return '';
          })
          .filter(Boolean);
        if (messages.length) {
          return messages.join('；');
        }
      }
      const responseMessage = (data as { message?: string }).message;
      if (typeof responseMessage === 'string' && responseMessage.trim()) {
        return responseMessage.trim();
      }
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  return fallback;
}

/** 弹出接口返回的错误信息；无 detail 时显示 fallback。 */
export function showApiError(error: unknown, fallback = '操作失败'): void {
  message.error(getApiErrorMessage(error, fallback));
}
