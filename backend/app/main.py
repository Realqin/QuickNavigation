import asyncio
import logging
import time
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import Connection, DictItem
from app.ping_scheduler import connection_ping_scheduler
from app.routers import api, webhooks
from app.services import DICT_ENVIRONMENT, DICT_LABEL, DICT_PROJECT

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler_task = asyncio.create_task(connection_ping_scheduler())
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="QuickNavigation API", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)
app.include_router(webhooks.router)


def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> None:
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            if i == max_retries - 1:
                raise
            time.sleep(delay)


def migrate_drop_dict_name_unique() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("dict_items"):
        return
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE dict_items DROP INDEX uq_dict_type_name"))
        except Exception:
            pass


def seed_dict_items(db) -> None:
    if db.query(DictItem).count() > 0:
        return
    seeds = [
        (DICT_PROJECT, "默认项目", "系统默认项目", 0),
        (DICT_PROJECT, "订单服务", "订单微服务项目", 1),
        (DICT_ENVIRONMENT, "开发环境", None, 0),
        (DICT_ENVIRONMENT, "测试环境", None, 1),
        (DICT_ENVIRONMENT, "预发环境", None, 2),
        (DICT_ENVIRONMENT, "生产环境", None, 3),
        (DICT_LABEL, "普通连接", None, 0),
        (DICT_LABEL, "GitHub 仓库", "GitHub 代码仓库", 1),
        (DICT_LABEL, "数据库", "数据库连接", 2),
    ]
    db.add_all(
        [
            DictItem(dict_type=dict_type, name=name, description=desc, sort_order=sort_order)
            for dict_type, name, desc, sort_order in seeds
        ]
    )
    db.commit()


def migrate_connection_multi_select() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    if "projects" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE connections ADD COLUMN projects JSON NULL"))
        conn.execute(text("ALTER TABLE connections ADD COLUMN environments JSON NULL"))
        if "project" in cols:
            conn.execute(
                text(
                    "UPDATE connections SET projects = JSON_ARRAY(project) "
                    "WHERE project IS NOT NULL AND project != ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE connections SET environments = JSON_ARRAY(environment) "
                    "WHERE environment IS NOT NULL AND environment != ''"
                )
            )
        conn.execute(text("UPDATE connections SET projects = JSON_ARRAY() WHERE projects IS NULL"))
        conn.execute(
            text("UPDATE connections SET environments = JSON_ARRAY() WHERE environments IS NULL")
        )


def migrate_connection_reachability() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "is_reachable" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN is_reachable BOOLEAN NULL"))
        if "last_checked_at" not in cols:
            conn.execute(text("ALTER TABLE connections ADD COLUMN last_checked_at DATETIME NULL"))


def migrate_connection_data_fix() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "projects" in cols:
            conn.execute(text("UPDATE connections SET projects = JSON_ARRAY() WHERE projects IS NULL"))
            if "project" in cols:
                conn.execute(
                    text(
                        "UPDATE connections SET projects = JSON_ARRAY(project) "
                        "WHERE (projects IS NULL OR JSON_LENGTH(projects) = 0) "
                        "AND project IS NOT NULL AND project != ''"
                    )
                )
        if "environments" in cols:
            conn.execute(
                text("UPDATE connections SET environments = JSON_ARRAY() WHERE environments IS NULL")
            )
            if "environment" in cols:
                conn.execute(
                    text(
                        "UPDATE connections SET environments = JSON_ARRAY(environment) "
                        "WHERE (environments IS NULL OR JSON_LENGTH(environments) = 0) "
                        "AND environment IS NOT NULL AND environment != ''"
                    )
                )


def migrate_drop_legacy_connection_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    with engine.begin() as conn:
        if "project" in cols and "projects" in cols:
            conn.execute(text("ALTER TABLE connections DROP COLUMN project"))
        if "environment" in cols and "environments" in cols:
            conn.execute(text("ALTER TABLE connections DROP COLUMN environment"))


def migrate_connection_type_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    for column in inspector.get_columns("connections"):
        if column["name"] == "type" and "enum" in str(column["type"]).lower():
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE connections MODIFY COLUMN type VARCHAR(64) "
                        "NOT NULL DEFAULT 'normal'"
                    )
                )
            break


def migrate_connection_sub_links() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("connections"):
        return
    cols = {column["name"] for column in inspector.get_columns("connections")}
    if "sub_links" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE connections ADD COLUMN sub_links JSON NULL")
        )
        conn.execute(text("UPDATE connections SET sub_links = JSON_ARRAY() WHERE sub_links IS NULL"))


def migrate_connection_dict_ids() -> None:
    import json as json_lib

    inspector = inspect(engine)
    if not inspector.has_table("connections") or not inspector.has_table("dict_items"):
        return

    db = SessionLocal()
    try:
        items = db.query(DictItem).all()
        name_maps: dict[str, dict[str, int]] = {
            DICT_PROJECT: {},
            DICT_ENVIRONMENT: {},
            DICT_LABEL: {},
        }
        for item in items:
            name_maps.setdefault(item.dict_type, {})[item.name] = item.id

        rows = db.execute(text("SELECT id, projects, environments, type FROM connections")).fetchall()
        for row_id, projects_raw, environments_raw, conn_type in rows:
            projects_data = projects_raw
            environments_data = environments_raw
            if isinstance(projects_data, str):
                projects_data = json_lib.loads(projects_data)
            if isinstance(environments_data, str):
                environments_data = json_lib.loads(environments_data)

            new_projects: list[int] = []
            for value in projects_data or []:
                if isinstance(value, int):
                    new_projects.append(value)
                elif isinstance(value, str):
                    mapped = name_maps.get(DICT_PROJECT, {}).get(value)
                    if mapped is not None:
                        new_projects.append(mapped)

            new_environments: list[int] = []
            for value in environments_data or []:
                if isinstance(value, int):
                    new_environments.append(value)
                elif isinstance(value, str):
                    mapped = name_maps.get(DICT_ENVIRONMENT, {}).get(value)
                    if mapped is not None:
                        new_environments.append(mapped)

            if isinstance(conn_type, str) and not conn_type.isdigit():
                new_type = name_maps.get(DICT_LABEL, {}).get(conn_type)
                if new_type is None:
                    new_type = name_maps.get(DICT_LABEL, {}).get("normal", 1)
            else:
                new_type = int(conn_type)

            db.execute(
                text(
                    "UPDATE connections SET projects = :projects, environments = :environments, "
                    "type = :type WHERE id = :id"
                ),
                {
                    "id": row_id,
                    "projects": json_lib.dumps(new_projects),
                    "environments": json_lib.dumps(new_environments),
                    "type": new_type,
                },
            )
        db.commit()
    finally:
        db.close()

    type_column = next(
        (column for column in inspector.get_columns("connections") if column["name"] == "type"),
        None,
    )
    if type_column and "int" not in str(type_column["type"]).lower():
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE connections MODIFY COLUMN type INT NOT NULL DEFAULT 1"))


def _dict_id(db, dict_type: str, name: str) -> int:
    item = (
        db.query(DictItem)
        .filter(DictItem.dict_type == dict_type, DictItem.name == name)
        .first()
    )
    if not item:
        raise RuntimeError(f"Missing dict seed: {dict_type}/{name}")
    return item.id


def seed_connections(db) -> None:
    if db.query(Connection).count() > 0:
        return
    normal = _dict_id(db, DICT_LABEL, "普通连接")
    database = _dict_id(db, DICT_LABEL, "数据库")
    github = _dict_id(db, DICT_LABEL, "GitHub 仓库")
    order_service = _dict_id(db, DICT_PROJECT, "订单服务")
    test_env = _dict_id(db, DICT_ENVIRONMENT, "测试环境")
    dev_env = _dict_id(db, DICT_ENVIRONMENT, "开发环境")
    seed = [
        Connection(
            name="团队 Wiki",
            url="https://wiki.example.com",
            description="内部文档",
            projects=[],
            environments=[],
            type=normal,
            is_shared=True,
            sort_order=0,
        ),
        Connection(
            name="监控大盘",
            url="https://grafana.example.com",
            description="Grafana 监控",
            projects=[],
            environments=[],
            type=normal,
            is_shared=True,
            sort_order=1,
        ),
        Connection(
            name="测试 API",
            url="https://api-test.example.com",
            description="测试环境接口",
            projects=[order_service],
            environments=[test_env],
            type=normal,
            is_shared=False,
            sort_order=0,
        ),
        Connection(
            name="测试数据库",
            url="https://db-admin.example.com",
            description="MySQL 管理",
            projects=[order_service],
            environments=[test_env],
            type=database,
            is_shared=False,
            sort_order=1,
        ),
        Connection(
            name="GitHub 仓库",
            url="https://github.com/org/order-service",
            description="代码仓库",
            projects=[order_service],
            environments=[test_env, dev_env],
            type=github,
            is_shared=False,
            sort_order=2,
        ),
    ]
    db.add_all(seed)
    db.commit()


def init_db() -> None:
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    migrate_connection_multi_select()
    migrate_connection_reachability()
    migrate_connection_data_fix()
    migrate_drop_legacy_connection_columns()
    migrate_connection_type_column()
    migrate_connection_sub_links()
    migrate_connection_dict_ids()
    migrate_drop_dict_name_unique()
    db = SessionLocal()
    try:
        seed_dict_items(db)
        seed_connections(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
