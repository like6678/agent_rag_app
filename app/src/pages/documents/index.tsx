/**
 * 文档管理页 - 上传(MD5去重) / 列表 / 下载 / 预览 / 删除
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Upload,
  message,
  Modal,
  Tag,
  Tooltip,
  Typography,
  Statistic,
  Row,
  Col,
  Select,
} from 'antd';
import {
  InboxOutlined,
  DownloadOutlined,
  EyeOutlined,
  DeleteOutlined,
  ReloadOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  ScissorOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { ColumnsType } from 'antd/es/table';
import {
  uploadDocument,
  listDocuments,
  deleteDocument,
  downloadDocumentUrl,
  previewDocumentUrl,
  DocumentInfo,
} from '@/services/api';

const { Dragger } = Upload;
const { Text } = Typography;

/** 切片方式选项(与后端一致) */
const SPLIT_METHOD_OPTIONS = [
  { value: 'recursive', label: '递归字符切片 (默认)', desc: '按分隔符递归切分,通用性强' },
  { value: 'fixed', label: '固定大小切片', desc: '按固定字符数硬切分' },
  { value: 'semantic', label: '语义感知切片', desc: '按段落/空行等语义边界切分' },
  { value: 'structure', label: '文档结构切片', desc: '按 Markdown 标题/章节切分' },
  { value: 'sentence', label: '句子切片', desc: '按句子粒度切分' },
  { value: 'llm', label: 'LLM 智能切片', desc: '用大模型按主题切分(消耗 token)' },
];

const DocumentPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [splitMethod, setSplitMethod] = useState<string>('recursive');

  /** 加载文档列表 */
  const loadDocuments = async () => {
    setLoading(true);
    try {
      const res = await listDocuments();
      setDocuments(res.documents || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  /** 自定义上传(走我们的 API) */
  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    showUploadList: false,
    accept: '.pdf,.txt,.md,.docx',
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options;
      setUploading(true);
      try {
        const res = await uploadDocument(file as File, splitMethod);
        if (res.duplicated) {
          message.warning(`文档已存在, 跳过上传: ${res.filename}`);
        } else {
          message.success(`上传成功: ${res.filename} (${res.chunk_count} 块 / ${res.vector_count} 向量)`);
        }
        onSuccess?.(res, file);
        await loadDocuments();
      } catch (err: any) {
        message.error(`上传失败: ${err?.message || '未知错误'}`);
        onError?.(err);
      } finally {
        setUploading(false);
      }
    },
  };

  /** 删除文档 */
  const handleDelete = (record: DocumentInfo) => {
    Modal.confirm({
      title: '确认删除文档?',
      content: `文件名: ${record.filename}\n将同时删除 MinIO 文件、Milvus 向量、数据库记录`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const res = await deleteDocument(record.doc_id);
          message.success(`已删除: ${res.filename} (${res.deleted_vectors} 向量)`);
          await loadDocuments();
        } catch (err: any) {
          message.error(`删除失败: ${err?.message || '未知错误'}`);
        }
      },
    });
  };

  /** 下载文档 */
  const handleDownload = (record: DocumentInfo) => {
    window.open(downloadDocumentUrl(record.doc_id), '_blank');
  };

  /** 预览文档 */
  const handlePreview = (record: DocumentInfo) => {
    window.open(previewDocumentUrl(record.doc_id), '_blank');
  };

  /** 格式化文件大小 */
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  };

  /** 格式化时间 */
  const formatTime = (t: string) => {
    if (!t) return '-';
    return t.replace('T', ' ').slice(0, 19);
  };

  // 表格列定义
  const columns: ColumnsType<DocumentInfo> = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <FileTextOutlined />
          <Text strong>{text}</Text>
        </Space>
      ),
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (size: number) => formatSize(size),
    },
    {
      title: '向量数',
      dataIndex: 'vector_count',
      key: 'vector_count',
      width: 90,
      align: 'center',
    },
    {
      title: '文本块',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 90,
      align: 'center',
    },
    {
      title: 'MD5',
      dataIndex: 'md5',
      key: 'md5',
      width: 120,
      render: (md5: string) => (
        <Tooltip title={md5}>
          <Text code style={{ fontSize: 12 }}>
            {md5?.slice(0, 12)}...
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) =>
        status === 'active' ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            正常
          </Tag>
        ) : (
          <Tag icon={<WarningOutlined />} color="warning">
            {status}
          </Tag>
        ),
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => formatTime(t),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: any, record: DocumentInfo) => (
        <Space size="small">
          <Tooltip title="预览">
            <Button size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record)} />
          </Tooltip>
          <Tooltip title="下载">
            <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(record)} />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 统计
  const totalVectors = documents.reduce((sum, d) => sum + (d.vector_count || 0), 0);
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunk_count || 0), 0);

  return (
    <div className="page-container">
      <Typography.Title level={4}>文档管理</Typography.Title>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8}>
          <Card>
            <Statistic title="文档总数" value={documents.length} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card>
            <Statistic title="文本块总数" value={totalChunks} />
          </Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card>
            <Statistic title="向量总数" value={totalVectors} />
          </Card>
        </Col>
      </Row>

      {/* 上传区 */}
      <Card title="上传文档(支持 PDF / TXT / MD / DOCX, 自动 MD5 去重)" style={{ marginBottom: 16 }}>
        {/* 切片方式选择 */}
        <Space style={{ marginBottom: 16, width: '100%' }}>
          <ScissorOutlined style={{ color: '#1677ff' }} />
          <Text strong>切片方式:</Text>
          <Select
            value={splitMethod}
            onChange={setSplitMethod}
            style={{ width: 300 }}
            options={SPLIT_METHOD_OPTIONS.map((m) => ({
              label: m.label,
              value: m.value,
            }))}
          />
          <Tooltip title={SPLIT_METHOD_OPTIONS.find((m) => m.value === splitMethod)?.desc || ''}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {SPLIT_METHOD_OPTIONS.find((m) => m.value === splitMethod)?.desc}
            </Text>
          </Tooltip>
        </Space>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
          <p className="ant-upload-hint">
            支持单次或批量上传。重复文件将自动跳过(MD5 去重)。上传后按所选切片方式切分、向量化并入库。
          </p>
        </Dragger>
      </Card>

      {/* 文档列表 */}
      <Card
        title="文档列表"
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadDocuments} loading={loading}>
            刷新
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={documents}
          rowKey="doc_id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          scroll={{ x: 900 }}
          size="middle"
          locale={{ emptyText: '暂无文档,请先上传' }}
        />
      </Card>
    </div>
  );
};

export default DocumentPage;
