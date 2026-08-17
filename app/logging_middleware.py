import os
import sqlite3
from datetime import datetime, timedelta, timezone


def init_log_db(db_path: str = 'data/logs.db') -> None:
    """
    Initializes the logging database and creates the required table if it doesn't exist.
    """
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                thread_id TEXT,
                input_query TEXT NOT NULL,
                final_answer TEXT NOT NULL,
                category TEXT,
                agent_name TEXT,
                sentiment TEXT,
                was_escalated INTEGER DEFAULT 0,
                latency_ms REAL,
                estimated_tokens INTEGER,
                estimated_cost_usd REAL
            )
        ''')
        conn.commit()

def estimate_tokens(text: str) -> int:
    """
    Estimates the number of tokens in a string.
    Note: This is an approximation using len(text) // 4.
    """
    return len(text) // 4

def estimate_cost(token_count: int) -> float:
    """
    Estimates the cost of API usage based on token count.
    Note: This uses a GPT-3.5-turbo-like reference rate of $0.002 per 1000 tokens.
    """
    return (token_count * 0.002) / 1000.0

def log_request(
    db_path: str,
    customer_id: str,
    thread_id: str | None,
    input_query: str,
    final_answer: str,
    category: str,
    agent_name: str,
    sentiment: str,
    was_escalated: int,
    latency_ms: float
) -> None:
    """
    Logs a single request to the database, including estimated tokens and cost.
    """
    tokens = estimate_tokens(input_query + final_answer)
    cost = estimate_cost(tokens)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO request_logs (
                timestamp, customer_id, thread_id, input_query, final_answer,
                category, agent_name, sentiment, was_escalated, latency_ms,
                estimated_tokens, estimated_cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp, customer_id, thread_id, input_query, final_answer,
            category, agent_name, sentiment, was_escalated, latency_ms,
            tokens, cost
        ))
        conn.commit()

def get_metrics(db_path: str = 'data/logs.db') -> dict:
    """
    Calculates and returns various metrics from the request logs.
    """
    metrics = {
        'total_requests': 0,
        'avg_latency_ms': 0.0,
        'p95_latency_ms': 0.0,
        'resolution_rate': 0.0,
        'total_estimated_cost_usd': 0.0,
        'requests_last_hour': 0
    }
    
    if not os.path.exists(db_path):
        return metrics

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Total requests
        cursor.execute('SELECT COUNT(*) as cnt FROM request_logs')
        row = cursor.fetchone()
        if not row or row['cnt'] == 0:
            return metrics
        total = row['cnt']
        metrics['total_requests'] = total
        
        # Avg latency, Total cost
        cursor.execute('SELECT AVG(latency_ms) as avg_lat, SUM(estimated_cost_usd) as tot_cost FROM request_logs')
        row = cursor.fetchone()
        metrics['avg_latency_ms'] = float(row['avg_lat'] or 0.0)
        metrics['total_estimated_cost_usd'] = float(row['tot_cost'] or 0.0)
        
        # p95 latency
        offset = max(0, int(total * 0.95) - 1)
        cursor.execute('SELECT latency_ms FROM request_logs ORDER BY latency_ms ASC LIMIT 1 OFFSET ?', (offset,))
        row = cursor.fetchone()
        if row:
            metrics['p95_latency_ms'] = float(row['latency_ms'] or 0.0)
            
        # Resolution rate (percentage where was_escalated = 0)
        cursor.execute('SELECT COUNT(*) as escalated_cnt FROM request_logs WHERE was_escalated = 1')
        row = cursor.fetchone()
        escalated_cnt = row['escalated_cnt'] if row else 0
        metrics['resolution_rate'] = ((total - escalated_cnt) / total) * 100.0 if total > 0 else 0.0
        
        # Requests last hour
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cursor.execute('SELECT COUNT(*) as cnt FROM request_logs WHERE timestamp >= ?', (one_hour_ago,))
        row = cursor.fetchone()
        metrics['requests_last_hour'] = row['cnt'] if row else 0

    return metrics

def get_recent_requests(db_path: str = 'data/logs.db', limit: int = 10) -> list[dict]:
    """
    Returns the N most recent request logs.
    """
    if not os.path.exists(db_path):
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM request_logs ORDER BY timestamp DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_hourly_stats(db_path: str = 'data/logs.db', hours: int = 24) -> list[dict]:
    """
    Returns hourly statistics for charting.
    """
    if not os.path.exists(db_path):
        return []

    time_limit = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Extract the hour part from the ISO timestamp string. Format is 'YYYY-MM-DDTHH:MM:SS...'
        # SUBSTR(timestamp, 1, 13) gives 'YYYY-MM-DDTHH'
        cursor.execute('''
            SELECT 
                SUBSTR(timestamp, 1, 13) || ':00:00' as hour,
                COUNT(*) as count,
                AVG(latency_ms) as avg_latency
            FROM request_logs
            WHERE timestamp >= ?
            GROUP BY SUBSTR(timestamp, 1, 13)
            ORDER BY hour ASC
        ''', (time_limit,))
        
        return [dict(row) for row in cursor.fetchall()]
