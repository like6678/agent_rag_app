/**
 * 仪表盘首页 - 系统概览
 */
import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Spin, Alert, Button, Space, Typography } from 'antd';
import {
  DatabaseOutlined,
  FileTextOutlined,
  CloudServerOutlined,
  RobotOutlined,
  MessageOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { history } from '@umijs/max';
import {
  healthCheck,
  getKBStats,
  listDocuments,
  HealthData,
  KBStats,
} from '@/services/api';

const { Title, Paragraph } = Typography;

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [kbStats, setKbStats] = useState<KBStats | null>(null);
  const [docCount, setDocCount] = useState(0);

  const loadData = async () => {
    setLoading(true);
    try {
      const [h, kb, docs] = await Promise.all([
        healthCheck().catch(() => null),
        getKBStats().catch(() => null),
        listDocuments().catch(() => ({ total: 0, documents: [] })),
      ]);
      setHealth(h);
      setKbStats(kb);
      setDocCount(docs?.total || 0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="page-container">
      <Title level={4}>系统概览</Title>
      <Paragraph type="secondary">
        Agent RAG 智能问答平台 — 基于 FastAPI + Milvus + 通义千问的检索增强问答系统
      </Paragraph>

      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable>
              <Statistic
                title="后端状态"
                value={health?.status === 'healthy' ? '正常' : health?.status || '未知'}
                prefix={<CloudServerOutlined style={{ color: health?.status === 'healthy' ? '#52c41a' : '#ff4d4f' }} />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable>
              <Statistic
                title="知识库向量数"
                value={kbStats?.num_entities ?? '-'}
                prefix={<DatabaseOutlined style={{ color: '#1677ff' }} />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable>
              <Statistic
                title="文档总数"
                value={docCount}
                prefix={<FileTextOutlined style={{ color: '#722ed1' }} />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable>
              <Statistic
                title="记忆后端"
                value={health?.memory_backend || '-'}
                prefix={<RobotOutlined style={{ color: '#fa8c16' }} />}
              />
            </Card>
          </Col>
        </Row>
      </Spin>

      {!health && !loading && (
        <Alert
          style={{ marginTop: 16 }}
          type="error"
          message="后端服务未连接"
          description="请确认后端服务已启动(默认 http://localhost:8000)"
          showIcon
        />
      )}

      <Card title="快速入口" style={{ marginTop: 24 }}>
        <Space wrap size="large">
          <Button
            type="primary"
            size="large"
            icon={<MessageOutlined />}
            onClick={() => history.push('/chat')}
          >
            开始对话
          </Button>
          <Button
            size="large"
            icon={<FileTextOutlined />}
            onClick={() => history.push('/documents')}
          >
            上传文档
          </Button>
          <Button
            size="large"
            icon={<DatabaseOutlined />}
            onClick={() => history.push('/knowledge')}
          >
            知识库管理
          </Button>
          <Button size="large" icon={<ReloadOutlined />} onClick={loadData}>
            刷新数据
          </Button>
        </Space>
      </Card>

      <Card title="系统架构" style={{ marginTop: 24 }}>
        <Paragraph>
          <ul>
            <li>
              <strong>对话引擎</strong>: 通义千问 DashScope + Function Call 工具调用循环
            </li>
            <li>
              <strong>RAG 流程</strong>: 文档加载 → 文本切分 → 向量化 → Milvus 检索
            </li>
            <li>
              <strong>存储</strong>: MinIO 文件存储 + Milvus 向量库 + SQLite 文档元数据
            </li>
            <li>
              <strong>会话记忆</strong>: {health?.memory_backend === 'redis' ? 'Redis 持久化' : '内存存储(开发模式)'}
            </li>
          </ul>
        </Paragraph>
      </Card>
    </div>
  );
};

export default Dashboard;
