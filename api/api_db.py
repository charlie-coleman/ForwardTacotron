import sqlite3
import uuid
import datetime
import threading
from enum import Enum

class RequestStatus(Enum):
  PENDING = 0
  COMPLETED = 1
  FAILED = 2

class API_DB:
  conn = None
  lock = threading.Lock()
  def __init__(self, db_path):
    self.conn = sqlite3.connect(db_path, check_same_thread=False)
    with self.conn:
      self.conn.execute("""
        CREATE TABLE IF NOT EXISTS REQUESTS (
          id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
          requestid TEXT NOT NULL,
          input TEXT NOT NULL,
          status INTEGER NOT NULL,
          utctime INTEGER NOT NULL
        );
      """)
    
  def add_request(self, text):
    request_id = str(uuid.uuid4())
    status = RequestStatus.PENDING
    timestamp = int(datetime.datetime.utcnow().timestamp())
    with self.conn:
      self.lock.acquire()
      self.conn.execute(f"INSERT INTO REQUESTS (requestid, input, status, utctime) VALUES(?, ?, ?, ?);", (request_id, text, status.value, timestamp))
      self.lock.release()
    return (request_id, status)

  def check_request(self, request_id):
    with self.conn:
      self.lock.acquire()
      data = self.conn.execute(f"SELECT * FROM REQUESTS WHERE requestid = ?", (request_id,))
      self.lock.release()
      for row in data:
        return row
      return None

  def update_request_status(self, request_id, status):
    with self.conn:
      self.lock.acquire()
      ex = f"""UPDATE REQUESTS
               SET status = ?
               WHERE requestid = ?"""
      cur = self.conn.cursor()
      cur.execute(ex, (status.value, request_id))
      self.conn.commit()
      self.lock.release()

