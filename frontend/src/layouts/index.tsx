import React, { useEffect, useState } from 'react';
import { Layout, Menu, theme, ConfigProvider, Button, Popover, Slider, Space } from 'antd';
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
  BgColorsOutlined,
  UndoOutlined,
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

const GLASS_KEY = 'app-glass-alpha';
const DEFAULT_GLASS = 45; // 0-100, 45 -> rgba(255,255,255,0.045) 默认浓度

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

  // 毛玻璃浓度(0-100): Header 按钮调节, localStorage 持久化
  const [glassAlpha, setGlassAlpha] = useState<number>(() => {
    const v = Number(localStorage.getItem(GLASS_KEY));
    return Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : DEFAULT_GLASS;
  });
  useEffect(() => {
    localStorage.setItem(GLASS_KEY, String(glassAlpha));
  }, [glassAlpha]);
  // 0 = 无毛玻璃(全透明), 45(默认) = 当前效果(blur 26px), 100 = 最浓
  const glassBlur =
    glassAlpha <= DEFAULT_GLASS
      ? (glassAlpha / DEFAULT_GLASS) * 26
      : 26 + ((glassAlpha - DEFAULT_GLASS) / (100 - DEFAULT_GLASS)) * 14;
  const glassStyle = {
    '--glass-alpha': String(glassAlpha / 1000),
    '--glass-blur': glassBlur.toFixed(1) + 'px',
  } as React.CSSProperties;

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
            <Space size={14}>
              <Popover
                trigger='click'
                placement='bottomRight'
                content={
                  <div style={{ width: 250 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <span>毛玻璃浓度</span>
                      <span className='mono'>{Math.round(glassAlpha)}%</span>
                    </div>
                    <Slider min={0} max={100} value={glassAlpha} onChange={setGlassAlpha} tooltip={{ formatter: (v?: number) => (v ?? 0) + '%' }} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                      <span style={{ fontSize: 12, color: token.colorTextTertiary }}>0 = 无毛玻璃（全透明）· 默认 45 = 有毛玻璃</span>
                      <Button size='small' icon={<UndoOutlined />} onClick={() => setGlassAlpha(DEFAULT_GLASS)}>默认</Button>
                    </div>
                  </div>
                }
              >
                <Button type='text' size='small' icon={<BgColorsOutlined />} style={{ color: 'rgba(230, 237, 248, 0.72)' }}>毛玻璃</Button>
              </Popover>
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
            </Space>
          </Header>
          <Content style={{ padding: '4px 28px 28px' }}>
            {/* 单个大毛玻璃容器承载全部正文 */}
            <div className="app-glass-panel" style={glassStyle}>
              <Outlet />
            </div>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
};

export default App;