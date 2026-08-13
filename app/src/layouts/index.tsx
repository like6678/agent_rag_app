/**
 * 全局布局 - 侧边栏导航 + 顶部 + 内容区
 */
import React, { useState, useEffect } from 'react';
import { Layout, Menu, theme, Button, Space, Tag } from 'antd';
import {
  DashboardOutlined,
  MessageOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  SettingOutlined,
  TrophyOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  GithubOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, Link, history } from '@umijs/max';
import { healthCheck } from '@/services/api';

const { Header, Sider, Content } = Layout;

/** 菜单项配置 */
const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/chat', icon: <MessageOutlined />, label: '智能对话' },
  { key: '/documents', icon: <FileTextOutlined />, label: '文档管理' },
  { key: '/knowledge', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
  { key: '/evaluation', icon: <TrophyOutlined />, label: 'RAG评测' },
];

const AgentRagLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const location = useLocation();
  const { token: themeToken } = theme.useToken();

  // 当前选中的菜单(根据路径高亮)
  const selectedKey = '/' + (location.pathname.split('/')[1] || 'dashboard');

  // 健康检查
  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        await healthCheck();
        if (mounted) setBackendStatus('online');
      } catch {
        if (mounted) setBackendStatus('offline');
      }
    };
    check();
    const timer = setInterval(check, 30000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme="light"
        style={{ borderRight: `1px solid ${themeToken.colorBorderSecondary}` }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 600,
            fontSize: collapsed ? 16 : 15,
            color: themeToken.colorPrimary,
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          {collapsed ? 'AI' : 'Agent RAG 平台'}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => history.push(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            padding: '0 24px',
            background: themeToken.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Space>
            <Tag color={backendStatus === 'online' ? 'success' : backendStatus === 'offline' ? 'error' : 'processing'}>
              后端: {backendStatus === 'online' ? '在线' : backendStatus === 'offline' ? '离线' : '检测中'}
            </Tag>
            <Link to="https://github.com" target="_blank">
              <GithubOutlined />
            </Link>
          </Space>
        </Header>

        <Content style={{ overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AgentRagLayout;
