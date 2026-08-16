import { defineConfig } from '@umijs/max';

export default defineConfig({
  antd: {},
  npmClient: 'npm',
  title: 'Agent RAG 智能问答',
  favicons: ['/favicon.svg'],
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: './dashboard' },
    { path: '/chat', component: './chat' },
    { path: '/documents', component: './documents' },
    { path: '/knowledge', component: './knowledge' },
    { path: '/config', component: './config' },
    { path: '/memory', component: './memory' },
    { path: '/evaluation', component: './evaluation' },
    { path: '/skills', component: './skills' },
  ],
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
});