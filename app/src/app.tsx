/**
 * Umi Max 运行时配置
 * 文档: https://umijs.org/docs/max/request#运行时配置
 */
import { RequestConfig } from '@umijs/max';
import { message } from 'antd';

/** 请求运行时配置 */
export const request: RequestConfig = {
  // 基础配置
  timeout: 60000,

  // 请求拦截器
  requestInterceptors: [
    (config: any) => {
      // 可在此添加 token 等
      return config;
    },
  ],

  // 响应拦截器
  responseInterceptors: [
    (response: any) => {
      return response;
    },
  ],

  // 错误处理
  errorConfig: {
    errorThrower(res: any) {
      // 后端返回的错误统一处理
      if (res?.detail) {
        throw new Error(typeof res.detail === 'string' ? res.detail : JSON.stringify(res.detail));
      }
    },
    errorHandler(error: any, opts: any) {
      if (opts?.skipErrorHandler) return;
      let msg = '请求失败';
      if (error?.response) {
        const { status, data } = error.response;
        if (data?.detail) {
          msg = typeof data.detail === 'string' ? data.detail : '请求错误: ' + status;
        } else {
          msg = `请求错误 (${status})`;
        }
      } else if (error?.message) {
        msg = error.message;
      }
      message.error(msg);
    },
  },
};

/** 初始化应用 */
export async function render(oldRender: () => void) {
  oldRender();
}
