# Money Manager 💰

A comprehensive personal finance management web application built with Flask. Track your income, expenses, and generate detailed financial reports with a clean, responsive interface.

## Features ✨

- **Transaction Management**: Add, edit, and delete financial transactions with ease
- **Category Organization**: Organize transactions by customizable categories
- **Financial Reports**: Generate detailed PDF reports with charts and summaries
- **Data Export/Import**: Backup and restore your financial data securely
- **Responsive Design**: Mobile-friendly interface using Bootstrap 5.1.3
- **Local Asset Hosting**: Self-hosted Bootstrap and Font Awesome for offline use
- **Privacy-Focused**: All data stored locally with no external transmission

## Prerequisites 📋

- Python 3.7 or higher
- pip (Python package installer)

## Quick Start 🚀

1. **Clone or download the project**
   ```bash
   cd Money_Manager
   ```

2. **Install required dependencies**
   ```bash
   pip install flask reportlab
   ```
   *Note: SQLite3 is included with Python*

3. **Download static assets** (Bootstrap & Font Awesome)
   ```bash
   python styles_download.py
   ```
   This automatically downloads all required CSS, JavaScript, and font files to the `static/` directory.

4. **Start the application**
   ```bash
   python app.py
   ```

5. **Access the web interface**
   Open your browser and navigate to `http://localhost:5000`

## Project Structure 📁

```
Money_Manager/
├── app.py                    # Main Flask application
├── styles_download.py        # Asset download utility
├── static/                   # Static assets (CSS, JS, fonts)
│   ├── css/
│   │   ├── bootstrap.min.css
│   │   └── fontawesome.min.css
│   ├── js/
│   │   └── bootstrap.bundle.min.js
│   └── webfonts/            # Font Awesome fonts
├── templates/               # HTML templates
├── instance/               # Database and configuration files
└── README.md               # This file
```

## Key Features 🔧

### Asset Management
The `styles_download.py` utility provides:
- **Automatic Download**: Bootstrap 5.1.3 and Font Awesome 6.0.0
- **Local Hosting**: Complete offline functionality
- **Path Correction**: Automatic Font Awesome font path fixing
- **Integrity Validation**: File size and existence verification
- **Error Recovery**: Comprehensive error handling and cleanup

### Financial Management
- **Transaction Tracking**: Income and expense management
- **Category System**: Customizable transaction categories
- **Search & Filter**: Find transactions quickly
- **Date Range Analysis**: Track spending over time periods

### Reporting & Export
- **PDF Generation**: Professional reports using ReportLab
- **Data Backup**: Database backup and restore functionality
- **Export Options**: Multiple data export formats
- **Chart Integration**: Visual spending analysis

### Security & Privacy
- **Local Storage**: SQLite database stored locally
- **No External Transmission**: Complete data privacy
- **Backup System**: Secure data backup and restore
- **Permission Management**: Proper file access controls

## Dependencies 📦

### Core Dependencies
- **Flask**: Web framework for the application
- **ReportLab**: PDF generation for financial reports
- **SQLite3**: Database (built into Python)

### Frontend Assets (Downloaded Automatically)
- **Bootstrap 5.1.3**: Responsive UI framework
- **Font Awesome 6.0.0**: Icon library
- **jQuery**: JavaScript functionality (included with Bootstrap)

## Usage Guide 🖥️

### Adding Transactions
1. Navigate to the main dashboard
2. Click "Add Transaction"
3. Fill in transaction details (amount, category, description, date)
4. Submit to save

### Generating Reports
1. Go to "Reports" section
2. Select date range and categories
3. Choose report format (PDF/HTML)
4. Generate and download

### Managing Categories
1. Access "Categories" from the main menu
2. Add, edit, or delete categories as needed
3. Assign colors and descriptions for better organization

### Data Backup
1. Use the "Backup" feature in settings
2. Export your database to a safe location
3. Restore from backup when needed

## Troubleshooting 🔧

### Static Assets Not Loading
If icons or styling don't appear correctly:
```bash
python styles_download.py
```
This will re-download all required assets and fix any path issues.

### Database Issues
For database problems:
- Use the backup/restore feature in the web interface
- Check the application logs for error details
- Ensure proper write permissions for the database file

### Permission Errors
Ensure the application has write permissions for:
- Database file creation (`instance/` directory)
- Static file downloads (`static/` directory)
- Log file generation (current directory)

### Asset Download Problems
If `styles_download.py` fails:
```bash
python styles_download.py
```
Check the generated `asset_download.log` for detailed error information.

## Development 👨‍💻

### Project Architecture
The application follows a clean Flask structure:
- **Modular Design**: Separate concerns for database, routes, and templates
- **Bootstrap Integration**: Responsive design with local assets
- **SQLite Integration**: Lightweight, serverless database
- **Error Handling**: Comprehensive logging and error management

### Adding New Features
1. **Routes**: Define new routes in `app.py`
2. **Templates**: Create HTML templates in `templates/`
3. **Database**: Extend schema as needed
4. **Static Assets**: Add custom CSS/JS to complement Bootstrap

### Customization Options
- Modify templates for UI changes
- Add custom CSS for branding
- Extend transaction categories
- Customize report formats
- Add new export options

## Configuration ⚙️

### Environment Variables
- `FLASK_ENV`: Set to `development` for debug mode
- `FLASK_APP`: Set to `app.py` (default)

### Database Configuration
- Database automatically created on first run
- Location: `instance/money_manager.db`
- Backup location: User-configurable

## Contributing 🤝

### Development Guidelines
1. Ensure all static assets are properly downloaded
2. Test database backup/restore functionality
3. Verify PDF report generation works
4. Check responsive design on multiple devices
5. Validate form inputs and error handling

### Code Standards
- Follow PEP 8 Python style guidelines
- Use comprehensive error handling
- Include meaningful comments and documentation
- Test all functionality before submitting changes

## Support & Resources 📚

### Getting Help
- Check the troubleshooting section above
- Review application logs for error details
- Ensure all dependencies are properly installed

### Additional Resources
- Flask Documentation: [flask.palletsprojects.com](https://flask.palletsprojects.com/)
- Bootstrap Documentation: [getbootstrap.com](https://getbootstrap.com/)
- ReportLab Documentation: [reportlab.com](https://www.reportlab.com/)

## License 📄

This project is designed for personal financial management. Feel free to modify and use according to your needs while respecting the included dependencies' licenses.

## Technical Notes 🔧

### Performance Considerations
- SQLite is suitable for personal use (single user)
- Static assets are cached for improved performance
- PDF generation may be resource-intensive for large datasets

### Browser Compatibility
- Modern browsers with ES6 support
- Mobile-responsive design tested on major platforms
- Offline functionality when assets are locally hosted

---

**Security Notice**: This application stores all data locally and does not transmit financial information over the internet, ensuring your privacy and data security. Always keep regular backups of your financial data.