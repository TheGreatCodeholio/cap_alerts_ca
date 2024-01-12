import logging
import os
import sqlite3

from werkzeug.security import generate_password_hash

module_logger = logging.getLogger('icad_cap_alerts.sqlite')


class SQLiteDatabase:
    """
    Represents an SQLite database.

    Attributes:
        dbconfig (dict): Configuration data for the SQLite connection.
        db_path (str): Path to the SQLite database file.
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self.schema_path = "etc/icad_cap_alerts.sql"
        if not os.path.exists(self.db_path):
            module_logger.warning("Database not found, Creating.")
            try:
                self._create_database()
                self.create_admin_user()
            except Exception as e:
                module_logger.error(f"Unexpected Error Creating Database: {e}")
            module_logger.info(f"Database Created Successfully")

    def _create_database(self):
        with open(self.schema_path, 'r') as f:
            schema = f.read()
        with self._acquire_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(schema)
            cursor.close()

    def create_admin_user(self):
        password = generate_password_hash("admin")
        query = "INSERT INTO users (username, password) VALUES (?, ?)"
        params = ("admin", password)
        self.execute_commit(query, params)

    def _acquire_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Set the row factory
        return conn

    def _release_connection(self, conn):
        conn.close()

    def execute_query(self, query: str, params=None, fetch_mode="all"):
        """
        Execute a SELECT query and fetch results.

        Args:
            query (str): The SQL query string.
            params (tuple or dict, optional): The parameters for the SQL query.
            fetch_mode (str, optional): The mode to fetch results ("all", "many", or "one"). Default is "all".

        Returns:
            dict: A dictionary containing 'success' (bool) and 'result' (list of results or single result).
        """
        conn = self._acquire_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())

            if fetch_mode == "all":
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            elif fetch_mode == "one":
                row = cursor.fetchone()
                result = dict(row) if row else None
            else:
                raise ValueError(f"Invalid fetch_mode: {fetch_mode}")

            return {'success': True, 'result': result}

        except sqlite3.Error as error:
            module_logger.error(f"<<SQLite>> <<Query>> Execution Error: {error}")
            return {'success': False, 'message': str(error)}
        finally:
            self._release_connection(conn)

    def execute_commit(self, query: str, params=None, return_row=False):
        """
        Execute an INSERT, UPDATE, or DELETE query.

        Args:
            query (str): The SQL query string.
            params (tuple or dict, optional): The parameters for the SQL query.
            return_row (bool, optional): If True, return the last row ID.

        Returns:
            dict: A dictionary containing 'success' (bool) and 'message' (str) or 'row_id' (int).
        """
        conn = self._acquire_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()

            if return_row:
                row_id = cursor.lastrowid
                return {'success': True, 'row_id': row_id}

            return {'success': True, 'message': 'SQLite Commit Query Executed Successfully'}
        except sqlite3.Error as error:
            module_logger.error(f"<<SQLite>> <<Commit>> Execution Error: {error}")
            conn.rollback()
            return {'success': False, 'message': f'SQLite Commit Query Execution Error: {error}'}
        finally:
            self._release_connection(conn)

    def execute_many_commit(self, query: str, data: list):
        """
        Execute an INSERT, UPDATE, or DELETE query for multiple data rows.

        Args:
            query (str): The SQL query string.
            data (list): A list of parameter tuples for the SQL query.

        Returns:
            dict: A dictionary containing 'success' (bool) and 'message' (str or exception message).
        """
        if not data:
            return {'success': False, 'message': 'No data provided for batch execution.'}

        conn = self._acquire_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(query, data)
            conn.commit()

            return {'success': True, 'message': 'SQLite Multi-Commit Executed Successfully'}
        except sqlite3.Error as error:
            module_logger.error(f"<<SQLite>> <<Multi-Commit>> Error: {error}")
            return {'success': False, 'message': f'SQLite Multi-Commit Error: {error}'}
        finally:
            self._release_connection(conn)
