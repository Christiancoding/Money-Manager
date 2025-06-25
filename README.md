# Money Manager 💰

A comprehensive personal finance management web application built with Flask. Track your income, expenses, and generate detailed financial reports with a clean, responsive interface.

## Features ✨

- **Transaction Management**: Add, edit, and delete financial transactions
- **Category Organization**: Organize transactions by customizable categories
- **Financial Reports**: Generate detailed PDF reports with charts and summaries
- **Data Export/Import**: Backup and restore your financial data
- **Responsive Design**: Mobile-friendly interface using Bootstrap
- **Local Asset Hosting**: Self-hosted Bootstrap and Font Awesome for offline use

## Prerequisites 📋

- Python 3.7 or higher
- pip (Python package installer)

## Installation 🚀

1. **Clone or download the project**
   ```bash
   cd Money_Manager
   ```

2. **Install required dependencies**
   ```bash
   pip install flask sqlite3 reportlab
   ```

3. **Download static assets** (Bootstrap & Font Awesome)
   ```bash
   python styles_download.py
   ```
   This will download all required CSS, JavaScript, and font files to the `static/` directory.

4. **Initialize the database**
   The application will automatically create the SQLite database on first run.

## Usage 🖥️

1. **Start the application**
   ```bash
   python app.py
   ```

2. **Access the web interface**
   Open your browser and navigate to `http://localhost:5000`

3. **Begin managing your finances**
   - Add transactions using the intuitive form interface
   - Categorize your income and expenses
   - Generate reports to track your financial progress

## Project Structure 📁

```
Money_Manager/
├── app.py                 # Main Flask application
├── styles_download.py     # Asset download utility
├── database.py           # Database management (if separate)
├── static/               # Static assets (CSS, JS, fonts)
│   ├── css/
│   │   ├── bootstrap.min.css
│   │   └── fontawesome.min.css
│   ├── js/
│   │   └── bootstrap.bundle.min.js
│   └── webfonts/         # Font Awesome fonts
├── templates/            # HTML templates
└── README.md            # This file
```

## Key Features Details 🔧

### Asset Management
The `styles_download.py` utility provides:
- Automatic download of Bootstrap 5.1.3 and Font Awesome 6.0.0
- Local hosting for offline functionality
- Path correction for Font Awesome fonts
- Comprehensive validation and error handling

### Financial Reports
- PDF generation with ReportLab
- Transaction summaries and categorization
- Timestamped report files
- Professional formatting with charts

### Data Security
- Local SQLite database storage
- Database backup and restore functionality
- No external data transmission (privacy-focused)

## Troubleshooting 🔧

### Static Assets Not Loading
If icons or styling don't appear correctly:
```bash
python styles_download.py
```
This will re-download all required assets.

### Database Issues
For database problems, use the backup/restore feature in the web interface or check the application logs.

### Permission Errors
Ensure the application has write permissions for:
- Database file creation
- Static file downloads
- Log file generation

## Development 👨‍💻

### Adding New Features
The application follows a modular Flask structure:
- Routes are defined in `app.py`
- Database operations are centralized
- Templates use Bootstrap components
- Static assets are locally hosted

### Customization
- Modify templates in the `templates/` directory
- Add custom CSS to complement Bootstrap
- Extend database schema as needed
- Add new transaction categories through the interface

## Dependencies 📦

- **Flask**: Web framework
- **SQLite3**: Database (built into Python)
- **ReportLab**: PDF generation
- **Bootstrap 5.1.3**: UI framework (downloaded locally)
- **Font Awesome 6.0.0**: Icons (downloaded locally)

## Contributing 🤝

1. Ensure all static assets are properly downloaded
2. Test database backup/restore functionality
3. Verify PDF report generation
4. Check responsive design on multiple devices

## License 📄

This project is designed for personal financial management. Modify and use according to your needs.

---

**Note**: This application stores all data locally and does not transmit financial information over the internet, ensuring your privacy and data security.
