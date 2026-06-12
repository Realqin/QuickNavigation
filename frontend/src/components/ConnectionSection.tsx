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
import { useMemo } from 'react';
import { sortConnectionsByTypeOrder } from '../hooks/useDict';
import type { Connection, DictItem } from '../types';
import { LABEL_DATABASE, LABEL_KAFKA, LABEL_MQTT, LABEL_TERMINAL } from '../utils/connectionType';
import ConnectionCard from './ConnectionCard';

interface Props {
  title: string;
  panelKey: string;
  connections: Connection[];
  expanded: boolean;
  editMode?: boolean;
  onExpandChange: (key: string, expanded: boolean) => void;
  onReorder: (items: Connection[]) => void;
  onEdit: (connection: Connection) => void;
  onDelete?: (connection: Connection) => void;
  onOpen?: (connection: Connection, kind: 'database' | 'terminal' | 'mqtt' | 'kafka') => void;
  labelItems?: DictItem[];
  labelIdMap?: Record<number, string>;
  labelColorMap?: Record<number, string>;
  labelIconIndexMap?: Record<number, number>;
  labelOrderMap?: Record<number, number>;
  projectIdMap?: Record<number, string>;
  envIdMap?: Record<number, string>;
}

export default function ConnectionSection({
  title,
  panelKey,
  connections,
  expanded,
  editMode = false,
  onExpandChange,
  onReorder,
  onEdit,
  onDelete,
  onOpen,
  labelItems = [],
  labelIdMap,
  labelColorMap,
  labelIconIndexMap,
  labelOrderMap = {},
  projectIdMap,
  envIdMap,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const databaseTypeIds = useMemo(
    () => new Set(labelItems.filter((item) => item.name === LABEL_DATABASE).map((item) => item.id)),
    [labelItems],
  );

  const terminalTypeIds = useMemo(
    () => new Set(labelItems.filter((item) => item.name === LABEL_TERMINAL).map((item) => item.id)),
    [labelItems],
  );

  const mqttTypeIds = useMemo(
    () => new Set(labelItems.filter((item) => item.name === LABEL_MQTT).map((item) => item.id)),
    [labelItems],
  );

  const kafkaTypeIds = useMemo(
    () => new Set(labelItems.filter((item) => item.name === LABEL_KAFKA).map((item) => item.id)),
    [labelItems],
  );

  const displayConnections = useMemo(
    () => sortConnectionsByTypeOrder(connections, labelOrderMap),
    [connections, labelOrderMap],
  );

  const handleDragEnd = (event: DragEndEvent) => {
    if (!editMode) return;
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = displayConnections.findIndex((c) => c.id === active.id);
    const newIndex = displayConnections.findIndex((c) => c.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(arrayMove(displayConnections, oldIndex, newIndex));
  };

  const grid = (
    <div className="card-grid">
      {displayConnections.map((conn) => (
        <ConnectionCard
          key={conn.id}
          connection={conn}
          editMode={editMode}
          typeLabel={labelIdMap?.[conn.type]}
          typeColor={labelColorMap?.[conn.type]}
          typeIconIndex={labelIconIndexMap?.[conn.type] ?? 0}
          projectLabels={(conn.projects ?? []).map((id) => projectIdMap?.[id] ?? String(id))}
          envLabels={(conn.environments ?? []).map((id) => envIdMap?.[id] ?? String(id))}
          onEdit={onEdit}
          onDelete={onDelete}
          onOpen={onOpen}
          isDatabaseType={databaseTypeIds.has(conn.type)}
          isTerminalType={terminalTypeIds.has(conn.type)}
          isMqttType={mqttTypeIds.has(conn.type)}
          isKafkaType={kafkaTypeIds.has(conn.type)}
        />
      ))}
    </div>
  );

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
            ) : editMode ? (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={displayConnections.map((c) => c.id)} strategy={rectSortingStrategy}>
                  {grid}
                </SortableContext>
              </DndContext>
            ) : (
              grid
            ),
        },
      ]}
    />
  );
}
