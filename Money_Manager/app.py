from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from datetime import datetime
import database
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
# Configure static file serving
app.static_folder = 'static'
app.static_url_path = '/static'
# Initialize database on startup
database.init_database()
# Verify database tables
if not database.verify_iou_tables():
    app.logger.error("IOU tables missing - please run database migration")

@app.route('/')
def index():
    # Get summaries for different periods
    today_summary = database.get_summary(1)
    week_summary = database.get_summary(7)
    month_summary = database.get_summary(30)
    
    # Get recent transactions
    recent_transactions = database.get_transactions(days=7, limit=10)
    
    # Get account summary for multi-account overview
    accounts_summary = database.get_account_summary()
    
    # Calculate total portfolio value with proper type conversion and logging
    total_balance = 0.0
    try:
        for acc in accounts_summary:
            balance = float(acc.get('current_balance', 0.0))
            total_balance += balance
            app.logger.debug(f"Account {acc.get('name', 'Unknown')}: ${balance:.2f}")
        
        app.logger.info(f"Total portfolio balance calculated: ${total_balance:.2f}")
        
    except Exception as e:
        app.logger.error(f"Error calculating total balance: {e}")
        total_balance = 0.0
    # Fetch pending IOUs summary for dashboard
    try:
        pending_ious = database.get_ious('pending')
        total_owed_to_me = sum(iou['remaining_balance'] for iou in pending_ious if iou['creditor_name'].lower() == 'me')
        total_i_owe = sum(iou['remaining_balance'] for iou in pending_ious if iou['debtor_name'].lower() == 'me')
        
        pending_ious_summary: dict[str, float | int] = {
            'owed_to_me': total_owed_to_me,
            'i_owe': total_i_owe,
            'count_owed_to_me': len([iou for iou in pending_ious if iou['creditor_name'].lower() == 'me']),
            'count_i_owe': len([iou for iou in pending_ious if iou['debtor_name'].lower() == 'me'])
        }
    except Exception as e:
        app.logger.error(f"Error loading IOU summary: {e}")
        pending_ious_summary = {
            'owed_to_me': 0.0,
            'i_owe': 0.0,
            'count_owed_to_me': 0,
            'count_i_owe': 0
        }

    # Update the return statement to include:
    return render_template('index.html',
                        today=today_summary,
                        week=week_summary,
                        month=month_summary,
                        recent_transactions=recent_transactions,
                        accounts_summary=accounts_summary,
                        total_balance=total_balance,
                        pending_ious_summary=pending_ious_summary)

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    try:
        amount = float(request.form['amount'])
        category = request.form['category']
        trans_type = request.form['type']
        description = request.form['description']
        date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
        account_id = int(request.form.get('account_id', 1))  # Add this line
        
        database.add_transaction(amount, category, trans_type, description, date, account_id)
        flash(f'Transaction added and account balance automatically updated!', 'success')
        
    except ValueError:
        flash('Please enter valid values.', 'error')
    except Exception as e:
        flash(f'Error adding transaction: {str(e)}', 'error')
    
    return redirect(url_for('transactions'))

# Find the @app.route('/api/categories/<category_type>') function and replace it with:
@app.route('/api/categories/<category_type>')
def get_categories(category_type: str):
    """Get available categories including custom ones with error handling."""
    try:
        from typing import List, Dict, Any
        # Get default categories
        categories = database.get_default_categories(category_type)
        
        # Get custom categories
        custom_categories: List[Dict[str, Any]] = database.get_custom_categories(category_type)
        
        # Combine and format for JSON response
        all_categories = [{'name': cat} for cat in categories]
        all_categories.extend([{'name': cat['name'], 'custom': str(True)} for cat in custom_categories])
        
        return jsonify(all_categories)
    except Exception as e:
        app.logger.error(f"Error retrieving categories: {e}", exc_info=True)
        return jsonify([]), 500
# Removed duplicate charts route to resolve function name conflict

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id: int):
    try:
        database.delete_transaction(transaction_id)
        flash('Transaction deleted and account balance automatically updated!', 'success')
    except Exception as e:
        flash(f'Error deleting transaction: {str(e)}', 'error')
    
    return redirect(url_for('transactions'))

@app.context_processor
def utility_processor():
    """Make datetime available in templates"""
    return dict(moment=datetime)
@app.route('/export')
def export_page():
    return render_template('export.html')

@app.route('/export/csv/transactions')
def export_transactions_csv():
    days = request.args.get('days', type=int)
    filename = database.export_transactions_csv(days=days)
    
    return send_file(filename, as_attachment=True, download_name=filename,
                     mimetype='text/csv')

@app.route('/export/csv/summary')
def export_summary_csv():
    filename = database.export_summary_csv()
    
    return send_file(filename, as_attachment=True, download_name=filename,
                     mimetype='text/csv')

@app.route('/export/pdf/report')
def export_pdf_report():
    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    from typing import List
    from reportlab.platypus import Flowable
    story: List[Flowable] = []
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Title'], 
                                spaceAfter=30, textColor=colors.darkblue)
    story.append(Paragraph("Financial Report", title_style))
    story.append(Spacer(1, 12))
    
    # Get data
    today_summary = database.get_summary(1)
    week_summary = database.get_summary(7)
    month_summary = database.get_summary(30)
    category_data = database.get_category_spending(30)
    recent_transactions = database.get_transactions(days=30)
    
    # Summary table
    story.append(Paragraph("Financial Summary", styles['Heading2']))
    summary_data = [
        ['Period', 'Income', 'Expenses', 'Net'],
        ['Today', f"${today_summary['income']:.2f}", f"${today_summary['expense']:.2f}", f"${today_summary['net']:.2f}"],
        ['This Week', f"${week_summary['income']:.2f}", f"${week_summary['expense']:.2f}", f"${week_summary['net']:.2f}"],
        ['This Month', f"${month_summary['income']:.2f}", f"${month_summary['expense']:.2f}", f"${month_summary['net']:.2f}"]
    ]
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 24))
    
    # Category breakdown
    if category_data:
        story.append(Paragraph("Category Breakdown (Last 30 Days)", styles['Heading2']))
        category_table_data = [['Category', 'Amount', 'Transactions']]
        for cat in category_data[:10]:  # Top 10 categories
            category_table_data.append([
                cat['category'], 
                f"${cat['total']:.2f}", 
                str(cat['count'])
            ])
        
        category_table = Table(category_table_data)
        category_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(category_table)
        story.append(Spacer(1, 24))
    
    # Recent transactions
    if recent_transactions:
        story.append(Paragraph("Recent Transactions (Last 30 Days)", styles['Heading2']))
        trans_data = [['Date', 'Type', 'Category', 'Description', 'Amount']]
        for trans in recent_transactions[:20]:  # Last 20 transactions
            amount_str = f"+${trans['amount']:.2f}" if trans['type'] == 'income' else f"-${trans['amount']:.2f}"
            trans_data.append([
                trans['date'],
                trans['type'].title(),
                trans['category'],
                trans['description'][:30] + '...' if trans['description'] and len(trans['description']) > 30 else (trans['description'] or ''),
                amount_str
            ])
        
        trans_table = Table(trans_data)
        trans_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(trans_table)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"financial_report_{timestamp}.pdf"
    
    return send_file(BytesIO(buffer.read()), as_attachment=True, 
                     download_name=filename, mimetype='application/pdf')

@app.route('/backup/create')
def create_backup():
    try:
        backup_file = database.backup_database()
        flash(f'Database backed up successfully as {backup_file}', 'success')
        return send_file(backup_file, as_attachment=True, download_name=backup_file)
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('export_page'))

@app.route('/backup/restore', methods=['POST'])
def restore_backup():
    if 'backup_file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('export_page'))
    
    file = request.files['backup_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('export_page'))
    
    if file and file.filename and file.filename.endswith('.db'):
        try:
            # Save uploaded file temporarily
            temp_path = f"temp_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            file.save(temp_path)
            
            # Restore database
            if database.restore_database(temp_path):
                flash('Database restored successfully!', 'success')
                # Clean up temp file
                os.remove(temp_path)
            else:
                flash('Error restoring database', 'error')
                
        except Exception as e:
            flash(f'Error restoring backup: {str(e)}', 'error')
    else:
        flash('Please upload a valid .db file', 'error')
    
    return redirect(url_for('export_page'))
#@app.errorhandler(404)
#def page_not_found(e):
#    """Custom 404 error page."""
#    return render_template('404.html'), 404
#@app.errorhandler(500)
#def internal_server_error(e):
#    """Custom 500 error page."""
#    app.logger.error(f"Internal Server Error: {str(e)}", exc_info=True)
#    return render_template('500.html'), 500
    
@app.route('/settings')
def settings():
    """Settings page for account management and customization."""
    try:
        current_balance = database.get_current_balance()
        calculated_balance = database.calculate_balance_from_transactions()
        custom_categories = database.get_custom_categories()
        
        return render_template('settings.html',
                             current_balance=current_balance,
                             calculated_balance=calculated_balance,
                             custom_categories=custom_categories)
    except Exception as e:
        app.logger.error(f"Error loading settings: {e}", exc_info=True)
        flash('Error loading settings. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/add_custom_category', methods=['POST'])
def add_custom_category():
    """Add new custom category with comprehensive validation."""
    try:
        name = request.form.get('name', '').strip()
        category_type = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        
        # Input validation
        if not name or not category_type:
            flash('Category name and type are required.', 'error')
            return redirect(url_for('settings'))
            
        if len(name) > 50:
            flash('Category name must be 50 characters or less.', 'error')
            return redirect(url_for('settings'))
        
        success = database.add_custom_category(name, category_type, description)
        
        if success:
            flash(f'Custom category "{name}" added successfully!', 'success')
        else:
            flash(f'Category "{name}" already exists or invalid type.', 'error')
            
    except Exception as e:
        app.logger.error(f"Error adding custom category: {e}", exc_info=True)
        flash('Error adding category. Please try again.', 'error')
    
    return redirect(url_for('settings'))

@app.route('/update_balance', methods=['POST'])
def update_balance():
    """Update account balance with validation and logging."""
    try:
        new_balance = float(request.form.get('balance', 0))
        
        # Validation
        if new_balance < -999999.99 or new_balance > 999999.99:
            flash('Balance must be between -$999,999.99 and $999,999.99', 'error')
            return redirect(url_for('settings'))
        
        success = database.update_account_balance(1, new_balance)
        
        if success:
            flash(f'Account balance updated to ${new_balance:.2f}', 'success')
        else:
            flash('Error updating balance. Please try again.', 'error')
            
    except ValueError:
        flash('Please enter a valid number for balance.', 'error')
    except Exception as e:
        app.logger.error(f"Error updating balance: {e}", exc_info=True)
        flash('Error updating balance. Please try again.', 'error')
    
    return redirect(url_for('settings'))

@app.route('/clear_all_data', methods=['POST'])
def clear_all_data():
    """Clear all application data with safety confirmation."""
    try:
        confirmation = request.form.get('confirmation', '').strip()
        
        # Create automatic backup
        backup_path = database.backup_before_clear()
        if backup_path:
            flash(f'Automatic backup created: {backup_path}', 'info')
        
        # Perform data clearing
        result = database.clear_all_data(confirmation)
        
        if result['success']:
            flash(f"All data cleared successfully. {result['message']}", 'warning')
            app.logger.warning(f"Data clearing completed: {result}")
        else:
            flash(f"Error clearing data: {result['error']}", 'error')
            
    except Exception as e:
        app.logger.error(f"Error during data clearing: {e}", exc_info=True)
        flash('Unexpected error during data clearing. Please try again.', 'error')
    
    return redirect(url_for('settings'))
@app.route('/import_csv', methods=['POST'])
def import_csv():
    """
    Handle CSV file upload and import with comprehensive validation.
    Supports multiple file formats and provides detailed feedback.
    """
    import os
    import tempfile
    from werkzeug.utils import secure_filename
    
    try:
        # Validate file upload
        if 'csv_file' not in request.files:
            flash('No file selected for upload.', 'error')
            return redirect(url_for('settings'))
        
        file = request.files['csv_file']
        
        if file.filename == '':
            flash('No file selected for upload.', 'error')
            return redirect(url_for('settings'))
        
        # Validate file extension
        if not file.filename or not file.filename.lower().endswith('.csv'):
            flash('Please upload a CSV file only.', 'error')
            return redirect(url_for('settings'))
        
        # Validate file size (limit to 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            flash('File size too large. Please limit to 5MB.', 'error')
            return redirect(url_for('settings'))
        
        if file_size == 0:
            flash('Uploaded file is empty.', 'error')
            return redirect(url_for('settings'))
        
        # Get import options
        update_balance = request.form.get('update_balance') == 'on'
        import_mode = request.form.get('import_mode', 'append')  # Default to append mode
        # Save file temporarily for processing
        filename = secure_filename(file.filename)
        
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as tmp_file:
            try:
                file.save(tmp_file.name)
                
                # Process the CSV import
                result = database.import_transactions_from_csv(tmp_file.name, update_balance, import_mode)
                
                if result['success']:
                    # Automatically fix balance issues after successful import
                    try:
                        balance_fix_result = auto_fix_balances_after_import()
                        
                        if balance_fix_result['success']:
                            mode_text = "replaced all existing data with" if result.get('import_mode') == 'replace' else "imported"
                            success_msg = f"Import completed! {mode_text} {result['imported_count']} transactions."
                            if balance_fix_result.get('balance_updated'):
                                success_msg += f" Account balance automatically reconciled to ${balance_fix_result['new_balance']:.2f}."
                            
                            if result['error_count'] > 0:
                                success_msg += f" {result['error_count']} rows had errors."
                                flash(success_msg, 'warning')
                            else:
                                flash(success_msg, 'success')
                        else:
                            # Import successful but balance fix failed
                            flash(f"Import completed with {result['imported_count']} transactions, but balance reconciliation failed: {balance_fix_result.get('error', 'Unknown error')}", 'warning')
                            
                    except Exception as e:
                        app.logger.error(f"Error during automatic balance reconciliation: {e}", exc_info=True)
                        flash(f"Import completed with {result['imported_count']} transactions, but automatic balance reconciliation failed. Please use the reconcile button in accounts.", 'warning')
                    
                    # Log detailed errors for review
                    if result.get('errors'):
                        app.logger.warning(f"CSV import errors for {filename}: {result['errors']}")
                    
                    app.logger.info(f"CSV import successful: {filename} - {result['imported_count']} transactions")
                    
                else:
                    flash(f"Import failed: {result['error']}", 'error')
                    app.logger.error(f"CSV import failed for {filename}: {result['error']}")
            
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    app.logger.warning(f"Failed to delete temporary file: {tmp_file.name}")
    
    except Exception as e:
        app.logger.error(f"Unexpected error during CSV import: {e}", exc_info=True)
        flash('An unexpected error occurred during import. Please try again.', 'error')
    
    return redirect(url_for('settings'))

@app.route('/download_csv_template')
def download_csv_template():
    """
    Provide a downloadable CSV template with proper formatting and examples.
    """
    from flask import Response
    import io
    
    try:
        # Create CSV template with headers and example data
        template_content = [
            "Date, Type, Description, Category, Amount, Balance, Note",
            "06-23-2025,priority post debit,Coffee Shop Purchase,Food,-4.50,1995.50,Morning coffee",
            "06-22-2025,ach credit,Salary Direct Deposit,Salary,2500.00,2000.00,Bi-weekly payroll",  
            "06-21-2025,pos debit,Grocery Store,Food,-75.30,1924.70,Weekly groceries",
            "06-20-2025,atm withdrawal,Cash Withdrawal,Cash,-40.00,1849.40,Weekend spending money"
        ]
        
        output = io.StringIO()
        output.write('\n'.join(template_content))
        output.seek(0)
        
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=money_manager_template.csv'
            }
        )
        
        app.logger.info("CSV template downloaded")
        return response
        
    except Exception as e:
        app.logger.error(f"Error generating CSV template: {e}", exc_info=True)
        flash('Error generating template. Please try again.', 'error')
        return redirect(url_for('settings'))
@app.route('/reconcile_data', methods=['POST'])
def reconcile_data():
    """Fix balance mismatch between stored and calculated values."""
    try:
        result = database.reconcile_balance()
        
        if result.get('success'):
            if result.get('was_reconciled'):
                difference = result.get('difference', 0)
                flash(f'Balance reconciled! Updated from ${result.get("previous_balance", 0):.2f} '
                      f'to ${result.get("new_balance", 0):.2f} '
                      f'(difference: ${difference:+.2f})', 'success')
            else:
                flash('No reconciliation needed - balances already match!', 'info')
        else:
            flash(f'Reconciliation failed: {result.get("error", "Unknown error")}', 'error')
            
    except Exception as e:
        app.logger.error(f"Error during reconciliation: {e}", exc_info=True)
        flash('Error during reconciliation. Please try again.', 'error')
    
    return redirect(url_for('settings'))
@app.route('/debug/transactions')
def debug_transactions():
    """Debug route to see all transactions in database"""
    try:
        conn = database.get_db_connection()
        
        # Get total count
        total_count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        
        # Get all transactions with raw data
        all_transactions = conn.execute('''
            SELECT id, date, type, category, description, amount, created_at 
            FROM transactions 
            ORDER BY date DESC, created_at DESC
        ''').fetchall()
        
        # Get date range
        date_range = conn.execute('''
            SELECT MIN(date) as min_date, MAX(date) as max_date 
            FROM transactions
        ''').fetchone()
        
        conn.close()
        
        from typing import Any, Dict
        debug_info: Dict[str, Any] = {
            'total_transactions': total_count,
            'date_range': dict(date_range) if date_range else None,
            'sample_transactions': [dict(t) for t in all_transactions[:20]]
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/charts')
def charts():
    """Display financial analytics charts with account filtering support."""
    try:
        account_id = request.args.get('account_id', type=int)
        
        # Get data for charts with optional account filtering
        category_data = database.get_category_spending(30, account_id)
        daily_data = database.get_daily_balance(30, account_id)
        monthly_data = database.get_monthly_balance_history(12)
        
        # Get accounts for filter dropdown
        accounts = database.get_accounts()
        
        # Get account-specific balance history if account is selected
        account_balance_history = []
        selected_account = None
        if account_id:
            account_balance_history = database.get_account_balance_history(account_id, 30)
            selected_account = next((acc for acc in accounts if acc['id'] == account_id), None)
        
        app.logger.info(f"Charts: Found {len(category_data)} categories, {len(daily_data)} daily records for account {account_id}")
        
        return render_template('charts.html', 
                             category_data=category_data or [],
                             daily_data=daily_data or [],
                             monthly_data=monthly_data or [],
                             account_balance_history=account_balance_history or [],
                             accounts=accounts,
                             selected_account=selected_account)
    except Exception as e:
        app.logger.error(f"Error loading charts: {str(e)}", exc_info=True)
        flash('Error loading chart data. Please try again.', 'error')
        return render_template('charts.html', 
                             category_data=[],
                             daily_data=[],
                             monthly_data=[],
                             account_balance_history=[],
                             accounts=[],
                             selected_account=None)
@app.route('/accounts')
def accounts():
    """Account management page."""
    try:
        accounts = database.get_account_summary()
        account_types = ['checking', 'savings', 'credit_card', 'investment', 'cash', 'other']
        return render_template('accounts.html', accounts=accounts, account_types=account_types)
    except Exception as e:
        app.logger.error(f"Error loading accounts: {e}", exc_info=True)
        flash('Error loading accounts. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/add_account', methods=['POST'])
def add_account():
    """Add new account."""
    try:
        name = request.form.get('name', '').strip()
        account_type = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()
        initial_balance = float(request.form.get('initial_balance', 0))
        
        if not name or not account_type:
            flash('Account name and type are required.', 'error')
            return redirect(url_for('accounts'))
        
        success = database.add_account(name, account_type, description, initial_balance)
        
        if success:
            flash(f'Account "{name}" added successfully!', 'success')
        else:
            flash(f'Account "{name}" already exists.', 'error')
            
    except ValueError:
        flash('Please enter a valid initial balance.', 'error')
    except Exception as e:
        app.logger.error(f"Error adding account: {e}", exc_info=True)
        flash('Error adding account. Please try again.', 'error')
    
    return redirect(url_for('accounts'))

@app.route('/api/accounts')
def get_accounts_api():
    """API endpoint for getting accounts."""
    try:
        accounts = database.get_accounts()
        return jsonify(accounts)
    except Exception as e:
        app.logger.error(f"Error retrieving accounts: {e}", exc_info=True)
        return jsonify([]), 500
@app.route('/reconcile_account/<int:account_id>', methods=['POST'])
def reconcile_account(account_id: int):
    """Reconcile account balance with calculated balance."""
    try:
        calculated_balance = database.calculate_account_balance(account_id)
        success = database.update_account_balance(account_id, calculated_balance)
        
        if success:
            return jsonify({
                'success': True,
                'new_balance': calculated_balance
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update account balance'
            })
            
    except Exception as e:
        app.logger.error(f"Error reconciling account {account_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        })
@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    """Handle account transfers."""
    if request.method == 'POST':
        try:
            from_account_id = int(request.form['from_account'])
            to_account_id = int(request.form['to_account'])
            amount = float(request.form['amount'])
            description = request.form.get('description', '').strip()
            date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            
            if from_account_id == to_account_id:
                flash('Cannot transfer to the same account.', 'error')
                return redirect(url_for('transfer'))
            
            if amount <= 0:
                flash('Transfer amount must be positive.', 'error')
                return redirect(url_for('transfer'))
            
            success = database.create_transfer(from_account_id, to_account_id, amount, description, date)
            
            if success:
                flash(f'Transfer of ${amount:.2f} completed and account balances automatically updated!', 'success')
                return redirect(url_for('accounts'))
            else:
                flash('Transfer failed. Please try again.', 'error')
                
        except (ValueError, KeyError) as e:
            flash('Please enter valid values for all fields.', 'error')
        except Exception as e:
            app.logger.error(f"Error creating transfer: {e}", exc_info=True)
            flash('An error occurred during transfer. Please try again.', 'error')
    
    # GET request - show transfer form
    accounts = database.get_accounts()
    return render_template('transfer.html', accounts=accounts)

@app.route('/transactions')
def transactions():
    """Display transactions with comprehensive filtering support."""
    days = request.args.get('days', type=int)
    account_id = request.args.get('account_id', type=int)
    category = request.args.get('category', type=str)
    
    # Get transactions with all filters
    from typing import List, Dict, Any
    all_transactions_raw = database.get_transactions_with_category(days=days, account_id=account_id, category=category)
    all_transactions: List[Dict[str, Any]] = [dict(row) for row in all_transactions_raw]
    
    # Get filter options
    categories = database.get_categories()
    accounts = database.get_accounts()
    unique_categories = database.get_unique_categories()
    
    # Get selected filter objects for template
    selected_account = None
    if account_id:
        selected_account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    selected_category = category if category else None
    
    return render_template('transactions.html', 
                         transactions=all_transactions,
                         categories=categories,
                         accounts=accounts,
                         unique_categories=unique_categories,
                         selected_account=selected_account,
                         selected_category=selected_category)
@app.route('/edit_account/<int:account_id>', methods=['GET', 'POST'])
def edit_account(account_id: int):
    """Edit account details."""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            account_type = request.form.get('type', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name or not account_type:
                flash('Account name and type are required.', 'error')
                return redirect(url_for('accounts'))
            
            success = database.update_account(account_id, name, account_type, description)
            
            if success:
                flash(f'Account "{name}" updated successfully!', 'success')
            else:
                flash('Account not found or name already exists.', 'error')
                
        except Exception as e:
            app.logger.error(f"Error updating account: {e}", exc_info=True)
            flash('Error updating account. Please try again.', 'error')
        
        return redirect(url_for('accounts'))
    
    # GET request - return account data as JSON for modal population
    account = database.get_account_by_id(account_id)
    if account:
        return jsonify(account)
    else:
        return jsonify({'error': 'Account not found'}), 404
@app.route('/delete_account/<int:account_id>', methods=['POST'])
def delete_account(account_id: int):
    """Delete account with comprehensive safety checks and user feedback."""
    try:
        # Check if this is a force delete request
        force_delete = request.form.get('force_delete') == 'true'
        
        # First, get transaction count for this account
        conn = database.get_db_connection()
        transaction_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id = ?', 
            (account_id,)
        ).fetchone()[0]
        conn.close()
        
        # If account has transactions and no force flag, show warning and ask for confirmation
        if transaction_count > 0 and not force_delete:
            flash(
                f'Cannot delete account: {transaction_count} transactions found. '
                f'Transactions must be moved to another account first.', 
                'error'
            )
            return redirect(url_for('accounts'))
        
        # Proceed with deletion
        result = database.delete_account(account_id, force_delete)
        
        if result['success']:
            message = f'Account "{result["account_name"]}" deleted successfully!'
            if result.get('moved_transactions', 0) > 0:
                message += f' {result["moved_transactions"]} transactions moved to default account.'
            flash(message, 'success')
        else:
            flash(result['error'], 'error')
            
    except Exception as e:
        app.logger.error(f"Error deleting account {account_id}: {e}", exc_info=True)
        flash('Error deleting account. Please try again.', 'error')
    
    return redirect(url_for('accounts'))

@app.route('/ious')
def ious():
    """IOU management page."""
    try:
        # Get active IOUs (both pending and partially paid)
        pending_ious = database.get_ious('pending')  # This now includes partially_paid
        paid_ious = database.get_ious('paid')
        accounts = database.get_accounts()
        
        # Calculate summary stats - only count actual remaining balances
        total_owed_to_me = sum(iou['remaining_balance'] for iou in pending_ious if iou['creditor_name'].lower() == 'me')
        total_i_owe = sum(iou['remaining_balance'] for iou in pending_ious if iou['debtor_name'].lower() == 'me')
        
        return render_template('ious.html',
                             pending_ious=pending_ious,
                             paid_ious=paid_ious,
                             accounts=accounts,
                             total_owed_to_me=total_owed_to_me,
                             total_i_owe=total_i_owe)
    except Exception as e:
        app.logger.error(f"Error loading IOUs: {e}", exc_info=True)
        flash('Error loading IOUs. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/add_iou', methods=['POST'])
def add_iou():
    """Add new IOU."""
    try:
        creditor_name = request.form.get('creditor_name', '').strip()
        debtor_name = request.form.get('debtor_name', '').strip()
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', '').strip()
        due_date = request.form.get('due_date') or None
        payment_identifier = request.form.get('payment_identifier', '').strip()
        
        if not creditor_name or not debtor_name or amount <= 0:
            flash('All fields are required and amount must be positive.', 'error')
            return redirect(url_for('ious'))
        
        success = database.add_iou(creditor_name, debtor_name, amount, description, due_date, payment_identifier)
        
        if success:
            flash(f'IOU added: {debtor_name} owes {creditor_name} ${amount:.2f}', 'success')
        else:
            flash('Error adding IOU. Please try again.', 'error')
            
    except ValueError:
        flash('Please enter a valid amount.', 'error')
    except Exception as e:
        app.logger.error(f"Error adding IOU: {e}", exc_info=True)
        flash('Error adding IOU. Please try again.', 'error')

    return redirect(url_for('ious'))

@app.route('/settle_iou/<int:iou_id>', methods=['POST'])
def settle_iou_payment(iou_id: int):
    """Make a payment towards an IOU (partial or full)."""
    try:
        payment_amount = float(request.form.get('payment_amount', 0))
        payment_method = request.form.get('payment_method', '').strip()
        payment_notes = request.form.get('payment_notes', '').strip()
        create_transaction = request.form.get('create_transaction') == 'on'
        account_id_str = request.form.get('account_id')
        account_id = int(account_id_str) if account_id_str else None
        
        if payment_amount <= 0:
            flash('Payment amount must be positive.', 'error')
            return redirect(url_for('ious'))
        
        # Verify payment amount doesn't exceed remaining balance
        remaining_balance = database.get_iou_remaining_balance(iou_id)
        if payment_amount > remaining_balance + 0.01:  # Allow small rounding differences
            flash(f'Payment amount (${payment_amount:.2f}) exceeds remaining balance (${remaining_balance:.2f}).', 'error')
            return redirect(url_for('ious'))
        
        # Add the payment
        success = database.add_iou_payment(iou_id, payment_amount, payment_method, payment_notes, account_id)
        
        if success:
            # Check if IOU is now fully paid
            new_remaining = database.get_iou_remaining_balance(iou_id)
            if new_remaining <= 0.01:
                flash(f'IOU fully paid with ${payment_amount:.2f} payment!', 'success')
            else:
                flash(f'Payment of ${payment_amount:.2f} recorded. Remaining balance: ${new_remaining:.2f}', 'success')
            
            # Create transaction if requested
            if create_transaction and account_id:
                # Get IOU details for transaction description
                ious = database.get_ious()
                iou = next((i for i in ious if i['id'] == iou_id), None)
                
                if iou:
                    # Determine transaction type
                    if iou['creditor_name'].lower() == 'me':
                        transaction_type = 'income'
                        description = f"IOU payment received: {payment_notes or iou['description']} from {iou['debtor_name']}"
                        category = 'Debt Collection'
                    elif iou['debtor_name'].lower() == 'me':
                        transaction_type = 'expense'
                        description = f"IOU payment made: {payment_notes or iou['description']} to {iou['creditor_name']}"
                        category = 'Debt Payment'
                    else:
                        transaction_type = 'income'
                        description = f"IOU payment: {iou['creditor_name']} received from {iou['debtor_name']}"
                        category = 'Debt Settlement'
                    
                    database.add_transaction(
                        payment_amount, category, transaction_type, description,
                        datetime.now().strftime('%Y-%m-%d'), account_id
                    )
                    flash('Transaction record created.', 'info')
        else:
            flash('Error processing payment. Please try again.', 'error')
            
    except ValueError:
        flash('Please enter a valid payment amount.', 'error')
    except Exception as e:
        app.logger.error(f"Error processing IOU payment: {e}", exc_info=True)
        flash('Error processing payment. Please try again.', 'error')
    
    return redirect(url_for('ious'))
@app.route('/iou_payments/<int:iou_id>')
def get_iou_payments(iou_id: int):
    """Get payment history for an IOU."""
    try:
        payments = database.get_iou_payments(iou_id)
        return jsonify({
            'success': True,
            'payments': payments
        })
    except Exception as e:
        app.logger.error(f"Error retrieving IOU payments: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@app.route('/debug/accounts')
def debug_accounts():
    """Debug route to inspect account data"""
    try:
        from typing import Any, Dict
        accounts = database.get_account_summary()
        debug_info: Dict[str, Any] = {
            'account_count': len(accounts),
            'accounts': []  # type: List[Dict[str, Any]]
        }
        
        for acc in accounts:
            debug_info['accounts'].append({
                'id': acc.get('id'),
                'name': acc.get('name'),
                'current_balance': acc.get('current_balance'),
                'current_balance_type': type(acc.get('current_balance')).__name__,
                'calculated_balance': acc.get('calculated_balance'),
                'calculated_balance_type': type(acc.get('calculated_balance')).__name__,
            })
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/fix/recalculate_balance', methods=['POST'])
def fix_recalculate_balance():
    """Recalculate account balance from all transactions"""
    try:
        # Calculate what the balance should be from all transactions
        calculated_balance = database.calculate_balance_from_transactions()
        
        # Update the account balance
        success = database.update_global_account_balance(calculated_balance, 'manual_recalculation')
        
        if success:
            app.logger.info(f"Account balance recalculated to ${calculated_balance:.2f}")
            return jsonify({
                'success': True,
                'new_balance': calculated_balance
            })
        else:
            return jsonify({'error': 'Failed to update balance'}), 500
            
    except Exception as e:
        app.logger.error(f"Error recalculating balance: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/debug/transactions_raw')
def debug_transactions_raw():
    """Debug route to see raw transaction data and account relationships"""
    try:
        conn = database.get_db_connection()
        
        # Check total transactions
        total_transactions = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        
        # Check transactions with account_id
        transactions_with_account = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id IS NOT NULL'
        ).fetchone()[0]
        
        # Check transactions without account_id  
        transactions_without_account = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id IS NULL'
        ).fetchone()[0]
        
        # Get sample transactions
        sample_transactions = conn.execute('''
            SELECT id, date, type, amount, category, description, account_id 
            FROM transactions 
            ORDER BY date DESC 
            LIMIT 10
        ''').fetchall()
        
        # Calculate total income/expense
        totals = conn.execute('''
            SELECT 
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as total_income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as total_expense
            FROM transactions
        ''').fetchone()
        
        # Check account record
        account_record = conn.execute(
            'SELECT * FROM accounts WHERE id = 1'
        ).fetchone()
        
        conn.close()
        
        return jsonify({
            'total_transactions': total_transactions,
            'transactions_with_account_id': transactions_with_account,
            'transactions_without_account_id': transactions_without_account,
            'total_income': float(totals[0]) if totals[0] else 0.0,
            'total_expense': float(totals[1]) if totals[1] else 0.0,
            'net_from_all_transactions': float(totals[0] or 0) - float(totals[1] or 0),
            'account_record': dict(account_record) if account_record else None,
            'sample_transactions': [dict(t) for t in sample_transactions]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/fix/link_transactions', methods=['POST'])
def fix_link_transactions():
    """One-time fix to link existing transactions to default account"""
    try:
        conn = database.get_db_connection()
        
        # Count transactions without account_id
        unlinked_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id IS NULL'
        ).fetchone()[0]
        
        if unlinked_count > 0:
            # Link all transactions without account_id to account 1
            conn.execute(
                'UPDATE transactions SET account_id = 1 WHERE account_id IS NULL'
            )
            conn.commit()
            
            app.logger.info(f"Linked {unlinked_count} transactions to default account")
            
            # Recalculate and update account balance
            calculated_balance = database.calculate_account_balance(1)
            database.update_account_balance(1, calculated_balance)
            
            conn.close()
            
            return jsonify({
                'success': True,
                'linked_transactions': unlinked_count,
                'new_balance': calculated_balance
            })
        else:
            conn.close()
            return jsonify({
                'success': True,
                'message': 'No transactions need linking',
                'linked_transactions': 0
            })
            
    except Exception as e:
        app.logger.error(f"Error linking transactions: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/fix/balance_auto')
def fix_balance_auto():
    """Auto-fix balance issues based on diagnosis"""
    conn = None
    try:
        conn = database.get_db_connection()
        
        # Run diagnosis
        total_transactions = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        
        if total_transactions == 0:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'No transactions found - nothing to fix'
            })
        
        # Check for account_id column
        account_columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
        has_account_id_column = any(col[1] == 'account_id' for col in account_columns)
        
        if not has_account_id_column:
            # Add account_id column and link transactions
            conn.execute('ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id)')
            conn.execute('UPDATE transactions SET account_id = 1')
            app.logger.info("Added account_id column and linked all transactions to account 1")
        
        # Check for unlinked transactions
        unlinked_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id IS NULL'
        ).fetchone()[0]
        
        if unlinked_count > 0:
            # Link unlinked transactions to account 1
            conn.execute('UPDATE transactions SET account_id = 1 WHERE account_id IS NULL')
            app.logger.info(f"Linked {unlinked_count} transactions to account 1")
        
        # Calculate correct balance
        totals = conn.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) as total_income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as total_expense
            FROM transactions 
            WHERE account_id = 1
        ''').fetchone()
        
        correct_balance = float(totals[0]) - float(totals[1])
        
        # Update account balance
        conn.execute('''
            UPDATE accounts 
            SET current_balance = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE id = 1
        ''', (correct_balance,))
        
        conn.commit()
        conn.close()
        
        app.logger.info(f"Fixed balance calculation - new balance: ${correct_balance:.2f}")
        
        return jsonify({
            'success': True,
            'message': f'Balance fixed successfully',
            'new_balance': correct_balance,
            'transactions_processed': total_transactions
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        app.logger.error(f"Auto-fix balance error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
@app.route('/delete_iou/<int:iou_id>', methods=['POST'])
def delete_iou_route(iou_id: int):
    """Delete IOU with comprehensive validation and user feedback."""
    try:
        confirmation_token = request.form.get('confirmation_token', '').strip()
        
        # Attempt deletion
        result = database.delete_iou(iou_id, confirmation_token)
        
        if result['success']:
            iou_details = result['iou_details']
            base_message = (f'IOU deleted: {iou_details["debtor"]} owed '
                          f'{iou_details["creditor"]} ${iou_details["amount"]:.2f}')
            
            if result.get('deleted_payments', 0) > 0:
                base_message += f' (including {result["deleted_payments"]} payment records)'
            
            flash(base_message, 'success')
            app.logger.info(f"IOU {iou_id} deleted successfully by user")
            
        elif result.get('requires_confirmation'):
            flash('Deletion of paid IOUs requires confirmation. Please confirm deletion.', 'warning')
            # Store confirmation token in session for the confirmation modal
            from flask import session
            session[f'delete_confirmation_{iou_id}'] = result['confirmation_token']
            
        else:
            flash(f'Error deleting IOU: {result["error"]}', 'error')
            app.logger.warning(f"Failed to delete IOU {iou_id}: {result['error']}")
            
    except Exception as e:
        app.logger.error(f"Unexpected error deleting IOU {iou_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again.', 'error')
    
    return redirect(url_for('ious'))
from typing import Dict, Any
def auto_fix_balances_after_import() -> Dict[str, Any]:
    """
    Automatically fix balance issues after CSV import.
    Similar to fix_balance_auto route but returns result instead of JSON response.
    """
    conn = None
    try:
        conn = database.get_db_connection()
        
        # Check if we have transactions
        total_transactions = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        
        if total_transactions == 0:
            conn.close()
            return {'success': False, 'error': 'No transactions found'}
        
        # Check for account_id column and fix if needed
        account_columns = conn.execute("PRAGMA table_info(transactions)").fetchall()
        has_account_id_column = any(col[1] == 'account_id' for col in account_columns)
        
        if not has_account_id_column:
            conn.execute('ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id)')
            conn.execute('UPDATE transactions SET account_id = 1')
            app.logger.info("Added account_id column and linked all transactions to account 1")
        
        # Check for unlinked transactions
        unlinked_count = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE account_id IS NULL'
        ).fetchone()[0]
        
        if unlinked_count > 0:
            conn.execute('UPDATE transactions SET account_id = 1 WHERE account_id IS NULL')
            app.logger.info(f"Linked {unlinked_count} transactions to account 1")
        
        # Calculate correct balance for account 1
        totals = conn.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) as total_income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as total_expense
            FROM transactions 
            WHERE account_id = 1
        ''').fetchone()
        
        correct_balance = float(totals[0]) - float(totals[1])
        
        # Get current balance to check if update is needed
        current_balance_result = conn.execute(
            'SELECT current_balance FROM accounts WHERE id = 1'
        ).fetchone()
        
        current_balance = float(current_balance_result[0]) if current_balance_result else 0.0
        balance_updated = abs(current_balance - correct_balance) > 0.01
        
        # Update account balance
        conn.execute('''
            UPDATE accounts 
            SET current_balance = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE id = 1
        ''', (correct_balance,))
        
        conn.commit()
        conn.close()
        
        app.logger.info(f"Automatic balance fix completed - balance: ${correct_balance:.2f}")
        
        return {
            'success': True,
            'new_balance': correct_balance,
            'balance_updated': balance_updated,
            'transactions_processed': total_transactions
        }
        
    except Exception as e:
        if conn is not None:
            conn.rollback()
            conn.close()
        app.logger.error(f"Automatic balance fix error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
@app.route('/edit_iou_payment/<int:payment_id>', methods=['GET', 'POST'])
def edit_iou_payment(payment_id: int):
    """Edit IOU payment details."""
    if request.method == 'POST':
        try:
            payment_method = request.form.get('payment_method', '').strip()
            notes = request.form.get('notes', '').strip()
            
            # Validate input length
            if payment_method and len(payment_method) > 50:
                flash('Payment method must be 50 characters or less.', 'error')
                return redirect(url_for('ious'))
            
            if notes and len(notes) > 200:
                flash('Notes must be 200 characters or less.', 'error')
                return redirect(url_for('ious'))
            
            success = database.update_iou_payment(payment_id, payment_method, notes)
            
            if success:
                flash('Payment details updated successfully!', 'success')
            else:
                flash('Error updating payment details. Please try again.', 'error')
                
        except Exception as e:
            app.logger.error(f"Error updating IOU payment {payment_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again.', 'error')
        
        return redirect(url_for('ious'))
    
    # GET request - return payment data for modal population
    try:
        # Get the specific payment details
        conn = database.get_db_connection()
        payment = conn.execute(
            'SELECT * FROM iou_payments WHERE id = ?', (payment_id,)
        ).fetchone()
        conn.close()
        
        if payment:
            return jsonify(dict(payment))
        else:
            return jsonify({'error': 'Payment not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error retrieving payment {payment_id}: {e}", exc_info=True)
        return jsonify({'error': 'Error retrieving payment details'}), 500
@app.route('/process_automatic_payment', methods=['POST'])
def process_automatic_payment_route():
    """Process automatic payment from external source (bank feed, etc.)."""
    try:
        data = request.get_json() if request.is_json else request.form
        
        payment_identifier = data.get('payment_identifier', '').strip()
        payment_amount = float(data.get('payment_amount', 0))
        transaction_description = data.get('description', '').strip()
        account_id_str = data.get('account_id')
        account_id = int(account_id_str) if account_id_str else None
        
        if not payment_identifier:
            return jsonify({"success": False, "error": "Payment identifier required"}), 400
        
        if payment_amount <= 0:
            return jsonify({"success": False, "error": "Valid payment amount required"}), 400
        
        # Process the automatic payment
        result = database.process_automatic_payment(
            payment_identifier, payment_amount, transaction_description, account_id
        )
        
        if result["success"]:
            app.logger.info(f"Automatic payment processed: {payment_identifier} - ${payment_amount:.2f}")
            
            # Create success response with details
            response_data = {
                "success": True,
                "message": f"Payment of ${result['payment_applied']:.2f} automatically applied",
                "iou_details": result["iou_details"],
                "remaining_balance": result["remaining_balance"],
                "fully_paid": result["fully_paid"]
            }
            
            if result.get("overpayment"):
                response_data["warning"] = result["warning"]
            
            return jsonify(response_data)
        else:
            return jsonify(result), 400
            
    except ValueError:
        return jsonify({"success": False, "error": "Invalid payment amount format"}), 400
    except Exception as e:
        app.logger.error(f"Error processing automatic payment: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Internal server error"}), 500
if __name__ == '__main__':
    app.run(debug=True)