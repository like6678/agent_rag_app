import { defineConfig } from '@umijs/max';

export default defineConfig({
  antd: {},
  npmClient: 'npm',
  title: 'Agent RAG 智能问答',
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: './dashboard' },
    { path: '/chat', component: './chat' },
    { path: '/documents', component: './documents' },
    { path: '/knowledge', component: './knowledge' },
    { path: '/config', component: './config' },
    { path: '/memory', component: './memory' },
    { path: '/evaluation', component: './evaluation' },
  ],
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
});