import os
import sys
from pathlib import Path

# 將專案根目錄加入路徑，確保能正確 import backend 與 core 的模組
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# 必須早於 import backend.database：engine 建立時會讀 config.DATABASE_URL
from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from sqlalchemy.orm import Session
from passlib.context import CryptContext

# 匯入你剛建立好的 Database 與 Models
from backend.database import SessionLocal, engine
from backend.models import Base, User, Project, ProjectUserLink, Task, TaskStatus

# 資料庫連線與 docker-compose / 本機後端相同：由 config.DATABASE_URL（環境變數 DATABASE_URL）決定。
# Docker 時請在 .env 設 DB_USER / DB_PASS / DB_NAME 供 compose 建立 Postgres，並讓 DATABASE_URL 與之一致。
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin_password")

# 密碼雜湊設定 (確保與你 backend/routers/auth.py 的設定一致)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# 鎖定實體資料夾路徑 (根據你的系統架構，預設為根目錄下的 data)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

def seed_database():
    print("🌱 正在初始化資料庫...")
    
    # 若資料表還沒建立，這裡會自動建立 (安全機制)
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    try:
        # 1. 檢查是否已經初始化過 (冪等性檢查)
        admin_user = db.query(User).filter(User.username == ADMIN_USER).first()
        if admin_user:
            print(f"✅ 資料庫已經存在 {ADMIN_USER} 帳號，跳過初始化。")
            return

        # 2. 建立預設專案 (Project)
        default_project = Project(
            name="預設專案 (Default Project)", 
            description="系統初始化自動建立的預設專案"
        )
        db.add(default_project)
        db.flush() # 取得 project 的 id
        print(f"👉 建立專案：{default_project.name}")

        # 3. 建立 Admin 帳號 (User)
        admin_user = User(
            username=ADMIN_USER,
            password_hash=pwd_context.hash(ADMIN_PASS),
            real_name="系統管理員",
            role="admin"
        )
        db.add(admin_user)
        db.flush() 
        print(f"👉 建立網頁管理員帳號：{ADMIN_USER} / 密碼：{ADMIN_PASS}")

        # 4. 綁定 Admin 與 預設專案 (ProjectUserLink)
        link = ProjectUserLink(user_id=admin_user.id, project_id=default_project.id)
        db.add(link)
        print("👉 已將管理員綁定至預設專案")

        # 5. 掃描 data/ 目錄，將現有音檔案例寫入 Task 表
        data_path = Path(DATA_DIR)
        cases_added = 0
        if data_path.exists() and data_path.is_dir():
            for item in data_path.iterdir():
                # 排除隱藏檔案 (如 .DS_Store 或 .gitkeep)
                if item.is_dir() and not item.name.startswith("."):
                    case_name = item.name
                    
                    # 檢查是否已存在 (以防萬一)
                    existing_task = db.query(Task).filter(Task.case_name == case_name).first()
                    if not existing_task:
                        new_task = Task(
                            case_name=case_name,
                            status=TaskStatus.PENDING,
                            project_id=default_project.id,
                            assignee_id=None # 初始未指派負責人
                        )
                        db.add(new_task)
                        cases_added += 1
                        
            print(f"👉 掃描完成：共匯入 {cases_added} 筆既有音檔至資料庫")
        else:
            print("⚠️ 找不到 data/ 目錄或目錄為空，跳過案例匯入。")

        # 確認寫入資料庫
        db.commit()
        print("🎉 資料庫初始化成功！")

    except Exception as e:
        db.rollback()
        print(f"❌ 初始化過程中發生錯誤: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()