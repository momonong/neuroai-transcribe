"""
SQLAlchemy 2.0 模型：使用者、專案、任務與多對多關聯。

多對多僅透過關聯表實體 ProjectUserLink 表達（association object），
不再額外宣告 secondary 的 User.projects / Project.users，避免與
project_links / user_links 寫入同一組 FK 而觸發 overlapping relationships 警告。

若要在 Python 端取得對方的列表：
  [link.project for link in user.project_links]
  [link.user for link in project.user_links]
"""
from __future__ import annotations

import enum
from typing import List

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project_links: Mapped[List["ProjectUserLink"]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # 避免 Python 3.14 + SQLAlchemy 對 Union 註解的相容問題，可為 null 的欄位不用 Mapped[...|None]
    description = mapped_column(Text, nullable=True)

    user_links: Mapped[List["ProjectUserLink"]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")


class ProjectUserLink(Base):
    __tablename__ = "project_user_link"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_project_user"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)

    user: Mapped["User"] = relationship(
        back_populates="project_links",
        foreign_keys=[user_id],
    )
    project: Mapped["Project"] = relationship(
        back_populates="user_links",
        foreign_keys=[project_id],
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, native_enum=False, values_callable=lambda enum_cls: [i.value for i in enum_cls]),
        default=TaskStatus.PENDING,
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    assignee_id = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")
    # assignee 可為 None（DB nullable）；避免 Python 3.14 下 Mapped[Optional[...]] 觸發 SQLAlchemy Union 解析錯誤
    assignee: Mapped["User"] = relationship(foreign_keys=[assignee_id])
