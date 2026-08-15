import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Spin, Tag, Button, Space, Typography } from 'antd';
import { useNavigate } from 'umi';
import {
  DatabaseOutlined,
  FileTextOutlined,
  CloudServerOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { healthApi, kbApi, docApi, errorMsg } from '@/services';

const { Title, Paragraph } = Typography;

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<any>(null);
  const [stats, setStats] = useState<{ num_entities: number; collection: string } | null>(null);
  const [docCount, setDocCount] = useState(0);

  const load = async () => {
    setLoading(true);
    try {
      const [h, s, d] = await Promise.all([
        healthApi.check().catch(() => null),
        kbApi.stats().catch(() => null),
        docApi.list().catch(() => null),
      ]);
      setHealth(h);
      if (s) setStats(s);
      if (d) setDocCount(d.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Title level={4} style={{ margin: 0 }}>
            Agent RAG 智能问答系统
          </Title>
          <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
            基于 FastAPI + RAG + Agent + 通义千问，采用三层记忆分层存储架构。
          </Paragraph>
        </Card>

        <Row gutter={16}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="服务状态"
                valueRender={() => (<Tag icon={<CheckCircleOutlined />} color="success">
                    {health?.status || '检测中'}
                  </Tag>)}
              />
              <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                后端: {health ? '在线' : '离线'}
              </Paragraph>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="知识库向量数"
                value={stats?.num_entities ?? '-'}
                prefix={<DatabaseOutlined />}
              />
              <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                集合: {stats?.collection || '-'}
              </Paragraph>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="已上传文档"
                value={docCount}
                prefix={<FileTextOutlined />}
              />
              <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                文档元数据条目
              </Paragraph>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="记忆后端"
                value={health?.memory_backend || '-'}
                prefix={<CloudServerOutlined />}
              />
              <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                短期会话记忆存储
              </Paragraph>
            </Card>
          </Col>
        </Row>

        <Card title="快速入口">
          <Space wrap>
            <Button type="primary" onClick={() => navigate('/chat')}>
              开始对话
            </Button>
            <Button onClick={() => navigate('/documents')}>上传文档</Button>
            <Button onClick={() => navigate('/knowledge')}>检索测试</Button>
            <Button onClick={() => navigate('/config')}>RAG 配置</Button>
            <Button onClick={() => navigate('/memory')}>长期记忆</Button>
            <Button onClick={() => navigate('/evaluation')}>系统评测</Button>
          </Space>
        </Card>
      </Space>
    </Spin>
  );
};

export default Dashboard;