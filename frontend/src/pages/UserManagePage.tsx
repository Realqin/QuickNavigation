import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Switch,
  Table,
  Tree,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DataNode } from 'antd/es/tree';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createUser, deleteUser, fetchMenuPermissions, fetchUsers, updateUser } from '../api';
import type { MenuPermissionNode, UserFormValues, UserInfo } from '../types/auth';
import { ALL_MENU_PERMISSION_KEYS } from '../types/auth';
import { showApiError } from '../utils/apiError';
import { formatBeijingTime } from '../utils/dateTime';

function toTreeData(nodes: MenuPermissionNode[]): DataNode[] {
  return nodes.map((node) => ({
    key: node.key,
    title: node.title,
    children: node.children ? toTreeData(node.children) : undefined,
  }));
}

function collectLeafKeys(nodes: MenuPermissionNode[]): string[] {
  const keys: string[] = [];
  for (const node of nodes) {
    if (node.children?.length) {
      keys.push(...collectLeafKeys(node.children));
    } else {
      keys.push(node.key);
    }
  }
  return keys;
}

export default function UserManagePage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<UserInfo[]>([]);
  const [permissionTree, setPermissionTree] = useState<MenuPermissionNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<UserInfo | null>(null);
  const [form] = Form.useForm<UserFormValues>();

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const [users, tree] = await Promise.all([fetchUsers(), fetchMenuPermissions()]);
      setItems(users);
      setPermissionTree(tree);
    } catch (error) {
      showApiError(error, '加载用户列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const treeData = useMemo(() => toTreeData(permissionTree), [permissionTree]);
  const allLeafKeys = useMemo(
    () => (permissionTree.length ? collectLeafKeys(permissionTree) : ALL_MENU_PERMISSION_KEYS),
    [permissionTree],
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      username: '',
      nickname: '',
      password: '',
      menu_permissions: ['home'],
      is_admin: false,
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (item: UserInfo) => {
    setEditing(item);
    form.setFieldsValue({
      username: item.username,
      nickname: item.nickname,
      password: item.password || '',
      menu_permissions: item.menu_permissions,
      is_admin: item.is_admin,
      is_active: item.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateUser(editing.id, {
          nickname: values.nickname,
          password: values.password?.trim() || undefined,
          menu_permissions: values.menu_permissions,
          is_admin: values.is_admin,
          is_active: values.is_active,
        });
        message.success('更新成功');
      } else {
        await createUser({
          username: values.username,
          nickname: values.nickname,
          password: values.password || '',
          menu_permissions: values.menu_permissions,
          is_admin: values.is_admin,
          is_active: values.is_active,
        });
        message.success('创建成功');
      }
      setModalOpen(false);
      await loadItems();
    } catch (error) {
      showApiError(error, '保存失败');
    }
  };

  const handleDelete = async (item: UserInfo) => {
    try {
      await deleteUser(item.id);
      message.success('删除成功');
      await loadItems();
    } catch (error) {
      showApiError(error, '删除失败');
    }
  };

  const columns: ColumnsType<UserInfo> = [
    { title: '用户 ID', dataIndex: 'username', width: 140 },
    { title: '昵称', dataIndex: 'nickname', width: 140 },
    {
      title: '密码',
      dataIndex: 'password',
      width: 140,
      render: (value: string | undefined) => value || '-',
    },
    {
      title: '管理员',
      dataIndex: 'is_admin',
      width: 90,
      render: (value: boolean) => (value ? '是' : '否'),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (value: boolean) => (value ? '启用' : '禁用'),
    },
    {
      title: '菜单权限数',
      dataIndex: 'menu_permissions',
      width: 120,
      render: (value: string[]) => value.length,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatBeijingTime(value) || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该用户？" onConfirm={() => void handleDelete(record)}>
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-panel">
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增用户
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void loadItems()}>
          刷新
        </Button>
      </Space>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={items} scroll={{ x: 980 }} />

      <Modal
        title={editing ? '编辑用户' : '新增用户'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSubmit()}
        width={720}
        destroyOnClose
        className="user-form-modal"
      >
        <Form form={form} layout="vertical" size="small">
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="username"
                label="用户 ID"
                rules={[{ required: true, message: '请输入用户 ID' }]}
              >
                <Input disabled={Boolean(editing)} placeholder="登录用户名" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="nickname"
                label="昵称"
                rules={[{ required: true, message: '请输入昵称' }]}
              >
                <Input placeholder="显示名称，如：测试人员" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="password"
            label="密码"
            rules={editing ? [] : [{ required: true, message: '请输入密码' }]}
          >
            <Input placeholder="登录密码" autoComplete="off" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="is_admin" label="管理员" valuePropName="checked">
                <Switch
                  onChange={(checked) => {
                    if (checked) {
                      form.setFieldValue('menu_permissions', allLeafKeys);
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_active" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="menu_permissions"
            label="菜单权限"
            rules={[{ required: true, message: '请至少选择一个菜单权限' }]}
          >
            <Form.Item noStyle shouldUpdate>
              {() => {
                const checkedKeys = form.getFieldValue('menu_permissions') as string[] | undefined;
                return (
                  <div className="permission-tree-wrap">
                    <Typography.Paragraph type="secondary" className="permission-tree-hint">
                      按系统菜单树勾选可访问页面
                    </Typography.Paragraph>
                    <Tree
                      checkable
                      selectable={false}
                      defaultExpandAll
                      treeData={treeData}
                      checkedKeys={checkedKeys || []}
                      onCheck={(keys) => {
                        const next = (Array.isArray(keys) ? keys : keys.checked).map(String);
                        form.setFieldValue('menu_permissions', next);
                      }}
                    />
                  </div>
                );
              }}
            </Form.Item>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
