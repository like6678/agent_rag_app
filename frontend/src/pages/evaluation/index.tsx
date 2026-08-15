import React, { useState } from 'react';
import {
  Card,
  Button,
  Space,
  Input,
  Table,
  Statistic,
  Col,
  Row,
  Progress,
  Tag,
  Empty,
  Spin,
  Popconfirm,
  message,
  Typography,
} from 'antd';
import { PlayCircleOutlined, PlusOutlined, DeleteOutlined, ExperimentOutlined } from '@ant-design/icons';
import { evalApi, EvalTestItem, EvalReport, errorMsg } from '@/services';

const { Text, Paragraph } = Typography;

interface Row extends EvalTestItem {
  key: string;
}

const Evaluation: React.FC = () => {
  const [items, setItems] = useState<Row[]>([
    { key: '1', question: '', expected_answer: '', expected_source: '' },
  ]);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<EvalReport | null>(null);

  const update = (key: string, field: keyof EvalTestItem, value: string) => {
    setItems((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)));
  };
  const addRow = () =>
    setItems((prev) => [...prev, { key: Date.now().toString(), question: '', expected_answer: '', expected_source: '' }]);
  const removeRow = (key: string) => setItems((prev) => prev.filter((r) => r.key !== key));

  const fillSample = () =>
    setItems([
      { key: '1', question: '什么是 RAG？', expected_answer: '检索增强生成', expected_source: '' },
      { key: '2', question: '系统支持哪些文档格式？', expected_answer: 'PDF/TXT/MD/DOCX', expected_source: '' },
    ]);

  const onRun = async () => {
    const valid = items.filter((r) => r.question.trim());
    if (valid.length === 0) {
      message.warning('请至少填写一个测试问题');
      return;
    }
    setRunning(true);
    setReport(null);
    try {
      const r = await evalApi.run({
        test_items: valid.map(({ key, ...rest }) => rest),
        use_current_config: true,
      });
      setReport(r);
      message.success('评测完成');
    } catch (e) {
      errorMsg(e);
    } finally {
      setRunning(false);
    }
  };

  const columns = [
    {
      title: '问题',
      dataIndex: 'question',
      width: '35%',
      render: (_: any, r: Row) => (
        <Input value={r.question} onChange={(e) => update(r.key, 'question', e.target.value)} placeholder="测试问题" />
      ),
    },
    {
      title: '期望答案',
      dataIndex: 'expected_answer',
      width: '25%',
      render: (_: any, r: Row) => (
        <Input value={r.expected_answer} onChange={(e) => update(r.key, 'expected_answer', e.target.value)} />
      ),
    },
    {
      title: '期望来源',
      dataIndex: 'expected_source',
      width: '25%',
      render: (_: any, r: Row) => (
        <Input value={r.expected_source} onChange={(e) => update(r.key, 'expected_source', e.target.value)} />
      ),
    },
    {
      title: '',
      width: 60,
      render: (_: any, r: Row) => (
        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeRow(r.key)} disabled={items.length === 1} />
      ),
    },
  ];

  const scoreColor = (s: number) => (s >= 0.8 ? '#52c41a' : s >= 0.6 ? '#faad14' : '#ff4d4f');

  return (
    <Spin spinning={running} tip="评测进行中…">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card
          title="测试问答集"
          extra={
            <Space>
              <Button icon={<ExperimentOutlined />} onClick={fillSample}>
                示例
              </Button>
              <Button icon={<PlusOutlined />} onClick={addRow}>
                添加
              </Button>
            </Space>
          }
        >
          <Table
            rowKey="key"
            columns={columns}
            dataSource={items}
            pagination={false}
            size="small"
            scroll={{ x: 600 }}
          />
          <div style={{ marginTop: 16 }}>
            <Popconfirm title="确认运行评测？" okText="运行" cancelText="取消" onConfirm={onRun}>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={running}>
                运行评测
              </Button>
            </Popconfirm>
          </div>
        </Card>

        {report && (
          <>
            <Card title="评测总览">
              <Row gutter={16}>
                <Col xs={12} sm={8} md={4}>
                  <Statistic
                    title="综合评分"
                    value={report.overall_score}
                    precision={2}
                    valueStyle={{ color: scoreColor(report.overall_score) }}
                  />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Statistic title="召回率" value={report.recall_rate} precision={2} />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Statistic title="上下文相关性" value={report.avg_context_relevance} precision={2} />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Statistic title="回答忠实度" value={report.avg_answer_faithfulness} precision={2} />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Statistic title="回答相关性" value={report.avg_answer_relevance} precision={2} />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Statistic title="测试项数" value={report.total} />
                </Col>
              </Row>
            </Card>

            <Card title="五维度评分">
              {report.dimensions.length === 0 ? (
                <Empty />
              ) : (
                report.dimensions.map((d, i) => (
                  <div key={i} style={{ marginBottom: 16 }}>
                    <div style={{ marginBottom: 4 }}>
                      <Text strong>{d.name}</Text>
                      <Tag color={scoreColor(d.score)} style={{ marginLeft: 8 }}>
                        {d.score.toFixed(2)}
                      </Tag>
                    </div>
                    <Progress percent={Math.round(d.score * 100)} strokeColor={scoreColor(d.score)} />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {d.detail}
                    </Text>
                  </div>
                ))
              )}
            </Card>

            <Card title="逐项结果">
              <Table
                rowKey={(_, i) => String(i)}
                size="small"
                pagination={{ pageSize: 10 }}
                scroll={{ x: 800 }}
                dataSource={report.items}
                columns={[
                  { title: '问题', dataIndex: 'question', ellipsis: true, width: 200 },
                  {
                    title: '召回',
                    dataIndex: 'recall_hit',
                    width: 70,
                    render: (v: boolean) => (v ? <Tag color="green">命中</Tag> : <Tag color="red">未中</Tag>),
                  },
                  { title: '上下文相关', dataIndex: 'context_relevance', width: 110, render: (v: number) => v?.toFixed(2) },
                  { title: '忠实度', dataIndex: 'answer_faithfulness', width: 90, render: (v: number) => v?.toFixed(2) },
                  { title: '相关性', dataIndex: 'answer_relevance', width: 90, render: (v: number) => v?.toFixed(2) },
                  {
                    title: '生成回答',
                    dataIndex: 'generated_answer',
                    ellipsis: true,
                    render: (v: string) => <Text type="secondary">{v}</Text>,
                  },
                ]}
              />
            </Card>
          </>
        )}
      </Space>
    </Spin>
  );
};

export default Evaluation;