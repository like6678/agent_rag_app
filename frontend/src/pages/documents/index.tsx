import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Upload,
  Select,
  Button,
  Space,
  Tag,
  Popconfirm,
  message,
  Typography,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  InboxOutlined,
  EyeOutlined,
  DownloadOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { docApi, DocumentInfo, DocumentProcessResult, errorMsg } from '@/services';

const { Dragger } = Upload;
const { Text } = Typography;

const SPLIT_OPTIONS = [
  { label: '递归字符切片', value: 'recursive' },
  { label: '固定大小切片', value: 'fixed' },
  { label: '语义感知切片', value: 'semantic' },
  { label: '文档结构切片', value: 'structure' },
  { label: '句子切片', value: 'sentence' },
  { label: 'LLM 智能切片', value: 'llm' },
];

function formatSize(bytes: number) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

const Documents: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [splitMethod, setSplitMethod] = useState<string>('recursive');

  const load = async () => {
    setLoading(true);
    try {
      const d = await docApi.list();
      setDocs(d.documents);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onDelete = async (doc_id: string) => {
    try {
      const r = await docApi.remove(doc_id);
      message.success(r.message);
      load();
    } catch (e) {
      errorMsg(e);
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.pdf,.txt,.md,.docx',
    action: docApi.uploadUrl,
    data: { split_method: splitMethod },
    onChange(info) {
      const { status, response, name } = info.file;
      if (status === 'done') {
        const r = response as DocumentProcessResult;
        if (r?.duplicated) {
          message.warning(`${name}：${r.message}`);
        } else {
          message.success(`${name}：${r?.message || '上传成功'}（${r?.chunk_count} 块 / ${r?.vector_count} 向量）`);
        }
        load();
      } else if (status === 'error') {
        const detail = response?.detail || '上传失败';
        message.error(`${name}：${detail}`);
      }
    },
  };

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      ellipsis: true,
      render: (v: string, r: DocumentInfo) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatSize(r.file_size)} · {r.char_count} 字符
          </Text>
        </Space>
      ),
    },
    { title: '切片/向量', dataIndex: 'chunk_count', width: 110, render: (_: any, r: DocumentInfo) => `${r.chunk_count} / ${r.vector_count}` },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (v: string) => v?.replace('T', ' ').slice(0, 19) },
    {
      title: '操作',
      width: 160,
      render: (_: any, r: DocumentInfo) => (
        <Space size={4}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => window.open(docApi.previewUrl(r.doc_id))}>
            预览
          </Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => window.open(docApi.downloadUrl(r.doc_id))} />
          <Popconfirm title="确认删除该文档？" okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => onDelete(r.doc_id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="上传文档（MD5 自动去重 + 入库）">
        <Space style={{ marginBottom: 16 }}>
          <span>切片方式：</span>
          <Select
            value={splitMethod}
            onChange={setSplitMethod}
            options={SPLIT_OPTIONS}
            style={{ width: 180 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            支持 PDF / TXT / MD / DOCX
          </Text>
        </Space>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">支持单个或批量上传，重复文件将自动跳过</p>
        </Dragger>
      </Card>

      <Card
        title="文档列表"
        extra={
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
        }
      >
        <Table
          rowKey="doc_id"
          columns={columns}
          dataSource={docs}
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          scroll={{ x: 700 }}
        />
      </Card>
    </Space>
  );
};

export default Documents;