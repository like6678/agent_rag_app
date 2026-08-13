/**
 * RAG 配置页 - 切片/召回/重排/生成/向量库 五组参数配置
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Select,
  InputNumber,
  Switch,
  Input,
  AutoComplete,
  Button,
  Space,
  message,
  Spin,
  Collapse,
  Tag,
  Typography,
  Divider,
} from 'antd';
import {
  SaveOutlined,
  ReloadOutlined,
  UndoOutlined,
  ScissorOutlined,
  SearchOutlined,
  SortAscendingOutlined,
  RobotOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { getConfig, updateConfig, resetConfig, RAGConfig } from '@/services/api';

const { Title, Text, Paragraph } = Typography;

const ConfigPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState<Record<string, any>>({});
  const [defaults, setDefaults] = useState<Partial<RAGConfig>>({});

  /** 加载配置 */
  const loadConfig = async () => {
    setLoading(true);
    try {
      const res = await getConfig();
      form.setFieldsValue(res.config);
      setOptions(res.options || {});
      setDefaults(res.defaults || {});
    } catch (err: any) {
      message.error(`加载配置失败: ${err?.message || '未知错误'}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  /** 保存配置 */
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const res = await updateConfig(values);
      message.success(`配置已更新: ${res.updated_fields.join(', ')}`);
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验错误
      message.error(`保存失败: ${err?.message || '未知错误'}`);
    } finally {
      setSaving(false);
    }
  };

  /** 重置配置 */
  const handleReset = async () => {
    try {
      await resetConfig();
      message.success('配置已重置为默认值');
      await loadConfig();
    } catch (err: any) {
      message.error(`重置失败: ${err?.message || '未知错误'}`);
    }
  };

  // 选项渲染辅助
  const numOptions = (arr: number[]) =>
    arr.map((v) => ({ label: String(v), value: v }));

  const methodOptions = (arr: any[]) =>
    (arr || []).map((m) => ({ label: `${m.label} - ${m.desc}`, value: m.value }));

  const simpleOptions = (arr: any[]) =>
    (arr || []).map((m) => ({ label: m.desc ? `${m.label} (${m.desc})` : m.label, value: m.value }));

  const collapseItems = [
    {
      key: 'split',
      label: (
        <Space>
          <ScissorOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 500 }}>切片参数</span>
          <Text type="secondary" style={{ fontSize: 12 }}>影响文档切分质量</Text>
        </Space>
      ),
      children: (
        <>
          <Form.Item label="切片方式" name="split_method" tooltip="选择文档切分策略">
            <Select options={methodOptions(options.split_methods)} />
          </Form.Item>
          <Form.Item
            label="块大小 (chunk_size)"
            name="chunk_size"
            tooltip="考虑 Embedding 输入上限(8192 tokens)和 LLM 上下文, 500-1000 为推荐区间"
          >
            <Select options={numOptions(options.chunk_size || [])} />
          </Form.Item>
          <Form.Item label="重叠字符数" name="chunk_overlap" tooltip="相邻块的重叠, 保持上下文连贯">
            <Select options={numOptions(options.chunk_overlap || [])} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'retrieval',
      label: (
        <Space>
          <SearchOutlined style={{ color: '#52c41a' }} />
          <span style={{ fontWeight: 500 }}>召回参数</span>
          <Text type="secondary" style={{ fontSize: 12 }}>影响检索召回率</Text>
        </Space>
      ),
      children: (
        <>
          <Form.Item label="Top-K" name="retrieval_top_k" tooltip="检索返回的最相关结果数量">
            <Select options={numOptions(options.retrieval_top_k || [])} />
          </Form.Item>
          <Form.Item label="相似度度量" name="search_metric" tooltip="向量相似度计算方式">
            <Select options={simpleOptions(options.search_metrics)} />
          </Form.Item>
          <Form.Item label="nprobe" name="nprobe" tooltip="IVF 索引搜索的聚类数, 越大越精确但越慢">
            <InputNumber min={1} max={256} style={{ width: '100%' }} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'rerank',
      label: (
        <Space>
          <SortAscendingOutlined style={{ color: '#722ed1' }} />
          <span style={{ fontWeight: 500 }}>重排参数</span>
          <Text type="secondary" style={{ fontSize: 12 }}>二次精排提升精确率</Text>
        </Space>
      ),
      children: (
        <>
          <Form.Item label="启用重排" name="rerank_enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="重排方式" name="rerank_model">
            <Select options={simpleOptions(options.rerank_models)} />
          </Form.Item>
          <Form.Item label="重排后保留" name="rerank_top_k" tooltip="重排后保留的 top 结果数">
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'generation',
      label: (
        <Space>
          <RobotOutlined style={{ color: '#fa8c16' }} />
          <span style={{ fontWeight: 500 }}>生成参数</span>
          <Text type="secondary" style={{ fontSize: 12 }}>大模型回答配置</Text>
        </Space>
      ),
      children: (
        <>
          <Form.Item label="DashScope API Key" name="dashscope_api_key">
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item
            label="API Endpoint (可选)"
            name="dashscope_base_url"
            tooltip="留空=国内版(默认); 国际版 key 填 https://dashscope-intl.aliyuncs.com (路径会自动补全)"
          >
            <Input placeholder="留空=国内版; 国际版填 https://dashscope-intl.aliyuncs.com" />
          </Form.Item>
          <Form.Item
            label="对话模型"
            name="dashscope_chat_model"
            tooltip="可从下拉选择, 也可直接输入自定义模型名称(如 qwen3-max, qwen-plus 等)"
          >
            <AutoComplete
              options={(options.chat_models || []).map((m: any) => ({
                value: m.value,
                label: `${m.label}${m.desc ? ' - ' + m.desc : ''}`,
              }))}
              filterOption={(input, opt) =>
                !opt || (opt.value as string).toLowerCase().includes(input.toLowerCase())
              }
              placeholder="选择建议模型或输入自定义名称"
              allowClear
            />
          </Form.Item>
          <Form.Item label="温度 (temperature)" name="temperature" tooltip="越高越创造性, 越低越确定">
            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Agent 最大迭代" name="max_tool_iterations">
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'vector',
      label: (
        <Space>
          <DatabaseOutlined style={{ color: '#eb2f96' }} />
          <span style={{ fontWeight: 500 }}>向量库参数</span>
          <Text type="secondary" style={{ fontSize: 12 }}>嵌入模型与索引配置</Text>
        </Space>
      ),
      children: (
        <>
          <Form.Item
            label="嵌入模型"
            name="dashscope_embed_model"
            tooltip="切换建议模型后 embed_dim 自动联动; 也可直接输入自定义名称"
          >
            <AutoComplete
              options={(options.embed_models || []).map((m: any) => ({
                value: m.value,
                label: `${m.label}${m.desc ? ' - ' + m.desc : ''}`,
              }))}
              filterOption={(input, opt) =>
                !opt || (opt.value as string).toLowerCase().includes(input.toLowerCase())
              }
              placeholder="选择建议模型或输入自定义名称"
              allowClear
            />
          </Form.Item>
          <Form.Item label="向量维度" name="embed_dim" tooltip="跟随嵌入模型自动设置">
            <InputNumber disabled style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="索引类型" name="index_type">
            <Select options={simpleOptions(options.index_types)} />
          </Form.Item>
          <Form.Item label="nlist" name="nlist" tooltip="IVF 聚类中心数">
            <InputNumber min={1} max={4096} style={{ width: '100%' }} />
          </Form.Item>
        </>
      ),
    },
  ];

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>RAG 系统配置</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadConfig} loading={loading}>
            重新加载
          </Button>
          <Button icon={<UndoOutlined />} onClick={handleReset}>
            重置默认
          </Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
            保存配置
          </Button>
        </Space>
      </div>

      <Paragraph type="secondary">
        配置 RAG 系统的切片、召回、重排、生成、向量库五组参数。修改后立即生效(已入库文档需重新上传才会应用新切片参数)。
      </Paragraph>

      <Spin spinning={loading}>
        <Form form={form} layout="vertical">
          <Collapse
            defaultActiveKey={['split', 'retrieval', 'rerank', 'generation', 'vector']}
            items={collapseItems}
          />
        </Form>
      </Spin>

      <Divider />
      <Card size="small" title="参数说明">
        <Paragraph>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li><Tag color="blue">切片参数</Tag> chunk_size 建议 500-1000, 考虑 Embedding 输入上限和 LLM 上下文窗口</li>
            <li><Tag color="green">召回参数</Tag> top_k 越大召回越多但增加 LLM 输入, 建议 3-5</li>
            <li><Tag color="purple">重排参数</Tag> LLM 重排可提升精确率, 但增加延迟和 token 消耗</li>
            <li><Tag color="orange">生成参数</Tag> qwen-max 能力最强, qwen-turbo 最快; temperature 建议 0.3-0.7</li>
            <li><Tag color="magenta">向量库参数</Tag> text-embedding-v3 + IVF_FLAT 为推荐组合</li>
          </ul>
        </Paragraph>
      </Card>
    </div>
  );
};

export default ConfigPage;
