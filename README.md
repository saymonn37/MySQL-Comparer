# 🔍 MySQL Comparer

## 📌 Overview

**MySQL Comparer** is a powerful GUI application that allows users to track and compare changes in MySQL databases. It captures the state of database tables at specific points in time, compares them to the current state, and highlights all differences. This tool is ideal for database administrators, developers, and QA specialists who need to monitor and validate database changes during development, testing, or migration processes.

## 🎯 Features

- ✅ **Complete Database Comparison** – Tracks additions, modifications, and deletions across all tables
- ✅ **High Performance** – Optimized for large databases with batched processing and connection pooling
- ✅ **Fast Mode** – Optional in-memory processing for faster comparisons on powerful systems
- ✅ **Table Selection** – Ability to focus comparison on specific tables of interest
- ✅ **Advanced Filtering** – Filter results by table, column, or value changes
- ✅ **Color-Coded Results** – Visual differentiation between added, modified, and deleted data
- ✅ **Pagination** – Efficiently navigate through large result sets
- ✅ **Export Options** – Save comparison results to CSV or copy to clipboard
- ✅ **Configurable Settings** – Customize database connections and display preferences

## 🖥️ Screenshot

![13-03-2025T17-43-52](https://github.com/user-attachments/assets/26fd2bdc-1088-4afd-a75d-8ce059d6a022)

## 🛠️ Requirements

Before running the application, ensure you have the following installed:

- Python 3.x
- `mysql-connector-python`
- `tkinter` (built-in with Python)
- `configparser`

Install missing dependencies using:

```bash
pip install mysql-connector-python
```

## 📥 Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/saymonn37/MySQL-Comparer.git
   cd MySQL-Comparer
   ```

2. Create a `config.ini` file in the root directory with the following structure:

   ```ini
   [mysql]
   host = your_mysql_host
   user = your_mysql_user
   password = your_mysql_password
   database = your_database_name
   pool_size = 5
   ```
   
   Note: The application will create a default config file on first run if none exists.

3. Run the script:

   ```bash
   python3 mysql_comparer.py
   ```

## 🚀 Usage

### Basic Operations

1. **Fetch State** – Click the "Fetch State" button to capture the initial database state
2. **Make Changes** – Modify your database through your normal tools and applications
3. **Compare States** – Click "Compare States" to analyze differences between the initial and current state
4. **Export Results** – Save the comparison results as CSV or copy to clipboard
5. **Clear All** – Reset the application to start a new comparison

### Advanced Features

- **Table Selection** – Use Options → Select Tables to focus on specific tables
- **Fast Mode** – Enable for faster processing (requires more RAM)
- **Filtering** – Use the filter box to search for specific changes
- **Pagination** – Navigate through results using the pagination controls
- **Stop Button** – Cancel long-running operations

## 🖥️ GUI Overview

The application consists of:

- **Control Panel** – Buttons for fetching state, comparing, exporting, and clearing data
- **Filter Bar** – Tools to search and filter comparison results
- **Results Table** – Displays detected changes with color-coding:
  - **Green** – Added records
  - **Orange** – Modified records
  - **Red** – Deleted records
- **Status Bar** – Shows operation progress and current status

## 📊 Example Output

When a database change is detected, the following information is displayed:

| Table  | ID | Column | Column Name | Old Value | New Value |
|--------|----|--------|-------------|-----------|-----------|
| users  | 1  | 2      | username    | JohnDoe   | John_Doe  |
| orders | 5  | 4      | status      | pending   | shipped   |

## ⚙️ Configuration Options

Access additional settings through the Options → Settings menu:

- **Database Settings** – Configure connection parameters
- **Display Settings** – Customize page size and result highlighting colors

## 🚨 Error Handling

- If MySQL credentials are incorrect, an error message will be displayed
- Connection issues are logged to an error.log file
- Long-running operations can be canceled using the STOP button

## 🏗️ Future Improvements

- Support for other database systems (PostgreSQL, SQLite, Oracle)
- Differential backups based on comparison results
- Schema change detection and comparison
- SQL script generation for synchronizing databases
- Dark mode for reduced eye strain

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection errors | Verify credentials in `config.ini` and ensure the database server is running |
| Application seems slow | Consider enabling Fast Mode for performance or select only necessary tables |
| High memory usage | Disable Fast Mode if experiencing memory issues on large databases |
| No changes detected | Ensure you've properly fetched the initial state and that changes were actually made |

## 📝 License

This project is open-source under the **MIT License**.

## 👤 Author

Developed by [Saymonn](https://github.com/saymonn37). Contributions and feedback are welcome!
