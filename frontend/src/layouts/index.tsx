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
  RobotOutlined,
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

const App: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const selected = '/' + (location.pathname.split('/')[1] || 'dashboard');

  return (
    <ConfigProvider locale={zhCN}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider breakpoint="lg" collapsedWidth="0" theme="dark">
          <div
            style={{
              color: '#fff',
              height: 56,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              fontSize: 16,
              fontWeight: 600,
            }}
          >
            <RobotOutlined /> Agent RAG
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
              background: token.colorBgContainer,
              padding: '0 20px',
              display: 'flex',
              alignItems: 'center',
              fontSize: 15,
              fontWeight: 500,
            }}
          >
            智能问答管理系统
          </Header>
          <Content style={{ margin: 16 }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
};

export default App;