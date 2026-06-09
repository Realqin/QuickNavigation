import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tabs,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { createDictItem, deleteDictItem, fetchDictItems, updateDictItem } from '../api';
import type { DictFormValues, DictItem, DictType } from '../types';
import { DICT_TYPE_LABELS } from '../types';

const DICT_TYPES: DictType[] = ['project', 'environment', 'label'];
const PAGE_SIZE = 10;

export default function DictPage() {
  const [activeType, setActiveType] = useState<DictType>('project');
  const [data, setData] = useState<DictItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DictItem | null>(null);
  const [page, setPage] = useState(1);
  const [form] = Form.useForm<DictFormValues>();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchDictItems(activeType);
      setData(list);
      setPage(1);
    } catch {
      message.error('加载字典失败');
    } finally {
      setLoading(false);
    }
  }, [activeType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ type: activeType, sort_order: data.length });
    setModalOpen(true);
  };

  const openEdit = (record: DictItem) => {
    setEditing(record);
    form.setFieldsValue({
      type: record.type,
      name: record.name,
      description: record.description ?? undefined,
      sort_order: record.sort_order,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateDictItem(editing.id, values);
        message.success('更新成功');
      } else {
        await createDictItem(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      loadData();
    } catch {
      message.error('保存失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteDictItem(id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div className="tab-page">
      <div className="tab-page-toolbar">
        <Typography.Title level={5} style={{ margin: 0 }}>
          字典管理
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增
        </Button>
      </div>

      <Tabs
        activeKey={activeType}
        onChange={(key) => setActiveType(key as DictType)}
        items={DICT_TYPES.map((type) => ({
          key: type,
          label: DICT_TYPE_LABELS[type],
        }))}
      />

      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        pagination={{
          pageSize: PAGE_SIZE,
          current: page,
          onChange: (nextPage) => setPage(nextPage),
        }}
        columns={[
          {
            title: '序号',
            width: 72,
            render: (_value, _record, index) => (page - 1) * PAGE_SIZE + index + 1,
          },
          { title: '名称', dataIndex: 'name', ellipsis: true },
          { title: '描述', dataIndex: 'description', ellipsis: true, render: (v) => v || '-' },
          { title: '排序', dataIndex: 'sort_order', width: 80 },
          {
            title: '操作',
            width: 120,
            render: (_, record) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
                <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑字典' : '新增字典'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onOk={handleSubmit}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="type" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：测试环境" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选说明" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
