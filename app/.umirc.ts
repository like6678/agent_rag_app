import { defineConfig } from 'umi';

/**
 * Umi Max 配置
 * 文档: https://umijs.org/docs/api/config
 */
export default defineConfig({
  // 启用 antd、request、model 插件(Umi Max 内置, 配置项开启即可)
  antd: {},
  request: {},
  model: {},
  // 禁用 Umi Max 内置的 ProLayout, 只使用自定义布局(避免双重菜单)
  layout: false,

  // 路由配置(扁平结构, Umi 自动用 src/layouts/index.tsx 作为全局布局包裹)
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/dashboard',
      name: '仪表盘',
      component: '@/pages/index',
    },
    {
      path: '/chat',
      name: '智能对话',
      component: '@/pages/chat/index',
    },
    {
      path: '/documents',
      name: '文档管理',
      component: '@/pages/documents/index',
    },
    {
      path: '/knowledge',
      name: '知识库',
      component: '@/pages/knowledge/index',
    },
    {
      path: '/config',
      name: '系统配置',
      component: '@/pages/config/index',
    },
    {
      path: '/evaluation',
      name: 'RAG评测',
      component: '@/pages/evaluation/index',
    },
  ],

  // 开发代理: /api → 后端 8000
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
    '/health': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },

  // 构建排除依赖(减少打包体积)
  npmClient: 'npm',

  // 别名
  alias: {},

  // 标题
  title: 'Agent RAG 智能问答平台',

  // favicon
  favicons: [],
});
