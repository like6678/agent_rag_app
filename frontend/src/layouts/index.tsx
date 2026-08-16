import React from 'react';
import { Layout, Menu, theme, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import {
  DashboardOutlined,
  MessageOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  SettingOutlined,
  BulbOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'umi';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/chat', icon: <MessageOutlined />, label: '智能对话' },
  { key: '/documents', icon: <FileTextOutlined />, label: '文档管理' },
  { key: '/knowledge', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/config', icon: <SettingOutlined />, label: 'RAG 配置' },
  { key: '/memory', icon: <BulbOutlined />, label: '长期记忆' },
  { key: '/evaluation', icon: <BarChartOutlined />, label: '系统评测' },
];

// Apple-inspired 主题: 通透毛玻璃 + 大圆角 + 柔和微光, 层级靠透明度与 blur 而非边框
const appleTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#2997ff',
    colorInfo: '#2997ff',
    colorLink: '#2997ff',
    borderRadius: 14,
    fontSize: 15,
    wireframe: false,
  },
  components: {
    Layout: {
      headerBg: 'transparent',
      bodyBg: 'transparent',
      siderBg: 'transparent',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(41, 151, 255, 0.16)',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.05)',
      darkItemColor: 'rgba(230, 237, 248, 0.66)',
      darkItemSelectedColor: '#7ec3ff',
      itemBorderRadius: 12,
    },
    Card: {
      headerBg: 'transparent',
      borderRadiusLG: 22,
    },
    Table: {
      headerBg: 'rgba(255, 255, 255, 0.03)',
      headerColor: 'rgba(230, 237, 248, 0.85)',
      borderColor: 'rgba(255, 255, 255, 0.06)',
      rowHoverBg: 'rgba(41, 151, 255, 0.06)',
    },
  },
};

const App: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const selected = '/' + (location.pathname.split('/')[1] || 'dashboard');

  return (
    <ConfigProvider locale={zhCN} theme={appleTheme}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          breakpoint="lg"
          collapsedWidth="0"
          theme="dark"
          width={232}
          style={{
            padding: '16px 10px',
          }}
        >
          <div
            style={{
              height: 52,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '0 12px',
              color: '#eef3fa',
              fontWeight: 700,
              letterSpacing: 0.6,
              fontSize: 16,
            }}
          >
            <ThunderboltOutlined style={{ color: token.colorPrimary, fontSize: 20 }} />
            <span>AGENT RAG</span>
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selected]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Layout>
          <Header
            style={{
              height: 64,
              background: 'transparent',
              padding: '0 28px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span style={{ fontSize: 17, fontWeight: 650, color: '#f2f6fc', letterSpacing: 0.3 }}>
              智能问答管理系统
            </span>
            <span
              style={{
                fontSize: 12,
                color: 'rgba(230, 237, 248, 0.38)',
                letterSpacing: 1.2,
                textTransform: 'uppercase',
              }}
            >
              Agent · RAG · Vector
            </span>
          </Header>
          <Content style={{ padding: '4px 28px 28px' }}>
            {/* 单个大毛玻璃容器承载全部正文 */}
            <div className="app-glass-panel">
              <Outlet />
            </div>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
};

export default App;