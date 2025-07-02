import sqlite3
import os
import csv
import shutil
from datetime import datetime
import logging
from typing import List, Dict, Optional, Any
init_logging = logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DATABASE = 'money_manager.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=30)  # Increased timeout
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = 10000')  # 10 second busy timeout
    conn.execute('PRAGMA journal_mode = WAL')     # Enable WAL mode for better concurrency
    return conn

def init_database():
    conn = get_db_connection()
    # Create accounts table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Create transactions table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            description TEXT,
            date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create categories table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            color TEXT DEFAULT '#007bff'
        )
    ''')
    
    # Insert default categories
    default_categories = [
        ('Salary', 'income', '#28a745'),
        ('Freelance', 'income', '#17a2b8'),
        ('Food', 'expense', '#dc3545'),
        ('Transportation', 'expense', '#fd7e14'),
        ('Entertainment', 'expense', '#6f42c1'),
        ('Utilities', 'expense', '#6c757d'),
    ]
    def create_custom_categories_table():
        """Initialize custom categories table with comprehensive structure."""
        conn = get_db_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS custom_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    color TEXT DEFAULT '#007bff',
                    description TEXT,
                    created_date DATE DEFAULT CURRENT_DATE,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            conn.commit()
            logger.info("Custom categories table initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to create custom categories table: {e}")
            raise
        finally:
            conn.close()
    def create_account_balance_table():
        """Initialize account balance tracking with audit trail."""
        conn = get_db_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS account_balance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT DEFAULT 'system'
                )
            ''')
            
            # Initialize with zero balance if table is empty
            existing = conn.execute('SELECT COUNT(*) FROM account_balance').fetchone()[0]
            if existing == 0:
                conn.execute(
                    'INSERT INTO account_balance (balance, updated_by) VALUES (0.00, ?)',
                    ('initial_setup',)
                )
                
            conn.commit()
            logger.info("Account balance table initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to create account balance table: {e}")
            raise
        finally:
            conn.close()
    def create_transactions_table():
        """Create transactions table with comprehensive structure."""
        conn = get_db_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                    description TEXT,
                    date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logger.info("Transactions table initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to create transactions table: {e}")
            raise
        finally:
            conn.close()
    def create_categories_table():
        """Create categories table with comprehensive structure."""
        conn = get_db_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                    color TEXT DEFAULT '#007bff'
                )
            ''')
            conn.commit()
            logger.info("Categories table initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to create categories table: {e}")
            raise
        finally:
            conn.close()
    # Then initialize other tables
    create_custom_categories_table()
    create_account_balance_table()
    create_ious_table()
    create_iou_payments_table()
    create_transactions_table()
    create_categories_table()
    migrate_ious_table()
    migrate_existing_data()
    
    # Insert default categories (existing code)
    for name, cat_type, color in default_categories:
        conn.execute(
            'INSERT OR IGNORE INTO categories (name, type, color) VALUES (?, ?, ?)',
            (name, cat_type, color)
        )
    
    conn.commit()
    conn.close()

def add_transaction(amount: float, category: str, trans_type: str, description: str, date: str, account_id: int = 1):
    """
    Add new transaction and automatically update account balance.
    
    Args:
        amount: Transaction amount (always positive)
        category: Transaction category
        trans_type: 'income' or 'expense'
        description: Transaction description
        date: Transaction date (YYYY-MM-DD format)
        account_id: Account ID (defaults to 1)
    """
    conn = get_db_connection()
    try:
        # Insert the transaction
        conn.execute(
            'INSERT INTO transactions (amount, category, type, description, date, account_id) VALUES (?, ?, ?, ?, ?, ?)',
            (amount, category, trans_type, description, date, account_id)
        )
        conn.commit()
        conn.close()
        
        # Automatically update account balance
        balance_updated = _auto_update_account_balance(account_id)
        
        if balance_updated:
            logger.info(f"Transaction added and account {account_id} balance auto-updated: {trans_type} ${amount:.2f}")
        else:
            logger.warning(f"Transaction added but failed to auto-update account {account_id} balance")
            
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to add transaction: {e}")
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        logger.error(f"Unexpected error adding transaction: {e}")
        raise

def get_transactions_with_category(days: Optional[int] = None, limit: Optional[int] = None, offset: int = 0, account_id: Optional[int] = None, category: Optional[str] = None) -> List[sqlite3.Row]:
    """
    Retrieve transactions with comprehensive filtering including account and category support.
    """
    conn = get_db_connection()
    try:
        base_query = "SELECT t.*, a.name as account_name FROM transactions t LEFT JOIN accounts a ON t.account_id = a.id"
        from typing import Any
        params: list[Any] = []
        conditions: list[str] = []
        
        # Add date filter if specified
        if days is not None and days > 0:
            conditions.append("t.date >= date('now', '-{} days')".format(int(days)))
            logger.debug(f"Adding date filter for last {days} days")
        
        # Add account filter if specified
        if account_id is not None:
            conditions.append("t.account_id = ?")
            params.append(account_id)
            logger.debug(f"Adding account filter for account {account_id}")
        
        # Add category filter if specified
        if category is not None and category.strip():
            conditions.append("t.category = ?")
            params.append(category.strip())
            logger.debug(f"Adding category filter for category '{category}'")
        
        # Build WHERE clause
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        # Order by date descending (newest first)
        base_query += " ORDER BY t.date DESC, t.created_at DESC"
        
        if limit and limit > 0:
            base_query += f" LIMIT {int(limit)}"
            if offset > 0:
                base_query += f" OFFSET {int(offset)}"
        
        logger.info(f"Executing query: {base_query} with params: {params}")
        transactions = conn.execute(base_query, params).fetchall()
        
        logger.info(f"Retrieved {len(transactions)} transactions (days={days}, account_id={account_id}, category={category}, limit={limit})")
        return transactions
        
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve transactions: {e}")
        return []
    finally:
        conn.close()

def get_categories(cat_type: Optional[str] = None):
    conn = get_db_connection()
    if cat_type:
        categories = conn.execute(
            'SELECT * FROM categories WHERE type = ? ORDER BY name',
            (cat_type,)
        ).fetchall()
    else:
        categories = conn.execute(
            'SELECT * FROM categories ORDER BY type, name'
        ).fetchall()
    conn.close()
    return categories

def get_summary(days: Optional[int] = None):
    conn = get_db_connection()
    
    date_filter = ""
    if days:
        date_filter = f"WHERE date >= date('now', '-{days} days')"
    
    query = f'''
        SELECT 
            type,
            SUM(amount) as total,
            COUNT(*) as count
        FROM transactions 
        {date_filter}
        GROUP BY type
    '''
    
    results = conn.execute(query).fetchall()
    conn.close()
    
    summary = {'income': 0, 'expense': 0, 'net': 0}
    for row in results:
        summary[row['type']] = row['total']
    
    summary['net'] = summary['income'] - summary['expense']
    return summary
def get_category_spending_basic(days: int = 30) -> List[Dict[str, Any]]:
    """Get spending breakdown by category for charts (basic version, no account filter)"""
    conn = get_db_connection()
    query = '''
        SELECT 
            category,
            SUM(amount) as total,
            COUNT(*) as count
        FROM transactions 
        WHERE type = 'expense' 
        AND date >= date('now', '-{} days')
        GROUP BY category
        ORDER BY total DESC
    '''.format(days)
    
    results = conn.execute(query).fetchall()
    conn.close()
    
    # Convert Row objects to dictionaries for JSON serialization
    return [{'category': row['category'], 'total': float(row['total']), 'count': row['count']} 
            for row in results]
def backup_database_with_filename(backup_filename: str) -> str:
    """Create database backup with timestamp."""
    import shutil
    import os
    
    try:
        # Ensure backup directory exists
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        # Create backup path
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Copy database file
        shutil.copy2('money_manager.db', backup_path)
        
        logger.info(f"Database backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise
from typing import List, Dict

def get_daily_balance_basic(days: int = 30) -> List[Dict[str, float]]:
    """Get daily income/expense for trend charts (basic version, no account filter)"""
    conn = get_db_connection()
    query = '''
        SELECT 
            date,
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
        FROM transactions 
        WHERE date >= date('now', '-{} days')
        GROUP BY date
        ORDER BY date
    '''.format(days)
    
    results = conn.execute(query).fetchall()
    conn.close()
    
    # Convert Row objects to dictionaries for JSON serialization
    return [{'date': row['date'], 'income': float(row['income']), 'expense': float(row['expense'])} 
            for row in results]

def delete_transaction(transaction_id: int):
    """
    Delete a transaction and automatically update account balance.
    
    Args:
        transaction_id: ID of transaction to delete
    """
    conn = get_db_connection()
    try:
        # Get account_id before deleting the transaction
        transaction = conn.execute(
            'SELECT account_id, amount, type FROM transactions WHERE id = ?', 
            (transaction_id,)
        ).fetchone()
        
        if not transaction:
            logger.warning(f"Transaction {transaction_id} not found for deletion")
            conn.close()
            return
        
        account_id = transaction[0] or 1  # Default to account 1 if None
        amount = transaction[1]
        trans_type = transaction[2]
        
        # Delete the transaction
        conn.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
        conn.commit()
        conn.close()
        
        # Automatically update account balance
        balance_updated = _auto_update_account_balance(account_id)
        
        if balance_updated:
            logger.info(f"Transaction {transaction_id} deleted and account {account_id} balance auto-updated: {trans_type} ${amount:.2f}")
        else:
            logger.warning(f"Transaction {transaction_id} deleted but failed to auto-update account {account_id} balance")
            
    except sqlite3.Error as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to delete transaction {transaction_id}: {e}")
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        logger.error(f"Unexpected error deleting transaction {transaction_id}: {e}")
        raise
def export_transactions_csv(filename: Optional[str] = None, days: Optional[int] = None) -> str:
    """Export transactions to CSV"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"transactions_{timestamp}.csv"
    
    transactions = get_transactions_with_category(days)
    # Convert sqlite3.Row objects to dictionaries for CSV export
    transactions = [dict(trans) for trans in transactions]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['date', 'type', 'category', 'description', 'amount']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for trans in transactions:
                writer.writerow({
                    'date': trans['date'],
                    'type': trans['type'],
                    'category': trans['category'],
                    'description': trans['description'] or '',
                    'amount': trans['amount']
                })
        return filename
    except Exception as e:
        logger.error(f"Failed to export transactions to CSV: {e}")
        raise RuntimeError(f"Failed to export transactions to CSV: {e}")

def export_summary_csv(filename: Optional[str] = None) -> str:
    """Export category summaries to CSV"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"summary_{timestamp}.csv"
    
    # Get summaries for different periods
    today_summary = get_summary(1)
    week_summary = get_summary(7)
    month_summary = get_summary(30)
    all_time_summary = get_summary()
    
    # Get category breakdown
    category_data: List[Dict[str, Any]] = get_category_spending(30)
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write summary data
        writer.writerow(['FINANCIAL SUMMARY'])
        writer.writerow(['Period', 'Income', 'Expenses', 'Net'])
        writer.writerow(['Today', today_summary['income'], today_summary['expense'], today_summary['net']])
        writer.writerow(['This Week', week_summary['income'], week_summary['expense'], week_summary['net']])
        writer.writerow(['This Month', month_summary['income'], month_summary['expense'], month_summary['net']])
        writer.writerow(['All Time', all_time_summary['income'], all_time_summary['expense'], all_time_summary['net']])
        
        writer.writerow([])  # Empty row
        writer.writerow(['CATEGORY BREAKDOWN (Last 30 Days)'])
        writer.writerow(['Category', 'Amount', 'Transactions'])
        for cat in category_data:
            writer.writerow([cat['category'], cat['total'], cat['count']])
    
    return filename

from typing import Optional

def backup_database(backup_path: Optional[str] = None) -> str:
    """Create a backup of the database"""
    if not backup_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"money_manager_backup_{timestamp}.db"
    
    shutil.copy2(DATABASE, backup_path)
    return backup_path

def restore_database(backup_path: str) -> bool:
    """Restore database from backup"""
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, DATABASE)
        return True
    return False
def create_custom_categories_table():
    """Initialize custom categories table with comprehensive structure."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                description TEXT,
                created_date DATE DEFAULT CURRENT_DATE,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        conn.commit()
        logger.info("Custom categories table initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to create custom categories table: {e}")
        raise
    finally:
        conn.close()

def create_account_balance_table():
    """Initialize account balance tracking with audit trail."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS account_balance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT DEFAULT 'system'
            )
        ''')
        
        # Initialize with zero balance if table is empty
        existing = conn.execute('SELECT COUNT(*) FROM account_balance').fetchone()[0]
        if existing == 0:
            conn.execute(
                'INSERT INTO account_balance (balance, updated_by) VALUES (0.00, ?)',
                ('initial_setup',)
            )
            
        conn.commit()
        logger.info("Account balance table initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to create account balance table: {e}")
        raise
    finally:
        conn.close()
from typing import Optional

def add_custom_category(name: str, category_type: str, description: Optional[str] = None) -> bool:
    """Add new custom category with validation and error handling."""
    if category_type not in ['income', 'expense']:
        logger.warning(f"Invalid category type attempted: {category_type}")
        return False
        
    conn = get_db_connection()
    try:
        conn.execute(
            '''INSERT INTO custom_categories (name, type, description) 
               VALUES (?, ?, ?)''',
            (name.strip(), category_type, description)
        )
        conn.commit()
        logger.info(f"Custom category added: {name} ({category_type})")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Category already exists: {name}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to add custom category: {e}")
        return False
    finally:
        conn.close()
def get_default_categories(category_type: str) -> List[str]:
    """Get default predefined categories for income and expense types."""
    default_categories = {
        'income': [
            'Salary', 'Freelance', 'Investment', 'Gift', 'Bonus', 
            'Rental Income', 'Business Income', 'Side Hustle', 'Other Income'
        ],
        'expense': [
            'Food', 'Transportation', 'Housing', 'Utilities', 'Healthcare',
            'Entertainment', 'Shopping', 'Education', 'Insurance', 'Other Expense'
        ]
    }
    
    return default_categories.get(category_type, [])
def get_custom_categories(category_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve custom categories with optional type filtering."""
    conn = get_db_connection()
    try:
        if category_type:
            query = '''SELECT * FROM custom_categories 
                      WHERE type = ? AND is_active = 1 
                      ORDER BY name'''
            results = conn.execute(query, (category_type,)).fetchall()
        else:
            query = '''SELECT * FROM custom_categories 
                      WHERE is_active = 1 
                      ORDER BY type, name'''
            results = conn.execute(query).fetchall()
            
        return [dict(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve custom categories: {e}")
        return []
    finally:
        conn.close()

def delete_custom_category(category_id: int) -> bool:
    """Safely deactivate custom category (soft delete for data integrity)."""
    conn = get_db_connection()
    try:
        # Check if category is in use
        usage_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE category = (SELECT name FROM custom_categories WHERE id = ?)',
            (category_id,)
        ).fetchone()[0]
        
        if usage_count > 0:
            # Soft delete to preserve transaction history
            conn.execute(
                'UPDATE custom_categories SET is_active = 0 WHERE id = ?',
                (category_id,)
            )
            logger.info(f"Custom category deactivated (in use): ID {category_id}")
        else:
            # Hard delete if unused
            conn.execute('DELETE FROM custom_categories WHERE id = ?', (category_id,))
            logger.info(f"Custom category permanently deleted: ID {category_id}")
            
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to delete custom category: {e}")
        return False
    finally:
        conn.close()
def get_current_balance() -> float:
    """Retrieve current account balance with error handling."""
    conn = get_db_connection()
    try:
        result = conn.execute(
            'SELECT balance FROM account_balance ORDER BY last_updated DESC LIMIT 1'
        ).fetchone()
        return float(result[0]) if result else 0.00
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve account balance: {e}")
        return 0.00
    finally:
        conn.close()

def update_global_account_balance(new_balance: float, updated_by: str = 'manual') -> bool:
    """Update account balance with audit trail."""
    conn = get_db_connection()
    try:
        conn.execute(
            '''INSERT INTO account_balance (balance, updated_by) 
               VALUES (?, ?)''',
            (new_balance, updated_by)
        )
        conn.commit()
        logger.info(f"Account balance updated to ${new_balance:.2f} by {updated_by}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to update account balance: {e}")
        return False
    finally:
        conn.close()

def calculate_balance_from_transactions() -> float:
    """Calculate theoretical balance from all transactions."""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as calculated_balance
            FROM transactions
        ''').fetchone()
        return float(result[0]) if result else 0.00
    except sqlite3.Error as e:
        logger.error(f"Failed to calculate balance from transactions: {e}")
        return 0.00
    finally:
        conn.close()
def clear_all_data(confirmation_token: str) -> Dict[str, Any]:
    """Comprehensive data clearing with safety mechanisms."""
    expected_token = "CONFIRM_DELETE_ALL_DATA"
    
    if confirmation_token != expected_token:
        logger.warning("Data clearing attempted with invalid confirmation token")
        return {"success": False, "error": "Invalid confirmation token"}
    
    conn = get_db_connection()
    transaction_count = 0
    category_count = 0
    
    try:
        # Count existing data for reporting
        transaction_count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        category_count = conn.execute('SELECT COUNT(*) FROM custom_categories').fetchone()[0]
        
        # Clear all tables in dependency order
        conn.execute('DELETE FROM transactions')
        conn.execute('DELETE FROM custom_categories')
        conn.execute('DELETE FROM account_balance')
        
        # Reset account balance to zero
        conn.execute(
            'INSERT INTO account_balance (balance, updated_by) VALUES (0.00, ?)',
            ('system_reset',)
        )
        
        conn.commit()
        
        logger.warning(f"All data cleared: {transaction_count} transactions, {category_count} categories")
        
        return {
            "success": True,
            "transactions_deleted": transaction_count,
            "categories_deleted": category_count,
            "message": "All data has been permanently deleted"
        }
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Failed to clear data: {e}")
        return {"success": False, "error": f"Database error: {str(e)}"}
    finally:
        conn.close()

def backup_before_clear() -> Optional[str]:
    """Create automatic backup before destructive operations."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"auto_backup_before_clear_{timestamp}.db"
        backup_path = backup_database_with_filename(backup_filename)
        logger.info(f"Automatic backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create automatic backup: {e}")
        return None
def _classify_by_amount_sign(amount: float, description: str = "") -> tuple[str, str]:
    """
    Classify transaction type based on amount sign (primary) and description (context).
    
    Args:
        amount: Transaction amount (positive = income, negative = expense)
        description: Transaction description for logging context
        
    Returns:
        Tuple of (transaction_type, confidence_level)
    """
    if amount >= 0:
        return 'income', 'high'
    else:
        return 'expense', 'high'
def import_transactions_from_csv(csv_file_path: str, update_balance: bool = True, import_mode: str = 'append') -> Dict[str, Any]:
    """
    Import transactions from CSV with comprehensive validation and error handling.
    
    Expected CSV format: date,type,amount,category,description
    """
    if not os.path.exists(csv_file_path):
        logger.error(f"CSV file not found: {csv_file_path}")
        return {"success": False, "error": "File not found"}
    
    conn = get_db_connection()
    # Handle replace mode - clear existing transactions
    if import_mode == 'replace':
        try:
            logger.info("Replace mode selected - clearing existing transactions")
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM categories WHERE id > 8")  # Keep default categories
            conn.commit()
            logger.info("Existing transactions cleared successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to clear existing transactions: {e}")
            return {"success": False, "error": f"Failed to clear existing data: {str(e)}"}
    imported_count = 0
    error_count = 0
    errors: List[str] = []
    type_mappings = {'confident': 0, 'uncertain': 0, 'original': 0}
    
    try:
        with open(csv_file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
            # Detect delimiter and validate headers
            sample = csvfile.read(1024)
            csvfile.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            # Validate required headers
            cleaned_columns: Dict[str, str] = {}
            if reader.fieldnames:
                for col in reader.fieldnames:
                    # Remove BOM, whitespace, and normalize
                    clean_name = col.strip().replace('\ufeff', '').lower()
                    cleaned_columns[clean_name] = col
                    
            required_fields = ['date', 'type', 'amount', 'category']
            missing_fields: list[str] = []

            for field in required_fields:
                if field not in cleaned_columns:
                    missing_fields.append(field)

            if missing_fields:
                available_cols: List[str] = list(cleaned_columns.keys())
                return {
                    "success": False,
                    "error": f"Missing required columns: {', '.join(missing_fields)}. Available: {', '.join(available_cols)}"
                }

            # Process each row with detailed validation
            for row_num, row in enumerate(reader, start=2):  # Start at 2 for header
                try:
                    date_col = cleaned_columns['date']
                    type_col = cleaned_columns['type'] 
                    amount_col = cleaned_columns['amount']
                    category_col = cleaned_columns['category']

                    transaction_date = row.get(date_col, '').strip()
                    transaction_type = row.get(type_col, '').strip().lower()
                    amount_str = row.get(amount_col, '').strip()
                    category = row.get(category_col, '').strip()

                    # Amount validation and parsing
                    try:
                        # Clean amount string - remove currency symbols, commas, etc.
                        clean_amount = amount_str.replace('$', '').replace(',', '').strip()
                        
                        # Handle negative amounts in parentheses (accounting format)
                        if clean_amount.startswith('(') and clean_amount.endswith(')'):
                            clean_amount = '-' + clean_amount[1:-1]
                        
                        amount = float(clean_amount)
                        
                        # Validate reasonable amount range
                        if abs(amount) > 999999.99:
                            raise ValueError(f"Amount too large: {amount}")
                            
                    except (ValueError, TypeError) as e:
                        errors.append(f"Row {row_num}: Invalid amount '{amount_str}' - {str(e)}")
                        error_count += 1
                        continue

                    # Handle optional columns safely
                    description_col = cleaned_columns.get('description')
                    note_col = cleaned_columns.get('note')

                    description = row.get(description_col, '').strip() if description_col else ''
                    note = row.get(note_col, '').strip() if note_col else ''

                    # Combine description and note intelligently
                    if description and note:
                        full_description = f"{description} | Note: {note}"
                    elif note and not description:
                        full_description = note
                    else:
                        full_description = description
                    
                    # Date validation and parsing
                    date_formats = [
                        '%Y-%m-%d',      # 2025-06-23
                        '%m/%d/%Y',      # 06/23/2025  
                        '%d/%m/%Y',      # 23/06/2025
                        '%Y/%m/%d',      # 2025/06/23
                        '%m-%d-%Y',      # 06-23-2025
                        '%d-%m-%Y',      # 23-06-2025
                        '%m/%d/%y',      # 06/23/25
                        '%d/%m/%y',      # 23/06/25
                        '%m-%d-%y'       # 06-23-25
                    ]

                    parsed_date = None

                    # Attempt to parse the date using multiple formats
                    for date_format in date_formats:
                        try:
                            parsed_date = datetime.strptime(transaction_date, date_format).date()
                            break
                        except ValueError:
                            continue

                    # Validate that we successfully parsed a date
                    if parsed_date is None:
                        errors.append(f"Row {row_num}: Invalid date format '{transaction_date}'. Expected formats: YYYY-MM-DD, MM/DD/YYYY, etc.")
                        error_count += 1
                        continue

                    original_type = transaction_type
                    amount_based_type, _ = _classify_by_amount_sign(amount, original_type)
                    
                    # Type validation
                    if transaction_type in ['income', 'expense']:
                        # Trust explicit income/expense designation
                        final_type = transaction_type
                        type_mappings['original'] += 1
                        
                        # Warn about potential sign conflicts
                        if (transaction_type == 'income' and amount < 0) or (transaction_type == 'expense' and amount > 0):
                            logger.warning(f"Row {row_num}: Type '{transaction_type}' conflicts with amount sign {amount}")
                            
                    elif transaction_type.lower().strip() in ['income', 'expense']:
                        # Handle case variations
                        final_type = transaction_type.lower().strip()
                        type_mappings['original'] += 1
                    else:
                        # Use amount sign as primary indicator for banking data
                        final_type = amount_based_type
                        type_mappings['confident'] += 1
                        # Log the amount-based classification
                        logger.info(f"Row {row_num}: Using amount-based classification '{final_type}' for '{original_type}' (amount: {amount:+.2f})")
                    
                    # Category validation
                    if not category or category.strip() == '':
                        # Auto-assign category based on transaction type and description
                        if 'atm' in original_type.lower() or 'withdrawal' in original_type.lower():
                            category = 'ATM/Cash'
                        elif 'transfer' in original_type.lower():
                            category = 'Transfer'
                        elif 'fee' in original_type.lower() or 'charge' in original_type.lower():
                            category = 'Bank Fees'
                        elif final_type == 'income':
                            category = 'Income'
                        else:
                            category = 'Other'
                        
                        logger.info(f"Row {row_num}: Auto-assigned category '{category}' for type '{original_type}'")
                        full_description = f"[Auto-categorized] {full_description}".strip()
                    
                    # Normalize amount to always be positive - type field determines income/expense
                    normalized_amount = abs(amount)

                    # Use date as created_at to ensure proper sorting regardless of import order
                    conn.execute('''
                        INSERT INTO transactions (date, type, amount, category, description, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''', (parsed_date, final_type, normalized_amount, category, full_description, parsed_date))
                    
                    logger.info(f"Inserted row {row_num}: {parsed_date}, {final_type}, {normalized_amount}, {category}")
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing row {row_num}: {e}")
                    errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                    error_count += 1
                    continue
            
            # Commit all valid transactions
            conn.commit()
            
            # Handle balance reconciliation with existing data
            if update_balance and imported_count > 0:
                pre_import_balance = get_current_balance()
                calculated_balance = calculate_balance_from_transactions()
                
                # Check if this is the first import vs adding to existing data
                existing_transaction_count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
                
                if existing_transaction_count == imported_count:
                    # First import - use calculated balance directly
                    update_global_account_balance(calculated_balance, 'csv_import_initial')
                    logger.info(f"Initial import: Set balance to ${calculated_balance:.2f}")
                else:
                    # Additional import - need to reconcile carefully
                    logger.warning(f"Balance reconciliation needed: Current=${pre_import_balance:.2f}, "
                                f"Calculated=${calculated_balance:.2f}")
                    
                    # Use calculated balance (replaces current)
                    update_global_account_balance(calculated_balance, 'csv_import_recalc')
                    
                    # Log the discrepancy for user review
                    balance_difference = calculated_balance - pre_import_balance
                    logger.info(f"Balance updated by ${balance_difference:+.2f} after import")
                
                # Validate final balance makes sense
                if calculated_balance < -10000:  # Arbitrary threshold for very negative balances
                    logger.warning(f"Calculated balance seems unusually negative: ${calculated_balance:.2f}. "
                                f"This might indicate incorrect income/expense classification.")
            
            logger.info(f"CSV import completed: {imported_count} imported, {error_count} errors")
            logger.info(f"Type mappings - Original format: {type_mappings['original']}, "
                    f"Confident mappings: {type_mappings['confident']}, "
                    f"Uncertain mappings: {type_mappings['uncertain']}")
            
            return {
                "success": True,
                "imported_count": imported_count,
                "error_count": error_count,
                "errors": errors[:10],  # Limit error messages for UI
                "total_errors": len(errors),
                "type_mappings": type_mappings,
                "mapping_summary": f"{type_mappings['confident']} confident, {type_mappings['uncertain']} uncertain mappings",
                "import_mode": import_mode
            }
            
    except PermissionError:
        logger.error(f"Permission denied reading CSV file: {csv_file_path}")
        return {"success": False, "error": "Permission denied reading file"}
    except UnicodeDecodeError:
        logger.error(f"Invalid file encoding: {csv_file_path}")
        return {"success": False, "error": "Invalid file encoding. Please use UTF-8"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Unexpected error during CSV import: {e}", exc_info=True)
        return {"success": False, "error": f"Import failed: {str(e)}"}
    finally:
        conn.close()
def reconcile_existing_transactions(csv_has_balance_column: bool, final_csv_balance: Optional[float] = None) -> Dict[str, Any]:
    """
    Intelligent balance reconciliation after CSV import.
    
    Args:
        csv_has_balance_column: Whether CSV contained balance information
        final_csv_balance: The final balance from CSV if available
    
    Returns:
        Dictionary with reconciliation results
    """
    conn = get_db_connection()
    correct_balance = 0.0
    csv_has_balance_column = bool(csv_has_balance_column)
    final_csv_balance = final_csv_balance if final_csv_balance is not None else 0.
    try:
        calculated_balance = calculate_balance_from_transactions()
        current_stored_balance = get_current_balance()
        
        # Determine the correct balance to use
        if csv_has_balance_column:
            # Use the final balance from CSV as authoritative
            correct_balance = final_csv_balance
            update_global_account_balance(correct_balance, 'csv_import_with_balance')
            logger.info(f"Balance set to CSV final balance: ${correct_balance:.2f}")
            
        elif abs(current_stored_balance - calculated_balance) > 0.01:
            # Significant mismatch - likely need to use calculated balance
            logger.warning(f"Balance mismatch detected: Stored=${current_stored_balance:.2f}, "
                         f"Calculated=${calculated_balance:.2f}")
            
            # Use calculated balance as authoritative for new imports
            update_global_account_balance(calculated_balance, 'csv_import_reconciliation')
            correct_balance = calculated_balance
            logger.info(f"Balance reconciled to calculated amount: ${correct_balance:.2f}")
        else:
            correct_balance = current_stored_balance
            logger.info(f"Balance reconciliation not needed: ${correct_balance:.2f}")
        
        return {
            "success": True,
            "final_balance": correct_balance,
            "was_reconciled": abs(current_stored_balance - correct_balance) > 0.01,
            "previous_balance": current_stored_balance,
            "calculated_balance": calculated_balance
        }
        
    except Exception as e:
        logger.error(f"Balance reconciliation failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
def reconcile_balance() -> Dict[str, Any]:
    """
    Simple balance reconciliation - updates stored balance to match calculated balance.
    
    Returns:
        Dictionary with reconciliation results
    """
    try:
        current_stored_balance = get_current_balance()
        calculated_balance = calculate_balance_from_transactions()
        
        # Check if there's a significant mismatch (more than 1 cent)
        mismatch = abs(current_stored_balance - calculated_balance) > 0.01
        
        if mismatch:
            # Update stored balance to match calculated balance
            update_global_account_balance(calculated_balance, 'manual_reconciliation')
            
            logger.info(f"Balance reconciled: ${current_stored_balance:.2f} -> ${calculated_balance:.2f}")
            
            return {
                "success": True,
                "was_reconciled": True,
                "previous_balance": current_stored_balance,
                "new_balance": calculated_balance,
                "difference": calculated_balance - current_stored_balance
            }
        else:
            return {
                "success": True,
                "was_reconciled": False,
                "current_balance": current_stored_balance,
                "message": "No reconciliation needed"
            }
            
    except Exception as e:
        logger.error(f"Balance reconciliation failed: {e}")
        return {"success": False, "error": str(e)}
def get_transaction_count(days: Optional[int] = None) -> int:
    """
    Get total count of transactions for pagination support.
    
    Args:
        days: Filter transactions within last N days
        
    Returns:
        Total number of matching transactions
    """
    conn = get_db_connection()
    try:
        if days:
            query = "SELECT COUNT(*) FROM transactions WHERE date >= date('now', '-{} days')".format(days)
        else:
            query = "SELECT COUNT(*) FROM transactions"
            
        result = conn.execute(query).fetchone()
        return result[0] if result else 0
        
    except sqlite3.Error as e:
        logger.error(f"Failed to get transaction count: {e}")
        return 0
    finally:
        conn.close()
def get_monthly_balance_history(months: int = 12) -> List[Dict[str, Any]]:
    """Get monthly account balance progression for the last N months"""
    conn = get_db_connection()
    try:
        # Calculate cumulative balance from ALL transactions, but only return recent months
        query = '''
        WITH all_monthly_data AS (
            SELECT 
                strftime('%Y-%m', date) as month,
                strftime('%Y-%m-01', date) as month_start,
                SUM(CASE WHEN type = 'income' THEN amount ELSE -amount END) as monthly_net
            FROM transactions 
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month
        ),
        cumulative_balance AS (
            SELECT 
                month,
                month_start,
                monthly_net,
                SUM(monthly_net) OVER (ORDER BY month) as running_balance
            FROM all_monthly_data
        ),
        recent_months AS (
            SELECT 
                month,
                month_start,
                monthly_net,
                running_balance
            FROM cumulative_balance
            WHERE month >= strftime('%Y-%m', date('now', '-{} months'))
            ORDER BY month
        )
        SELECT * FROM recent_months
        '''.format(months)
        
        results = conn.execute(query).fetchall()
        
        # Format for Chart.js
        monthly_data: List[Dict[str, Any]] = []
        for row in results:
            # Convert YYYY-MM to MM/YY format for display
            month_date = datetime.strptime(row['month_start'], '%Y-%m-%d')
            formatted_month = month_date.strftime('%m/%y')
            
            monthly_data.append({
                'month': formatted_month,
                'balance': float(row['running_balance']),
                'monthly_change': float(row['monthly_net'])
            })
        
        # If no data exists, return empty array
        if not monthly_data:
            logger.info("No monthly balance data available")
            return []
        
        logger.info(f"Generated {len(monthly_data)} months of balance history")
        return monthly_data
        
    except sqlite3.Error as e:
        logger.error(f"Failed to get monthly balance history: {e}")
        return []  # type: List[Dict[str, Any]]
    finally:
        conn.close()
def create_accounts_table():
    """Create accounts table for multiple account support."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL CHECK(type IN ('checking', 'savings', 'credit_card', 'investment', 'cash', 'other')),
                description TEXT,
                initial_balance DECIMAL(10, 2) DEFAULT 0.00,
                current_balance DECIMAL(10, 2) DEFAULT 0.00,
                is_active BOOLEAN DEFAULT 1,
                created_date DATE DEFAULT CURRENT_DATE,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if transactions table exists and needs account_id column
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'").fetchall()
        
        if tables:  # Only proceed if transactions table exists
            columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
            has_account_id = any(col[1] == 'account_id' for col in columns)
            
            if not has_account_id:
                conn.execute('ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id)')
        else:
            logger.warning("Transactions table not found - skipping account_id column addition")
        
        # Create default account if none exist
        account_count = conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
        if account_count == 0:
            conn.execute('''
                INSERT INTO accounts (name, type, description, current_balance, initial_balance) 
                VALUES (?, ?, ?, ?, ?)
            ''', ('Main Account', 'checking', 'Default account', get_current_balance(), 0.00))
            
            # Update existing transactions to use default account
            conn.execute('UPDATE transactions SET account_id = 1 WHERE account_id IS NULL')
        
        conn.commit()
        logger.info("Accounts table initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to create accounts table: {e}")
        raise
    finally:
        conn.close()

def get_accounts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Get all accounts with optional filtering."""
    conn = get_db_connection()
    try:
        if active_only:
            accounts = conn.execute(
                'SELECT * FROM accounts WHERE is_active = 1 ORDER BY name'
            ).fetchall()
        else:
            accounts = conn.execute(
                'SELECT * FROM accounts ORDER BY name'
            ).fetchall()
        return [dict(account) for account in accounts]
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve accounts: {e}")
        return []
    finally:
        conn.close()

def add_account(name: str, account_type: str, description: Optional[str] = None, initial_balance: float = 0.00):
    """Add new account."""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO accounts (name, type, description, initial_balance, current_balance) 
            VALUES (?, ?, ?, ?, ?)
        ''', (name.strip(), account_type, description, initial_balance, initial_balance))
        conn.commit()
        logger.info(f"Account added: {name} ({account_type})")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Account already exists: {name}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to add account: {e}")
        return False
    finally:
        conn.close()

def update_account_balance(account_id: int, new_balance: float):
    """Update specific account balance."""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE accounts 
            SET current_balance = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (new_balance, account_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to update account balance: {e}")
        return False
    finally:
        conn.close()

def calculate_account_balance(account_id: int) -> float:
    """Calculate balance for specific account from transactions."""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as calculated_balance
            FROM transactions
            WHERE account_id = ?
        ''', (account_id,)).fetchone()
        
        # Add initial balance
        initial_balance = conn.execute(
            'SELECT initial_balance FROM accounts WHERE id = ?', (account_id,)
        ).fetchone()
        
        calculated = float(result[0]) if result else 0.00
        initial = float(initial_balance[0]) if initial_balance else 0.00
        
        return calculated + initial
    except sqlite3.Error as e:
        logger.error(f"Failed to calculate account balance: {e}")
        return 0.00
    finally:
        conn.close()

def get_account_summary() -> List[Dict[str, Any]]:
    """Get summary of all accounts with balances and comprehensive error handling."""
    try:
        # First, verify accounts table exists
        conn = get_db_connection()
        try:
            # Check if accounts table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
            ).fetchone()
            
            if not table_check:
                logger.error("Accounts table does not exist - running migration")
                conn.close()
                # Trigger migration
                create_accounts_table()
                migrate_existing_data()
                conn = get_db_connection()
            
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Database structure check failed: {e}")
            conn.close()
            raise
        
        # Load accounts with error handling
        accounts = get_accounts()
        logger.info(f"Successfully loaded {len(accounts)} accounts")
        
        # Calculate balances with individual error handling and proper type conversion
        for account in accounts:
            try:
                # Ensure current_balance is a float
                account['current_balance'] = float(account.get('current_balance', 0.0))
                account['initial_balance'] = float(account.get('initial_balance', 0.0))
                
                # Calculate balance from transactions
                calculated_balance = calculate_account_balance(account['id'])
                account['calculated_balance'] = float(calculated_balance)
                
                logger.debug(f"Account {account['id']} ({account['name']}): "
                           f"current=${account['current_balance']:.2f}, "
                           f"calculated=${account['calculated_balance']:.2f}")
                           
            except Exception as e:
                logger.error(f"Failed to calculate balance for account {account['id']} ({account.get('name', 'Unknown')}): {e}")
                # Set fallback balances to prevent template errors
                account['current_balance'] = float(account.get('current_balance', 0.0))
                account['calculated_balance'] = account['current_balance']
                account['initial_balance'] = float(account.get('initial_balance', 0.0))
        
        return accounts
        
    except Exception as e:
        logger.error(f"Critical error in get_account_summary: {e}", exc_info=True)
        # Return empty list with default account to prevent complete failure
        return [{
            'id': 1,
            'name': 'Default Account',
            'type': 'checking',
            'description': 'Fallback account due to loading error',
            'current_balance': 0.0,
            'calculated_balance': 0.0,
            'initial_balance': 0.0,
            'is_active': 1,
            'created_date': datetime.now().strftime('%Y-%m-%d'),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }]
def get_category_spending(days: int = 30, account_id: Optional[int] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get spending breakdown by category for charts with optional account and category filtering"""
    conn = get_db_connection()
    
    # Build query with optional filters
    base_query = '''
        SELECT 
            category,
            SUM(amount) as total,
            COUNT(*) as count
        FROM transactions 
        WHERE type = 'expense' 
        AND date >= date('now', '-{} days')
    '''.format(days)
    
    params: List[Any] = []
    
    if account_id:
        base_query += ' AND account_id = ?'
        params.append(account_id)
    
    if category:
        base_query += ' AND category = ?'
        params.append(category)
    
    base_query += '''
        GROUP BY category
        ORDER BY total DESC
    '''
    
    results = conn.execute(base_query, params).fetchall()
    conn.close()
    
    return [{'category': row['category'], 'total': float(row['total']), 'count': row['count']} 
            for row in results]

def get_daily_balance(days: int = 30, account_id: Optional[int] = None) -> List[Dict[str, float]]:
    """Get daily income/expense for trend charts with optional account filtering"""
    conn = get_db_connection()
    
    base_query = '''
        SELECT 
            date,
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as expense
        FROM transactions 
        WHERE date >= date('now', '-{} days')
    '''.format(days)
    
    params: List[Any] = []
    if account_id:
        base_query += ' AND account_id = ?'
        params.append(account_id)
    
    base_query += '''
        GROUP BY date
        ORDER BY date
    '''
    
    results = conn.execute(base_query, params).fetchall()
    conn.close()
    
    return [{'date': row['date'], 'income': float(row['income']), 'expense': float(row['expense'])} 
            for row in results]

def get_account_balance_history(account_id: int, days: int = 30) -> List[Dict[str, Any]]:
    """Get daily balance progression for specific account"""
    conn = get_db_connection()
    try:
        # Get initial balance
        initial_balance = conn.execute(
            'SELECT initial_balance FROM accounts WHERE id = ?', (account_id,)
        ).fetchone()
        initial = float(initial_balance[0]) if initial_balance else 0.00
        
        # Get daily running totals
        query = '''
        WITH daily_transactions AS (
            SELECT 
                date,
                SUM(CASE WHEN type = 'income' THEN amount ELSE -amount END) as daily_net
            FROM transactions 
            WHERE account_id = ? AND date >= date('now', '-{} days')
            GROUP BY date
            ORDER BY date
        ),
        running_balance AS (
            SELECT 
                date,
                daily_net,
                SUM(daily_net) OVER (ORDER BY date) + ? as running_balance
            FROM daily_transactions
        )
        SELECT date, running_balance, daily_net
        FROM running_balance
        ORDER BY date
        '''.format(days)
        
        results = conn.execute(query, (account_id, initial)).fetchall()
        
        return [{'date': row['date'], 'balance': float(row['running_balance']), 
                'daily_change': float(row['daily_net'])} for row in results]
        
    except sqlite3.Error as e:
        logger.error(f"Failed to get account balance history: {e}")
        return []
    finally:
        conn.close()
def create_transfer(from_account_id: int, to_account_id: int, amount: float, description: Optional[str] = None, date: Optional[str] = None) -> bool:
    """Create a transfer between accounts."""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    
    if from_account_id == to_account_id:
        logger.error("Cannot transfer to the same account")
        return False
    
    if amount <= 0:
        logger.error("Transfer amount must be positive")
        return False
    
    conn = get_db_connection()
    try:
        # Start transaction
        conn.execute('BEGIN')
        
        # Create expense transaction for source account
        conn.execute('''
            INSERT INTO transactions (amount, category, type, description, date, account_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (amount, 'Transfer Out', 'expense', f"Transfer to account ID {to_account_id}: {description or ''}", date, from_account_id))
        
        # Create income transaction for destination account
        conn.execute('''
            INSERT INTO transactions (amount, category, type, description, date, account_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (amount, 'Transfer In', 'income', f"Transfer from account ID {from_account_id}: {description or ''}", date, to_account_id))
        
        conn.commit()
        conn.close()
        
        # Automatically update both account balances
        from_balance_updated = _auto_update_account_balance(from_account_id)
        to_balance_updated = _auto_update_account_balance(to_account_id)
        
        if from_balance_updated and to_balance_updated:
            logger.info(f"Transfer created and both account balances auto-updated: ${amount} from account {from_account_id} to {to_account_id}")
        else:
            logger.warning(f"Transfer created but failed to auto-update one or both account balances")
        
        return True
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Failed to create transfer: {e}")
        return False
    finally:
        conn.close()

def get_transactions(days: Optional[int] = None, limit: Optional[int] = None, offset: int = 0, account_id: Optional[int] = None) -> List[sqlite3.Row]:
    """
    Retrieve transactions with comprehensive filtering including account support.
    """
    conn = get_db_connection()
    try:
        base_query = "SELECT t.*, a.name as account_name FROM transactions t LEFT JOIN accounts a ON t.account_id = a.id"
        from typing import Any
        params: list[Any] = []
        conditions: list[str] = []
        
        # Add date filter if specified
        if days is not None and days > 0:
            conditions.append("t.date >= date('now', '-{} days')".format(int(days)))
            logger.debug(f"Adding date filter for last {days} days")
        
        # Add account filter if specified
        if account_id is not None:
            conditions.append("t.account_id = ?")
            params.append(account_id)
            logger.debug(f"Adding account filter for account {account_id}")
        
        # Build WHERE clause
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        # Order by date descending (newest first)
        base_query += " ORDER BY t.date DESC, t.created_at DESC"
        
        if limit and limit > 0:
            base_query += f" LIMIT {int(limit)}"
            if offset > 0:
                base_query += f" OFFSET {int(offset)}"
        
        logger.info(f"Executing query: {base_query} with params: {params}")
        transactions = conn.execute(base_query, params).fetchall()
        
        logger.info(f"Retrieved {len(transactions)} transactions (days={days}, account_id={account_id}, limit={limit})")
        return transactions
        
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve transactions: {e}")
        return []
    finally:
        conn.close()
def migrate_existing_data():
    """Migrate existing installations to support multiple accounts."""
    conn = get_db_connection()
    try:
        # Check if accounts table exists
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'").fetchall()
        
        if not tables:
            logger.info("Creating accounts table for existing installation")
            create_accounts_table()
        else:
            # Check if accounts table has the new schema
            columns = conn.execute("PRAGMA table_info(accounts)").fetchall()
            column_names = [col[1] for col in columns]
            
            # If missing the 'type' column, we need to migrate the table
            if 'type' not in column_names:
                logger.info("Migrating accounts table to new schema")
                
                # Backup existing data
                existing_accounts = conn.execute('SELECT * FROM accounts').fetchall()
                
                # Drop and recreate table with new schema
                conn.execute('DROP TABLE accounts')
                
                # Create new accounts table
                conn.execute('''
                    CREATE TABLE accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        type TEXT NOT NULL CHECK(type IN ('checking', 'savings', 'credit_card', 'investment', 'cash', 'other')),
                        description TEXT,
                        initial_balance DECIMAL(10, 2) DEFAULT 0.00,
                        current_balance DECIMAL(10, 2) DEFAULT 0.00,
                        is_active BOOLEAN DEFAULT 1,
                        created_date DATE DEFAULT CURRENT_DATE,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Restore data with default values for new columns
                for account in existing_accounts:
                    conn.execute('''
                        INSERT INTO accounts (id, name, type, description, initial_balance, current_balance, is_active) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        account['id'], 
                        account['name'], 
                        'checking',  # Default type
                        f"Migrated from old schema", 
                        account.get('balance', 0.00),  # Use old balance as initial
                        account.get('balance', 0.00),  # Use old balance as current
                        1  # Active
                    ))
                
                logger.info("Accounts table migration completed")
            
        # Check if transactions have account_id column
        trans_columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
        has_account_id = any(col[1] == 'account_id' for col in trans_columns)
        
        if not has_account_id:
            logger.info("Adding account_id column to transactions")
            conn.execute('ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id)')
            
            # Create default account if none exist
            account_count = conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
            if account_count == 0:
                current_balance = get_current_balance()
                conn.execute('''
                    INSERT INTO accounts (name, type, description, current_balance, initial_balance) 
                    VALUES (?, ?, ?, ?, ?)
                ''', ('Main Account', 'checking', 'Default account', current_balance, 0.00))
                
            # Update existing transactions to use default account (ID = 1)
            conn.execute('UPDATE transactions SET account_id = 1 WHERE account_id IS NULL')
        
        conn.commit()
        logger.info("Data migration completed successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to migrate data: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
def update_account(account_id: int, name: str, account_type: str, description: Optional[str] = None) -> bool:
    """Update account details."""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE accounts 
            SET name = ?, type = ?, description = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (name.strip(), account_type, description, account_id))
        conn.commit()
        
        if conn.total_changes > 0:
            logger.info(f"Account updated: ID {account_id}, Name: {name}")
            return True
        else:
            logger.warning(f"No account found with ID {account_id}")
            return False
            
    except sqlite3.IntegrityError:
        logger.warning(f"Account name already exists: {name}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Failed to update account: {e}")
        return False
    finally:
        conn.close()

def get_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    """Get account details by ID."""
    conn = get_db_connection()
    try:
        account = conn.execute(
            'SELECT * FROM accounts WHERE id = ?', (account_id,)
        ).fetchone()
        return dict(account) if account else None
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve account: {e}")
        return None
    finally:
        conn.close()
def delete_account(account_id: int, force_delete: bool = False) -> Dict[str, Any]:
    """
    Delete account with safety checks for transaction integrity.
    
    Args:
        account_id: ID of account to delete
        force_delete: If True, moves transactions to default account before deletion
    
    Returns:
        Dictionary with success status and details
    """
    conn = get_db_connection()
    try:
        # Check if account exists
        account = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
        if not account:
            return {"success": False, "error": "Account not found"}
        
        # Prevent deletion of last remaining account
        account_count = conn.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1').fetchone()[0]
        if account_count <= 1:
            return {"success": False, "error": "Cannot delete the last remaining account"}
        
        # Check for existing transactions
        transaction_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id = ?', (account_id,)
        ).fetchone()[0]
        
        if transaction_count > 0 and not force_delete:
            return {
                "success": False, 
                "error": f"Cannot delete account with {transaction_count} transactions. Use force delete to move transactions to default account.",
                "transaction_count": transaction_count
            }
        
        if transaction_count > 0 and force_delete:
            # Move transactions to default account (ID 1)
            conn.execute(
                'UPDATE transactions SET account_id = 1 WHERE account_id = ?', 
                (account_id,)
            )
            logger.info(f"Moved {transaction_count} transactions from account {account_id} to default account")
        
        # Soft delete the account
        conn.execute(
            'UPDATE accounts SET is_active = 0, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (account_id,)
        )
        
        conn.commit()
        logger.info(f"Account {account_id} deleted successfully")
        
        return {
            "success": True,
            "account_name": account['name'],
            "moved_transactions": transaction_count if force_delete else 0
        }
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Failed to delete account {account_id}: {e}")
        return {"success": False, "error": f"Database error: {str(e)}"}
    finally:
        conn.close()

def create_ious_table():
    """Create table for managing IOUs and pending transactions."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ious (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creditor_name TEXT NOT NULL,
                debtor_name TEXT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                description TEXT,
                due_date DATE,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'partially_paid', 'paid', 'cancelled')),
                created_date DATE DEFAULT CURRENT_DATE,
                settled_date DATE,
                notes TEXT
            )
        ''')
        conn.commit()

        logger.info("IOUs table created successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to create IOUs table: {e}")
        raise
    finally:
        conn.close()
def create_iou_payments_table():
    """Create table for tracking partial IOU payments."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS iou_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iou_id INTEGER NOT NULL,
                payment_amount DECIMAL(10, 2) NOT NULL,
                payment_date DATE DEFAULT CURRENT_DATE,
                payment_method TEXT,
                notes TEXT,
                account_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (iou_id) REFERENCES ious(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        conn.commit()
        logger.info("IOU payments table created successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to create IOU payments table: {e}")
        raise
    finally:
        conn.close()
def migrate_ious_table():
    """Migrate existing IOUs table to correct schema and add missing columns."""
    conn = get_db_connection()
    try:
        # Check current table structure
        columns = conn.execute("PRAGMA table_info(ious)").fetchall()
        column_names = [col[1] for col in columns]
        
        # Check if we have the old schema (lender_id/borrower_id) or new schema (creditor_name/debtor_name)
        has_old_schema = 'lender_id' in column_names and 'borrower_id' in column_names
        has_new_schema = 'creditor_name' in column_names and 'debtor_name' in column_names
        
        if has_old_schema and not has_new_schema:
            logger.info("Migrating IOUs table from old schema to new schema")
            
            # Create new table with correct schema
            conn.execute('''
                CREATE TABLE ious_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creditor_name TEXT NOT NULL,
                    debtor_name TEXT NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    description TEXT,
                    due_date DATE,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'partially_paid', 'paid', 'cancelled')),
                    created_date DATE DEFAULT CURRENT_DATE,
                    settled_date DATE,
                    notes TEXT
                )
            ''')
            
            # Copy data from old table (converting IDs to names - simplified approach)
            # Since we can't easily convert IDs to names without account data, we'll start fresh
            logger.warning("Old IOU data will not be migrated due to schema incompatibility")
            
            # Drop old table and rename new table
            conn.execute('DROP TABLE ious')
            conn.execute('ALTER TABLE ious_new RENAME TO ious')
            
        elif not has_new_schema:
            # Table doesn't exist or is completely wrong, create new one
            logger.info("Creating new IOUs table with correct schema")
            conn.execute('DROP TABLE IF EXISTS ious')
            conn.execute('''
                CREATE TABLE ious (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creditor_name TEXT NOT NULL,
                    debtor_name TEXT NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    description TEXT,
                    due_date DATE,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'partially_paid', 'paid', 'cancelled')),
                    created_date DATE DEFAULT CURRENT_DATE,
                    settled_date DATE,
                    notes TEXT
                )
            ''')
        else:
            # Table has correct schema, just add missing columns if needed
            if 'created_date' not in column_names:
                logger.info("Adding created_date column to ious table")
                conn.execute('ALTER TABLE ious ADD COLUMN created_date DATE DEFAULT CURRENT_DATE')
                
            if 'settled_date' not in column_names:
                logger.info("Adding settled_date column to ious table")
                conn.execute('ALTER TABLE ious ADD COLUMN settled_date DATE')
                
            if 'notes' not in column_names:
                logger.info("Adding notes column to ious table")
                conn.execute('ALTER TABLE ious ADD COLUMN notes TEXT')
            if 'payment_identifier' not in column_names:
                logger.info("Adding payment_identifier column to ious table")
                conn.execute('ALTER TABLE ious ADD COLUMN payment_identifier TEXT') 
        conn.commit()
        logger.info("IOUs table migration completed successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to migrate IOUs table: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
def add_iou(creditor_name: str, debtor_name: str, amount: float, 
           description: str = "", due_date: Optional[str] = None, 
           payment_identifier: Optional[str] = None) -> bool:
    """Add new IOU/pending transaction."""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO ious (creditor_name, debtor_name, amount, description, due_date, payment_identifier)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (creditor_name, debtor_name, amount, description, due_date, payment_identifier))
        conn.commit()
        logger.info(f"IOU added: {creditor_name} owes {debtor_name} ${amount}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to add IOU: {e}")
        return False
    finally:
        conn.close()

def get_ious(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get IOUs with optional status filtering and payment information."""
    conn = get_db_connection()
    try:
        # Check if created_date column exists before using it
        columns = conn.execute("PRAGMA table_info(ious)").fetchall()
        column_names = [col[1] for col in columns]
        
        # Use appropriate ordering based on available columns
        if 'created_date' in column_names:
            order_clause = "ORDER BY created_date DESC"
        else:
            order_clause = "ORDER BY id DESC"
        
        # Modified logic to handle "pending" status properly
        if status == 'pending':
            # Include both 'pending' and 'partially_paid' IOUs as they're both still active
            query = f"SELECT * FROM ious WHERE status IN ('pending', 'partially_paid') {order_clause}"
            ious = conn.execute(query).fetchall()
        elif status:
            query = f'SELECT * FROM ious WHERE status = ? {order_clause}'
            ious = conn.execute(query, (status,)).fetchall()
        else:
            query = f'SELECT * FROM ious {order_clause}'
            ious = conn.execute(query).fetchall()
        
        # Add payment information to each IOU
        result: List[Dict[str, Any]] = []
        for iou in ious:
            iou_dict = dict(iou)
            iou_dict['remaining_balance'] = get_iou_remaining_balance(iou['id'])
            iou_dict['total_paid'] = float(iou['amount']) - iou_dict['remaining_balance']
            result.append(iou_dict)
            
        return result
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve IOUs: {e}")
        return []
    finally:
        conn.close()
def update_iou_payment(payment_id: int, payment_method: Optional[str] = None, 
                      notes: Optional[str] = None) -> bool:
    """Update IOU payment method and notes."""
    conn = get_db_connection()
    try:
        # Build update query dynamically based on provided parameters
        updates: list[str] = []
        params: list[Any] = []
        
        if payment_method is not None:
            updates.append("payment_method = ?")
            params.append(payment_method.strip() if payment_method else None)
            
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes.strip() if notes else None)
        
        if not updates:
            logger.warning("No updates provided for payment update")
            return False
            
        # Add timestamp update
        updates.append("created_at = created_at")  # Keep original timestamp
        
        query = f"UPDATE iou_payments SET {', '.join(updates)} WHERE id = ?"
        params.append(payment_id)
        
        conn.execute(query, params)
        conn.commit()
        
        logger.info(f"IOU payment {payment_id} updated successfully")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Failed to update IOU payment {payment_id}: {e}")
        return False
    finally:
        conn.close()
def settle_iou(iou_id: int, create_transaction: bool = False, account_id: Optional[int] = None) -> bool:
    """Mark IOU as settled with proper transaction handling and retry logic."""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        conn = None
        try:
            conn = get_db_connection()
            
            # Get IOU details first to determine transaction type
            iou = conn.execute('SELECT * FROM ious WHERE id = ?', (iou_id,)).fetchone()
            if not iou:
                logger.error(f"IOU {iou_id} not found")
                return False
            
            # Start explicit transaction
            conn.execute('BEGIN IMMEDIATE')
            
            # Update IOU status
            conn.execute('''
                UPDATE ious 
                SET status = 'paid', settled_date = CURRENT_DATE 
                WHERE id = ?
            ''', (iou_id,))
            
            if create_transaction and account_id:
                # Determine transaction type based on who you are in the IOU
                if iou['creditor_name'].lower() == 'me':
                    # You are receiving money - this is income
                    transaction_type = 'income'
                    description = f"Received payment: {iou['description']} from {iou['debtor_name']}"
                    category = 'Debt Collection'
                elif iou['debtor_name'].lower() == 'me':
                    # You are paying money - this is expense
                    transaction_type = 'expense'
                    description = f"Paid debt: {iou['description']} to {iou['creditor_name']}"
                    category = 'Debt Payment'
                else:
                    # Third-party settlement - default to income (recording that debt was settled)
                    transaction_type = 'income'
                    description = f"Debt settled: {iou['creditor_name']} received from {iou['debtor_name']} - {iou['description']}"
                    category = 'Debt Settlement'
                
                # Create the transaction within the same transaction
                conn.execute('''
                    INSERT INTO transactions (amount, category, type, description, date, account_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    float(iou['amount']),
                    category,
                    transaction_type,
                    description,
                    datetime.now().strftime('%Y-%m-%d'),
                    account_id
                ))
                
                logger.info(f"Created {transaction_type} transaction for IOU settlement: ${iou['amount']}")
            
            # Commit the transaction
            conn.commit()
            logger.info(f"IOU {iou_id} settled successfully")
            return True
            
        except sqlite3.OperationalError as e:
            if conn:
                conn.rollback()
            if "database is locked" in str(e).lower():
                retry_count += 1
                logger.warning(f"Database locked, retry {retry_count}/{max_retries}")
                if retry_count < max_retries:
                    import time
                    time.sleep(0.1 * retry_count)  # Exponential backoff
                    continue
            logger.error(f"Database operational error settling IOU {iou_id}: {e}")
            return False
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to settle IOU {iou_id}: {e}")
            return False
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Unexpected error settling IOU {iou_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    logger.error(f"Failed to settle IOU {iou_id} after {max_retries} retries")
    return False
def get_unique_categories() -> List[str]:
    """Get all unique categories used in transactions for filtering."""
    conn = get_db_connection()
    try:
        results = conn.execute('''
            SELECT DISTINCT category 
            FROM transactions 
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category
        ''').fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve unique categories: {e}")
        return []
    finally:
        conn.close()
def add_iou_payment(iou_id: int, payment_amount: float, payment_method: Optional[str] = None, 
                   notes: Optional[str] = None, account_id: Optional[int] = None) -> bool:
    """Add a partial payment to an IOU."""
    conn = get_db_connection()
    try:
        # Verify IOU exists and is not already fully paid
        iou = conn.execute('SELECT * FROM ious WHERE id = ? AND status != ?', (iou_id, 'paid')).fetchone()
        if not iou:
            logger.warning(f"IOU {iou_id} not found or already paid")
            return False
        
        # Check if payment amount is valid
        remaining_balance = get_iou_remaining_balance(iou_id)
        if payment_amount <= 0 or payment_amount > remaining_balance:
            logger.warning(f"Invalid payment amount: ${payment_amount:.2f} (remaining: ${remaining_balance:.2f})")
            return False
        # Enhanced payment validation
        if payment_amount > remaining_balance * 1.01:  # Allow 1% tolerance for rounding
            logger.warning(f"Payment amount ${payment_amount:.2f} significantly exceeds remaining balance ${remaining_balance:.2f}")
            return False

        # Validate payment method if provided
        if payment_method and len(payment_method.strip()) > 50:
            logger.warning(f"Payment method too long: {len(payment_method)} characters")
            return False
        # Start transaction
        conn.execute('BEGIN')
        
        # Add payment record
        conn.execute('''
            INSERT INTO iou_payments (iou_id, payment_amount, payment_method, notes, account_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (iou_id, payment_amount, payment_method, notes, account_id))
        
        # Update IOU status based on remaining balance
        new_remaining = remaining_balance - payment_amount
        if new_remaining <= 0.01:  # Consider fully paid if less than 1 cent remains
            conn.execute('''
                UPDATE ious 
                SET status = 'paid', settled_date = CURRENT_DATE 
                WHERE id = ?
            ''', (iou_id,))
            logger.info(f"IOU {iou_id} fully paid with final payment of ${payment_amount:.2f}")
        else:
            conn.execute('''
                UPDATE ious 
                SET status = 'partially_paid'
                WHERE id = ?
            ''', (iou_id,))
            logger.info(f"Partial payment of ${payment_amount:.2f} added to IOU {iou_id}")
        
        conn.commit()
        return True
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Failed to add IOU payment: {e}")
        return False
    finally:
        conn.close()

def get_iou_payments(iou_id: int) -> List[Dict[str, Any]]:
    """Get all payments for a specific IOU."""
    conn = get_db_connection()
    try:
        payments = conn.execute('''
            SELECT p.*, a.name as account_name
            FROM iou_payments p
            LEFT JOIN accounts a ON p.account_id = a.id
            WHERE p.iou_id = ?
            ORDER BY p.payment_date DESC, p.created_at DESC
        ''', (iou_id,)).fetchall()
        return [dict(payment) for payment in payments]
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve IOU payments: {e}")
        return []
    finally:
        conn.close()

def get_iou_remaining_balance(iou_id: int) -> float:
    """Calculate remaining balance for an IOU."""
    conn = get_db_connection()
    try:
        # Get original IOU amount
        iou = conn.execute('SELECT amount FROM ious WHERE id = ?', (iou_id,)).fetchone()
        if not iou:
            return 0.0
        
        original_amount = float(iou[0])
        
        # Get total payments
        payments_result = conn.execute('''
            SELECT COALESCE(SUM(payment_amount), 0) as total_paid
            FROM iou_payments 
            WHERE iou_id = ?
        ''', (iou_id,)).fetchone()
        
        total_paid = float(payments_result[0]) if payments_result else 0.0
        remaining = original_amount - total_paid
        
        return max(0.0, remaining)  # Ensure non-negative
        
    except sqlite3.Error as e:
        logger.error(f"Failed to calculate remaining balance: {e}")
        return 0.0
    finally:
        conn.close()
def get_overdue_ious() -> List[Dict[str, Any]]:
    """Get IOUs that are past their due date."""
    conn = get_db_connection()
    try:
        overdue_ious = conn.execute('''
            SELECT i.*, 
                   (CASE WHEN i.creditor_name = 'me' THEN 'receiving' ELSE 'paying' END) as role,
                   (julianday('now') - julianday(i.due_date)) as days_overdue
            FROM ious i
            WHERE i.status IN ('pending', 'partially_paid')
            AND i.due_date IS NOT NULL
            AND i.due_date < date('now')
            ORDER BY i.due_date ASC
        ''').fetchall()
        
        result: List[Dict[str, Any]] = []
        for iou in overdue_ious:
            iou_dict = dict(iou)
            iou_dict['remaining_balance'] = get_iou_remaining_balance(iou['id'])
            result.append(iou_dict)
            
        return result
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve overdue IOUs: {e}")
        return []
    finally:
        conn.close()
def delete_iou(iou_id: int, confirmation_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Delete IOU with comprehensive validation and safety checks.
    
    Args:
        iou_id: ID of IOU to delete
        confirmation_token: Required confirmation for paid IOUs
    
    Returns:
        Dictionary with success status and details
    """
    conn = get_db_connection()
    try:
        # Get IOU details first
        iou = conn.execute('SELECT * FROM ious WHERE id = ?', (iou_id,)).fetchone()
        if not iou:
            return {"success": False, "error": "IOU not found"}
        
        iou_dict = dict(iou)
        is_paid = iou_dict['status'] == 'paid'
        
        # For paid IOUs, require confirmation token
        if is_paid and confirmation_token != f"DELETE_PAID_IOU_{iou_id}":
            return {
                "success": False, 
                "error": "Paid IOUs require confirmation token for deletion",
                "requires_confirmation": True,
                "confirmation_token": f"DELETE_PAID_IOU_{iou_id}"
            }
        
        # Start transaction for data integrity
        conn.execute('BEGIN')
        
        # Check for related payments
        payment_count = conn.execute(
            'SELECT COUNT(*) FROM iou_payments WHERE iou_id = ?', (iou_id,)
        ).fetchone()[0]
        
        if payment_count > 0:
            # Delete related payments first
            conn.execute('DELETE FROM iou_payments WHERE iou_id = ?', (iou_id,))
            logger.info(f"Deleted {payment_count} payment records for IOU {iou_id}")
        
        # Delete the IOU
        conn.execute('DELETE FROM ious WHERE id = ?', (iou_id,))
        
        conn.commit()
        
        logger.info(f"IOU {iou_id} deleted successfully (status: {iou_dict['status']}, "
                   f"amount: ${iou_dict['amount']:.2f})")
        
        return {
            "success": True,
            "iou_details": {
                "creditor": iou_dict['creditor_name'],
                "debtor": iou_dict['debtor_name'],
                "amount": float(iou_dict['amount']),
                "status": iou_dict['status'],
                "description": iou_dict.get('description', '')
            },
            "deleted_payments": payment_count
        }
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Failed to delete IOU {iou_id}: {e}")
        return {"success": False, "error": f"Database error: {str(e)}"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Unexpected error deleting IOU {iou_id}: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}
    finally:
        conn.close()
def add_payment_identifier_column():
    """Add payment_identifier column to ious table for automatic matching."""
    conn = get_db_connection()
    try:
        # Check if column already exists
        cursor = conn.execute("PRAGMA table_info(ious)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'payment_identifier' not in columns:
            conn.execute('ALTER TABLE ious ADD COLUMN payment_identifier TEXT')
            conn.commit()
            logger.info("Added payment_identifier column to ious table")
        else:
            logger.info("payment_identifier column already exists")
        
    except sqlite3.Error as e:
        logger.error(f"Error adding payment_identifier column: {e}")
        raise
    finally:
        conn.close()
def process_automatic_payment(payment_identifier: str, payment_amount: float, 
                            transaction_description: str = "", account_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Process automatic payment matching based on payment identifier.
    
    Args:
        payment_identifier: The identifier found in the payment (e.g., "PAY_MENOW")
        payment_amount: Amount of the payment
        transaction_description: Full transaction description
        account_id: Account where payment was received
    
    Returns:
        Dictionary with processing results and status
    """
    conn = get_db_connection()
    try:
        # Find IOUs with matching payment identifiers
        matching_ious = conn.execute('''
            SELECT * FROM ious 
            WHERE payment_identifier = ? 
            AND status IN ('pending', 'partially_paid')
            ORDER BY created_date ASC
        ''', (payment_identifier,)).fetchall()
        
        if not matching_ious:
            logger.warning(f"No matching IOUs found for payment identifier: {payment_identifier}")
            return {
                "success": False,
                "error": f"No active IOUs found with identifier '{payment_identifier}'",
                "payment_amount": payment_amount
            }
        
        # For multiple matches, apply to oldest first
        target_iou = matching_ious[0]
        iou_id = target_iou['id']
        remaining_balance = get_iou_remaining_balance(iou_id)
        
        # Validate payment amount
        if payment_amount <= 0:
            return {"success": False, "error": "Invalid payment amount"}
        
        # Apply payment (can be partial or overpayment)
        actual_payment = min(payment_amount, remaining_balance)
        
        # Add the payment with automatic processing note
        payment_notes = f"Auto-processed: {transaction_description[:100]}"
        success = add_iou_payment(iou_id, actual_payment, "Automatic", payment_notes, account_id)
        
        if not success:
            return {"success": False, "error": "Failed to process payment"}
        
        # Calculate results
        new_remaining = remaining_balance - actual_payment
        is_fully_paid = new_remaining <= 0.01
        
        result = {
            "success": True,
            "iou_id": iou_id,
            "payment_applied": actual_payment,
            "remaining_balance": new_remaining,
            "fully_paid": is_fully_paid,
            "iou_details": {
                "creditor": target_iou['creditor_name'],
                "debtor": target_iou['debtor_name'],
                "description": target_iou['description'],
                "original_amount": float(target_iou['amount'])
            }
        }
        
        # Handle overpayment
        if payment_amount > actual_payment:
            result["overpayment"] = payment_amount - actual_payment
            result["warning"] = f"Overpayment of ${result['overpayment']:.2f} detected"
        
        logger.info(f"Automatic payment processed: ${actual_payment:.2f} applied to IOU {iou_id}")
        return result
        
    except sqlite3.Error as e:
        logger.error(f"Database error processing automatic payment: {e}")
        return {"success": False, "error": f"Database error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error processing automatic payment: {e}", exc_info=True)
        return {"success": False, "error": f"Processing error: {str(e)}"}
    finally:
        conn.close()
def _auto_update_account_balance(account_id: int) -> bool:
    """
    Automatically update account balance based on transactions.
    
    Args:
        account_id: ID of account to update
        
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Calculate balance from transactions for this account
        calculated_balance = calculate_account_balance(account_id)
        
        # Update the account's current balance
        conn.execute('''
            UPDATE accounts 
            SET current_balance = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (calculated_balance, account_id))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Auto-updated account {account_id} balance to ${calculated_balance:.2f}")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Failed to auto-update account {account_id} balance: {e}")
        if conn is not None:
            conn.close()
        return False
    except Exception as e:
        logger.error(f"Unexpected error auto-updating account {account_id} balance: {e}")
        if conn is not None:
            conn.close()
        return False
def verify_iou_tables():
    """Verify IOU tables exist and have correct schema."""
    conn = get_db_connection()
    try:
        # Check if ious table exists
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ious'").fetchone()
        if not result:
            logger.error("IOUs table does not exist")
            return False
        
        # Check if iou_payments table exists
        result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='iou_payments'").fetchone()
        if not result:
            logger.error("IOU payments table does not exist")
            return False
            
        logger.info("All IOU tables verified successfully")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error verifying IOU tables: {e}")
        return False
    finally:
        conn.close()
def initialize_database():
    """Initialize and migrate all database tables."""
    try:
        create_ious_table()
        create_iou_payments_table()
        migrate_ious_table()  # This should already be here
        # Add this line if it's not already present:
        add_payment_identifier_column()
        
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise