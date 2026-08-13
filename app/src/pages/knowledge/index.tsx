/**
 * 知识库管理页 - 统计 / 检索测试 / 清空
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  Button,
  Input,
  InputNumber,
  Space,
  Typography,
  Statistic,
  Row,
  Col,
  Modal,
  message,
  Spin,
  Empty,
  Tag,
  Divider,
  Tooltip,
} from 'antd';
import {
  DatabaseOutlined,
  SearchOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import {
  getKBStats,
  resetCollection,
  searchKnowledge,
  KBStats,
  SearchResultItem,
} from '@/services/api';

const { Title, Paragraph, Text } = Typography;

const KnowledgePage: React.FC = () => {
  const [stats, setStats] = useState<KBStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);

  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(4);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);

  /** 加载统计 */
  const loadStats = async () => {
    setLoadingStats(true);
    try {
      const res = await getKBStats();
      setStats(res);
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  /** 检索测试 */
  const handleSearch = async () => {
    if (!query.trim()) {
      message.warning('请输入检索查询');
      return;
    }
    setSearching(true);
    try {
      const res = await searchKnowledge(query, topK);
      setResults(res.results || []);
      if (res.results.length === 0) {
        message.info('未找到相关结果');
      }
    } catch (err: any) {
      message.error(`检索失败: ${err?.message || '未知错误'}`);
    } finally {
      setSearching(false);
    }
  };

  /** 清空知识库(危险操作) */
  const handleReset = () => {
    Modal.confirm({
      title: '⚠️ 危险操作: 清空知识库',
      content: (
        <div>
          <Paragraph type="danger" strong>
            此操作将删除知识库中的所有向量和文档元数据,不可恢复!
          </Paragraph>
          <ul>
            <li>Milvus 集合将被删除并重建</li>
            <li>数据库中的文档记录将被清空</li>
            <li>MinIO 中的文件不会被删除(需在文档管理页单独删除)</li>
          </ul>
        </div>
      ),
      okText: '确认清空',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const res = await resetCollection();
          message.success(`知识库已清空 (删除 ${res.cleared_documents} 条文档记录)`);
          await loadStats();
          setResults([]);
        } catch (err: any) {
          message.error(`清空失败: ${err?.message || '未知错误'}`);
        }
      },
    });
  };

  /** 格式化相似度分数 */
  const formatScore = (score: number) => {
    return (score * 100).toFixed(2) + '%';
  };

  return (
    <div className="page-container">
      <Title level={4}>知识库管理</Title>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12}>
          <Card>
            <Spin spinning={loadingStats}>
              <Statistic
                title="向量集合"
                value={stats?.collection || '-'}
                prefix={<DatabaseOutlined style={{ color: '#1677ff' }} />}
              />
            </Spin>
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card>
            <Spin spinning={loadingStats}>
              <Statistic
                title="向量总数"
                value={stats?.num_entities ?? 0}
                prefix={<ThunderboltOutlined style={{ color: '#722ed1' }} />}
              />
            </Spin>
          </Card>
        </Col>
      </Row>

      {/* 检索测试 */}
      <Card
        title={
          <Space>
            <ExperimentOutlined />
            <span>检索测试</span>
          </Space>
        }
        style={{ marginTop: 24 }}
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadStats} loading={loadingStats}>
            刷新统计
          </Button>
        }
      >
        <Paragraph type="secondary">
          直接对知识库进行向量检索(不经过 Agent / 大模型), 用于验证文档入库效果。相似度基于 COSINE 距离。
        </Paragraph>

        <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
          <Input
            placeholder="输入检索查询, 例如: 什么是 RAG?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={handleSearch}
            size="large"
            prefix={<SearchOutlined />}
          />
          <Tooltip title="返回结果数量">
            <InputNumber
              min={1}
              max={20}
              value={topK}
              onChange={(v) => setTopK(v || 4)}
              size="large"
              style={{ width: 90 }}
            />
          </Tooltip>
          <Button
            type="primary"
            size="large"
            icon={<SearchOutlined />}
            onClick={handleSearch}
            loading={searching}
          >
            检索
          </Button>
        </Space.Compact>

        {/* 检索结果 */}
        <Spin spinning={searching}>
          {results.length === 0 ? (
            <Empty description="暂无检索结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div>
              <Divider>
                <Tag color="blue">共 {results.length} 条结果</Tag>
              </Divider>
              {results.map((item, idx) => (
                <div className="search-result-item" key={item.id || idx}>
                  <Space
                    style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}
                  >
                    <Space>
                      <Tag color="purple">#{idx + 1}</Tag>
                      <Text type="secondary">来源: {item.source}</Text>
                    </Space>
                    <Space>
                      <Text type="secondary">相似度:</Text>
                      <span className="search-result-score">{formatScore(item.score)}</span>
                    </Space>
                  </Space>
                  <div
                    style={{
                      background: '#fff',
                      padding: '8px 12px',
                      borderRadius: 4,
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.6,
                      border: '1px solid #f0f0f0',
                    }}
                  >
                    {item.text}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: '#999' }}>
                    chunk_index: {item.chunk_index} · doc_id: {item.doc_id?.slice(0, 8)}...
                  </div>
                </div>
              ))}
            </div>
          )}
        </Spin>
      </Card>

      {/* 危险操作区 */}
      <Card
        title={<span style={{ color: '#ff4d4f' }}>⚠️ 危险操作</span>}
        style={{ marginTop: 24, borderColor: '#ffccc7' }}
      >
        <Space>
          <Text>清空知识库: 删除所有向量并重建集合</Text>
          <Button danger icon={<DeleteOutlined />} onClick={handleReset}>
            清空知识库
          </Button>
        </Space>
      </Card>
    </div>
  );
};

export default KnowledgePage;
