import {
  DndContext,
  DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { Collapse, Empty, Typography } from 'antd';
import type { Connection } from '../types';
import ConnectionCard from './ConnectionCard';

interface Props {
  title: string;
  panelKey: string;
  connections: Connection[];
  expanded: boolean;
  onExpandChange: (key: string, expanded: boolean) => void;
  onReorder: (items: Connection[]) => void;
  onEdit: (connection: Connection) => void;
  labelIdMap?: Record<number, string>;
  projectIdMap?: Record<number, string>;
  envIdMap?: Record<number, string>;
}

export default function ConnectionSection({
  title,
  panelKey,
  connections,
  expanded,
  onExpandChange,
  onReorder,
  onEdit,
  labelIdMap,
  projectIdMap,
  envIdMap,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = connections.findIndex((c) => c.id === active.id);
    const newIndex = connections.findIndex((c) => c.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(arrayMove(connections, oldIndex, newIndex));
  };

  return (
    <Collapse
      activeKey={expanded ? [panelKey] : []}
      onChange={(keys) => onExpandChange(panelKey, keys.includes(panelKey))}
      items={[
        {
          key: panelKey,
          label: (
            <Typography.Text strong>
              {title} ({connections.length})
            </Typography.Text>
          ),
          children:
            connections.length === 0 ? (
              <Empty description="暂无连接" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={connections.map((c) => c.id)} strategy={rectSortingStrategy}>
                  <div className="card-grid">
                    {connections.map((conn) => (
                      <ConnectionCard
                        key={conn.id}
                        connection={conn}
                        typeLabel={labelIdMap?.[conn.type]}
                        projectLabels={(conn.projects ?? []).map((id) => projectIdMap?.[id] ?? String(id))}
                        envLabels={(conn.environments ?? []).map((id) => envIdMap?.[id] ?? String(id))}
                        onEdit={onEdit}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            ),
        },
      ]}
    />
  );
}
