import React, { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Select,
  InputNumber,
  Input,
  Switch,
  Slider,
  Button,
  Space,
  Spin,
  Tag,
  Row,
  Col,
  message,
} from 'antd';
import { SaveOutlined, UndoOutlined } from '@ant-design/icons';
import { configApi, RAGConfig, ConfigOption, errorMsg } from '@/services';

const numberOptions = (arr: number[]) =>
  arr.map((v) => ({ label: String(v), value: v }));

const objOptions = (arr: ConfigOption[]) =>
  arr.map((o) => ({ label: `${o.label}（${o.desc}）`, value: o.value }));

const ConfigPage: React.FC = () => {
  const [form] = Form.useForm<RAGConfig>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState<Record<string, any>>({});
  const [config, setConfig] = useState<RAGConfig | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await configApi.get();
      setOptions(data.options);
      setConfig(data.config);
      form.setFieldsValue(data.config);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const r = await configApi.update(values as Partial<RAGConfig>);
      message.success(`${r.message}：${r.updated_fields.join(', ')}`);
      setConfig(r.config);
      form.setFieldsValue(r.config);
    } catch (e: any) {
      if (e?.errorFields) return;
      errorMsg(e);
    } finally {
      setSaving(false);
    }
  };

  const onReset = async () => {
    try {
      setSaving(true);
      const r = await configApi.reset();
      message.success(r.message);
      setConfig(r.config);
      form.setFieldsValue(r.config);
    } catch (e) {
      errorMsg(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <Form
        form={form}
        layout="vertical"
        style={{ maxWidth: 900 }}
      >
        <Card title="切片参数" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item label="切片方式" name="split_method">
                <Select options={objOptions(options.split_methods || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item label="块大小 (chunk_size)" name="chunk_size">
                <Select options={numberOptions(options.chunk_size || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item label="重叠 (chunk_overlap)" name="chunk_overlap">
                <Select options={numberOptions(options.chunk_overlap || [])} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card title="召回参数" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={6}>
              <Form.Item label="返回数量 (top_k)" name="retrieval_top_k">
                <Select options={numberOptions(options.retrieval_top_k || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={6}>
              <Form.Item label="相似度度量" name="search_metric">
                <Select options={objOptions(options.search_metrics || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={6}>
              <Form.Item label="nprobe" name="nprobe">
                <InputNumber min={1} max={256} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card title="重排参数" style={{ marginBottom: 16 }}>
          <Row gutter={16} align="middle">
            <Col xs={24} sm={6}>
              <Form.Item label="启用重排" name="rerank_enabled" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={24} sm={10}>
              <Form.Item label="重排模型" name="rerank_model">
                <Select options={objOptions(options.rerank_models || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={6}>
              <Form.Item label="重排保留数 (top_k)" name="rerank_top_k">
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card title="生成参数" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item label="对话模型" name="dashscope_chat_model">
                <Select options={objOptions(options.chat_models || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                label={
                  <Space>
                    嵌入模型
                    {config && <Tag color="blue">维度 {config.embed_dim}</Tag>}
                  </Space>
                }
                name="dashscope_embed_model"
              >
                <Select options={objOptions(options.embed_models || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label={`温度 (temperature)`} name="temperature">
                <Slider min={0} max={2} step={0.1} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="最大工具迭代" name="max_tool_iterations">
                <InputNumber min={1} max={20} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="Base URL（空=默认国内版）" name="dashscope_base_url">
                <Input placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label="API Key" name="dashscope_api_key">
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card title="向量库参数" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item label="索引类型" name="index_type">
                <Select options={objOptions(options.index_types || [])} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item label="nlist" name="nlist">
                <InputNumber min={1} max={4096} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Space>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={onSave}>
            保存配置
          </Button>
          <Button icon={<UndoOutlined />} loading={saving} onClick={onReset}>
            重置默认
          </Button>
        </Space>
      </Form>
    </Spin>
  );
};

export default ConfigPage;