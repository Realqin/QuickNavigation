import { Select, Space, Typography } from 'antd';
import { useWorkspace } from '../contexts/WorkspaceContext';

export default function WorkspaceSelector() {
  const {
    globalProject,
    globalEnvironment,
    projectOptions,
    environmentOptions,
    projectIdMap,
    environmentIdMap,
    setGlobalProject,
    setGlobalEnvironment,
  } = useWorkspace();

  const projectLabel =
    globalProject != null ? projectIdMap[globalProject] ?? String(globalProject) : '未选择';
  const environmentLabel =
    globalEnvironment != null
      ? environmentIdMap[globalEnvironment] ?? String(globalEnvironment)
      : '未选择';

  return (
    <div className="workspace-selector workspace-selector--header">
      <Typography.Text className="workspace-selector__header-label">大环境</Typography.Text>
      <Space size={8} wrap className="workspace-selector__header-controls">
        <Select
          size="middle"
          value={globalProject ?? undefined}
          options={projectOptions}
          onChange={setGlobalProject}
          placeholder="选择项目"
          className="workspace-selector__header-select"
          popupMatchSelectWidth={false}
        />
        <Select
          size="middle"
          value={globalEnvironment ?? undefined}
          options={environmentOptions}
          onChange={setGlobalEnvironment}
          placeholder="选择环境"
          className="workspace-selector__header-select workspace-selector__header-select--env"
          popupMatchSelectWidth={false}
        />
      </Space>
      <Typography.Text className="workspace-selector__header-summary" title={`${projectLabel} / ${environmentLabel}`}>
        {projectLabel} / {environmentLabel}
      </Typography.Text>
    </div>
  );
}
