import React, { useEffect, useState } from 'react';
import {
  Tabs,
  Card,
  Table,
  Button,
  Tag,
  Space,
  Switch,
  Popconfirm,
  Upload,
  message,
  Typography,
  theme,
  Spin,
  Empty,
  Tooltip,
} from 'antd';
import {
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
  ImportOutlined,
} from '@ant-design/icons';
import { skillApi, SkillInfo, SkillStoreItem, errorMsg } from '@/services';

const { Title, Paragraph, Text } = Typography;

const SkillsPage: React.FC = () => {
  const { token } = theme.useToken();
  const [tab, setTab] = useState('store');
  const [store, setStore] = useState<SkillStoreItem[]>([]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, list] = await Promise.all([skillApi.store(), skillApi.list()]);
      setStore(s);
      setSkills(list);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onInstall = async (item: SkillStoreItem) => {
    try {
      const r = await skillApi.install(item.name);
      message.success(r.message);
      await load();
    } catch (e) {
      errorMsg(e);
    }
  };

  const onToggle = async (s: SkillInfo, enabled: boolean) => {
    try {
      const r = await skillApi.setEnabled(s.id, enabled);
      message.success(r.message);
      setSkills((prev) => prev.map((x) => (x.id === s.id ? { ...x, enabled } : x)));
    } catch (e) {
      errorMsg(e);
    }
  };

  const onUninstall = async (s: SkillInfo) => {
    try {
      const r = await skillApi.remove(s.id);
      message.success(r.message);
      await load();
    } catch (e) {
      errorMsg(e);
    }
  };

  const onImport = async (file: File) => {
    try {
      const r = await skillApi.importSkill(file);
      message.success(r.message);
      await load();
    } catch (e) {
      errorMsg(e);
    }
    return false;
  };

  const cardStyle: React.CSSProperties = {
    background: 'rgba(255,255,255, calc(var(--glass-alpha, 0.045) * 1.1))',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 18,
    boxShadow: '0 8px 26px rgba(0,0,0,0.18)',
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <Title level={4} style={{ marginTop: 4, marginBottom: 4 }}>
        <ThunderboltOutlined style={{ marginRight: 8, color: token.colorPrimary }} />
        技能中心
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        从应用商店一键安装开箱即用的技能，或导入自定义技能（ZIP / SKILL.md）。技能可在智能对话中显式选择或由 AI 按意图自动调用，并支持生成文档（MD/PDF）一键下载。
      </Paragraph>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        tabBarExtraContent={
          <Space>
            <Upload
              accept=".zip,.md,.markdown"
              showUploadList={false}
              beforeUpload={onImport}
            >
              <Button type="primary" ghost icon={<ImportOutlined />}>
                导入技能
              </Button>
            </Upload>
          </Space>
        }
      >
        <Tabs.TabPane tab="应用商店" key="store">
          <Spin spinning={loading}>
            {store.length === 0 ? (
              <Empty description="商店暂无可用技能" style={{ marginTop: 60 }} />
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
                {store.map((item) => (
                  <Card key={item.name} size="small" style={cardStyle} styles={{ body: { padding: 16 } }}>
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Text strong style={{ fontSize: 15 }}>{item.display_name}</Text>
                        <Tag color="blue">{item.version}</Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12, minHeight: 40, display: 'block' }}>
                        {item.description}
                      </Text>
                      <Space>
                        {item.tags.map((t) => (
                          <Tag key={t} style={{ background: 'rgba(41,151,255,0.12)', border: 'none' }}>{t}</Tag>
                        ))}
                      </Space>
                      <Button
                        type={item.installed ? 'default' : 'primary'}
                        size="small"
                        icon={item.installed ? <CheckCircleOutlined /> : <DownloadOutlined />}
                        disabled={item.installed}
                        onClick={() => onInstall(item)}
                        style={{ width: '100%' }}
                      >
                        {item.installed ? '已安装' : '安装'}
                      </Button>
                    </Space>
                  </Card>
                ))}
              </div>
            )}
          </Spin>
        </Tabs.TabPane>

        <Tabs.TabPane tab="我的技能" key="mine">
          <Card style={cardStyle} size="small">
            <Table<SkillInfo>
              rowKey="id"
              loading={loading}
              dataSource={skills}
              pagination={false}
              locale={{ emptyText: <Empty description="尚未安装技能" /> }}
              columns={[
                {
                  title: '技能',
                  dataIndex: 'display_name',
                  render: (_, s) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{s.display_name}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>{s.name}</Text>
                    </Space>
                  ),
                },
                { title: '描述', dataIndex: 'description', ellipsis: true },
                {
                  title: '来源',
                  dataIndex: 'source',
                  width: 90,
                  render: (v: string) => <Tag color={v === 'store' ? 'blue' : 'green'}>{v === 'store' ? '商店' : '导入'}</Tag>,
                },
                { title: '版本', dataIndex: 'version', width: 80 },
                { title: '使用次数', dataIndex: 'used_count', width: 90 },
                {
                  title: '启用',
                  dataIndex: 'enabled',
                  width: 80,
                  render: (v: boolean, s) => (
                    <Switch
                      size="small"
                      checked={v}
                      onChange={(c) => onToggle(s, c)}
                    />
                  ),
                },
                {
                  title: '操作',
                  width: 100,
                  render: (_, s) => (
                    <Popconfirm
                      title="确认卸载该技能？"
                      description="将删除技能及其资产文件"
                      onConfirm={() => onUninstall(s)}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />}>卸载</Button>
                    </Popconfirm>
                  ),
                },
              ]}
            />
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default SkillsPage;