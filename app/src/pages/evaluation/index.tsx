/**
 * RAG 评测页 - 测试集提交 + 五维度评测报告
 */
import React, { useState } from 'react';
import {
  Card,
  Button,
  Space,
  Input,
  Table,
  message,
  Spin,
  Statistic,
  Row,
  Col,
  Progress,
  Tag,
  Typography,
  Divider,
  Empty,
  Tooltip,
  Collapse,
} from 'antd';
import {
  PlayCircleOutlined,
  PlusOutlined,
  DeleteOutlined,
  TrophyOutlined,
  RadarChartOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { runEvaluation, EvalTestItem, EvalReport, EvalResultItem } from '@/services/api';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

interface TestRow extends EvalTestItem {
  key: string;
}

const EvaluationPage: React.FC = () => {
  const [testRows, setTestRows] = useState<TestRow[]>([
    { key: '1', question: '', expected_answer: '', expected_source: '' },
  ]);
  const [bulkText, setBulkText] = useState('');
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<EvalReport | null>(null);

  /** 添加测试行 */
  const addRow = () => {
    setTestRows((prev) => [
      ...prev,
      { key: String(Date.now()), question: '', expected_answer: '', expected_source: '' },
    ]);
  };

  /** 删除测试行 */
  const removeRow = (key: string) => {
    setTestRows((prev) => prev.filter((r) => r.key !== key));
  };

  /** 更新测试行 */
  const updateRow = (key: string, field: keyof TestRow, value: string) => {
    setTestRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)),
    );
  };

  /** 从批量JSON导入 */
  const importBulk = () => {
    try {
      const items = JSON.parse(bulkText);
      if (!Array.isArray(items)) {
        message.error('JSON 必须是数组格式');
        return;
      }
      const rows: TestRow[] = items.map((item: any, idx: number) => ({
        key: String(Date.now()) + idx,
        question: item.question || '',
        expected_answer: item.expected_answer || '',
        expected_source: item.expected_source || '',
      }));
      setTestRows(rows);
      message.success(`已导入 ${rows.length} 条测试项`);
      setBulkText('');
    } catch (err: any) {
      message.error(`JSON 解析失败: ${err.message}`);
    }
  };

  /** 执行评测 */
  const handleRun = async () => {
    const validItems = testRows.filter((r) => r.question.trim());
    if (validItems.length === 0) {
      message.warning('请至少添加一个测试问题');
      return;
    }

    setRunning(true);
    setReport(null);
    try {
      const testItems: EvalTestItem[] = validItems.map((r) => ({
        question: r.question,
        expected_answer: r.expected_answer,
        expected_source: r.expected_source,
      }));
      const res = await runEvaluation(testItems);
      setReport(res);
      message.success(`评测完成: 综合评分 ${res.overall_score}`);
    } catch (err: any) {
      message.error(`评测失败: ${err?.message || '未知错误'}`);
    } finally {
      setRunning(false);
    }
  };

  // 维度颜色映射
  const dimColors = ['#1677ff', '#52c41a', '#722ed1', '#fa8c16', '#eb2f96'];
  const scoreColor = (s: number) =>
    s >= 0.8 ? '#52c41a' : s >= 0.6 ? '#faad14' : '#ff4d4f';

  // 详细结果表格列
  const resultColumns: ColumnsType<EvalResultItem> = [
    {
      title: '#',
      width: 50,
      render: (_: any, __: any, idx: number) => idx + 1,
    },
    {
      title: '问题',
      dataIndex: 'question',
      key: 'question',
      ellipsis: true,
      width: 200,
    },
    {
      title: '生成回答',
      dataIndex: 'generated_answer',
      key: 'generated_answer',
      ellipsis: true,
      width: 250,
      render: (text: string) => <Text style={{ fontSize: 12 }}>{text}</Text>,
    },
    {
      title: '召回',
      dataIndex: 'recall_hit',
      key: 'recall_hit',
      width: 70,
      align: 'center',
      render: (hit: boolean) =>
        hit ? (
          <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
        ) : (
          <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 16 }} />
        ),
    },
    {
      title: '上下文相关性',
      dataIndex: 'context_relevance',
      key: 'context_relevance',
      width: 130,
      render: (v: number) => (
        <Progress percent={Math.round(v * 100)} size="small" strokeColor={scoreColor(v)} />
      ),
    },
    {
      title: '回答忠实度',
      dataIndex: 'answer_faithfulness',
      key: 'answer_faithfulness',
      width: 130,
      render: (v: number) => (
        <Progress percent={Math.round(v * 100)} size="small" strokeColor={scoreColor(v)} />
      ),
    },
    {
      title: '回答相关性',
      dataIndex: 'answer_relevance',
      key: 'answer_relevance',
      width: 130,
      render: (v: number) => (
        <Progress percent={Math.round(v * 100)} size="small" strokeColor={scoreColor(v)} />
      ),
    },
  ];

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>RAG 系统评测</Title>
        <Button
          type="primary"
          size="large"
          icon={<PlayCircleOutlined />}
          onClick={handleRun}
          loading={running}
        >
          执行评测
        </Button>
      </div>

      <Paragraph type="secondary">
        提交测试问答集, 系统将执行完整 RAG 流程(检索→重排→生成), 并用 LLM 从五个维度自动评测系统优劣。
      </Paragraph>

      {/* 测试集输入 */}
      <Card
        title={
          <Space>
            <PlusOutlined />
            <span>测试集</span>
            <Tag color="blue">{testRows.filter((r) => r.question.trim()).length} 条有效</Tag>
          </Space>
        }
        extra={
          <Space>
            <Button size="small" icon={<PlusOutlined />} onClick={addRow}>
              添加
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          dataSource={testRows}
          rowKey="key"
          pagination={false}
          size="small"
          columns={[
            {
              title: '问题',
              dataIndex: 'question',
              render: (_: any, record: TestRow) => (
                <Input
                  value={record.question}
                  onChange={(e) => updateRow(record.key, 'question', e.target.value)}
                  placeholder="测试问题"
                  size="small"
                />
              ),
            },
            {
              title: '期望答案',
              dataIndex: 'expected_answer',
              width: 250,
              render: (_: any, record: TestRow) => (
                <Input
                  value={record.expected_answer}
                  onChange={(e) => updateRow(record.key, 'expected_answer', e.target.value)}
                  placeholder="期望答案(可选)"
                  size="small"
                />
              ),
            },
            {
              title: '期望来源',
              dataIndex: 'expected_source',
              width: 150,
              render: (_: any, record: TestRow) => (
                <Input
                  value={record.expected_source}
                  onChange={(e) => updateRow(record.key, 'expected_source', e.target.value)}
                  placeholder="来源文件(可选)"
                  size="small"
                />
              ),
            },
            {
              title: '',
              width: 50,
              render: (_: any, record: TestRow) => (
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => removeRow(record.key)}
                  disabled={testRows.length <= 1}
                />
              ),
            },
          ]}
        />

        <Collapse
          style={{ marginTop: 12 }}
          items={[
            {
              key: 'bulk',
              label: '批量导入 (JSON 数组格式)',
              children: (
                <Space.Compact style={{ width: '100%' }}>
                  <TextArea
                    value={bulkText}
                    onChange={(e) => setBulkText(e.target.value)}
                    placeholder={'[{"question":"什么是RAG?","expected_answer":"检索增强生成"}]'}
                    autoSize={{ minRows: 2, maxRows: 6 }}
                  />
                  <Button type="primary" onClick={importBulk} style={{ marginLeft: 8 }}>
                    导入
                  </Button>
                </Space.Compact>
              ),
            },
          ]}
        />
      </Card>

      {/* 评测结果 */}
      <Spin spinning={running} tip="评测中, 请耐心等待...">
        {report ? (
          <>
            {/* 综合评分 */}
            <Card style={{ marginBottom: 16 }}>
              <Row gutter={16} align="middle">
                <Col xs={24} sm={6} style={{ textAlign: 'center' }}>
                  <Statistic
                    title="综合评分"
                    value={report.overall_score}
                    precision={2}
                    prefix={<TrophyOutlined style={{ color: scoreColor(report.overall_score) }} />}
                    valueStyle={{ color: scoreColor(report.overall_score), fontSize: 36 }}
                  />
                </Col>
                <Col xs={12} sm={4}>
                  <Statistic title="召回率" value={report.recall_rate} precision={2} suffix="" valueStyle={{ color: scoreColor(report.recall_rate) }} />
                </Col>
                <Col xs={12} sm={5}>
                  <Statistic title="上下文相关性" value={report.avg_context_relevance} precision={2} valueStyle={{ color: scoreColor(report.avg_context_relevance) }} />
                </Col>
                <Col xs={12} sm={5}>
                  <Statistic title="回答忠实度" value={report.avg_answer_faithfulness} precision={2} valueStyle={{ color: scoreColor(report.avg_answer_faithfulness) }} />
                </Col>
                <Col xs={12} sm={4}>
                  <Statistic title="回答相关性" value={report.avg_answer_relevance} precision={2} valueStyle={{ color: scoreColor(report.avg_answer_relevance) }} />
                </Col>
              </Row>
            </Card>

            {/* 五维度评分 */}
            <Card
              title={
                <Space>
                  <RadarChartOutlined />
                  <span>五维度评测</span>
                </Space>
              }
              style={{ marginBottom: 16 }}
            >
              <Row gutter={[16, 16]}>
                {report.dimensions.map((dim, idx) => (
                  <Col xs={24} sm={12} lg={8} xl={4} key={idx}>
                    <Card
                      size="small"
                      style={{ textAlign: 'center', borderColor: dimColors[idx % 5] + '40' }}
                    >
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>{dim.name}</Text>
                      <Progress
                        type="dashboard"
                        percent={Math.round(dim.score * 100)}
                        size={120}
                        strokeColor={scoreColor(dim.score)}
                      />
                      <Tooltip title={dim.detail}>
                        <Text
                          type="secondary"
                          style={{ fontSize: 11, display: 'block', marginTop: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        >
                          {dim.detail}
                        </Text>
                      </Tooltip>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>

            {/* 详细结果 */}
            <Card title={`详细结果 (${report.total} 项)`}>
              <Table
                columns={resultColumns}
                dataSource={report.items}
                rowKey={(_, idx) => String(idx)}
                pagination={{ pageSize: 10 }}
                scroll={{ x: 900 }}
                size="small"
                expandable={{
                  expandedRowRender: (record: EvalResultItem) => (
                    <div style={{ padding: 8 }}>
                      <Paragraph strong>检索上下文:</Paragraph>
                      <Paragraph type="secondary" style={{ fontSize: 12, whiteSpace: 'pre-wrap', maxHeight: 150, overflow: 'auto' }}>
                        {record.retrieved_context || '(空)'}
                      </Paragraph>
                      <Divider style={{ margin: '8px 0' }} />
                      <Paragraph strong>完整回答:</Paragraph>
                      <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{record.generated_answer}</Paragraph>
                    </div>
                  ),
                }}
              />
            </Card>
          </>
        ) : (
          !running && (
            <Card>
              <Empty description="点击「执行评测」开始评测" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </Card>
          )
        )}
      </Spin>
    </div>
  );
};

export default EvaluationPage;
