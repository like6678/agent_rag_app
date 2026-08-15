import React, { useEffect, useState } from 'react';
import {
  Card,
  Col,
  Row,
  Statistic,
  Input,
  InputNumber,
  Button,
  Space,
  Spin,
  Tag,
  Popconfirm,
  message,
  Empty,
} from 'antd';
import { DatabaseOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons';
import { kbApi, KBHit, errorMsg } from '@/services';

const Knowledge: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<{ collection: string; num_entities: number } | null>(null);
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(4);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<KBHit[]>([]);

  const loadStats = async () => {
    setLoading(true);
    try {
      const s = await kbApi.stats();
      setStats(s);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const onSearch = async () => {
    if (!query.trim()) {
      message.warning('请输入检索查询');
      return;
    }
    setSearching(true);
    try {
      const r = await kbApi.search(query, topK);
      setResults(r.results);
      message.success(`检索到 ${r.total} 条结果`);
    } catch (e) {
      errorMsg(e);
    } finally {
      setSearching(false);
    }
  };

  const onReset = async () => {
    try {
      const r = await kbApi.reset();
      message.success(`${r.message}（清除 ${r.cleared_documents} 条文档记录）`);
      setResults([]);
      loadStats();
    } catch (e) {
      errorMsg(e);
    }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Card>
              <Statistic
                title="向量集合"
                value={stats?.collection || '-'}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card>
              <Statistic title="向量总数" value={stats?.num_entities ?? '-'} />
            </Card>
          </Col>
        </Row>

        <Card title="检索测试（不经过 Agent / 大模型）">
          <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
            <Input
              placeholder="输入检索查询"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onPressEnter={onSearch}
              size="large"
            />
            <InputNumber
              min={1}
              max={20}
              value={topK}
              onChange={(v) => setTopK(v || 4)}
              style={{ width: 90 }}
              size="large"
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={onSearch}
              loading={searching}
              size="large"
            >
              检索
            </Button>
          </Space.Compact>

          {results.length === 0 ? (
            <Empty description="暂无检索结果" />
          ) : (
            results.map((hit, i) => (
              <div className="search-hit" key={hit.id || i}>
                <Space size="small" wrap>
                  <Tag color="blue">片段 {i + 1}</Tag>
                  <Tag>相似度: {hit.score.toFixed(3)}</Tag>
                  <Tag>来源: {hit.source || '-'}</Tag>
                  <Tag>chunk: {hit.chunk_index}</Tag>
                </Space>
                <div style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{hit.text}</div>
              </div>
            ))
          )}
        </Card>

        <Card title="危险操作">
          <Popconfirm
            title="确认清空知识库？"
            description="将删除所有向量并重建集合，同时清空文档元数据，不可恢复。"
            okText="确认清空"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={onReset}
          >
            <Button danger icon={<DeleteOutlined />}>
              清空知识库（重建集合）
            </Button>
          </Popconfirm>
        </Card>
      </Space>
    </Spin>
  );
};

export default Knowledge;