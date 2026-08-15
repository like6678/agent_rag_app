import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Input,
  InputNumber,
  Slider,
  Modal,
  Form,
  Tag,
  Popconfirm,
  Select,
  Empty,
  message,
  Typography,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  SearchOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EditOutlined,
  CloudUploadOutlined,
  HourglassOutlined,
} from '@ant-design/icons';
import { memoryApi, MemoryInfo, errorMsg } from '@/services';

const { Text, Paragraph } = Typography;

const Memory: React.FC = () => {
  const [userId, setUserId] = useState('user-001');
  const [statusFilter, setStatusFilter] = useState('active');
  const [memories, setMemories] = useState<MemoryInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<MemoryInfo | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [consolidateOpen, setConsolidateOpen] = useState(false);

  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [searchForm] = Form.useForm();
  const [consolidateForm] = Form.useForm();

  const [searchResults, setSearchResults] = useState<any[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await memoryApi.list(userId, statusFilter, 200);
      setMemories(r.memories);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [userId, statusFilter]);

  const onAdd = async () => {
    try {
      const v = await addForm.validateFields();
      const r = await memoryApi.add({
        user_id: userId,
        content: v.content,
        importance: v.importance ?? undefined,
        summary: v.summary,
      });
      if (r?.action === 'duplicated') {
        message.warning(r.message);
      } else {
        message.success('记忆已新增');
      }
      setAddOpen(false);
      addForm.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      errorMsg(e);
    }
  };

  const openEdit = (m: MemoryInfo) => {
    setEditTarget(m);
    editForm.setFieldsValue({ content: m.content, importance: m.importance_score, summary: m.summary });
    setEditOpen(true);
  };

  const onEdit = async () => {
    try {
      const v = await editForm.validateFields();
      await memoryApi.update(editTarget!.memory_id, {
        content: v.content,
        importance: v.importance,
        summary: v.summary,
      });
      message.success('记忆已更新');
      setEditOpen(false);
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      errorMsg(e);
    }
  };

  const onDelete = async (id: string) => {
    try {
      await memoryApi.remove(id);
      message.success('记忆已删除');
      load();
    } catch (e) {
      errorMsg(e);
    }
  };

  const onSearch = async () => {
    try {
      const v = await searchForm.validateFields();
      const r = await memoryApi.search({
        user_id: userId,
        query: v.query,
        top_k: v.top_k,
        min_importance: v.min_importance,
      });
      setSearchResults(r.results);
    } catch (e: any) {
      if (e?.errorFields) return;
      errorMsg(e);
    }
  };

  const onDecay = async (threshold: number) => {
    try {
      const r = await memoryApi.decay(threshold);
      message.success(r.message);
      load();
    } catch (e) {
      errorMsg(e);
    }
  };

  const onConsolidate = async () => {
    try {
      const v = await consolidateForm.validateFields();
      const r = await memoryApi.consolidate({ user_id: userId, session_id: v.session_id });
      message.success(`沉淀完成，提取 ${r.total} 条记忆`);
      setConsolidateOpen(false);
      consolidateForm.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return;
      errorMsg(e);
    }
  };

  const columns = [
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: (v: string, r: MemoryInfo) => (
        <div>
          <Text>{v}</Text>
          {r.summary && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                摘要：{r.summary}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '重要度',
      dataIndex: 'importance_score',
      width: 120,
      render: (v: number) => (
        <Tag color={v >= 0.7 ? 'red' : v >= 0.4 ? 'orange' : 'default'}>{v?.toFixed(2)}</Tag>
      ),
    },
    { title: '访问', dataIndex: 'access_count', width: 70 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
    {
      title: '最近访问',
      dataIndex: 'last_accessed_at',
      width: 160,
      render: (v: string) => v?.replace('T', ' ').slice(0, 19),
    },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: MemoryInfo) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          <Popconfirm title="删除该记忆？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => onDelete(r.memory_id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Space wrap>
          <span>用户 ID：</span>
          <Input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            style={{ width: 180 }}
            placeholder="user-001"
          />
          <span>状态：</span>
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 120 }}
            options={[
              { label: '活跃', value: 'active' },
              { label: '已遗忘', value: 'forgotten' },
              { label: '全部', value: 'all' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            新增记忆
          </Button>
          <Button icon={<SearchOutlined />} onClick={() => { setSearchOpen(true); setSearchResults([]); searchForm.resetFields(); }}>
            语义检索
          </Button>
          <Button icon={<CloudUploadOutlined />} onClick={() => setConsolidateOpen(true)}>
            沉淀
          </Button>
          <Popconfirm
            title="执行时间衰减遗忘？"
            description="将衰减后重要度低于阈值的记忆标记为 forgotten"
            okText="执行"
            cancelText="取消"
            onConfirm={() => onDecay(0.05)}
          >
            <Button icon={<HourglassOutlined />}>遗忘</Button>
          </Popconfirm>
        </Space>
      </Card>

      <Card title={`长期记忆（${memories.length} 条）`}>
        <Table
          rowKey="memory_id"
          columns={columns}
          dataSource={memories}
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          scroll={{ x: 800 }}
        />
      </Card>

      {/* 新增 */}
      <Modal title="新增长期记忆" open={addOpen} onOk={onAdd} onCancel={() => setAddOpen(false)} okText="新增" cancelText="取消" width={520}>
        <Form form={addForm} layout="vertical" initialValues={{ importance: 0.5 }}>
          <Form.Item label="记忆内容" name="content" rules={[{ required: true, message: '请输入内容' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="摘要（可选）" name="summary">
            <Input />
          </Form.Item>
          <Form.Item label="重要度（留空则 LLM 自动评分）" name="importance">
            <Slider min={0} max={1} step={0.05} marks={{ 0: '0', 0.5: '0.5', 1: '1' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑 */}
      <Modal title="编辑记忆" open={editOpen} onOk={onEdit} onCancel={() => setEditOpen(false)} okText="保存" cancelText="取消" width={520}>
        <Form form={editForm} layout="vertical">
          <Form.Item label="记忆内容" name="content" rules={[{ required: true, message: '请输入内容' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="摘要" name="summary">
            <Input />
          </Form.Item>
          <Form.Item label="重要度" name="importance">
            <Slider min={0} max={1} step={0.05} marks={{ 0: '0', 0.5: '0.5', 1: '1' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 语义检索 */}
      <Modal title="语义检索记忆" open={searchOpen} onCancel={() => setSearchOpen(false)} footer={null} width={640}>
        <Form form={searchForm} layout="inline" initialValues={{ top_k: 5, min_importance: 0 }}>
          <Form.Item label="查询" name="query" rules={[{ required: true, message: '请输入查询' }]}>
            <Input style={{ width: 220 }} />
          </Form.Item>
          <Form.Item label="top_k" name="top_k">
            <InputNumber min={1} max={20} />
          </Form.Item>
          <Form.Item label="最低重要度" name="min_importance">
            <InputNumber min={0} max={1} step={0.1} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<SearchOutlined />} onClick={onSearch}>
              检索
            </Button>
          </Form.Item>
        </Form>
        <div style={{ marginTop: 16 }}>
          {searchResults.length === 0 ? (
            <Empty description="暂无结果" />
          ) : (
            searchResults.map((r, i) => (
              <div className="search-hit" key={i}>
                <Space size="small" wrap>
                  <Tag color="blue">相似度: {(r.score ?? 0).toFixed(3)}</Tag>
                  <Tag>重要度: {(r.importance_score ?? 0).toFixed(2)}</Tag>
                </Space>
                <div style={{ marginTop: 6 }}>{r.content}</div>
              </div>
            ))
          )}
        </div>
      </Modal>

      {/* 沉淀 */}
      <Modal title="从短期记忆沉淀到长期记忆" open={consolidateOpen} onOk={onConsolidate} onCancel={() => setConsolidateOpen(false)} okText="沉淀" cancelText="取消">
        <Form form={consolidateForm} layout="vertical">
          <Form.Item
            label="会话 ID"
            name="session_id"
            rules={[{ required: true, message: '请输入会话 ID' }]}
            extra="从该会话的短期记忆中提取值得长期记住的信息"
          >
            <Input placeholder="session-xxx" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default Memory;