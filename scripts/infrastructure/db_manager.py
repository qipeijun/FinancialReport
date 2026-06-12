#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库管理模块

提供统一的数据库操作功能，支持：
- 连接池管理
- 事务自动处理
- 批量操作优化
- 上下文管理器
- 错误处理和重试
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Tuple, Any, Optional, Dict
from functools import wraps

from .logger import get_logger

logger = get_logger('db_manager')


class DatabaseError(Exception):
    """数据库操作异常"""
    pass


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: Path, timeout: int = 30):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
            timeout: 数据库锁超时时间（秒）
        """
        self.db_path = Path(db_path)
        self.timeout = timeout
        
        # 确保数据库目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def get_connection(self, row_factory: bool = True) -> Generator[sqlite3.Connection, None, None]:
        """
        获取数据库连接（上下文管理器）
        
        Args:
            row_factory: 是否使用Row工厂（返回字典式访问）
        
        Yields:
            sqlite3.Connection: 数据库连接
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> with db.get_connection() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("SELECT * FROM news_articles")
        """
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            if row_factory:
                conn.row_factory = sqlite3.Row
            
            yield conn
            
        except sqlite3.Error as e:
            logger.error(f"数据库连接错误: {e}")
            raise DatabaseError(f"数据库连接失败: {e}") from e
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def transaction(self, row_factory: bool = True) -> Generator[sqlite3.Connection, None, None]:
        """
        事务管理器（自动提交或回滚）
        
        Args:
            row_factory: 是否使用Row工厂
        
        Yields:
            sqlite3.Connection: 数据库连接
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> with db.transaction() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("INSERT INTO ...")
            ...     # 事务会自动提交
        """
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
            if row_factory:
                conn.row_factory = sqlite3.Row
            
            yield conn
            
            conn.commit()
            
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
                logger.warning(f"事务回滚: {e}")
            raise DatabaseError(f"事务执行失败: {e}") from e
        except Exception as e:
            if conn:
                conn.rollback()
                logger.error(f"事务异常回滚: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, sql: str, params: Optional[Tuple] = None) -> List[sqlite3.Row]:
        """
        执行查询语句
        
        Args:
            sql: SQL查询语句
            params: 查询参数
        
        Returns:
            查询结果列表
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> results = db.execute_query("SELECT * FROM news_articles WHERE id = ?", (123,))
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                results = cursor.fetchall()
                logger.debug(f"查询执行成功，返回 {len(results)} 行")
                return results
        except sqlite3.Error as e:
            logger.error(f"查询执行失败: {sql}, 错误: {e}")
            raise DatabaseError(f"查询失败: {e}") from e
    
    def execute_update(self, sql: str, params: Optional[Tuple] = None) -> int:
        """
        执行更新语句（INSERT, UPDATE, DELETE）
        
        Args:
            sql: SQL更新语句
            params: 更新参数
        
        Returns:
            受影响的行数
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> rows = db.execute_update("DELETE FROM news_articles WHERE id = ?", (123,))
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                affected = cursor.rowcount
                logger.info(f"更新执行成功，影响 {affected} 行")
                return affected
        except sqlite3.Error as e:
            logger.error(f"更新执行失败: {sql}, 错误: {e}")
            raise DatabaseError(f"更新失败: {e}") from e
    
    def execute_batch(self, sql: str, params_list: List[Tuple], batch_size: int = 1000) -> int:
        """
        批量执行操作（提高性能）
        
        Args:
            sql: SQL语句
            params_list: 参数列表
            batch_size: 批量大小
        
        Returns:
            总共影响的行数
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> data = [(1, 'title1'), (2, 'title2'), ...]
            >>> rows = db.execute_batch("INSERT INTO news_articles (id, title) VALUES (?, ?)", data)
        """
        if not params_list:
            logger.warning("批量操作参数列表为空")
            return 0
        
        total_affected = 0
        total_batches = (len(params_list) + batch_size - 1) // batch_size
        
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                for i in range(0, len(params_list), batch_size):
                    batch = params_list[i:i + batch_size]
                    cursor.executemany(sql, batch)
                    total_affected += cursor.rowcount
                return total_affected
                
        except sqlite3.Error as e:
            logger.error(f"批量操作失败: {e}")
            raise DatabaseError(f"批量操作失败: {e}") from e
    
    def execute_with_retry(self, func, max_retries: int = 3, retry_delay: float = 1.0):
        """
        执行操作并在失败时重试
        
        Args:
            func: 要执行的函数
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        
        Returns:
            函数执行结果
        
        Example:
            >>> db = DatabaseManager(db_path)
            >>> def query_data():
            ...     return db.execute_query("SELECT * FROM news_articles")
            >>> results = db.execute_with_retry(query_data)
        """
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                result = func()
                if attempt > 1:
                    logger.info(f"第 {attempt} 次尝试成功")
                return result
            except (sqlite3.OperationalError, DatabaseError) as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error(f"达到最大重试次数 {max_retries}")
        
        raise DatabaseError(f"操作失败（已重试{max_retries}次）: {last_error}") from last_error
    
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        获取表结构信息
        
        Args:
            table_name: 表名
        
        Returns:
            表结构信息列表
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                result = []
                for col in columns:
                    result.append({
                        'cid': col['cid'],
                        'name': col['name'],
                        'type': col['type'],
                        'notnull': col['notnull'],
                        'default': col['dflt_value'],
                        'pk': col['pk']
                    })
                
                logger.debug(f"表 {table_name} 包含 {len(result)} 列")
                return result
                
        except sqlite3.Error as e:
            logger.error(f"获取表结构失败: {table_name}, 错误: {e}")
            raise DatabaseError(f"获取表结构失败: {e}") from e
    
    def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name: 表名
        
        Returns:
            表是否存在
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                exists = cursor.fetchone() is not None
                logger.debug(f"表 {table_name} {'存在' if exists else '不存在'}")
                return exists
        except sqlite3.Error as e:
            logger.error(f"检查表存在性失败: {e}")
            return False
    
    def get_row_count(self, table_name: str, where_clause: str = "", params: Optional[Tuple] = None) -> int:
        """
        获取表行数
        
        Args:
            table_name: 表名
            where_clause: WHERE子句（可选）
            params: 查询参数
        
        Returns:
            行数
        """
        try:
            sql = f"SELECT COUNT(*) as count FROM {table_name}"
            if where_clause:
                sql += f" WHERE {where_clause}"
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                count = cursor.fetchone()['count']
                logger.debug(f"表 {table_name} 行数: {count}")
                return count
        except sqlite3.Error as e:
            logger.error(f"获取行数失败: {e}")
            raise DatabaseError(f"获取行数失败: {e}") from e
    
    def vacuum(self):
        """
        执行VACUUM优化数据库（释放空间、重建索引）
        """
        try:
            logger.info("开始VACUUM操作")
            with self.get_connection(row_factory=False) as conn:
                conn.execute("VACUUM")
            logger.info("VACUUM操作完成")
        except sqlite3.Error as e:
            logger.error(f"VACUUM操作失败: {e}")
            raise DatabaseError(f"VACUUM失败: {e}") from e


def retry_on_db_error(max_retries: int = 3, retry_delay: float = 1.0):
    """
    数据库操作重试装饰器
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 重试延迟
    
    Example:
        >>> @retry_on_db_error(max_retries=3)
        >>> def insert_data(db, data):
        ...     return db.execute_update("INSERT INTO ...", data)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            delay = retry_delay
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, DatabaseError) as e:
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(f"{func.__name__} 第{attempt}次失败: {e}, {delay}秒后重试")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.error(f"{func.__name__} 达到最大重试次数")
            
            raise DatabaseError(f"{func.__name__} 失败（已重试{max_retries}次）: {last_error}") from last_error
        
        return wrapper
    return decorator


if __name__ == '__main__':
    # 测试数据库管理器
    from pathlib import Path
    
    # 创建测试数据库
    test_db = Path('test_db.db')
    db = DatabaseManager(test_db)
    
    print("=== 测试数据库管理器 ===\n")
    
    # 创建测试表
    with db.transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id INTEGER PRIMARY KEY,
                name TEXT,
                value INTEGER
            )
        """)
    print("✓ 创建测试表")
    
    # 测试批量插入
    test_data = [(i, f'name_{i}', i * 10) for i in range(1, 101)]
    affected = db.execute_batch(
        "INSERT OR REPLACE INTO test_table (id, name, value) VALUES (?, ?, ?)",
        test_data,
        batch_size=25
    )
    print(f"✓ 批量插入: {affected} 行")
    
    # 测试查询
    results = db.execute_query("SELECT * FROM test_table WHERE value > ?", (500,))
    print(f"✓ 查询结果: {len(results)} 行")
    
    # 测试获取表信息
    table_info = db.get_table_info('test_table')
    print(f"✓ 表结构: {len(table_info)} 列")
    
    # 测试行数统计
    count = db.get_row_count('test_table')
    print(f"✓ 总行数: {count}")
    
    # 清理
    test_db.unlink()
    print("\n✓ 测试完成")

