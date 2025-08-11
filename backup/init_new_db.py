#!/usr/bin/env python3
"""
새로운 스키마로 데이터베이스 초기화
"""

import sys
import os

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, '/home/catch/server')

from database import init_db

if __name__ == "__main__":
    print("Initializing database with new schema...")
    init_db()
    print("Database initialized successfully!")
    print("New columns added: person_ids, processing_type, processing_color, webhook_status")